"""Tag management and type definition commands.

Types define the schema (expected data fields) for items. They are stored
in the 'types' table and referenced by items.type via foreign key.

Tags are hierarchical labels for search/categorization. Each tag can have a
parent_id to form a tree structure. Tags are defined in the 'tags' table and
referenced by tag_id (foreign key) in 'item_tags'.
"""

import json

from db import get_connection, ensure_schema


# -- Tag commands ------------------------------------------------------------


def _calc_level(conn, parent_id):
    """Calculate the level for a tag given its parent_id. Root = 0."""
    if parent_id is None:
        return 0
    row = conn.execute("SELECT level FROM tags WHERE id = ?", (parent_id,)).fetchone()
    if not row:
        return 0
    return row["level"] + 1


def _update_descendant_levels(conn, tag_id):
    """Recursively update levels for all descendants of a tag."""
    row = conn.execute("SELECT level FROM tags WHERE id = ?", (tag_id,)).fetchone()
    if not row:
        return
    parent_level = row["level"]
    children = conn.execute("SELECT id FROM tags WHERE parent_id = ?", (tag_id,)).fetchall()
    for child in children:
        conn.execute(
            "UPDATE tags SET level = ? WHERE id = ?",
            (parent_level + 1, child["id"]),
        )
        _update_descendant_levels(conn, child["id"])


def _build_tag_dict(row, count=None):
    """Build a tag dict from a database row."""
    d = {
        "id": row["id"],
        "name": row["name"],
        "display_name": row["display_name"],
        "parent_id": row["parent_id"],
        "level": row["level"],
    }
    if count is not None:
        d["count"] = count
    return d


def cmd_tag_create(data_json):
    """Create a new tag with optional parent_id for hierarchy."""
    data = json.loads(data_json)
    conn = get_connection()
    ensure_schema(conn)

    name = data["name"]

    # Check if tag already exists
    existing = conn.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()
    if existing:
        conn.close()
        print(json.dumps({"status": "error", "message": f"Tag already exists: {name}"}))
        return

    parent_id = data.get("parent_id")
    if parent_id is not None:
        parent_id = int(parent_id)
        parent = conn.execute("SELECT id FROM tags WHERE id = ?", (parent_id,)).fetchone()
        if not parent:
            conn.close()
            print(json.dumps({"status": "error", "message": f"Parent tag not found: {parent_id}"}))
            return

    level = _calc_level(conn, parent_id)
    cursor = conn.execute(
        "INSERT INTO tags (name, display_name, parent_id, level) VALUES (?, ?, ?, ?)",
        (name, data.get("display_name", ""), parent_id, level),
    )
    conn.commit()
    tag_id = cursor.lastrowid
    conn.close()
    print(json.dumps({"status": "ok", "id": tag_id, "name": name}))


def cmd_tag_update(tag_id, update_json):
    """Update a tag's name, display_name, or parent_id."""
    updates = json.loads(update_json)
    conn = get_connection()
    ensure_schema(conn)

    tag_id = int(tag_id)

    row = conn.execute("SELECT * FROM tags WHERE id = ?", (tag_id,)).fetchone()
    if not row:
        conn.close()
        print(json.dumps({"status": "error", "message": f"Tag not found: {tag_id}"}))
        return

    # Validate parent_id if being changed
    if "parent_id" in updates:
        new_parent_id = updates["parent_id"]
        if new_parent_id is not None:
            new_parent_id = int(new_parent_id)
            if new_parent_id == tag_id:
                conn.close()
                print(json.dumps({"status": "error", "message": "A tag cannot be its own parent"}))
                return
            parent = conn.execute("SELECT id FROM tags WHERE id = ?", (new_parent_id,)).fetchone()
            if not parent:
                conn.close()
                print(json.dumps({"status": "error", "message": f"Parent tag not found: {new_parent_id}"}))
                return
            # Check for circular reference
            current = new_parent_id
            visited = {tag_id}
            while current is not None:
                if current in visited:
                    conn.close()
                    print(json.dumps({"status": "error", "message": "Circular parent reference detected"}))
                    return
                visited.add(current)
                p_row = conn.execute("SELECT parent_id FROM tags WHERE id = ?", (current,)).fetchone()
                current = p_row["parent_id"] if p_row else None

    set_clauses = []
    params = []
    parent_changed = False

    for field in ("name", "display_name", "parent_id"):
        if field in updates:
            set_clauses.append(f"{field} = ?")
            val = updates[field]
            if field == "parent_id":
                if val is not None:
                    val = int(val)
                parent_changed = True
            params.append(val)

    if not set_clauses:
        conn.close()
        print(json.dumps({"status": "error", "message": "No valid fields to update"}))
        return

    # Recalculate level if parent changed
    if parent_changed:
        new_parent_id = updates["parent_id"]
        if new_parent_id is not None:
            new_parent_id = int(new_parent_id)
        new_level = _calc_level(conn, new_parent_id)
        set_clauses.append("level = ?")
        params.append(new_level)

    set_clauses.append("updated_at = datetime('now', 'localtime')")
    params.append(tag_id)
    conn.execute(f"UPDATE tags SET {', '.join(set_clauses)} WHERE id = ?", params)

    # If parent changed, update descendant levels
    if parent_changed:
        _update_descendant_levels(conn, tag_id)

    conn.commit()
    conn.close()
    print(json.dumps({"status": "ok", "id": tag_id}))


def cmd_tag_delete(tag_id):
    """Delete a tag. Children will have their parent_id set to NULL."""
    conn = get_connection()
    ensure_schema(conn)

    tag_id = int(tag_id)
    row = conn.execute("SELECT name FROM tags WHERE id = ?", (tag_id,)).fetchone()
    if not row:
        conn.close()
        print(json.dumps({"status": "error", "message": f"Tag not found: {tag_id}"}))
        return

    tag_name = row["name"]
    # item_tags rows are removed automatically via ON DELETE CASCADE
    # children's parent_id will be SET NULL via FK
    conn.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
    conn.commit()
    conn.close()
    print(json.dumps({"status": "ok", "id": tag_id, "name": tag_name}))


def cmd_tag_get(tag_id):
    """Get a tag with its children and usage count."""
    conn = get_connection()
    ensure_schema(conn)

    tag_id = int(tag_id)
    row = conn.execute("SELECT * FROM tags WHERE id = ?", (tag_id,)).fetchone()
    if not row:
        conn.close()
        print(json.dumps({"status": "error", "message": f"Tag not found: {tag_id}"}))
        return

    count_row = conn.execute(
        "SELECT COUNT(*) as count FROM item_tags WHERE tag_id = ?",
        (tag_id,),
    ).fetchone()

    d = _build_tag_dict(row, count=count_row["count"])

    # Include parent info
    if row["parent_id"]:
        parent = conn.execute("SELECT * FROM tags WHERE id = ?", (row["parent_id"],)).fetchone()
        if parent:
            d["parent"] = {"id": parent["id"], "name": parent["name"], "display_name": parent["display_name"]}

    # Include children
    children_rows = conn.execute(
        "SELECT * FROM tags WHERE parent_id = ? ORDER BY name", (tag_id,)
    ).fetchall()
    d["children"] = []
    for child in children_rows:
        c_count = conn.execute(
            "SELECT COUNT(*) as count FROM item_tags WHERE tag_id = ?",
            (child["id"],),
        ).fetchone()
        d["children"].append(_build_tag_dict(child, count=c_count["count"]))

    conn.close()
    print(json.dumps(d, ensure_ascii=False, indent=2))


def cmd_tags_list():
    """List all tags with hierarchy info and usage counts."""
    conn = get_connection()
    ensure_schema(conn)

    tag_rows = conn.execute("SELECT * FROM tags ORDER BY name").fetchall()

    # Get usage counts for all tags
    count_rows = conn.execute(
        "SELECT tag_id, COUNT(*) as count FROM item_tags GROUP BY tag_id"
    ).fetchall()
    count_map = {r["tag_id"]: r["count"] for r in count_rows}

    result = []
    for row in tag_rows:
        d = _build_tag_dict(row, count=count_map.get(row["id"], 0))
        result.append(d)

    conn.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_tags_list_level(level):
    """List tags at a specific hierarchy level (0 = root)."""
    level = int(level)
    conn = get_connection()
    ensure_schema(conn)

    tag_rows = conn.execute(
        "SELECT * FROM tags WHERE level = ? ORDER BY name", (level,)
    ).fetchall()

    count_rows = conn.execute(
        "SELECT tag_id, COUNT(*) as count FROM item_tags GROUP BY tag_id"
    ).fetchall()
    count_map = {r["tag_id"]: r["count"] for r in count_rows}

    result = []
    for row in tag_rows:
        d = _build_tag_dict(row, count=count_map.get(row["id"], 0))
        # Include children info
        children = conn.execute(
            "SELECT * FROM tags WHERE parent_id = ? ORDER BY name", (row["id"],)
        ).fetchall()
        d["children"] = [
            _build_tag_dict(c, count=count_map.get(c["id"], 0))
            for c in children
        ]
        result.append(d)

    conn.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_tags_tree():
    """List all tags as a tree structure."""
    conn = get_connection()
    ensure_schema(conn)

    tag_rows = conn.execute("SELECT * FROM tags ORDER BY name").fetchall()

    count_rows = conn.execute(
        "SELECT tag_id, COUNT(*) as count FROM item_tags GROUP BY tag_id"
    ).fetchall()
    count_map = {r["tag_id"]: r["count"] for r in count_rows}

    # Build tree from root nodes
    tags_by_id = {}
    for row in tag_rows:
        tags_by_id[row["id"]] = dict(row)

    def build_node(row):
        d = _build_tag_dict(row, count=count_map.get(row["id"], 0))
        children = [r for r in tag_rows if r["parent_id"] == row["id"]]
        d["children"] = [build_node(c) for c in sorted(children, key=lambda x: x["name"])]
        return d

    roots = [r for r in tag_rows if r["parent_id"] is None]
    result = [build_node(r) for r in sorted(roots, key=lambda x: x["name"])]

    conn.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


# -- Type commands -----------------------------------------------------------


def cmd_type_set(data_json):
    """Define or update a type (expected data fields for items of this type)."""
    data = json.loads(data_json)
    conn = get_connection()
    ensure_schema(conn)

    name = data["name"]
    fields_schema = data.get("fields_schema", [])
    if isinstance(fields_schema, list):
        fields_schema = json.dumps(fields_schema, ensure_ascii=False)

    conn.execute(
        """INSERT INTO types (name, display_name, description, fields_schema)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(name)
           DO UPDATE SET display_name = excluded.display_name,
                         description = excluded.description,
                         fields_schema = excluded.fields_schema,
                         updated_at = datetime('now', 'localtime')""",
        (
            name,
            data.get("display_name", ""),
            data.get("description", ""),
            fields_schema,
        ),
    )
    conn.commit()
    conn.close()
    print(json.dumps({"status": "ok", "name": name}))


def cmd_type_get(name):
    """Get a type's definition."""
    conn = get_connection()
    ensure_schema(conn)

    row = conn.execute("SELECT * FROM types WHERE name = ?", (name,)).fetchone()
    if not row:
        conn.close()
        print(json.dumps({"status": "error", "message": f"Type not found: {name}"}))
        return

    d = dict(row)
    try:
        d["fields_schema"] = json.loads(d["fields_schema"])
    except (json.JSONDecodeError, TypeError):
        d["fields_schema"] = []

    conn.close()
    print(json.dumps(d, ensure_ascii=False, indent=2))


def cmd_type_list():
    """List all defined types."""
    conn = get_connection()
    ensure_schema(conn)

    rows = conn.execute("SELECT * FROM types ORDER BY name").fetchall()
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


def cmd_type_delete(name):
    """Delete a type definition. Items with this type will have their type set to NULL."""
    conn = get_connection()
    ensure_schema(conn)
    conn.execute("DELETE FROM types WHERE name = ?", (name,))
    conn.commit()
    conn.close()
    print(json.dumps({"status": "ok", "name": name}))
