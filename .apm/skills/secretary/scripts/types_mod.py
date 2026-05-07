"""Type definition commands with inheritance and abstract type support.

Types define the schema (expected data fields) for items. They support
single inheritance via parent_type and can be marked abstract to prevent
direct use. Querying by a parent type returns items of all descendant types
(polymorphic filtering).
"""

import json

from db import get_connection, ensure_schema, get_resolved_fields


def _check_circular_parent(conn, type_name, new_parent):
    """Check for circular parent reference. Returns error message or None."""
    current = new_parent
    visited = {type_name}
    while current is not None:
        if current in visited:
            return "Circular parent_type reference detected"
        visited.add(current)
        row = conn.execute(
            "SELECT parent_type FROM types WHERE name = ?", (current,)
        ).fetchone()
        current = row["parent_type"] if row else None
    return None


def _build_type_dict(row, conn=None):
    """Build a type dict from a database row."""
    d = {
        "name": row["name"],
        "display_name": row["display_name"],
        "description": row["description"],
        "parent_type": row["parent_type"],
        "abstract": bool(row["abstract"]),
    }
    try:
        d["fields_schema"] = json.loads(row["fields_schema"])
    except (json.JSONDecodeError, TypeError):
        d["fields_schema"] = []
    return d


def cmd_type_set(data_json):
    """Define or update a type with optional parent_type and abstract flag."""
    data = json.loads(data_json)
    conn = get_connection()
    ensure_schema(conn)

    name = data["name"]
    parent_type = data.get("parent_type")
    abstract = 1 if data.get("abstract") else 0
    fields_schema = data.get("fields_schema", [])
    if isinstance(fields_schema, list):
        fields_schema = json.dumps(fields_schema, ensure_ascii=False)

    # Validate parent_type exists
    if parent_type is not None:
        parent_row = conn.execute(
            "SELECT 1 FROM types WHERE name = ?", (parent_type,)
        ).fetchone()
        if not parent_row:
            conn.close()
            print(json.dumps({"status": "error", "message": f"Parent type not found: {parent_type}"}))
            return

        # Check circular reference (only for updates where the type already exists)
        existing = conn.execute("SELECT 1 FROM types WHERE name = ?", (name,)).fetchone()
        if existing:
            err = _check_circular_parent(conn, name, parent_type)
            if err:
                conn.close()
                print(json.dumps({"status": "error", "message": err}))
                return

    conn.execute(
        """INSERT INTO types (name, display_name, description, parent_type, abstract, fields_schema)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(name)
           DO UPDATE SET display_name = excluded.display_name,
                         description = excluded.description,
                         parent_type = excluded.parent_type,
                         abstract = excluded.abstract,
                         fields_schema = excluded.fields_schema,
                         updated_at = datetime('now', 'localtime')""",
        (
            name,
            data.get("display_name", ""),
            data.get("description", ""),
            parent_type,
            abstract,
            fields_schema,
        ),
    )
    conn.commit()
    conn.close()
    print(json.dumps({"status": "ok", "name": name}))


def cmd_type_get(name):
    """Get a type's definition with resolved (inherited) fields."""
    conn = get_connection()
    ensure_schema(conn)

    row = conn.execute("SELECT * FROM types WHERE name = ?", (name,)).fetchone()
    if not row:
        conn.close()
        print(json.dumps({"status": "error", "message": f"Type not found: {name}"}))
        return

    d = _build_type_dict(row)
    d["resolved_fields"] = get_resolved_fields(conn, name)
    d["created_at"] = row["created_at"]
    d["updated_at"] = row["updated_at"]

    # Include children types
    children = conn.execute(
        "SELECT * FROM types WHERE parent_type = ? ORDER BY name", (name,)
    ).fetchall()
    d["children"] = [_build_type_dict(c) for c in children]

    # Include parent info
    if row["parent_type"]:
        parent = conn.execute(
            "SELECT * FROM types WHERE name = ?", (row["parent_type"],)
        ).fetchone()
        if parent:
            d["parent"] = {
                "name": parent["name"],
                "display_name": parent["display_name"],
                "abstract": bool(parent["abstract"]),
            }

    conn.close()
    print(json.dumps(d, ensure_ascii=False, indent=2))


def cmd_type_list():
    """List all defined types with hierarchy info."""
    conn = get_connection()
    ensure_schema(conn)

    rows = conn.execute("SELECT * FROM types ORDER BY name").fetchall()
    result = []
    for row in rows:
        d = _build_type_dict(row)
        result.append(d)

    conn.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_type_tree():
    """List all types as a tree structure."""
    conn = get_connection()
    ensure_schema(conn)

    rows = conn.execute("SELECT * FROM types ORDER BY name").fetchall()

    def build_node(row):
        d = _build_type_dict(row)
        children = [r for r in rows if r["parent_type"] == row["name"]]
        d["children"] = [build_node(c) for c in sorted(children, key=lambda x: x["name"])]
        return d

    roots = [r for r in rows if r["parent_type"] is None]
    result = [build_node(r) for r in sorted(roots, key=lambda x: x["name"])]

    conn.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_type_delete(name):
    """Delete a type. Items with this type get type=NULL. Child types get parent_type=NULL."""
    conn = get_connection()
    ensure_schema(conn)
    conn.execute("DELETE FROM types WHERE name = ?", (name,))
    conn.commit()
    conn.close()
    print(json.dumps({"status": "ok", "name": name}))
