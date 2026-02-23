"""Item commands for the secretary skill."""

import json

from db import get_connection, ensure_schema, seed_defaults, get_type_descendants, DB_PATH


def _enrich_items(conn, items):
    """Parse data JSON for item dicts (batch)."""
    for item in items:
        try:
            item["data"] = json.loads(item["data"]) if isinstance(item["data"], str) else item["data"]
        except (json.JSONDecodeError, TypeError):
            item["data"] = {}
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


def _insert_item(conn, data):
    """Insert a single item and return its ID."""
    type_name = data.get("type")
    err = _validate_type(conn, type_name)
    if err:
        raise ValueError(err)

    item_data = data.get("data", {})
    if isinstance(item_data, dict):
        item_data = json.dumps(item_data, ensure_ascii=False)

    cursor = conn.execute(
        """INSERT INTO items (type, title, content, data, parent_id, status)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            type_name,
            data["title"],
            data.get("content", ""),
            item_data,
            data.get("parent_id"),
            data.get("status", "active"),
        ),
    )
    return cursor.lastrowid


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

    if "data" in updates:
        d = updates["data"]
        if isinstance(d, dict):
            # Merge with existing data
            row = conn.execute(
                "SELECT data FROM items WHERE id = ?", (int(item_id),)
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

    if not set_clauses:
        print(json.dumps({"status": "error", "message": "No valid fields to update"}))
        return

    set_clauses.append("updated_at = datetime('now', 'localtime')")
    params.append(int(item_id))
    conn.execute(
        f"UPDATE items SET {', '.join(set_clauses)} WHERE id = ?",
        params,
    )

    conn.commit()
    conn.close()
    print(json.dumps({"status": "ok", "id": int(item_id)}))


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
    """Search items using LIKE (fallback)."""
    pattern = f"%{keyword}%"
    if type_names:
        placeholders = ",".join("?" for _ in type_names)
        return conn.execute(
            f"""SELECT * FROM items
               WHERE type IN ({placeholders}) AND (title LIKE ? OR content LIKE ? OR data LIKE ?)
               ORDER BY created_at DESC LIMIT 50""",
            type_names + [pattern, pattern, pattern],
        ).fetchall()
    return conn.execute(
        """SELECT * FROM items
           WHERE title LIKE ? OR content LIKE ? OR data LIKE ?
           ORDER BY created_at DESC LIMIT 50""",
        (pattern, pattern, pattern),
    ).fetchall()


def cmd_item_search(keyword, type_name=None):
    """Search items (optionally within a type and its descendants) using FTS5 with LIKE fallback."""
    conn = get_connection()
    ensure_schema(conn)

    type_names = None
    if type_name:
        type_names = get_type_descendants(conn, type_name)

    rows = []
    try:
        if type_names:
            placeholders = ",".join("?" for _ in type_names)
            rows = conn.execute(
                f"""SELECT i.*
                   FROM items_fts fts
                   JOIN items i ON i.id = fts.rowid
                   WHERE items_fts MATCH ? AND i.type IN ({placeholders})
                   ORDER BY rank LIMIT 50""",
                [keyword] + type_names,
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT i.*
                   FROM items_fts fts
                   JOIN items i ON i.id = fts.rowid
                   WHERE items_fts MATCH ?
                   ORDER BY rank LIMIT 50""",
                (keyword,),
            ).fetchall()
    except Exception:
        pass

    if not rows:
        rows = _search_items_like(conn, keyword, type_names)

    result = [dict(row) for row in rows]
    _enrich_items(conn, result)

    conn.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))
