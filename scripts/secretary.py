#!/usr/bin/env python3
"""Secretary Skill - SQLite storage for personal information management.

Usage:
    python3 secretary.py init
    python3 secretary.py store '<json>'
    python3 secretary.py store_batch '<json_array>'
    python3 secretary.py query '<json_filter>'
    python3 secretary.py search '<keyword>'
    python3 secretary.py update <id> '<json>'
    python3 secretary.py delete <id>
    python3 secretary.py summary '<json>'
    python3 secretary.py list
"""

import sqlite3
import json
import sys
import os
from datetime import datetime, timedelta

DB_DIR = os.path.expanduser("~/.secretary")
DB_PATH = os.path.join(DB_DIR, "data.db")

VALID_CATEGORIES = {"event", "plan", "goal", "task", "decision", "note"}
VALID_STATUSES = {"active", "completed", "archived"}
VALID_PRIORITIES = {"high", "medium", "low"}
VALID_RECURRENCES = {"daily", "weekly", "biweekly", "monthly", "yearly", None}

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL CHECK(category IN ('event', 'plan', 'goal', 'task', 'decision', 'note')),
    title TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    entry_date TEXT,
    due_date TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'completed', 'archived')),
    priority TEXT NOT NULL DEFAULT 'medium' CHECK(priority IN ('high', 'medium', 'low')),
    parent_id INTEGER REFERENCES entries(id) ON DELETE SET NULL,
    location TEXT DEFAULT '',
    url TEXT DEFAULT '',
    recurrence TEXT CHECK(recurrence IS NULL OR recurrence IN ('daily', 'weekly', 'biweekly', 'monthly', 'yearly')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now'))
);

CREATE TABLE IF NOT EXISTS entry_tags (
    entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
    tag TEXT NOT NULL,
    PRIMARY KEY (entry_id, tag)
);

CREATE INDEX IF NOT EXISTS idx_entries_category ON entries(category);
CREATE INDEX IF NOT EXISTS idx_entries_entry_date ON entries(entry_date);
CREATE INDEX IF NOT EXISTS idx_entries_status ON entries(status);
CREATE INDEX IF NOT EXISTS idx_entries_due_date ON entries(due_date);
CREATE INDEX IF NOT EXISTS idx_entries_created_at ON entries(created_at);
CREATE INDEX IF NOT EXISTS idx_entries_category_status ON entries(category, status);
CREATE INDEX IF NOT EXISTS idx_entries_status_due_date ON entries(status, due_date);
CREATE INDEX IF NOT EXISTS idx_entries_parent_id ON entries(parent_id);
CREATE INDEX IF NOT EXISTS idx_entry_tags_tag ON entry_tags(tag);
"""

FTS_SETUP_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(
    title, content, content=entries, content_rowid=id
);

CREATE TRIGGER IF NOT EXISTS entries_ai AFTER INSERT ON entries BEGIN
    INSERT INTO entries_fts(rowid, title, content) VALUES (new.id, new.title, new.content);
END;

CREATE TRIGGER IF NOT EXISTS entries_ad AFTER DELETE ON entries BEGIN
    INSERT INTO entries_fts(entries_fts, rowid, title, content) VALUES('delete', old.id, old.title, old.content);
END;

CREATE TRIGGER IF NOT EXISTS entries_au AFTER UPDATE OF title, content ON entries BEGIN
    INSERT INTO entries_fts(entries_fts, rowid, title, content) VALUES('delete', old.id, old.title, old.content);
    INSERT INTO entries_fts(rowid, title, content) VALUES (new.id, new.title, new.content);
END;
"""


def get_connection():
    """Get a database connection, creating the directory if needed."""
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def ensure_schema(conn):
    """Ensure the database schema exists."""
    conn.executescript(SCHEMA_SQL)
    try:
        conn.executescript(FTS_SETUP_SQL)
    except sqlite3.OperationalError:
        pass  # FTS5 already exists or not available


def cmd_init():
    """Initialize the database."""
    conn = get_connection()
    ensure_schema(conn)
    conn.close()
    print(json.dumps({"status": "ok", "message": "Database initialized", "path": DB_PATH}))


def _save_tags(conn, entry_id, tags_str):
    """Parse comma-separated tags string and save to entry_tags table."""
    if not tags_str:
        return
    tags = [t.strip() for t in tags_str.split(",") if t.strip()]
    for tag in tags:
        conn.execute(
            "INSERT OR IGNORE INTO entry_tags (entry_id, tag) VALUES (?, ?)",
            (entry_id, tag),
        )


def _get_tags(conn, entry_id):
    """Get tags for an entry as a comma-separated string."""
    rows = conn.execute(
        "SELECT tag FROM entry_tags WHERE entry_id = ? ORDER BY tag", (entry_id,)
    ).fetchall()
    return ",".join(row["tag"] for row in rows)


def _entry_to_dict(conn, row):
    """Convert an entry row to a dict, attaching tags from entry_tags table."""
    d = dict(row)
    d["tags"] = _get_tags(conn, d["id"])
    return d


def cmd_store(data_json):
    """Store a single entry."""
    data = json.loads(data_json)
    conn = get_connection()
    ensure_schema(conn)

    cursor = conn.execute(
        """INSERT INTO entries (category, title, content, entry_date, due_date,
                               status, priority, parent_id, location, url, recurrence)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            data.get("category", "note"),
            data["title"],
            data.get("content", ""),
            data.get("entry_date"),
            data.get("due_date"),
            data.get("status", "active"),
            data.get("priority", "medium"),
            data.get("parent_id"),
            data.get("location", ""),
            data.get("url", ""),
            data.get("recurrence"),
        ),
    )
    entry_id = cursor.lastrowid
    _save_tags(conn, entry_id, data.get("tags", ""))
    conn.commit()
    conn.close()
    print(json.dumps({"status": "ok", "id": entry_id}))


def cmd_store_batch(data_json):
    """Store multiple entries at once."""
    entries = json.loads(data_json)
    conn = get_connection()
    ensure_schema(conn)

    ids = []
    for data in entries:
        cursor = conn.execute(
            """INSERT INTO entries (category, title, content, entry_date, due_date,
                                   status, priority, parent_id, location, url, recurrence)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                data.get("category", "note"),
                data["title"],
                data.get("content", ""),
                data.get("entry_date"),
                data.get("due_date"),
                data.get("status", "active"),
                data.get("priority", "medium"),
                data.get("parent_id"),
                data.get("location", ""),
                data.get("url", ""),
                data.get("recurrence"),
            ),
        )
        entry_id = cursor.lastrowid
        _save_tags(conn, entry_id, data.get("tags", ""))
        ids.append(entry_id)

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
            "e.id IN (SELECT entry_id FROM entry_tags WHERE tag = ?)"
        )
        params.append(filters["tags"])
    if "location" in filters:
        where_clauses.append("e.location LIKE ?")
        params.append(f"%{filters['location']}%")
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

    result = [_entry_to_dict(conn, row) for row in rows]
    conn.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_search(keyword):
    """Full-text search across title, content, and tags."""
    conn = get_connection()
    ensure_schema(conn)

    # Try FTS5 first, fall back to LIKE if not available
    try:
        fts_ids = conn.execute(
            "SELECT rowid FROM entries_fts WHERE entries_fts MATCH ?",
            (keyword,),
        ).fetchall()
        fts_id_set = {row["rowid"] for row in fts_ids}
    except sqlite3.OperationalError:
        fts_id_set = None

    # Also search in tags via entry_tags table
    tag_entry_ids = conn.execute(
        "SELECT DISTINCT entry_id FROM entry_tags WHERE tag LIKE ?",
        (f"%{keyword}%",),
    ).fetchall()
    tag_id_set = {row["entry_id"] for row in tag_entry_ids}

    if fts_id_set is not None:
        all_ids = fts_id_set | tag_id_set
        if not all_ids:
            conn.close()
            print(json.dumps([], ensure_ascii=False, indent=2))
            return
        placeholders = ",".join("?" for _ in all_ids)
        rows = conn.execute(
            f"""SELECT * FROM entries
                WHERE id IN ({placeholders})
                ORDER BY COALESCE(entry_date, '9999-12-31') DESC, created_at DESC
                LIMIT 50""",
            list(all_ids),
        ).fetchall()
    else:
        # Fallback: LIKE-based search
        rows = conn.execute(
            """SELECT * FROM entries
               WHERE title LIKE ? OR content LIKE ?
               ORDER BY COALESCE(entry_date, '9999-12-31') DESC, created_at DESC
               LIMIT 50""",
            (f"%{keyword}%", f"%{keyword}%"),
        ).fetchall()
        like_id_set = {row["id"] for row in rows}
        all_ids = like_id_set | tag_id_set
        if tag_id_set - like_id_set:
            extra_placeholders = ",".join("?" for _ in (tag_id_set - like_id_set))
            extra_rows = conn.execute(
                f"SELECT * FROM entries WHERE id IN ({extra_placeholders})",
                list(tag_id_set - like_id_set),
            ).fetchall()
            rows = list(rows) + list(extra_rows)

    result = [_entry_to_dict(conn, row) for row in rows]
    conn.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_update(entry_id, update_json):
    """Update an existing entry."""
    updates = json.loads(update_json)
    conn = get_connection()
    ensure_schema(conn)

    entry_id = int(entry_id)
    set_clauses = []
    params = []

    allowed_fields = [
        "category", "title", "content",
        "entry_date", "due_date", "status", "priority",
        "parent_id", "location", "url", "recurrence",
    ]
    for field in allowed_fields:
        if field in updates:
            set_clauses.append(f"{field} = ?")
            params.append(updates[field])

    # Handle tags separately via entry_tags table
    if "tags" in updates:
        conn.execute("DELETE FROM entry_tags WHERE entry_id = ?", (entry_id,))
        _save_tags(conn, entry_id, updates["tags"])

    if not set_clauses and "tags" not in updates:
        print(json.dumps({"status": "error", "message": "No valid fields to update"}))
        return

    if set_clauses:
        set_clauses.append("updated_at = strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now')")
        params.append(entry_id)
        conn.execute(
            f"UPDATE entries SET {', '.join(set_clauses)} WHERE id = ?",
            params,
        )

    conn.commit()
    conn.close()
    print(json.dumps({"status": "ok", "id": entry_id}))


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

    # Get counts by category
    counts = conn.execute(
        """SELECT category, COUNT(*) as count FROM entries
           WHERE (entry_date BETWEEN ? AND ?) OR (due_date BETWEEN ? AND ?)
           GROUP BY category""",
        (from_date, to_date, from_date, to_date),
    ).fetchall()

    # Get overdue items (only categories where "overdue" is meaningful)
    overdue = conn.execute(
        """SELECT * FROM entries
           WHERE due_date < ? AND status = 'active'
             AND category IN ('task', 'plan', 'goal')
           ORDER BY due_date, priority DESC""",
        (today,),
    ).fetchall()

    # Get upcoming deadlines (next 7 days)
    upcoming_end = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    upcoming = conn.execute(
        """SELECT * FROM entries
           WHERE due_date BETWEEN ? AND ? AND status = 'active'
           ORDER BY due_date, priority DESC""",
        (today, upcoming_end),
    ).fetchall()

    # Get active goals
    goals = conn.execute(
        """SELECT * FROM entries
           WHERE category = 'goal' AND status = 'active'
           ORDER BY priority DESC, created_at DESC""",
    ).fetchall()

    result = {
        "period": {"from": from_date, "to": to_date, "type": period_type},
        "entries": [_entry_to_dict(conn, row) for row in rows],
        "counts": {row["category"]: row["count"] for row in counts},
        "overdue": [_entry_to_dict(conn, row) for row in overdue],
        "upcoming_deadlines": [_entry_to_dict(conn, row) for row in upcoming],
        "active_goals": [_entry_to_dict(conn, row) for row in goals],
    }

    conn.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_list():
    """List all active entries."""
    conn = get_connection()
    ensure_schema(conn)
    rows = conn.execute(
        """SELECT * FROM entries WHERE status = 'active'
           ORDER BY COALESCE(entry_date, '9999-12-31') DESC, created_at DESC
           LIMIT 100"""
    ).fetchall()
    result = [_entry_to_dict(conn, row) for row in rows]
    conn.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main():
    if len(sys.argv) < 2:
        print("Usage: secretary.py <command> [args...]")
        print("Commands: init, store, store_batch, query, search, update, delete, summary, list")
        sys.exit(1)

    command = sys.argv[1]

    try:
        if command == "init":
            cmd_init()
        elif command == "store":
            cmd_store(sys.argv[2])
        elif command == "store_batch":
            cmd_store_batch(sys.argv[2])
        elif command == "query":
            cmd_query(sys.argv[2] if len(sys.argv) > 2 else "{}")
        elif command == "search":
            cmd_search(sys.argv[2])
        elif command == "update":
            cmd_update(sys.argv[2], sys.argv[3])
        elif command == "delete":
            cmd_delete(sys.argv[2])
        elif command == "summary":
            cmd_summary(sys.argv[2] if len(sys.argv) > 2 else '{"type": "today"}')
        elif command == "list":
            cmd_list()
        else:
            print(json.dumps({"status": "error", "message": f"Unknown command: {command}"}))
            sys.exit(1)
    except json.JSONDecodeError as e:
        print(json.dumps({"status": "error", "message": f"Invalid JSON: {e}"}))
        sys.exit(1)
    except KeyError as e:
        print(json.dumps({"status": "error", "message": f"Missing required field: {e}"}))
        sys.exit(1)
    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
