"""Person commands, person tag commands, and attribute commands."""

import json

from db import get_connection, ensure_schema, parse_tags


def _enrich_persons(conn, persons):
    """Add attributes and tags to person dicts (batch, avoids N+1)."""
    if not persons:
        return persons

    person_ids = [p["id"] for p in persons]
    placeholders = ",".join("?" for _ in person_ids)

    # Attributes
    attr_rows = conn.execute(
        f"SELECT * FROM person_attributes WHERE person_id IN ({placeholders}) ORDER BY person_id, category, key",
        person_ids,
    ).fetchall()
    attrs_map = {}
    for row in attr_rows:
        attrs_map.setdefault(row["person_id"], []).append(dict(row))

    # Tags
    tag_rows = conn.execute(
        f"SELECT person_id, tag FROM person_tags WHERE person_id IN ({placeholders}) ORDER BY person_id, tag",
        person_ids,
    ).fetchall()
    tags_map = {}
    for row in tag_rows:
        tags_map.setdefault(row["person_id"], []).append(row["tag"])

    for person in persons:
        person["attributes"] = attrs_map.get(person["id"], [])
        person["tags"] = tags_map.get(person["id"], [])

    return persons


## ── Person commands ───────────────────────────────────────────────────


def cmd_person_add(data_json):
    """Add a new person (owner or contact)."""
    data = json.loads(data_json)
    conn = get_connection()
    ensure_schema(conn)

    cursor = conn.execute(
        """INSERT INTO persons (person_type, name, relationship, organization, role, birthday, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            data.get("person_type", "contact"),
            data["name"],
            data.get("relationship", ""),
            data.get("organization", ""),
            data.get("role", ""),
            data.get("birthday"),
            data.get("notes", ""),
        ),
    )
    person_id = cursor.lastrowid

    # Handle email as a contact attribute for backward compatibility
    if data.get("email"):
        conn.execute(
            """INSERT OR REPLACE INTO person_attributes (person_id, category, key, value)
               VALUES (?, 'contact', 'email', ?)""",
            (person_id, data["email"]),
        )

    # Store inline attributes
    attrs = data.get("attributes", [])
    for attr in attrs:
        conn.execute(
            """INSERT OR REPLACE INTO person_attributes (person_id, category, key, value)
               VALUES (?, ?, ?, ?)""",
            (person_id, attr["category"], attr["key"], attr["value"]),
        )

    # Store inline tags
    tags = parse_tags(data.get("tags", ""))
    for tag in tags:
        conn.execute(
            "INSERT OR IGNORE INTO person_tags (person_id, tag) VALUES (?, ?)",
            (person_id, tag),
        )

    conn.commit()
    conn.close()
    print(json.dumps({"status": "ok", "id": person_id}))


def cmd_person_update(person_id, update_json):
    """Update an existing person's basic info."""
    updates = json.loads(update_json)
    conn = get_connection()
    ensure_schema(conn)

    allowed = [
        "person_type", "name", "relationship", "organization",
        "role", "birthday", "notes", "last_contacted_at",
    ]
    set_clauses = []
    params = []
    for field in allowed:
        if field in updates:
            set_clauses.append(f"{field} = ?")
            params.append(updates[field])

    if not set_clauses:
        print(json.dumps({"status": "error", "message": "No valid fields to update"}))
        return

    set_clauses.append("updated_at = datetime('now', 'localtime')")
    params.append(int(person_id))

    conn.execute(f"UPDATE persons SET {', '.join(set_clauses)} WHERE id = ?", params)
    conn.commit()
    conn.close()
    print(json.dumps({"status": "ok", "id": int(person_id)}))


def cmd_person_delete(person_id):
    """Delete a person (cascades to attributes, tags, and entry links)."""
    conn = get_connection()
    ensure_schema(conn)
    conn.execute("DELETE FROM persons WHERE id = ?", (int(person_id),))
    conn.commit()
    conn.close()
    print(json.dumps({"status": "ok", "id": int(person_id)}))


def cmd_person_get(person_id):
    """Get a person with all their attributes and tags."""
    conn = get_connection()
    ensure_schema(conn)

    row = conn.execute("SELECT * FROM persons WHERE id = ?", (int(person_id),)).fetchone()
    if not row:
        conn.close()
        print(json.dumps({"status": "error", "message": "Person not found"}))
        return

    person = dict(row)
    _enrich_persons(conn, [person])

    conn.close()
    print(json.dumps(person, ensure_ascii=False, indent=2))


def cmd_person_list(filter_json=None):
    """List persons, optionally filtered."""
    filters = json.loads(filter_json) if filter_json else {}
    conn = get_connection()
    ensure_schema(conn)

    where_clauses = []
    params = []
    if "person_type" in filters:
        where_clauses.append("p.person_type = ?")
        params.append(filters["person_type"])
    if "name" in filters:
        where_clauses.append("p.name LIKE ?")
        params.append(f"%{filters['name']}%")
    if "relationship" in filters:
        where_clauses.append("p.relationship LIKE ?")
        params.append(f"%{filters['relationship']}%")
    if "organization" in filters:
        where_clauses.append("p.organization LIKE ?")
        params.append(f"%{filters['organization']}%")
    if "tag" in filters:
        where_clauses.append(
            "EXISTS (SELECT 1 FROM person_tags pt WHERE pt.person_id = p.id AND pt.tag = ?)"
        )
        params.append(filters["tag"])

    where = " AND ".join(where_clauses) if where_clauses else "1=1"
    rows = conn.execute(
        f"SELECT p.* FROM persons p WHERE {where} ORDER BY p.person_type, p.name", params
    ).fetchall()

    result = [dict(row) for row in rows]
    _enrich_persons(conn, result)

    conn.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _search_persons_like(conn, keyword):
    """Search persons using LIKE (fallback)."""
    pattern = f"%{keyword}%"
    return conn.execute(
        """SELECT DISTINCT p.* FROM persons p
           LEFT JOIN person_attributes pa ON p.id = pa.person_id
           WHERE p.name LIKE ? OR p.relationship LIKE ? OR p.organization LIKE ?
                 OR p.role LIKE ? OR p.notes LIKE ?
                 OR pa.key LIKE ? OR pa.value LIKE ?
           ORDER BY p.person_type, p.name""",
        (pattern, pattern, pattern, pattern, pattern, pattern, pattern),
    ).fetchall()


def cmd_person_search(keyword):
    """Search persons by keyword using FTS5, with LIKE fallback."""
    conn = get_connection()
    ensure_schema(conn)

    rows = []
    try:
        rows = conn.execute(
            """SELECT p.* FROM persons_fts fts
               JOIN persons p ON p.id = fts.rowid
               WHERE persons_fts MATCH ?
               ORDER BY rank""",
            (keyword,),
        ).fetchall()
    except Exception:
        pass

    # Fall back to LIKE if FTS returned nothing
    if not rows:
        rows = _search_persons_like(conn, keyword)

    result = [dict(row) for row in rows]
    _enrich_persons(conn, result)

    conn.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


## ── Person tag commands ───────────────────────────────────────────────


def cmd_person_tag_add(person_id, tag):
    """Add a tag to a person."""
    conn = get_connection()
    ensure_schema(conn)
    conn.execute(
        "INSERT OR IGNORE INTO person_tags (person_id, tag) VALUES (?, ?)",
        (int(person_id), tag.strip()),
    )
    conn.commit()
    conn.close()
    print(json.dumps({"status": "ok", "person_id": int(person_id), "tag": tag.strip()}))


def cmd_person_tag_remove(person_id, tag):
    """Remove a tag from a person."""
    conn = get_connection()
    ensure_schema(conn)
    conn.execute(
        "DELETE FROM person_tags WHERE person_id = ? AND tag = ?",
        (int(person_id), tag.strip()),
    )
    conn.commit()
    conn.close()
    print(json.dumps({"status": "ok", "person_id": int(person_id), "tag": tag.strip()}))


## ── Person attribute commands ─────────────────────────────────────────


def cmd_attr_set(person_id, data_json):
    """Set (upsert) one or more attributes for a person."""
    entries = json.loads(data_json)
    conn = get_connection()
    ensure_schema(conn)

    # Accept a single object or an array
    if isinstance(entries, dict):
        entries = [entries]

    ids = []
    for attr in entries:
        cursor = conn.execute(
            """INSERT INTO person_attributes (person_id, category, key, value)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(person_id, category, key)
               DO UPDATE SET value = excluded.value,
                             updated_at = datetime('now', 'localtime')""",
            (int(person_id), attr["category"], attr["key"], attr["value"]),
        )
        ids.append(cursor.lastrowid)

    conn.commit()
    conn.close()
    print(json.dumps({"status": "ok", "ids": ids, "count": len(ids)}))


def cmd_attr_delete(attr_id):
    """Delete a single attribute by its ID."""
    conn = get_connection()
    ensure_schema(conn)
    conn.execute("DELETE FROM person_attributes WHERE id = ?", (int(attr_id),))
    conn.commit()
    conn.close()
    print(json.dumps({"status": "ok", "id": int(attr_id)}))


def cmd_attr_list(person_id, category=None):
    """List attributes for a person, optionally filtered by category."""
    conn = get_connection()
    ensure_schema(conn)

    if category:
        rows = conn.execute(
            "SELECT * FROM person_attributes WHERE person_id = ? AND category = ? ORDER BY key",
            (int(person_id), category),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM person_attributes WHERE person_id = ? ORDER BY category, key",
            (int(person_id),),
        ).fetchall()

    result = [dict(r) for r in rows]
    conn.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))
