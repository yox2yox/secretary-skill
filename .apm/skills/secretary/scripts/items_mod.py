"""Item commands for the secretary skill."""

import json

from db import get_connection, ensure_schema, seed_defaults, get_type_descendants, get_ref_fields, DB_PATH


## -- Filter / sort helpers ---------------------------------------------------

# Allowed sort columns for item queries
_SORT_COLUMNS = {"created_at", "updated_at", "title", "status", "type"}
_DEFAULT_RELATION_NAME = "related"


def _build_date_clauses(filters, where_clauses, params):
    """Append WHERE clauses for created_at / updated_at range filters."""
    for col in ("created_at", "updated_at"):
        after_key = f"{col}_after"
        before_key = f"{col}_before"
        if after_key in filters:
            where_clauses.append(f"i.{col} >= ?")
            params.append(filters[after_key])
        if before_key in filters:
            where_clauses.append(f"i.{col} <= ?")
            params.append(filters[before_key])


def _build_data_filter_clauses(filters, where_clauses, params):
    """Append WHERE clauses for data JSON field filtering.

    ``data_filters`` is a dict whose keys are field names inside the ``data``
    JSON column.  Values can be:

    * A scalar (string / number) → exact match
    * A dict with comparison operators:
        - ``eq``       – equal
        - ``contains`` – substring match (LIKE %…%)
        - ``before``   – less than or equal (useful for dates)
        - ``after``    – greater than or equal (useful for dates)
    """
    data_filters = filters.get("data_filters")
    if not data_filters or not isinstance(data_filters, dict):
        return

    for field_name, condition in data_filters.items():
        json_path = f"$.{field_name}"
        if isinstance(condition, dict):
            if "eq" in condition:
                where_clauses.append(f"json_extract(i.data, ?) = ?")
                params.extend([json_path, condition["eq"]])
            if "contains" in condition:
                where_clauses.append(f"json_extract(i.data, ?) LIKE ?")
                params.extend([json_path, f"%{condition['contains']}%"])
            if "before" in condition:
                where_clauses.append(f"json_extract(i.data, ?) <= ?")
                params.extend([json_path, condition["before"]])
            if "after" in condition:
                where_clauses.append(f"json_extract(i.data, ?) >= ?")
                params.extend([json_path, condition["after"]])
        else:
            # Scalar → exact match
            where_clauses.append(f"json_extract(i.data, ?) = ?")
            params.extend([json_path, condition])


def _build_order_clause(filters, default_sort="created_at", default_order="desc"):
    """Return an ORDER BY clause string from *sort* and *sort_order* filters."""
    sort_col = filters.get("sort", default_sort)
    if sort_col not in _SORT_COLUMNS:
        sort_col = default_sort
    sort_order = filters.get("sort_order", default_order).upper()
    if sort_order not in ("ASC", "DESC"):
        sort_order = default_order.upper()
    return f"i.{sort_col} {sort_order}"


## -- Item enrichment --------------------------------------------------------


def _enrich_items(conn, items):
    """Parse data JSON and load relations from item_relations table."""
    if not items:
        return items

    for item in items:
        try:
            item["data"] = json.loads(item["data"]) if isinstance(item["data"], str) else item["data"]
        except (json.JSONDecodeError, TypeError):
            item["data"] = {}

    # Load relations for all items in one query
    item_ids = [item["id"] for item in items]
    placeholders = ",".join("?" for _ in item_ids)
    rel_rows = conn.execute(
        f"SELECT item_id, related_item_id, field_name FROM item_relations WHERE item_id IN ({placeholders})",
        item_ids,
    ).fetchall()

    # Group relations by item_id
    rel_map = {}  # item_id -> {field_name -> [related_item_ids]}
    for r in rel_rows:
        rel_map.setdefault(r["item_id"], {}).setdefault(r["field_name"], []).append(r["related_item_id"])

    # Build ref field info per type
    type_ref_cache = {}
    for item in items:
        itype = item.get("type")
        if itype and itype not in type_ref_cache:
            type_ref_cache[itype] = get_ref_fields(conn, itype)

    # Merge relations into item data
    for item in items:
        item_rels = rel_map.get(item["id"], {})
        item["relations"] = [
            {"related_item_id": related_id, "relation": field_name}
            for field_name, ids in item_rels.items()
            for related_id in ids
        ]
        ref_fields = type_ref_cache.get(item.get("type"), {})
        for fname, ids in item_rels.items():
            if fname not in ref_fields:
                continue
            finfo = ref_fields.get(fname, {})
            if finfo.get("multiple", False):
                item["data"][fname] = ids
            else:
                item["data"][fname] = ids[0] if ids else None

    return items


def _validate_type(conn, type_name):
    """Check that a type exists and is not abstract. Returns error message or None."""
    if type_name is None:
        return None
    row = conn.execute(
        "SELECT abstract FROM types WHERE name = ?", (type_name,)
    ).fetchone()
    if not row:
        return f"Type not found: '{type_name}'. Define it first with type_set."
    if row["abstract"]:
        return f"Type '{type_name}' is abstract and cannot be used directly. Use a concrete child type."
    return None


def _extract_refs(conn, type_name, item_data):
    """Extract ref fields from item data dict.

    Returns (cleaned_data, relations) where relations is a list of
    (related_item_id, field_name) tuples.
    """
    if not type_name or not isinstance(item_data, dict):
        return item_data, []

    ref_fields = get_ref_fields(conn, type_name)
    if not ref_fields:
        return item_data, []

    cleaned = dict(item_data)
    relations = []
    for fname, finfo in ref_fields.items():
        if fname not in cleaned:
            continue
        val = cleaned.pop(fname)
        if finfo["multiple"] and isinstance(val, list):
            for v in val:
                if v is not None:
                    relations.append((int(v), fname))
        elif not finfo["multiple"] and val is not None:
            relations.append((int(val), fname))
    return cleaned, relations


def _save_relations(conn, item_id, relations, type_name):
    """Save item relations to the item_relations table.

    Validates that each field_name is a ref field defined in the type's
    fields_schema. Raises ValueError if an undefined field_name is used.
    """
    if not relations:
        return
    ref_fields = get_ref_fields(conn, type_name) if type_name else {}
    for related_id, field_name in relations:
        if field_name not in ref_fields:
            raise ValueError(
                f"'{field_name}' is not a ref field defined in type '{type_name}'"
            )
        conn.execute(
            "INSERT OR IGNORE INTO item_relations (item_id, related_item_id, field_name) VALUES (?, ?, ?)",
            (item_id, related_id, field_name),
        )


def _normalize_direct_relations_payload(payload):
    """Normalize direct relation input into ``[(related_item_id, relation), ...]``."""
    if isinstance(payload, dict) and "relations" in payload:
        payload = payload["relations"]

    relations = []

    if isinstance(payload, int):
        return [(payload, _DEFAULT_RELATION_NAME)]

    if isinstance(payload, dict):
        relation_name = payload.get("relation", payload.get("field_name", _DEFAULT_RELATION_NAME))
        if "related_item_ids" in payload:
            values = payload["related_item_ids"]
        elif "related_item_id" in payload:
            values = [payload["related_item_id"]]
        else:
            raise ValueError("Relations JSON is missing related_item_id or related_item_ids")
        for related_id in values:
            if related_id is not None:
                relations.append((int(related_id), str(relation_name)))
        return relations

    if isinstance(payload, list):
        for entry in payload:
            if isinstance(entry, int):
                relations.append((entry, _DEFAULT_RELATION_NAME))
                continue
            if not isinstance(entry, dict):
                raise ValueError("Relation list entries must be item IDs or objects")
            relation_name = entry.get("relation", entry.get("field_name", _DEFAULT_RELATION_NAME))
            related_id = entry.get("related_item_id")
            if related_id is not None:
                relations.append((int(related_id), str(relation_name)))
        return relations

    raise ValueError("Relations JSON must be an object or an array")


def _ensure_item_exists(conn, item_id, label="Item"):
    row = conn.execute("SELECT 1 FROM items WHERE id = ?", (int(item_id),)).fetchone()
    if not row:
        raise ValueError(f"{label} not found: {item_id}")


def _insert_item(conn, data):
    """Insert a single item and return its ID."""
    type_name = data.get("type")
    err = _validate_type(conn, type_name)
    if err:
        raise ValueError(err)

    item_data = data.get("data", {})
    if isinstance(item_data, str):
        item_data = json.loads(item_data)

    # Extract ref fields before saving to JSON
    cleaned_data, relations = _extract_refs(conn, type_name, item_data)

    cursor = conn.execute(
        """INSERT INTO items (type, title, content, data, parent_id, status)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            type_name,
            data["title"],
            data.get("content", ""),
            json.dumps(cleaned_data, ensure_ascii=False),
            data.get("parent_id"),
            data.get("status", "active"),
        ),
    )
    item_id = cursor.lastrowid

    # Save relations
    _save_relations(conn, item_id, relations, type_name)

    return item_id


## -- Database initialization ------------------------------------------------


def cmd_init():
    """Initialize the database and seed default types."""
    conn = get_connection()
    ensure_schema(conn)
    seed_defaults(conn)
    conn.close()
    print(json.dumps({"status": "ok", "message": "Database initialized with default types", "path": DB_PATH}))


## -- Item commands ----------------------------------------------------------


def cmd_item_add(data_json):
    """Add a single item. JSON must include 'title', optionally 'type', 'content', 'data', etc."""
    data = json.loads(data_json)
    conn = get_connection()
    ensure_schema(conn)

    try:
        item_id = _insert_item(conn, data)
    except ValueError as e:
        conn.close()
        print(json.dumps({"status": "error", "message": str(e)}))
        return

    conn.commit()
    conn.close()
    print(json.dumps({"status": "ok", "id": item_id}))


def cmd_item_add_batch(data_json):
    """Add multiple items. JSON array, each element must include 'title'."""
    items = json.loads(data_json)
    conn = get_connection()
    ensure_schema(conn)

    ids = []
    try:
        for data in items:
            ids.append(_insert_item(conn, data))
    except ValueError as e:
        conn.close()
        print(json.dumps({"status": "error", "message": str(e)}))
        return

    conn.commit()
    conn.close()
    print(json.dumps({"status": "ok", "ids": ids, "count": len(ids)}))


def cmd_item_get(item_id):
    """Get a single item with all details."""
    conn = get_connection()
    ensure_schema(conn)

    row = conn.execute(
        "SELECT * FROM items WHERE id = ?",
        (int(item_id),),
    ).fetchone()

    if not row:
        conn.close()
        print(json.dumps({"status": "error", "message": "Item not found"}))
        return

    item = dict(row)
    _enrich_items(conn, [item])

    # Include children if any
    children_rows = conn.execute(
        "SELECT * FROM items WHERE parent_id = ? ORDER BY title",
        (int(item_id),),
    ).fetchall()
    children = [dict(r) for r in children_rows]
    if children:
        _enrich_items(conn, children)
    item["children"] = children

    conn.close()
    print(json.dumps(item, ensure_ascii=False, indent=2))


def cmd_item_update(item_id, update_json):
    """Update an item."""
    updates = json.loads(update_json)
    conn = get_connection()
    ensure_schema(conn)

    iid = int(item_id)

    set_clauses = []
    params = []

    # Validate type if being updated
    if "type" in updates:
        err = _validate_type(conn, updates["type"])
        if err:
            conn.close()
            print(json.dumps({"status": "error", "message": err}))
            return

    for field in ("title", "content", "parent_id", "status", "type"):
        if field in updates:
            set_clauses.append(f"{field} = ?")
            params.append(updates[field])

    # Determine the type (may be changing or existing)
    type_name = updates.get("type")
    if type_name is None:
        row = conn.execute("SELECT type FROM items WHERE id = ?", (iid,)).fetchone()
        type_name = row["type"] if row else None

    if "data" in updates:
        d = updates["data"]
        if isinstance(d, dict):
            # Extract ref fields from the update data
            ref_data, relations = _extract_refs(conn, type_name, d)

            # Merge non-ref data with existing data
            row = conn.execute(
                "SELECT data FROM items WHERE id = ?", (iid,)
            ).fetchone()
            if row:
                try:
                    existing = json.loads(row["data"]) if isinstance(row["data"], str) else row["data"]
                except (json.JSONDecodeError, TypeError):
                    existing = {}
                existing.update(ref_data)
                ref_data = existing
            d = json.dumps(ref_data, ensure_ascii=False)

            # Update relations: delete old relations for the updated fields and insert new ones
            updated_field_names = set()
            for _, fname in relations:
                updated_field_names.add(fname)
            # Also detect ref fields that were set to None/empty (explicit removal)
            ref_fields = get_ref_fields(conn, type_name) if type_name else {}
            for fname in ref_fields:
                if fname in updates["data"]:
                    updated_field_names.add(fname)

            for fname in updated_field_names:
                conn.execute(
                    "DELETE FROM item_relations WHERE item_id = ? AND field_name = ?",
                    (iid, fname),
                )
            _save_relations(conn, iid, relations, type_name)

        set_clauses.append("data = ?")
        params.append(d)

    if not set_clauses:
        print(json.dumps({"status": "error", "message": "No valid fields to update"}))
        return

    set_clauses.append("updated_at = datetime('now', 'localtime')")
    params.append(iid)
    conn.execute(
        f"UPDATE items SET {', '.join(set_clauses)} WHERE id = ?",
        params,
    )

    conn.commit()
    conn.close()
    print(json.dumps({"status": "ok", "id": iid}))


def cmd_item_relation_add(item_id, related_item_id, relation_name=None):
    """Add one direct item relation without requiring a ref field."""
    conn = get_connection()
    ensure_schema(conn)

    iid = int(item_id)
    rid = int(related_item_id)
    relation = relation_name or _DEFAULT_RELATION_NAME
    try:
        _ensure_item_exists(conn, iid)
        _ensure_item_exists(conn, rid, "Related item")
    except ValueError as e:
        conn.close()
        print(json.dumps({"status": "error", "message": str(e)}))
        return

    conn.execute(
        "INSERT OR IGNORE INTO item_relations (item_id, related_item_id, field_name) VALUES (?, ?, ?)",
        (iid, rid, relation),
    )
    conn.execute(
        "UPDATE items SET updated_at = datetime('now', 'localtime') WHERE id = ?",
        (iid,),
    )
    conn.commit()
    conn.close()
    print(json.dumps({"status": "ok", "item_id": iid, "related_item_id": rid, "relation": relation}))


def cmd_item_relation_set(item_id, relations_json):
    """Replace all direct relation rows for an item."""
    payload = json.loads(relations_json)
    conn = get_connection()
    ensure_schema(conn)

    iid = int(item_id)
    try:
        _ensure_item_exists(conn, iid)
        relations = _normalize_direct_relations_payload(payload)
        for related_id, _ in relations:
            _ensure_item_exists(conn, related_id, "Related item")
    except ValueError as e:
        conn.close()
        print(json.dumps({"status": "error", "message": str(e)}))
        return

    conn.execute("DELETE FROM item_relations WHERE item_id = ?", (iid,))
    for related_id, relation in relations:
        conn.execute(
            "INSERT OR IGNORE INTO item_relations (item_id, related_item_id, field_name) VALUES (?, ?, ?)",
            (iid, related_id, relation),
        )

    conn.execute(
        "UPDATE items SET updated_at = datetime('now', 'localtime') WHERE id = ?",
        (iid,),
    )
    conn.commit()
    conn.close()
    print(json.dumps({"status": "ok", "item_id": iid, "count": len(relations)}))


def cmd_item_relation_delete(item_id, related_item_id=None, relation_name=None):
    """Delete direct relation rows for an item."""
    conn = get_connection()
    ensure_schema(conn)

    iid = int(item_id)
    try:
        _ensure_item_exists(conn, iid)
    except ValueError as e:
        conn.close()
        print(json.dumps({"status": "error", "message": str(e)}))
        return

    params = [iid]
    clauses = ["item_id = ?"]
    if related_item_id is not None:
        clauses.append("related_item_id = ?")
        params.append(int(related_item_id))
    if relation_name is not None:
        clauses.append("field_name = ?")
        params.append(relation_name)

    cursor = conn.execute(
        f"DELETE FROM item_relations WHERE {' AND '.join(clauses)}",
        params,
    )
    conn.execute(
        "UPDATE items SET updated_at = datetime('now', 'localtime') WHERE id = ?",
        (iid,),
    )
    conn.commit()
    conn.close()
    print(json.dumps({"status": "ok", "item_id": iid, "deleted": cursor.rowcount}))


def cmd_item_relations(item_id):
    """List direct relation rows for an item, including incoming links."""
    conn = get_connection()
    ensure_schema(conn)

    iid = int(item_id)
    outgoing = conn.execute(
        """SELECT ir.item_id, ir.related_item_id, ir.field_name AS relation,
                  rel.type AS related_type, rel.title AS related_title
           FROM item_relations ir
           JOIN items rel ON rel.id = ir.related_item_id
           WHERE ir.item_id = ?
           ORDER BY ir.field_name, rel.title""",
        (iid,),
    ).fetchall()
    incoming = conn.execute(
        """SELECT ir.item_id, src.type AS source_type, src.title AS source_title,
                  ir.related_item_id, ir.field_name AS relation
           FROM item_relations ir
           JOIN items src ON src.id = ir.item_id
           WHERE ir.related_item_id = ?
           ORDER BY ir.field_name, src.title""",
        (iid,),
    ).fetchall()

    result = {
        "item_id": iid,
        "outgoing": [dict(row) for row in outgoing],
        "incoming": [dict(row) for row in incoming],
    }
    conn.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_item_delete(item_id):
    """Delete an item."""
    conn = get_connection()
    ensure_schema(conn)
    conn.execute("DELETE FROM items WHERE id = ?", (int(item_id),))
    conn.commit()
    conn.close()
    print(json.dumps({"status": "ok", "id": int(item_id)}))


def cmd_item_list(filter_json=None):
    """List items with optional filters and sorting.

    Supported filters:
        type         – polymorphic type filter (includes descendant types)
        status       – exact status match
        parent_id    – parent item ID (null for root items)
        limit        – max results (default 100)
        offset       – skip first N results (default 0, for pagination)
        sort         – sort column: created_at (default), updated_at, title, status, type
        sort_order   – asc or desc (default desc)
        created_at_after / created_at_before – filter by creation date range
        updated_at_after / updated_at_before – filter by update date range
        data_filters – dict of JSON data field filters (see _build_data_filter_clauses)
    """
    filters = json.loads(filter_json) if filter_json else {}
    conn = get_connection()
    ensure_schema(conn)

    where_clauses = []
    params = []

    if "type" in filters:
        type_names = get_type_descendants(conn, filters["type"])
        placeholders = ",".join("?" for _ in type_names)
        where_clauses.append(f"i.type IN ({placeholders})")
        params.extend(type_names)
    if "status" in filters:
        where_clauses.append("i.status = ?")
        params.append(filters["status"])
    if "parent_id" in filters:
        if filters["parent_id"] is None:
            where_clauses.append("i.parent_id IS NULL")
        else:
            where_clauses.append("i.parent_id = ?")
            params.append(int(filters["parent_id"]))

    _build_date_clauses(filters, where_clauses, params)
    _build_data_filter_clauses(filters, where_clauses, params)

    where = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
    order = _build_order_clause(filters)
    limit = filters.get("limit", 100)
    offset = filters.get("offset", 0)

    rows = conn.execute(
        f"""SELECT i.* FROM items i
            {where}
            ORDER BY {order}
            LIMIT ? OFFSET ?""",
        params + [limit, offset],
    ).fetchall()

    result = [dict(row) for row in rows]
    _enrich_items(conn, result)

    conn.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _parse_search_filters(type_or_json):
    """Parse the optional second argument of item_search.

    Accepts either a plain type name (backward compatible) or a JSON filter
    object.  Returns a filters dict.
    """
    if type_or_json is None:
        return {}
    # Try JSON first
    if type_or_json.startswith("{"):
        try:
            return json.loads(type_or_json)
        except (json.JSONDecodeError, ValueError):
            pass
    # Plain type name
    return {"type": type_or_json}


def _build_extra_where(filters):
    """Build additional WHERE clauses and params from search filters.

    Returns (clauses_list, params_list) for status, date ranges, and data
    filters.  Callers prepend alias ``i.`` already present in the SQL so the
    helpers work correctly.
    """
    clauses = []
    params = []
    if "status" in filters:
        clauses.append("i.status = ?")
        params.append(filters["status"])
    _build_date_clauses(filters, clauses, params)
    _build_data_filter_clauses(filters, clauses, params)
    return clauses, params


def _search_items_like(conn, keyword, type_names=None, filters=None):
    """Search items using LIKE (fallback), including matches through related items."""
    filters = filters or {}
    pattern = f"%{keyword}%"
    limit = filters.get("limit", 50)
    order = _build_order_clause(filters, default_sort="created_at", default_order="desc")
    extra_clauses, extra_params = _build_extra_where(filters)
    extra_sql = (" AND " + " AND ".join(extra_clauses)) if extra_clauses else ""

    if type_names:
        placeholders = ",".join("?" for _ in type_names)
        # Direct matches
        direct = conn.execute(
            f"""SELECT i.* FROM items i
               WHERE i.type IN ({placeholders}) AND (i.title LIKE ? OR i.content LIKE ? OR i.data LIKE ?)
               {extra_sql}
               ORDER BY {order} LIMIT ?""",
            type_names + [pattern, pattern, pattern] + extra_params + [limit],
        ).fetchall()
        direct_ids = {r["id"] for r in direct}

        # Matches via related items
        related = conn.execute(
            f"""SELECT DISTINCT i.* FROM item_relations ir
               JOIN items i ON i.id = ir.item_id
               JOIN items rel ON rel.id = ir.related_item_id
               WHERE i.type IN ({placeholders})
                 AND (rel.title LIKE ? OR rel.content LIKE ? OR rel.data LIKE ?)
               {extra_sql}
               LIMIT ?""",
            type_names + [pattern, pattern, pattern] + extra_params + [limit],
        ).fetchall()

        result = list(direct)
        for r in related:
            if r["id"] not in direct_ids:
                result.append(r)
        return result[:limit]

    # No type filter
    direct = conn.execute(
        f"""SELECT i.* FROM items i
           WHERE (i.title LIKE ? OR i.content LIKE ? OR i.data LIKE ?)
           {extra_sql}
           ORDER BY {order} LIMIT ?""",
        [pattern, pattern, pattern] + extra_params + [limit],
    ).fetchall()
    direct_ids = {r["id"] for r in direct}

    related = conn.execute(
        f"""SELECT DISTINCT i.* FROM item_relations ir
           JOIN items i ON i.id = ir.item_id
           JOIN items rel ON rel.id = ir.related_item_id
           WHERE (rel.title LIKE ? OR rel.content LIKE ? OR rel.data LIKE ?)
           {extra_sql}
           LIMIT ?""",
        [pattern, pattern, pattern] + extra_params + [limit],
    ).fetchall()

    result = list(direct)
    for r in related:
        if r["id"] not in direct_ids:
            result.append(r)
    return result[:limit]


def cmd_item_search(keyword, type_or_json=None):
    """Search items using FTS5 with LIKE fallback.

    The second argument can be either a plain type name (backward compatible)
    or a JSON object with advanced filters:

        type         – type name (polymorphic)
        status       – status filter
        limit        – max results (default 50)
        sort         – sort column: created_at, updated_at, title, status, type
        sort_order   – asc or desc (default: desc; FTS default is by rank)
        created_at_after / created_at_before – creation date range
        updated_at_after / updated_at_before – update date range
        data_filters – dict of JSON data field filters

    Search includes related items: if an item is linked to another item that
    matches the keyword, the linking item is also returned.
    """
    conn = get_connection()
    ensure_schema(conn)

    filters = _parse_search_filters(type_or_json)

    type_names = None
    if "type" in filters:
        type_names = get_type_descendants(conn, filters["type"])

    limit = filters.get("limit", 50)
    extra_clauses, extra_params = _build_extra_where(filters)
    extra_sql = (" AND " + " AND ".join(extra_clauses)) if extra_clauses else ""

    # Determine sort: if user specifies sort, use it; otherwise use FTS rank
    user_sort = "sort" in filters
    order = _build_order_clause(filters, default_sort="created_at", default_order="desc") if user_sort else None

    rows = []
    try:
        if type_names:
            placeholders = ",".join("?" for _ in type_names)
            fts_order = f"ORDER BY {order}" if order else "ORDER BY rank"
            # Direct FTS matches
            direct = conn.execute(
                f"""SELECT i.*
                   FROM items_fts fts
                   JOIN items i ON i.id = fts.rowid
                   WHERE items_fts MATCH ? AND i.type IN ({placeholders})
                   {extra_sql}
                   {fts_order} LIMIT ?""",
                [keyword] + type_names + extra_params + [limit],
            ).fetchall()

            # Matches via related items (FTS on related, filter source by type)
            related = conn.execute(
                f"""SELECT DISTINCT i.*
                   FROM item_relations ir
                   JOIN items i ON i.id = ir.item_id
                   JOIN items_fts fts ON fts.rowid = ir.related_item_id
                   WHERE items_fts MATCH ? AND i.type IN ({placeholders})
                   {extra_sql}
                   LIMIT ?""",
                [keyword] + type_names + extra_params + [limit],
            ).fetchall()

            direct_ids = {r["id"] for r in direct}
            rows = list(direct)
            for r in related:
                if r["id"] not in direct_ids:
                    rows.append(r)
            rows = rows[:limit]
        else:
            fts_order = f"ORDER BY {order}" if order else "ORDER BY rank"
            # Direct FTS matches
            direct = conn.execute(
                f"""SELECT i.*
                   FROM items_fts fts
                   JOIN items i ON i.id = fts.rowid
                   WHERE items_fts MATCH ?
                   {extra_sql}
                   {fts_order} LIMIT ?""",
                [keyword] + extra_params + [limit],
            ).fetchall()

            # Matches via related items
            related = conn.execute(
                f"""SELECT DISTINCT i.*
                   FROM item_relations ir
                   JOIN items i ON i.id = ir.item_id
                   JOIN items_fts fts ON fts.rowid = ir.related_item_id
                   WHERE items_fts MATCH ?
                   {extra_sql}
                   LIMIT ?""",
                [keyword] + extra_params + [limit],
            ).fetchall()

            direct_ids = {r["id"] for r in direct}
            rows = list(direct)
            for r in related:
                if r["id"] not in direct_ids:
                    rows.append(r)
            rows = rows[:limit]
    except Exception:
        pass

    if not rows:
        rows = _search_items_like(conn, keyword, type_names, filters)

    result = [dict(row) for row in rows]
    _enrich_items(conn, result)

    conn.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))
