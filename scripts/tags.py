"""Tag listing and tag schema commands.

Tag schemas define the expected data fields for a given 'type' value on items.
Tags (for search/categorization) and types (for data schema) are separate concepts.
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


def cmd_tag_schema_set(data_json):
    """Define or update a type's schema (expected data fields for items of this type)."""
    data = json.loads(data_json)
    conn = get_connection()
    ensure_schema(conn)

    tag = data["tag"]
    fields_schema = data.get("fields_schema", [])
    if isinstance(fields_schema, list):
        fields_schema = json.dumps(fields_schema, ensure_ascii=False)

    conn.execute(
        """INSERT INTO tag_schemas (tag, display_name, description, fields_schema)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(tag)
           DO UPDATE SET display_name = excluded.display_name,
                         description = excluded.description,
                         fields_schema = excluded.fields_schema,
                         updated_at = datetime('now', 'localtime')""",
        (
            tag,
            data.get("display_name", ""),
            data.get("description", ""),
            fields_schema,
        ),
    )
    conn.commit()
    conn.close()
    print(json.dumps({"status": "ok", "tag": tag}))


def cmd_tag_schema_get(tag):
    """Get a type's schema definition."""
    conn = get_connection()
    ensure_schema(conn)

    row = conn.execute("SELECT * FROM tag_schemas WHERE tag = ?", (tag,)).fetchone()
    if not row:
        conn.close()
        print(json.dumps({"status": "error", "message": f"No schema defined for type: {tag}"}))
        return

    d = dict(row)
    try:
        d["fields_schema"] = json.loads(d["fields_schema"])
    except (json.JSONDecodeError, TypeError):
        d["fields_schema"] = []

    conn.close()
    print(json.dumps(d, ensure_ascii=False, indent=2))


def cmd_tag_schema_list():
    """List all defined type schemas."""
    conn = get_connection()
    ensure_schema(conn)

    rows = conn.execute("SELECT * FROM tag_schemas ORDER BY tag").fetchall()
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


def cmd_tag_schema_delete(tag):
    """Delete a type's schema definition (does not affect items with this type)."""
    conn = get_connection()
    ensure_schema(conn)
    conn.execute("DELETE FROM tag_schemas WHERE tag = ?", (tag,))
    conn.commit()
    conn.close()
    print(json.dumps({"status": "ok", "tag": tag}))
