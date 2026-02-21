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

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    tags TEXT DEFAULT '',
    entry_date TEXT,
    due_date TEXT,
    status TEXT DEFAULT 'active',
    priority TEXT DEFAULT 'medium',
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_entries_category ON entries(category);
CREATE INDEX IF NOT EXISTS idx_entries_entry_date ON entries(entry_date);
CREATE INDEX IF NOT EXISTS idx_entries_status ON entries(status);
CREATE INDEX IF NOT EXISTS idx_entries_due_date ON entries(due_date);
CREATE INDEX IF NOT EXISTS idx_entries_created_at ON entries(created_at);
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

    cursor = conn.execute(
        """INSERT INTO entries (category, title, content, tags, entry_date, due_date, status, priority)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            data.get("category", "note"),
            data["title"],
            data.get("content", ""),
            data.get("tags", ""),
            data.get("entry_date"),
            data.get("due_date"),
            data.get("status", "active"),
            data.get("priority", "medium"),
        ),
    )
    conn.commit()
    entry_id = cursor.lastrowid
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
            """INSERT INTO entries (category, title, content, tags, entry_date, due_date, status, priority)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                data.get("category", "note"),
                data["title"],
                data.get("content", ""),
                data.get("tags", ""),
                data.get("entry_date"),
                data.get("due_date"),
                data.get("status", "active"),
                data.get("priority", "medium"),
            ),
        )
        ids.append(cursor.lastrowid)

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
        where_clauses.append("category = ?")
        params.append(filters["category"])
    if "status" in filters:
        where_clauses.append("status = ?")
        params.append(filters["status"])
    if "from_date" in filters:
        where_clauses.append("(entry_date >= ? OR due_date >= ?)")
        params.extend([filters["from_date"], filters["from_date"]])
    if "to_date" in filters:
        where_clauses.append("(entry_date <= ? OR due_date <= ?)")
        params.extend([filters["to_date"], filters["to_date"]])
    if "priority" in filters:
        where_clauses.append("priority = ?")
        params.append(filters["priority"])
    if "tags" in filters:
        where_clauses.append("(',' || tags || ',' LIKE '%,' || ? || ',%')")
        params.append(filters["tags"])
    if "id" in filters:
        where_clauses.append("id = ?")
        params.append(int(filters["id"]))

    where = " AND ".join(where_clauses) if where_clauses else "1=1"
    limit = filters.get("limit", 50)

    rows = conn.execute(
        f"SELECT * FROM entries WHERE {where} ORDER BY entry_date DESC, created_at DESC LIMIT ?",
        params + [limit],
    ).fetchall()

    result = [dict(row) for row in rows]
    conn.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_search(keyword):
    """Full-text search across title, content, and tags."""
    conn = get_connection()
    ensure_schema(conn)

    rows = conn.execute(
        """SELECT * FROM entries
           WHERE title LIKE ? OR content LIKE ? OR tags LIKE ?
           ORDER BY entry_date DESC, created_at DESC LIMIT 50""",
        (f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"),
    ).fetchall()

    result = [dict(row) for row in rows]
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
        "category", "title", "content", "tags",
        "entry_date", "due_date", "status", "priority",
    ]
    for field in allowed_fields:
        if field in updates:
            set_clauses.append(f"{field} = ?")
            params.append(updates[field])

    if not set_clauses:
        print(json.dumps({"status": "error", "message": "No valid fields to update"}))
        return

    set_clauses.append("updated_at = datetime('now', 'localtime')")
    params.append(int(entry_id))

    conn.execute(
        f"UPDATE entries SET {', '.join(set_clauses)} WHERE id = ?",
        params,
    )
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
           ORDER BY category, entry_date, priority DESC""",
        (from_date, to_date, from_date, to_date),
    ).fetchall()

    # Get counts by category
    counts = conn.execute(
        """SELECT category, COUNT(*) as count FROM entries
           WHERE (entry_date BETWEEN ? AND ?) OR (due_date BETWEEN ? AND ?)
           GROUP BY category""",
        (from_date, to_date, from_date, to_date),
    ).fetchall()

    # Get overdue items
    overdue = conn.execute(
        """SELECT * FROM entries
           WHERE due_date < ? AND status = 'active'
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
        "entries": [dict(row) for row in rows],
        "counts": {row["category"]: row["count"] for row in counts},
        "overdue": [dict(row) for row in overdue],
        "upcoming_deadlines": [dict(row) for row in upcoming],
        "active_goals": [dict(row) for row in goals],
    }

    conn.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_list():
    """List all active entries."""
    conn = get_connection()
    ensure_schema(conn)
    rows = conn.execute(
        "SELECT * FROM entries WHERE status = 'active' ORDER BY entry_date DESC, created_at DESC LIMIT 100"
    ).fetchall()
    result = [dict(row) for row in rows]
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
