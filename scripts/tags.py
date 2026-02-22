"""Tag listing and tag schema commands."""

import json

from db import get_connection, ensure_schema


def cmd_tags_list(source=None):
    """List all unique tags across all tables with usage counts and schema info.

    Optional source filter: 'entries', 'persons', 'items', or None for all.
    """
    conn = get_connection()
    ensure_schema(conn)

    queries = []

    if source is None or source == "entries":
        queries.append(
            "SELECT tag, 'entry' as source, COUNT(*) as count FROM entry_tags GROUP BY tag"
        )
    if source is None or source == "persons":
        queries.append(
            "SELECT tag, 'person' as source, COUNT(*) as count FROM person_tags GROUP BY tag"
        )
    if source is None or source == "items":
        queries.append(
            "SELECT tag, 'collection_item' as source, COUNT(*) as count FROM collection_item_tags GROUP BY tag"
        )

    if not queries:
        print(json.dumps({"status": "error", "message": "Invalid source filter. Use: entries, persons, items"}))
        return

    # Get per-source counts
    all_rows = []
    for q in queries:
        all_rows.extend(conn.execute(q).fetchall())

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
    for row in all_rows:
        tag = row["tag"]
        if tag not in tag_data:
            tag_data[tag] = {"tag": tag, "total_count": 0, "sources": {}}
        tag_data[tag]["total_count"] += row["count"]
        tag_data[tag]["sources"][row["source"]] = row["count"]

    # Include tags that have a schema but no usage yet
    for tag, schema in schemas.items():
        if tag not in tag_data:
            tag_data[tag] = {"tag": tag, "total_count": 0, "sources": {}}

    # Merge schema info
    for tag, data in tag_data.items():
        if tag in schemas:
            data["has_schema"] = True
            data["display_name"] = schemas[tag]["display_name"]
            data["description"] = schemas[tag]["description"]
            data["fields_schema"] = schemas[tag]["fields_schema"]
        else:
            data["has_schema"] = False

    result = sorted(tag_data.values(), key=lambda x: (-x["total_count"], x["tag"]))

    conn.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_tag_schema_set(data_json):
    """Define or update a tag's schema."""
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
    """Delete a tag's schema definition (does not remove the tag from entities)."""
    conn = get_connection()
    ensure_schema(conn)
    conn.execute("DELETE FROM tag_schemas WHERE tag = ?", (tag,))
    conn.commit()
    conn.close()
    print(json.dumps({"status": "ok", "tag": tag}))
