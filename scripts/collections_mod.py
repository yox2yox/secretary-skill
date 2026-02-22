"""Collection commands, collection item commands, and item relation commands."""

import json

from db import get_connection, ensure_schema, parse_tags


def _save_item_tags(conn, item_id, tags):
    """Save tags for a collection item."""
    for tag in tags:
        conn.execute(
            "INSERT OR IGNORE INTO collection_item_tags (item_id, tag) VALUES (?, ?)",
            (item_id, tag),
        )


def _enrich_items(conn, items):
    """Add tags and relations to item dicts (batch)."""
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

    # Relations
    rel_rows = conn.execute(
        f"""SELECT r.*, ci.title as related_item_title, e.title as related_entry_title, p.name as related_person_name
            FROM collection_item_relations r
            LEFT JOIN collection_items ci ON r.related_item_id = ci.id
            LEFT JOIN entries e ON r.related_entry_id = e.id
            LEFT JOIN persons p ON r.related_person_id = p.id
            WHERE r.item_id IN ({placeholders})
            ORDER BY r.item_id""",
        item_ids,
    ).fetchall()
    rels_map = {}
    for row in rel_rows:
        rels_map.setdefault(row["item_id"], []).append(dict(row))

    for item in items:
        item["tags"] = tags_map.get(item["id"], [])
        item["relations"] = rels_map.get(item["id"], [])

    return items


def _insert_item(conn, collection_id, data):
    """Insert a single collection item and return its ID."""
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

    tags = parse_tags(data.get("tags", ""))
    _save_item_tags(conn, item_id, tags)

    return item_id


## ── Collection commands ──────────────────────────────────────────────


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


## ── Collection item commands ─────────────────────────────────────────


def cmd_item_add(collection_id, data_json):
    """Add a single item to a collection."""
    data = json.loads(data_json)
    conn = get_connection()
    ensure_schema(conn)

    item_id = _insert_item(conn, collection_id, data)

    conn.commit()
    conn.close()
    print(json.dumps({"status": "ok", "id": item_id}))


def cmd_item_add_batch(collection_id, data_json):
    """Add multiple items to a collection."""
    items = json.loads(data_json)
    conn = get_connection()
    ensure_schema(conn)

    ids = []
    for data in items:
        ids.append(_insert_item(conn, collection_id, data))

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
        conn.execute("DELETE FROM collection_item_tags WHERE item_id = ?", (int(item_id),))
        tags = parse_tags(updates["tags"])
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
            ORDER BY ci.title
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
               ORDER BY ci.title LIMIT 50""",
            (int(collection_id), pattern, pattern, pattern),
        ).fetchall()
    return conn.execute(
        """SELECT ci.*, c.name as collection_name, c.display_name as collection_display_name
           FROM collection_items ci JOIN collections c ON ci.collection_id = c.id
           WHERE ci.title LIKE ? OR ci.content LIKE ? OR ci.data LIKE ?
           ORDER BY ci.title LIMIT 50""",
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


## ── Collection item relation commands ────────────────────────────────


def cmd_item_relate(data_json):
    """Create a relation from a collection item to another item, entry, or person."""
    data = json.loads(data_json)
    conn = get_connection()
    ensure_schema(conn)

    cursor = conn.execute(
        """INSERT INTO collection_item_relations
           (item_id, related_item_id, related_entry_id, related_person_id, relation_type)
           VALUES (?, ?, ?, ?, ?)""",
        (
            int(data["item_id"]),
            data.get("related_item_id"),
            data.get("related_entry_id"),
            data.get("related_person_id"),
            data["relation_type"],
        ),
    )
    rel_id = cursor.lastrowid
    conn.commit()
    conn.close()
    print(json.dumps({"status": "ok", "id": rel_id}))


def cmd_item_unrelate(relation_id):
    """Remove a relation."""
    conn = get_connection()
    ensure_schema(conn)
    conn.execute("DELETE FROM collection_item_relations WHERE id = ?", (int(relation_id),))
    conn.commit()
    conn.close()
    print(json.dumps({"status": "ok", "id": int(relation_id)}))
