"""Tag listing and type definition commands.

Types define the schema (expected data fields) for collections. They are stored
in the 'types' table and referenced by collections.type via foreign key.
All items in a collection share the same type (and thus the same fields_schema).

Tags are simple labels for search/categorization, stored in collection_item_tags.
"""

import json

from db import get_connection, ensure_schema


def cmd_tags_list():
    """List all unique tags with usage counts."""
    conn = get_connection()
    ensure_schema(conn)

    tag_rows = conn.execute(
        "SELECT tag, COUNT(*) as count FROM collection_item_tags GROUP BY tag ORDER BY count DESC, tag"
    ).fetchall()

    result = [{"tag": row["tag"], "count": row["count"]} for row in tag_rows]

    conn.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


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
