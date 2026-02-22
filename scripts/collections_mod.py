"""Collection commands and collection item commands."""

import json

from db import get_connection, ensure_schema, seed_default_collections, parse_tags, DB_PATH


def _validate_single_type_tag(conn, tags):
    """Validate that at most one 'type'-kind tag is present.

    Returns (type_tags, error_message). error_message is None if valid.
    """
    if not tags:
        return [], None
    placeholders = ",".join("?" for _ in tags)
    rows = conn.execute(
        f"SELECT tag FROM tag_schemas WHERE kind = 'type' AND tag IN ({placeholders})",
        tags,
    ).fetchall()
    type_tags = [r["tag"] for r in rows]
    if len(type_tags) > 1:
        return type_tags, f"Multiple type tags not allowed (got: {', '.join(type_tags)}). Only one type tag can be assigned per item."
    return type_tags, None


def _save_item_tags(conn, item_id, tags):
    """Save tags for a collection item."""
    for tag in tags:
        conn.execute(
            "INSERT OR IGNORE INTO collection_item_tags (item_id, tag) VALUES (?, ?)",
            (item_id, tag),
        )


def _enrich_items(conn, items):
    """Add tags and type to item dicts (batch)."""
    if not items:
        return items

    item_ids = [i["id"] for i in items]
    placeholders = ",".join("?" for _ in item_ids)

    # Parse data JSON
    for item in items:
        try:
            item["data"] = json.loads(item["data"]) if isinstance(item["data"], str) else item["data"]
        except (json.JSONDecodeError, TypeError):
            item["data"] = {}

    # Tags
    tag_rows = conn.execute(
        f"SELECT item_id, tag FROM collection_item_tags WHERE item_id IN ({placeholders}) ORDER BY item_id, tag",
        item_ids,
    ).fetchall()
    tags_map = {}
    for row in tag_rows:
        tags_map.setdefault(row["item_id"], []).append(row["tag"])

    # Lookup which tags are 'type'-kind
    all_tags = set()
    for tag_list in tags_map.values():
        all_tags.update(tag_list)
    type_tags = set()
    if all_tags:
        tp = ",".join("?" for _ in all_tags)
        type_rows = conn.execute(
            f"SELECT tag FROM tag_schemas WHERE kind = 'type' AND tag IN ({tp})",
            list(all_tags),
        ).fetchall()
        type_tags = {r["tag"] for r in type_rows}

    for item in items:
        item_tags = tags_map.get(item["id"], [])
        item["tags"] = [t for t in item_tags if t not in type_tags]
        item_type_tags = [t for t in item_tags if t in type_tags]
        item["type"] = item_type_tags[0] if item_type_tags else None

    return items


def _insert_item(conn, collection_id, data):
    """Insert a single collection item and return its ID.

    Returns item_id on success, or raises ValueError if tag validation fails.
    """
    tags = parse_tags(data.get("tags", ""))

    # Validate type-tag constraint before inserting
    _, err = _validate_single_type_tag(conn, tags)
    if err:
        raise ValueError(err)

    item_data = data.get("data", {})
    if isinstance(item_data, dict):
        item_data = json.dumps(item_data, ensure_ascii=False)

    cursor = conn.execute(
        """INSERT INTO collection_items (collection_id, title, content, data, parent_id, status)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            int(collection_id),
            data["title"],
            data.get("content", ""),
            item_data,
            data.get("parent_id"),
            data.get("status", "active"),
        ),
    )
    item_id = cursor.lastrowid

    _save_item_tags(conn, item_id, tags)

    return item_id


## -- Database initialization ------------------------------------------------


def cmd_init():
    """Initialize the database and seed default collections."""
    conn = get_connection()
    ensure_schema(conn)
    seed_default_collections(conn)
    conn.close()
    print(json.dumps({"status": "ok", "message": "Database initialized with default collections", "path": DB_PATH}))


## -- Collection commands ----------------------------------------------------


def cmd_col_create(data_json):
    """Create a new collection."""
    data = json.loads(data_json)
    conn = get_connection()
    ensure_schema(conn)

    fields_schema = data.get("fields_schema", [])
    if isinstance(fields_schema, list):
        fields_schema = json.dumps(fields_schema, ensure_ascii=False)

    cursor = conn.execute(
        """INSERT INTO collections (name, display_name, description, fields_schema)
           VALUES (?, ?, ?, ?)""",
        (
            data["name"],
            data.get("display_name", data["name"]),
            data.get("description", ""),
            fields_schema,
        ),
    )
    col_id = cursor.lastrowid
    conn.commit()
    conn.close()
    print(json.dumps({"status": "ok", "id": col_id}))


def cmd_col_list():
    """List all collections with item counts."""
    conn = get_connection()
    ensure_schema(conn)

    rows = conn.execute(
        """SELECT c.*, COUNT(ci.id) as item_count
           FROM collections c
           LEFT JOIN collection_items ci ON c.id = ci.collection_id
           GROUP BY c.id
           ORDER BY c.name"""
    ).fetchall()

    result = []
    for row in rows:
        d = dict(row)
        try:
            d["fields_schema"] = json.loads(d["fields_schema"])
        except (json.JSONDecodeError, TypeError):
            d["fields_schema"] = []
        result.append(d)

    conn.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_col_get(col_id):
    """Get a collection with its schema and item count."""
    conn = get_connection()
    ensure_schema(conn)

    row = conn.execute(
        """SELECT c.*, COUNT(ci.id) as item_count
           FROM collections c
           LEFT JOIN collection_items ci ON c.id = ci.collection_id
           WHERE c.id = ?
           GROUP BY c.id""",
        (int(col_id),),
    ).fetchone()

    if not row:
        conn.close()
        print(json.dumps({"status": "error", "message": "Collection not found"}))
        return

    d = dict(row)
    try:
        d["fields_schema"] = json.loads(d["fields_schema"])
    except (json.JSONDecodeError, TypeError):
        d["fields_schema"] = []

    conn.close()
    print(json.dumps(d, ensure_ascii=False, indent=2))


def cmd_col_update(col_id, update_json):
    """Update collection metadata."""
    updates = json.loads(update_json)
    conn = get_connection()
    ensure_schema(conn)

    set_clauses = []
    params = []
    for field in ("name", "display_name", "description"):
        if field in updates:
            set_clauses.append(f"{field} = ?")
            params.append(updates[field])
    if "fields_schema" in updates:
        fs = updates["fields_schema"]
        if isinstance(fs, list):
            fs = json.dumps(fs, ensure_ascii=False)
        set_clauses.append("fields_schema = ?")
        params.append(fs)

    if not set_clauses:
        print(json.dumps({"status": "error", "message": "No valid fields to update"}))
        return

    set_clauses.append("updated_at = datetime('now', 'localtime')")
    params.append(int(col_id))
    conn.execute(f"UPDATE collections SET {', '.join(set_clauses)} WHERE id = ?", params)
    conn.commit()
    conn.close()
    print(json.dumps({"status": "ok", "id": int(col_id)}))


def cmd_col_delete(col_id):
    """Delete a collection and all its items (cascades)."""
    conn = get_connection()
    ensure_schema(conn)
    conn.execute("DELETE FROM collections WHERE id = ?", (int(col_id),))
    conn.commit()
    conn.close()
    print(json.dumps({"status": "ok", "id": int(col_id)}))


## -- Collection item commands -----------------------------------------------


def cmd_item_add(collection_id, data_json):
    """Add a single item to a collection."""
    data = json.loads(data_json)
    conn = get_connection()
    ensure_schema(conn)

    try:
        item_id = _insert_item(conn, collection_id, data)
    except ValueError as e:
        conn.close()
        print(json.dumps({"status": "error", "message": str(e)}))
        return

    conn.commit()
    conn.close()
    print(json.dumps({"status": "ok", "id": item_id}))


def cmd_item_add_batch(collection_id, data_json):
    """Add multiple items to a collection."""
    items = json.loads(data_json)
    conn = get_connection()
    ensure_schema(conn)

    ids = []
    try:
        for data in items:
            ids.append(_insert_item(conn, collection_id, data))
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
        """SELECT ci.*, c.name as collection_name, c.display_name as collection_display_name
           FROM collection_items ci
           JOIN collections c ON ci.collection_id = c.id
           WHERE ci.id = ?""",
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
        "SELECT * FROM collection_items WHERE parent_id = ? ORDER BY title",
        (int(item_id),),
    ).fetchall()
    children = [dict(r) for r in children_rows]
    if children:
        _enrich_items(conn, children)
    item["children"] = children

    conn.close()
    print(json.dumps(item, ensure_ascii=False, indent=2))


def cmd_item_update(item_id, update_json):
    """Update a collection item."""
    updates = json.loads(update_json)
    conn = get_connection()
    ensure_schema(conn)

    set_clauses = []
    params = []

    for field in ("title", "content", "parent_id", "status"):
        if field in updates:
            set_clauses.append(f"{field} = ?")
            params.append(updates[field])

    if "data" in updates:
        d = updates["data"]
        if isinstance(d, dict):
            # Merge with existing data
            row = conn.execute(
                "SELECT data FROM collection_items WHERE id = ?", (int(item_id),)
            ).fetchone()
            if row:
                try:
                    existing = json.loads(row["data"]) if isinstance(row["data"], str) else row["data"]
                except (json.JSONDecodeError, TypeError):
                    existing = {}
                existing.update(d)
                d = existing
            d = json.dumps(d, ensure_ascii=False)
        set_clauses.append("data = ?")
        params.append(d)

    has_field_updates = bool(set_clauses)
    has_tags = "tags" in updates

    if not has_field_updates and not has_tags:
        print(json.dumps({"status": "error", "message": "No valid fields to update"}))
        return

    if has_field_updates:
        set_clauses.append("updated_at = datetime('now', 'localtime')")
        params.append(int(item_id))
        conn.execute(
            f"UPDATE collection_items SET {', '.join(set_clauses)} WHERE id = ?",
            params,
        )

    if has_tags:
        tags = parse_tags(updates["tags"])
        _, err = _validate_single_type_tag(conn, tags)
        if err:
            conn.close()
            print(json.dumps({"status": "error", "message": err}))
            return
        conn.execute("DELETE FROM collection_item_tags WHERE item_id = ?", (int(item_id),))
        _save_item_tags(conn, int(item_id), tags)

    conn.commit()
    conn.close()
    print(json.dumps({"status": "ok", "id": int(item_id)}))


def cmd_item_delete(item_id):
    """Delete a collection item."""
    conn = get_connection()
    ensure_schema(conn)
    conn.execute("DELETE FROM collection_items WHERE id = ?", (int(item_id),))
    conn.commit()
    conn.close()
    print(json.dumps({"status": "ok", "id": int(item_id)}))


def cmd_item_list(collection_id, filter_json=None):
    """List items in a collection with optional filters."""
    filters = json.loads(filter_json) if filter_json else {}
    conn = get_connection()
    ensure_schema(conn)

    where_clauses = ["ci.collection_id = ?"]
    params = [int(collection_id)]

    if "status" in filters:
        where_clauses.append("ci.status = ?")
        params.append(filters["status"])
    if "parent_id" in filters:
        if filters["parent_id"] is None:
            where_clauses.append("ci.parent_id IS NULL")
        else:
            where_clauses.append("ci.parent_id = ?")
            params.append(int(filters["parent_id"]))
    if "tag" in filters:
        where_clauses.append(
            "EXISTS (SELECT 1 FROM collection_item_tags t WHERE t.item_id = ci.id AND t.tag = ?)"
        )
        params.append(filters["tag"])

    where = " AND ".join(where_clauses)
    limit = filters.get("limit", 100)

    rows = conn.execute(
        f"""SELECT ci.* FROM collection_items ci
            WHERE {where}
            ORDER BY ci.created_at DESC
            LIMIT ?""",
        params + [limit],
    ).fetchall()

    result = [dict(row) for row in rows]
    _enrich_items(conn, result)

    conn.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _search_items_like(conn, keyword, collection_id=None):
    """Search collection items using LIKE (fallback)."""
    pattern = f"%{keyword}%"
    if collection_id:
        return conn.execute(
            """SELECT ci.*, c.name as collection_name, c.display_name as collection_display_name
               FROM collection_items ci JOIN collections c ON ci.collection_id = c.id
               WHERE ci.collection_id = ? AND (ci.title LIKE ? OR ci.content LIKE ? OR ci.data LIKE ?)
               ORDER BY ci.created_at DESC LIMIT 50""",
            (int(collection_id), pattern, pattern, pattern),
        ).fetchall()
    return conn.execute(
        """SELECT ci.*, c.name as collection_name, c.display_name as collection_display_name
           FROM collection_items ci JOIN collections c ON ci.collection_id = c.id
           WHERE ci.title LIKE ? OR ci.content LIKE ? OR ci.data LIKE ?
           ORDER BY ci.created_at DESC LIMIT 50""",
        (pattern, pattern, pattern),
    ).fetchall()


def cmd_item_search(keyword, collection_id=None):
    """Search items across collections (or within one) using FTS5 with LIKE fallback."""
    conn = get_connection()
    ensure_schema(conn)

    rows = []
    try:
        if collection_id:
            rows = conn.execute(
                """SELECT ci.*, c.name as collection_name, c.display_name as collection_display_name
                   FROM collection_items_fts fts
                   JOIN collection_items ci ON ci.id = fts.rowid
                   JOIN collections c ON ci.collection_id = c.id
                   WHERE collection_items_fts MATCH ? AND ci.collection_id = ?
                   ORDER BY rank LIMIT 50""",
                (keyword, int(collection_id)),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT ci.*, c.name as collection_name, c.display_name as collection_display_name
                   FROM collection_items_fts fts
                   JOIN collection_items ci ON ci.id = fts.rowid
                   JOIN collections c ON ci.collection_id = c.id
                   WHERE collection_items_fts MATCH ?
                   ORDER BY rank LIMIT 50""",
                (keyword,),
            ).fetchall()
    except Exception:
        pass

    if not rows:
        rows = _search_items_like(conn, keyword, collection_id)

    result = [dict(row) for row in rows]
    _enrich_items(conn, result)

    conn.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))
