"""Item commands for the secretary skill."""

import json

from db import get_connection, ensure_schema, seed_defaults, get_type_descendants, get_ref_fields, DB_PATH


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
        ref_fields = type_ref_cache.get(item.get("type"), {})
        for fname, ids in item_rels.items():
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


def _save_relations(conn, item_id, relations):
    """Save item relations to the item_relations table."""
    for related_id, field_name in relations:
        conn.execute(
            "INSERT OR IGNORE INTO item_relations (item_id, related_item_id, field_name) VALUES (?, ?, ?)",
            (item_id, related_id, field_name),
        )


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
    _save_relations(conn, item_id, relations)

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
            _save_relations(conn, iid, relations)

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


def cmd_item_delete(item_id):
    """Delete an item."""
    conn = get_connection()
    ensure_schema(conn)
    conn.execute("DELETE FROM items WHERE id = ?", (int(item_id),))
    conn.commit()
    conn.close()
    print(json.dumps({"status": "ok", "id": int(item_id)}))


def cmd_item_list(filter_json=None):
    """List items with optional filters (type, status, parent_id, limit).

    Type filtering is polymorphic: filtering by a parent type also returns
    items of all descendant types.
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

    where = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
    limit = filters.get("limit", 100)

    rows = conn.execute(
        f"""SELECT i.* FROM items i
            {where}
            ORDER BY i.created_at DESC
            LIMIT ?""",
        params + [limit],
    ).fetchall()

    result = [dict(row) for row in rows]
    _enrich_items(conn, result)

    conn.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _search_items_like(conn, keyword, type_names=None):
    """Search items using LIKE (fallback), including matches through related items."""
    pattern = f"%{keyword}%"
    if type_names:
        placeholders = ",".join("?" for _ in type_names)
        # Direct matches
        direct = conn.execute(
            f"""SELECT * FROM items
               WHERE type IN ({placeholders}) AND (title LIKE ? OR content LIKE ? OR data LIKE ?)
               ORDER BY created_at DESC LIMIT 50""",
            type_names + [pattern, pattern, pattern],
        ).fetchall()
        direct_ids = {r["id"] for r in direct}

        # Matches via related items
        related = conn.execute(
            f"""SELECT DISTINCT i.* FROM item_relations ir
               JOIN items i ON i.id = ir.item_id
               JOIN items rel ON rel.id = ir.related_item_id
               WHERE i.type IN ({placeholders})
                 AND (rel.title LIKE ? OR rel.content LIKE ? OR rel.data LIKE ?)
               LIMIT 50""",
            type_names + [pattern, pattern, pattern],
        ).fetchall()

        result = list(direct)
        for r in related:
            if r["id"] not in direct_ids:
                result.append(r)
        return result[:50]

    # No type filter
    direct = conn.execute(
        """SELECT * FROM items
           WHERE title LIKE ? OR content LIKE ? OR data LIKE ?
           ORDER BY created_at DESC LIMIT 50""",
        (pattern, pattern, pattern),
    ).fetchall()
    direct_ids = {r["id"] for r in direct}

    related = conn.execute(
        """SELECT DISTINCT i.* FROM item_relations ir
           JOIN items i ON i.id = ir.item_id
           JOIN items rel ON rel.id = ir.related_item_id
           WHERE rel.title LIKE ? OR rel.content LIKE ? OR rel.data LIKE ?
           LIMIT 50""",
        (pattern, pattern, pattern),
    ).fetchall()

    result = list(direct)
    for r in related:
        if r["id"] not in direct_ids:
            result.append(r)
    return result[:50]


def cmd_item_search(keyword, type_name=None):
    """Search items (optionally within a type and its descendants) using FTS5 with LIKE fallback.

    Search includes related items: if an item is linked to another item that
    matches the keyword, the linking item is also returned.
    """
    conn = get_connection()
    ensure_schema(conn)

    type_names = None
    if type_name:
        type_names = get_type_descendants(conn, type_name)

    rows = []
    try:
        if type_names:
            placeholders = ",".join("?" for _ in type_names)
            # Direct FTS matches
            direct = conn.execute(
                f"""SELECT i.*
                   FROM items_fts fts
                   JOIN items i ON i.id = fts.rowid
                   WHERE items_fts MATCH ? AND i.type IN ({placeholders})
                   ORDER BY rank LIMIT 50""",
                [keyword] + type_names,
            ).fetchall()

            # Matches via related items (FTS on related, filter source by type)
            related = conn.execute(
                f"""SELECT DISTINCT i.*
                   FROM item_relations ir
                   JOIN items i ON i.id = ir.item_id
                   JOIN items_fts fts ON fts.rowid = ir.related_item_id
                   WHERE items_fts MATCH ? AND i.type IN ({placeholders})
                   LIMIT 50""",
                [keyword] + type_names,
            ).fetchall()

            direct_ids = {r["id"] for r in direct}
            rows = list(direct)
            for r in related:
                if r["id"] not in direct_ids:
                    rows.append(r)
            rows = rows[:50]
        else:
            # Direct FTS matches
            direct = conn.execute(
                """SELECT i.*
                   FROM items_fts fts
                   JOIN items i ON i.id = fts.rowid
                   WHERE items_fts MATCH ?
                   ORDER BY rank LIMIT 50""",
                (keyword,),
            ).fetchall()

            # Matches via related items
            related = conn.execute(
                """SELECT DISTINCT i.*
                   FROM item_relations ir
                   JOIN items i ON i.id = ir.item_id
                   JOIN items_fts fts ON fts.rowid = ir.related_item_id
                   WHERE items_fts MATCH ?
                   LIMIT 50""",
                (keyword,),
            ).fetchall()

            direct_ids = {r["id"] for r in direct}
            rows = list(direct)
            for r in related:
                if r["id"] not in direct_ids:
                    rows.append(r)
            rows = rows[:50]
    except Exception:
        pass

    if not rows:
        rows = _search_items_like(conn, keyword, type_names)

    result = [dict(row) for row in rows]
    _enrich_items(conn, result)

    conn.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))
