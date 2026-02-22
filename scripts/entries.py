"""Entry commands and entry-person link commands."""

import json
from datetime import datetime, timedelta

from db import get_connection, ensure_schema, parse_tags, DB_PATH


def _save_entry_tags(conn, entry_id, tags):
    """Save tags for an entry."""
    for tag in tags:
        conn.execute(
            "INSERT OR IGNORE INTO entry_tags (entry_id, tag) VALUES (?, ?)",
            (entry_id, tag),
        )


def _save_entry_persons(conn, entry_id, person_ids):
    """Link persons to an entry from a list of IDs or dicts."""
    if isinstance(person_ids, list):
        for item in person_ids:
            if isinstance(item, dict):
                pid = int(item["person_id"])
                role = item.get("role", "")
            else:
                pid = int(item)
                role = ""
            conn.execute(
                "INSERT OR IGNORE INTO entry_persons (entry_id, person_id, role) VALUES (?, ?, ?)",
                (entry_id, pid, role),
            )


def _enrich_entries(conn, entries):
    """Add tags and linked persons to entry dicts (batch, avoids N+1)."""
    if not entries:
        return entries

    entry_ids = [e["id"] for e in entries]
    placeholders = ",".join("?" for _ in entry_ids)

    # Tags
    tag_rows = conn.execute(
        f"SELECT entry_id, tag FROM entry_tags WHERE entry_id IN ({placeholders}) ORDER BY entry_id, tag",
        entry_ids,
    ).fetchall()
    tags_map = {}
    for row in tag_rows:
        tags_map.setdefault(row["entry_id"], []).append(row["tag"])

    # Linked persons
    person_rows = conn.execute(
        f"""SELECT ep.entry_id, ep.role, p.id as person_id, p.name
            FROM entry_persons ep JOIN persons p ON ep.person_id = p.id
            WHERE ep.entry_id IN ({placeholders})
            ORDER BY ep.entry_id, p.name""",
        entry_ids,
    ).fetchall()
    persons_map = {}
    for row in person_rows:
        persons_map.setdefault(row["entry_id"], []).append({
            "person_id": row["person_id"],
            "name": row["name"],
            "role": row["role"],
        })

    for entry in entries:
        entry["tags"] = tags_map.get(entry["id"], [])
        entry["persons"] = persons_map.get(entry["id"], [])

    return entries


def _insert_entry(conn, data):
    """Insert a single entry row and return its ID."""
    cursor = conn.execute(
        """INSERT INTO entries
           (category, title, content, entry_date, start_time, end_time,
            due_date, status, priority, parent_id, location, url,
            recurrence, recurrence_until, source)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            data.get("category", "note"),
            data["title"],
            data.get("content", ""),
            data.get("entry_date"),
            data.get("start_time"),
            data.get("end_time"),
            data.get("due_date"),
            data.get("status", "active"),
            data.get("priority", "medium"),
            data.get("parent_id"),
            data.get("location", ""),
            data.get("url", ""),
            data.get("recurrence", ""),
            data.get("recurrence_until"),
            data.get("source", ""),
        ),
    )
    entry_id = cursor.lastrowid

    tags = parse_tags(data.get("tags", ""))
    _save_entry_tags(conn, entry_id, tags)

    if "person_ids" in data:
        _save_entry_persons(conn, entry_id, data["person_ids"])

    return entry_id


def cmd_init():
    """Initialize the database."""
    conn = get_connection()
    ensure_schema(conn)
    conn.close()
    print(json.dumps({"status": "ok", "message": "Database initialized", "path": DB_PATH}))


def cmd_store(data_json):
    """Store a single entry."""
    data = json.loads(data_json)
    conn = get_connection()
    ensure_schema(conn)

    entry_id = _insert_entry(conn, data)

    conn.commit()
    conn.close()
    print(json.dumps({"status": "ok", "id": entry_id}))


def cmd_store_batch(data_json):
    """Store multiple entries at once."""
    items = json.loads(data_json)
    conn = get_connection()
    ensure_schema(conn)

    ids = []
    for data in items:
        ids.append(_insert_entry(conn, data))

    conn.commit()
    conn.close()
    print(json.dumps({"status": "ok", "ids": ids, "count": len(ids)}))


def cmd_query(filter_json):
    """Query entries with filters."""
    filters = json.loads(filter_json)
    conn = get_connection()
    ensure_schema(conn)

    where_clauses = []
    params = []

    if "category" in filters:
        where_clauses.append("e.category = ?")
        params.append(filters["category"])
    if "status" in filters:
        where_clauses.append("e.status = ?")
        params.append(filters["status"])
    if "from_date" in filters:
        where_clauses.append("(e.entry_date >= ? OR e.due_date >= ?)")
        params.extend([filters["from_date"], filters["from_date"]])
    if "to_date" in filters:
        where_clauses.append("(e.entry_date <= ? OR e.due_date <= ?)")
        params.extend([filters["to_date"], filters["to_date"]])
    if "priority" in filters:
        where_clauses.append("e.priority = ?")
        params.append(filters["priority"])
    if "tags" in filters:
        where_clauses.append(
            "EXISTS (SELECT 1 FROM entry_tags et WHERE et.entry_id = e.id AND et.tag = ?)"
        )
        params.append(filters["tags"])
    if "person_id" in filters:
        where_clauses.append(
            "EXISTS (SELECT 1 FROM entry_persons ep WHERE ep.entry_id = e.id AND ep.person_id = ?)"
        )
        params.append(int(filters["person_id"]))
    if "parent_id" in filters:
        where_clauses.append("e.parent_id = ?")
        params.append(int(filters["parent_id"]))
    if "id" in filters:
        where_clauses.append("e.id = ?")
        params.append(int(filters["id"]))

    where = " AND ".join(where_clauses) if where_clauses else "1=1"
    limit = filters.get("limit", 50)

    rows = conn.execute(
        f"""SELECT e.* FROM entries e
            WHERE {where}
            ORDER BY COALESCE(e.entry_date, '9999-12-31') DESC, e.created_at DESC
            LIMIT ?""",
        params + [limit],
    ).fetchall()

    result = [dict(row) for row in rows]
    _enrich_entries(conn, result)
    conn.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _search_entries_like(conn, keyword):
    """Search entries using LIKE (fallback for short queries or when FTS5 is unavailable)."""
    pattern = f"%{keyword}%"
    return conn.execute(
        """SELECT * FROM entries
           WHERE title LIKE ? OR content LIKE ?
           ORDER BY COALESCE(entry_date, '9999-12-31') DESC, created_at DESC
           LIMIT 50""",
        (pattern, pattern),
    ).fetchall()


def cmd_search(keyword):
    """Full-text search across entries using FTS5, with LIKE fallback."""
    conn = get_connection()
    ensure_schema(conn)

    rows = []
    try:
        rows = conn.execute(
            """SELECT e.* FROM entries_fts fts
               JOIN entries e ON e.id = fts.rowid
               WHERE entries_fts MATCH ?
               ORDER BY rank
               LIMIT 50""",
            (keyword,),
        ).fetchall()
    except Exception:
        pass

    # Fall back to LIKE if FTS returned nothing (e.g. query shorter than 3 chars for trigram)
    if not rows:
        rows = _search_entries_like(conn, keyword)

    result = [dict(row) for row in rows]
    _enrich_entries(conn, result)
    conn.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_update(entry_id, update_json):
    """Update an existing entry."""
    updates = json.loads(update_json)
    conn = get_connection()
    ensure_schema(conn)

    set_clauses = []
    params = []

    allowed_fields = [
        "category", "title", "content",
        "entry_date", "start_time", "end_time",
        "due_date", "status", "priority",
        "parent_id", "location", "url",
        "recurrence", "recurrence_until", "source",
    ]
    for field in allowed_fields:
        if field in updates:
            set_clauses.append(f"{field} = ?")
            params.append(updates[field])

    # Auto-set completed_at when status changes to completed
    if updates.get("status") == "completed":
        set_clauses.append("completed_at = datetime('now', 'localtime')")
    elif updates.get("status") in ("active", "on_hold"):
        set_clauses.append("completed_at = NULL")

    has_field_updates = bool(set_clauses)
    has_tags = "tags" in updates
    has_persons = "person_ids" in updates

    if not has_field_updates and not has_tags and not has_persons:
        print(json.dumps({"status": "error", "message": "No valid fields to update"}))
        return

    if has_field_updates:
        set_clauses.append("updated_at = datetime('now', 'localtime')")
        params.append(int(entry_id))
        conn.execute(
            f"UPDATE entries SET {', '.join(set_clauses)} WHERE id = ?",
            params,
        )

    if has_tags:
        conn.execute("DELETE FROM entry_tags WHERE entry_id = ?", (int(entry_id),))
        tags = parse_tags(updates["tags"])
        _save_entry_tags(conn, int(entry_id), tags)

    if has_persons:
        conn.execute("DELETE FROM entry_persons WHERE entry_id = ?", (int(entry_id),))
        _save_entry_persons(conn, int(entry_id), updates["person_ids"])

    conn.commit()
    conn.close()
    print(json.dumps({"status": "ok", "id": int(entry_id)}))


def cmd_delete(entry_id):
    """Delete an entry."""
    conn = get_connection()
    ensure_schema(conn)
    conn.execute("DELETE FROM entries WHERE id = ?", (int(entry_id),))
    conn.commit()
    conn.close()
    print(json.dumps({"status": "ok", "id": int(entry_id)}))


def cmd_summary(period_json):
    """Get a summary of entries for a given period."""
    period = json.loads(period_json)
    conn = get_connection()
    ensure_schema(conn)

    today = datetime.now().strftime("%Y-%m-%d")

    period_type = period.get("type", "today")
    if period_type == "today":
        from_date = today
        to_date = today
    elif period_type == "yesterday":
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        from_date = yesterday
        to_date = yesterday
    elif period_type == "week":
        now = datetime.now()
        from_date = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")
        to_date = (now + timedelta(days=6 - now.weekday())).strftime("%Y-%m-%d")
    elif period_type == "month":
        now = datetime.now()
        from_date = now.strftime("%Y-%m-01")
        next_month = now.replace(day=28) + timedelta(days=4)
        to_date = (next_month - timedelta(days=next_month.day)).strftime("%Y-%m-%d")
    elif period_type == "all":
        from_date = "2000-01-01"
        to_date = "2099-12-31"
    else:
        from_date = period.get("from_date", today)
        to_date = period.get("to_date", today)

    # Get entries in the period
    rows = conn.execute(
        """SELECT * FROM entries
           WHERE (entry_date BETWEEN ? AND ?) OR (due_date BETWEEN ? AND ?)
           ORDER BY category, COALESCE(entry_date, '9999-12-31'), priority DESC""",
        (from_date, to_date, from_date, to_date),
    ).fetchall()
    entries = [dict(row) for row in rows]
    _enrich_entries(conn, entries)

    # Get counts by category
    counts = conn.execute(
        """SELECT category, COUNT(*) as count FROM entries
           WHERE (entry_date BETWEEN ? AND ?) OR (due_date BETWEEN ? AND ?)
           GROUP BY category""",
        (from_date, to_date, from_date, to_date),
    ).fetchall()

    # Get overdue items
    overdue_rows = conn.execute(
        """SELECT * FROM entries
           WHERE due_date < ? AND status = 'active'
           ORDER BY due_date, priority DESC""",
        (today,),
    ).fetchall()
    overdue = [dict(row) for row in overdue_rows]
    _enrich_entries(conn, overdue)

    # Get upcoming deadlines (next 7 days)
    upcoming_end = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    upcoming_rows = conn.execute(
        """SELECT * FROM entries
           WHERE due_date BETWEEN ? AND ? AND status = 'active'
           ORDER BY due_date, priority DESC""",
        (today, upcoming_end),
    ).fetchall()
    upcoming = [dict(row) for row in upcoming_rows]
    _enrich_entries(conn, upcoming)

    # Get active goals
    goal_rows = conn.execute(
        """SELECT * FROM entries
           WHERE category = 'goal' AND status = 'active'
           ORDER BY priority DESC, created_at DESC""",
    ).fetchall()
    goals = [dict(row) for row in goal_rows]
    _enrich_entries(conn, goals)

    result = {
        "period": {"from": from_date, "to": to_date, "type": period_type},
        "entries": entries,
        "counts": {row["category"]: row["count"] for row in counts},
        "overdue": overdue,
        "upcoming_deadlines": upcoming,
        "active_goals": goals,
    }

    conn.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_list():
    """List all active entries."""
    conn = get_connection()
    ensure_schema(conn)
    rows = conn.execute(
        """SELECT * FROM entries WHERE status = 'active'
           ORDER BY COALESCE(entry_date, '9999-12-31') DESC, created_at DESC LIMIT 100"""
    ).fetchall()
    result = [dict(row) for row in rows]
    _enrich_entries(conn, result)
    conn.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


## ── Entry-Person link commands ────────────────────────────────────────


def cmd_entry_link(entry_id, data_json):
    """Link one or more persons to an entry."""
    data = json.loads(data_json)
    conn = get_connection()
    ensure_schema(conn)

    items = data if isinstance(data, list) else [data]
    for item in items:
        conn.execute(
            """INSERT OR REPLACE INTO entry_persons (entry_id, person_id, role)
               VALUES (?, ?, ?)""",
            (int(entry_id), int(item["person_id"]), item.get("role", "")),
        )

    conn.commit()
    conn.close()
    print(json.dumps({"status": "ok", "entry_id": int(entry_id)}))


def cmd_entry_unlink(entry_id, person_id):
    """Unlink a person from an entry."""
    conn = get_connection()
    ensure_schema(conn)
    conn.execute(
        "DELETE FROM entry_persons WHERE entry_id = ? AND person_id = ?",
        (int(entry_id), int(person_id)),
    )
    conn.commit()
    conn.close()
    print(json.dumps({"status": "ok", "entry_id": int(entry_id), "person_id": int(person_id)}))


def cmd_person_entries(person_id):
    """List entries linked to a person."""
    conn = get_connection()
    ensure_schema(conn)
    rows = conn.execute(
        """SELECT e.*, ep.role as link_role FROM entries e
           JOIN entry_persons ep ON e.id = ep.entry_id
           WHERE ep.person_id = ?
           ORDER BY COALESCE(e.entry_date, '9999-12-31') DESC, e.created_at DESC
           LIMIT 100""",
        (int(person_id),),
    ).fetchall()
    result = [dict(row) for row in rows]
    _enrich_entries(conn, result)
    conn.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))
