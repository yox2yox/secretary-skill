"""Tag listing and tag schema commands."""

import json

from db import get_connection, ensure_schema


def cmd_tags_list():
    """List all unique tags with usage counts and schema info."""
    conn = get_connection()
    ensure_schema(conn)

    # Get per-tag counts
    tag_rows = conn.execute(
        "SELECT tag, COUNT(*) as count FROM collection_item_tags GROUP BY tag"
    ).fetchall()

    # Get all tag schemas
    schema_rows = conn.execute("SELECT * FROM tag_schemas").fetchall()
    schemas = {}
    for row in schema_rows:
        d = dict(row)
        try:
            d["fields_schema"] = json.loads(d["fields_schema"])
        except (json.JSONDecodeError, TypeError):
            d["fields_schema"] = []
        schemas[d["tag"]] = d

    # Aggregate by tag
    tag_data = {}
    for row in tag_rows:
        tag = row["tag"]
        tag_data[tag] = {"tag": tag, "count": row["count"]}

    # Include tags that have a schema but no usage yet
    for tag, schema in schemas.items():
        if tag not in tag_data:
            tag_data[tag] = {"tag": tag, "count": 0}

    # Merge schema info
    for tag, data in tag_data.items():
        if tag in schemas:
            data["has_schema"] = True
            data["kind"] = schemas[tag].get("kind", "tag")
            data["display_name"] = schemas[tag]["display_name"]
            data["description"] = schemas[tag]["description"]
            data["fields_schema"] = schemas[tag]["fields_schema"]
        else:
            data["has_schema"] = False
            data["kind"] = "tag"

    result = sorted(tag_data.values(), key=lambda x: (-x["count"], x["tag"]))

    conn.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_tag_schema_set(data_json):
    """Define or update a tag's schema."""
    data = json.loads(data_json)
    conn = get_connection()
    ensure_schema(conn)

    tag = data["tag"]
    kind = data.get("kind", "tag")
    if kind not in ("tag", "type"):
        conn.close()
        print(json.dumps({"status": "error", "message": "kind must be 'tag' or 'type'"}))
        return

    fields_schema = data.get("fields_schema", [])
    if isinstance(fields_schema, list):
        fields_schema = json.dumps(fields_schema, ensure_ascii=False)

    conn.execute(
        """INSERT INTO tag_schemas (tag, kind, display_name, description, fields_schema)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(tag)
           DO UPDATE SET kind = excluded.kind,
                         display_name = excluded.display_name,
                         description = excluded.description,
                         fields_schema = excluded.fields_schema,
                         updated_at = datetime('now', 'localtime')""",
        (
            tag,
            kind,
            data.get("display_name", ""),
            data.get("description", ""),
            fields_schema,
        ),
    )
    conn.commit()
    conn.close()
    print(json.dumps({"status": "ok", "tag": tag, "kind": kind}))


def cmd_tag_schema_get(tag):
    """Get a tag's schema definition."""
    conn = get_connection()
    ensure_schema(conn)

    row = conn.execute("SELECT * FROM tag_schemas WHERE tag = ?", (tag,)).fetchone()
    if not row:
        conn.close()
        print(json.dumps({"status": "error", "message": f"No schema defined for tag: {tag}"}))
        return

    d = dict(row)
    try:
        d["fields_schema"] = json.loads(d["fields_schema"])
    except (json.JSONDecodeError, TypeError):
        d["fields_schema"] = []

    conn.close()
    print(json.dumps(d, ensure_ascii=False, indent=2))


def cmd_tag_schema_list():
    """List all defined tag schemas."""
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
    """Delete a tag's schema definition (does not remove the tag from items)."""
    conn = get_connection()
    ensure_schema(conn)
    conn.execute("DELETE FROM tag_schemas WHERE tag = ?", (tag,))
    conn.commit()
    conn.close()
    print(json.dumps({"status": "ok", "tag": tag}))
