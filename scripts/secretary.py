#!/usr/bin/env python3
"""Secretary Skill - SQLite storage for personal information management.

Usage:
    python3 secretary.py <command> [args...]

Commands:
    init                                  Initialize the database
    store '<json>'                        Store a single entry
    store_batch '<json_array>'            Store multiple entries
    query '<json_filter>'                 Query entries with filters
    search '<keyword>'                    Full-text search entries
    update <id> '<json>'                  Update an entry
    delete <id>                           Delete an entry
    summary '<json>'                      Get a period summary
    list                                  List all active entries
    entry_link <entry_id> '<json>'        Link person(s) to an entry
    entry_unlink <entry_id> <person_id>   Unlink a person from an entry
    person_entries <person_id>            List entries linked to a person
    person_add '<json>'                   Add a new person
    person_update <id> '<json>'           Update a person
    person_delete <id>                    Delete a person
    person_get <id>                       Get a person with attributes
    person_list ['<json_filter>']         List persons
    person_search '<keyword>'             Search persons
    person_tag_add <person_id> <tag>      Add a tag to a person
    person_tag_remove <person_id> <tag>   Remove a tag from a person
    attr_set <person_id> '<json>'         Set attributes
    attr_delete <attr_id>                 Delete an attribute
    attr_list <person_id> [category]      List attributes
    tags_list [source]                    List all tags (entries|persons|items)
    col_create '<json>'                   Create a new collection
    col_list                              List all collections
    col_get <id>                          Get collection details
    col_update <id> '<json>'              Update a collection
    col_delete <id>                       Delete a collection
    item_add <col_id> '<json>'            Add item to a collection
    item_add_batch <col_id> '<json>'      Add multiple items
    item_get <id>                         Get item details
    item_update <id> '<json>'             Update an item
    item_delete <id>                      Delete an item
    item_list <col_id> ['<json_filter>']  List items in a collection
    item_search '<keyword>' [col_id]      Search items
    item_relate '<json>'                  Create a relation
    item_unrelate <id>                    Remove a relation
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
    category TEXT NOT NULL CHECK(category IN ('event', 'plan', 'goal', 'task', 'decision', 'note')),
    title TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    entry_date TEXT,
    start_time TEXT,
    end_time TEXT,
    due_date TEXT,
    status TEXT DEFAULT 'active' CHECK(status IN ('active', 'completed', 'cancelled', 'on_hold')),
    priority TEXT DEFAULT 'medium' CHECK(priority IN ('high', 'medium', 'low')),
    parent_id INTEGER REFERENCES entries(id) ON DELETE SET NULL,
    location TEXT DEFAULT '',
    url TEXT DEFAULT '',
    recurrence TEXT DEFAULT '',
    recurrence_until TEXT,
    source TEXT DEFAULT '',
    completed_at TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_entries_category ON entries(category);
CREATE INDEX IF NOT EXISTS idx_entries_entry_date ON entries(entry_date);
CREATE INDEX IF NOT EXISTS idx_entries_status ON entries(status);
CREATE INDEX IF NOT EXISTS idx_entries_due_date ON entries(due_date);
CREATE INDEX IF NOT EXISTS idx_entries_created_at ON entries(created_at);
CREATE INDEX IF NOT EXISTS idx_entries_parent_id ON entries(parent_id);
CREATE INDEX IF NOT EXISTS idx_entries_category_status ON entries(category, status);
CREATE INDEX IF NOT EXISTS idx_entries_status_due_date ON entries(status, due_date);

CREATE TABLE IF NOT EXISTS entry_tags (
    entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
    tag TEXT NOT NULL,
    PRIMARY KEY (entry_id, tag)
);
CREATE INDEX IF NOT EXISTS idx_entry_tags_tag ON entry_tags(tag);

CREATE TABLE IF NOT EXISTS persons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_type TEXT NOT NULL DEFAULT 'contact' CHECK(person_type IN ('owner', 'contact')),
    name TEXT NOT NULL,
    relationship TEXT DEFAULT '',
    organization TEXT DEFAULT '',
    role TEXT DEFAULT '',
    birthday TEXT,
    notes TEXT DEFAULT '',
    last_contacted_at TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_persons_person_type ON persons(person_type);
CREATE INDEX IF NOT EXISTS idx_persons_name ON persons(name);

CREATE TABLE IF NOT EXISTS entry_persons (
    entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
    person_id INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    role TEXT DEFAULT '',
    PRIMARY KEY (entry_id, person_id)
);
CREATE INDEX IF NOT EXISTS idx_entry_persons_person_id ON entry_persons(person_id);

CREATE TABLE IF NOT EXISTS person_attributes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER NOT NULL,
    category TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (person_id) REFERENCES persons(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_person_attributes_person_id ON person_attributes(person_id);
CREATE INDEX IF NOT EXISTS idx_person_attributes_category ON person_attributes(category);
CREATE UNIQUE INDEX IF NOT EXISTS idx_person_attributes_unique ON person_attributes(person_id, category, key);

CREATE TABLE IF NOT EXISTS person_tags (
    person_id INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    tag TEXT NOT NULL,
    PRIMARY KEY (person_id, tag)
);
CREATE INDEX IF NOT EXISTS idx_person_tags_tag ON person_tags(tag);

CREATE TABLE IF NOT EXISTS collections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    fields_schema TEXT NOT NULL DEFAULT '[]',
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_collections_name ON collections(name);

CREATE TABLE IF NOT EXISTS collection_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    collection_id INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    data TEXT NOT NULL DEFAULT '{}',
    parent_id INTEGER REFERENCES collection_items(id) ON DELETE SET NULL,
    status TEXT DEFAULT 'active' CHECK(status IN ('active', 'archived', 'draft')),
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_collection_items_collection_id ON collection_items(collection_id);
CREATE INDEX IF NOT EXISTS idx_collection_items_parent_id ON collection_items(parent_id);
CREATE INDEX IF NOT EXISTS idx_collection_items_status ON collection_items(status);
CREATE INDEX IF NOT EXISTS idx_collection_items_collection_status ON collection_items(collection_id, status);

CREATE TABLE IF NOT EXISTS collection_item_tags (
    item_id INTEGER NOT NULL REFERENCES collection_items(id) ON DELETE CASCADE,
    tag TEXT NOT NULL,
    PRIMARY KEY (item_id, tag)
);
CREATE INDEX IF NOT EXISTS idx_collection_item_tags_tag ON collection_item_tags(tag);

CREATE TABLE IF NOT EXISTS collection_item_relations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL REFERENCES collection_items(id) ON DELETE CASCADE,
    related_item_id INTEGER REFERENCES collection_items(id) ON DELETE CASCADE,
    related_entry_id INTEGER REFERENCES entries(id) ON DELETE CASCADE,
    related_person_id INTEGER REFERENCES persons(id) ON DELETE CASCADE,
    relation_type TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_cir_item_id ON collection_item_relations(item_id);
CREATE INDEX IF NOT EXISTS idx_cir_related_item_id ON collection_item_relations(related_item_id);
CREATE INDEX IF NOT EXISTS idx_cir_related_entry_id ON collection_item_relations(related_entry_id);
CREATE INDEX IF NOT EXISTS idx_cir_related_person_id ON collection_item_relations(related_person_id);
"""

FTS_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(
    title, content,
    content=entries, content_rowid=id,
    tokenize='trigram'
);

CREATE TRIGGER IF NOT EXISTS entries_fts_ai AFTER INSERT ON entries BEGIN
    INSERT INTO entries_fts(rowid, title, content) VALUES (new.id, new.title, new.content);
END;
CREATE TRIGGER IF NOT EXISTS entries_fts_ad AFTER DELETE ON entries BEGIN
    INSERT INTO entries_fts(entries_fts, rowid, title, content) VALUES('delete', old.id, old.title, old.content);
END;
CREATE TRIGGER IF NOT EXISTS entries_fts_au AFTER UPDATE ON entries BEGIN
    INSERT INTO entries_fts(entries_fts, rowid, title, content) VALUES('delete', old.id, old.title, old.content);
    INSERT INTO entries_fts(rowid, title, content) VALUES (new.id, new.title, new.content);
END;

CREATE VIRTUAL TABLE IF NOT EXISTS persons_fts USING fts5(
    name, organization, role, notes,
    content=persons, content_rowid=id,
    tokenize='trigram'
);

CREATE TRIGGER IF NOT EXISTS persons_fts_ai AFTER INSERT ON persons BEGIN
    INSERT INTO persons_fts(rowid, name, organization, role, notes) VALUES (new.id, new.name, new.organization, new.role, new.notes);
END;
CREATE TRIGGER IF NOT EXISTS persons_fts_ad AFTER DELETE ON persons BEGIN
    INSERT INTO persons_fts(persons_fts, rowid, name, organization, role, notes) VALUES('delete', old.id, old.name, old.organization, old.role, old.notes);
END;
CREATE TRIGGER IF NOT EXISTS persons_fts_au AFTER UPDATE ON persons BEGIN
    INSERT INTO persons_fts(persons_fts, rowid, name, organization, role, notes) VALUES('delete', old.id, old.name, old.organization, old.role, old.notes);
    INSERT INTO persons_fts(rowid, name, organization, role, notes) VALUES (new.id, new.name, new.organization, new.role, new.notes);
END;

CREATE VIRTUAL TABLE IF NOT EXISTS collection_items_fts USING fts5(
    title, content, data,
    content=collection_items, content_rowid=id,
    tokenize='trigram'
);

CREATE TRIGGER IF NOT EXISTS collection_items_fts_ai AFTER INSERT ON collection_items BEGIN
    INSERT INTO collection_items_fts(rowid, title, content, data) VALUES (new.id, new.title, new.content, new.data);
END;
CREATE TRIGGER IF NOT EXISTS collection_items_fts_ad AFTER DELETE ON collection_items BEGIN
    INSERT INTO collection_items_fts(collection_items_fts, rowid, title, content, data) VALUES('delete', old.id, old.title, old.content, old.data);
END;
CREATE TRIGGER IF NOT EXISTS collection_items_fts_au AFTER UPDATE ON collection_items BEGIN
    INSERT INTO collection_items_fts(collection_items_fts, rowid, title, content, data) VALUES('delete', old.id, old.title, old.content, old.data);
    INSERT INTO collection_items_fts(rowid, title, content, data) VALUES (new.id, new.title, new.content, new.data);
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
        conn.executescript(FTS_SQL)
    except Exception:
        # FTS5 may not be available on all systems; degrade gracefully
        pass


## ── Helper functions ──────────────────────────────────────────────────


def _parse_tags(tags_input):
    """Parse tags from string or list input."""
    if isinstance(tags_input, list):
        return [t.strip() for t in tags_input if t.strip()]
    if isinstance(tags_input, str) and tags_input.strip():
        return [t.strip() for t in tags_input.split(",") if t.strip()]
    return []


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


## ── Entry commands ────────────────────────────────────────────────────


def cmd_init():
    """Initialize the database."""
    conn = get_connection()
    ensure_schema(conn)
    conn.close()
    print(json.dumps({"status": "ok", "message": "Database initialized", "path": DB_PATH}))


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

    tags = _parse_tags(data.get("tags", ""))
    _save_entry_tags(conn, entry_id, tags)

    if "person_ids" in data:
        _save_entry_persons(conn, entry_id, data["person_ids"])

    return entry_id


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
        tags = _parse_tags(updates["tags"])
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
    tags = _parse_tags(data.get("tags", ""))
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


## ── Tag listing command ──────────────────────────────────────────────


def cmd_tags_list(source=None):
    """List all unique tags across all tables with usage counts.

    Optional source filter: 'entries', 'persons', 'items', or None for all.
    """
    conn = get_connection()
    ensure_schema(conn)

    queries = []
    params = []

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

    # Aggregate by tag
    tag_data = {}
    for row in all_rows:
        tag = row["tag"]
        if tag not in tag_data:
            tag_data[tag] = {"tag": tag, "total_count": 0, "sources": {}}
        tag_data[tag]["total_count"] += row["count"]
        tag_data[tag]["sources"][row["source"]] = row["count"]

    result = sorted(tag_data.values(), key=lambda x: (-x["total_count"], x["tag"]))

    conn.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


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


## ── Collection commands ──────────────────────────────────────────────


def cmd_col_create(data_json):
    """Create a new collection."""
    data = json.loads(data_json)
    conn = get_connection()
    ensure_schema(conn)

    fields_schema = data.get("fields_schema", [])
    if isinstance(fields_schema, list):
        fields_schema = json.dumps(fields_schema, ensure_ascii=False)

    cursor = conn.execute(
        """INSERT INTO collections (name, display_name, description, fields_schema)
           VALUES (?, ?, ?, ?)""",
        (
            data["name"],
            data.get("display_name", data["name"]),
            data.get("description", ""),
            fields_schema,
        ),
    )
    col_id = cursor.lastrowid
    conn.commit()
    conn.close()
    print(json.dumps({"status": "ok", "id": col_id}))


def cmd_col_list():
    """List all collections with item counts."""
    conn = get_connection()
    ensure_schema(conn)

    rows = conn.execute(
        """SELECT c.*, COUNT(ci.id) as item_count
           FROM collections c
           LEFT JOIN collection_items ci ON c.id = ci.collection_id
           GROUP BY c.id
           ORDER BY c.name"""
    ).fetchall()

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


def cmd_col_get(col_id):
    """Get a collection with its schema and item count."""
    conn = get_connection()
    ensure_schema(conn)

    row = conn.execute(
        """SELECT c.*, COUNT(ci.id) as item_count
           FROM collections c
           LEFT JOIN collection_items ci ON c.id = ci.collection_id
           WHERE c.id = ?
           GROUP BY c.id""",
        (int(col_id),),
    ).fetchone()

    if not row:
        conn.close()
        print(json.dumps({"status": "error", "message": "Collection not found"}))
        return

    d = dict(row)
    try:
        d["fields_schema"] = json.loads(d["fields_schema"])
    except (json.JSONDecodeError, TypeError):
        d["fields_schema"] = []

    conn.close()
    print(json.dumps(d, ensure_ascii=False, indent=2))


def cmd_col_update(col_id, update_json):
    """Update collection metadata."""
    updates = json.loads(update_json)
    conn = get_connection()
    ensure_schema(conn)

    set_clauses = []
    params = []
    for field in ("name", "display_name", "description"):
        if field in updates:
            set_clauses.append(f"{field} = ?")
            params.append(updates[field])
    if "fields_schema" in updates:
        fs = updates["fields_schema"]
        if isinstance(fs, list):
            fs = json.dumps(fs, ensure_ascii=False)
        set_clauses.append("fields_schema = ?")
        params.append(fs)

    if not set_clauses:
        print(json.dumps({"status": "error", "message": "No valid fields to update"}))
        return

    set_clauses.append("updated_at = datetime('now', 'localtime')")
    params.append(int(col_id))
    conn.execute(f"UPDATE collections SET {', '.join(set_clauses)} WHERE id = ?", params)
    conn.commit()
    conn.close()
    print(json.dumps({"status": "ok", "id": int(col_id)}))


def cmd_col_delete(col_id):
    """Delete a collection and all its items (cascades)."""
    conn = get_connection()
    ensure_schema(conn)
    conn.execute("DELETE FROM collections WHERE id = ?", (int(col_id),))
    conn.commit()
    conn.close()
    print(json.dumps({"status": "ok", "id": int(col_id)}))


## ── Collection item commands ─────────────────────────────────────────


def _save_item_tags(conn, item_id, tags):
    """Save tags for a collection item."""
    for tag in tags:
        conn.execute(
            "INSERT OR IGNORE INTO collection_item_tags (item_id, tag) VALUES (?, ?)",
            (item_id, tag),
        )


def _enrich_items(conn, items):
    """Add tags and relations to item dicts (batch)."""
    if not items:
        return items

    item_ids = [i["id"] for i in items]
    placeholders = ",".join("?" for _ in item_ids)

    # Parse data JSON
    for item in items:
        try:
            item["data"] = json.loads(item["data"]) if isinstance(item["data"], str) else item["data"]
        except (json.JSONDecodeError, TypeError):
            item["data"] = {}

    # Tags
    tag_rows = conn.execute(
        f"SELECT item_id, tag FROM collection_item_tags WHERE item_id IN ({placeholders}) ORDER BY item_id, tag",
        item_ids,
    ).fetchall()
    tags_map = {}
    for row in tag_rows:
        tags_map.setdefault(row["item_id"], []).append(row["tag"])

    # Relations
    rel_rows = conn.execute(
        f"""SELECT r.*, ci.title as related_item_title, e.title as related_entry_title, p.name as related_person_name
            FROM collection_item_relations r
            LEFT JOIN collection_items ci ON r.related_item_id = ci.id
            LEFT JOIN entries e ON r.related_entry_id = e.id
            LEFT JOIN persons p ON r.related_person_id = p.id
            WHERE r.item_id IN ({placeholders})
            ORDER BY r.item_id""",
        item_ids,
    ).fetchall()
    rels_map = {}
    for row in rel_rows:
        rels_map.setdefault(row["item_id"], []).append(dict(row))

    for item in items:
        item["tags"] = tags_map.get(item["id"], [])
        item["relations"] = rels_map.get(item["id"], [])

    return items


def _insert_item(conn, collection_id, data):
    """Insert a single collection item and return its ID."""
    item_data = data.get("data", {})
    if isinstance(item_data, dict):
        item_data = json.dumps(item_data, ensure_ascii=False)

    cursor = conn.execute(
        """INSERT INTO collection_items (collection_id, title, content, data, parent_id, status)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            int(collection_id),
            data["title"],
            data.get("content", ""),
            item_data,
            data.get("parent_id"),
            data.get("status", "active"),
        ),
    )
    item_id = cursor.lastrowid

    tags = _parse_tags(data.get("tags", ""))
    _save_item_tags(conn, item_id, tags)

    return item_id


def cmd_item_add(collection_id, data_json):
    """Add a single item to a collection."""
    data = json.loads(data_json)
    conn = get_connection()
    ensure_schema(conn)

    item_id = _insert_item(conn, collection_id, data)

    conn.commit()
    conn.close()
    print(json.dumps({"status": "ok", "id": item_id}))


def cmd_item_add_batch(collection_id, data_json):
    """Add multiple items to a collection."""
    items = json.loads(data_json)
    conn = get_connection()
    ensure_schema(conn)

    ids = []
    for data in items:
        ids.append(_insert_item(conn, collection_id, data))

    conn.commit()
    conn.close()
    print(json.dumps({"status": "ok", "ids": ids, "count": len(ids)}))


def cmd_item_get(item_id):
    """Get a single item with all details."""
    conn = get_connection()
    ensure_schema(conn)

    row = conn.execute(
        """SELECT ci.*, c.name as collection_name, c.display_name as collection_display_name
           FROM collection_items ci
           JOIN collections c ON ci.collection_id = c.id
           WHERE ci.id = ?""",
        (int(item_id),),
    ).fetchone()

    if not row:
        conn.close()
        print(json.dumps({"status": "error", "message": "Item not found"}))
        return

    item = dict(row)
    _enrich_items(conn, [item])

    # Include children if any
    children_rows = conn.execute(
        "SELECT * FROM collection_items WHERE parent_id = ? ORDER BY title",
        (int(item_id),),
    ).fetchall()
    children = [dict(r) for r in children_rows]
    if children:
        _enrich_items(conn, children)
    item["children"] = children

    conn.close()
    print(json.dumps(item, ensure_ascii=False, indent=2))


def cmd_item_update(item_id, update_json):
    """Update a collection item."""
    updates = json.loads(update_json)
    conn = get_connection()
    ensure_schema(conn)

    set_clauses = []
    params = []

    for field in ("title", "content", "parent_id", "status"):
        if field in updates:
            set_clauses.append(f"{field} = ?")
            params.append(updates[field])

    if "data" in updates:
        d = updates["data"]
        if isinstance(d, dict):
            # Merge with existing data
            row = conn.execute(
                "SELECT data FROM collection_items WHERE id = ?", (int(item_id),)
            ).fetchone()
            if row:
                try:
                    existing = json.loads(row["data"]) if isinstance(row["data"], str) else row["data"]
                except (json.JSONDecodeError, TypeError):
                    existing = {}
                existing.update(d)
                d = existing
            d = json.dumps(d, ensure_ascii=False)
        set_clauses.append("data = ?")
        params.append(d)

    has_field_updates = bool(set_clauses)
    has_tags = "tags" in updates

    if not has_field_updates and not has_tags:
        print(json.dumps({"status": "error", "message": "No valid fields to update"}))
        return

    if has_field_updates:
        set_clauses.append("updated_at = datetime('now', 'localtime')")
        params.append(int(item_id))
        conn.execute(
            f"UPDATE collection_items SET {', '.join(set_clauses)} WHERE id = ?",
            params,
        )

    if has_tags:
        conn.execute("DELETE FROM collection_item_tags WHERE item_id = ?", (int(item_id),))
        tags = _parse_tags(updates["tags"])
        _save_item_tags(conn, int(item_id), tags)

    conn.commit()
    conn.close()
    print(json.dumps({"status": "ok", "id": int(item_id)}))


def cmd_item_delete(item_id):
    """Delete a collection item."""
    conn = get_connection()
    ensure_schema(conn)
    conn.execute("DELETE FROM collection_items WHERE id = ?", (int(item_id),))
    conn.commit()
    conn.close()
    print(json.dumps({"status": "ok", "id": int(item_id)}))


def cmd_item_list(collection_id, filter_json=None):
    """List items in a collection with optional filters."""
    filters = json.loads(filter_json) if filter_json else {}
    conn = get_connection()
    ensure_schema(conn)

    where_clauses = ["ci.collection_id = ?"]
    params = [int(collection_id)]

    if "status" in filters:
        where_clauses.append("ci.status = ?")
        params.append(filters["status"])
    if "parent_id" in filters:
        if filters["parent_id"] is None:
            where_clauses.append("ci.parent_id IS NULL")
        else:
            where_clauses.append("ci.parent_id = ?")
            params.append(int(filters["parent_id"]))
    if "tag" in filters:
        where_clauses.append(
            "EXISTS (SELECT 1 FROM collection_item_tags t WHERE t.item_id = ci.id AND t.tag = ?)"
        )
        params.append(filters["tag"])

    where = " AND ".join(where_clauses)
    limit = filters.get("limit", 100)

    rows = conn.execute(
        f"""SELECT ci.* FROM collection_items ci
            WHERE {where}
            ORDER BY ci.title
            LIMIT ?""",
        params + [limit],
    ).fetchall()

    result = [dict(row) for row in rows]
    _enrich_items(conn, result)

    conn.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _search_items_like(conn, keyword, collection_id=None):
    """Search collection items using LIKE (fallback)."""
    pattern = f"%{keyword}%"
    if collection_id:
        return conn.execute(
            """SELECT ci.*, c.name as collection_name, c.display_name as collection_display_name
               FROM collection_items ci JOIN collections c ON ci.collection_id = c.id
               WHERE ci.collection_id = ? AND (ci.title LIKE ? OR ci.content LIKE ? OR ci.data LIKE ?)
               ORDER BY ci.title LIMIT 50""",
            (int(collection_id), pattern, pattern, pattern),
        ).fetchall()
    return conn.execute(
        """SELECT ci.*, c.name as collection_name, c.display_name as collection_display_name
           FROM collection_items ci JOIN collections c ON ci.collection_id = c.id
           WHERE ci.title LIKE ? OR ci.content LIKE ? OR ci.data LIKE ?
           ORDER BY ci.title LIMIT 50""",
        (pattern, pattern, pattern),
    ).fetchall()


def cmd_item_search(keyword, collection_id=None):
    """Search items across collections (or within one) using FTS5 with LIKE fallback."""
    conn = get_connection()
    ensure_schema(conn)

    rows = []
    try:
        if collection_id:
            rows = conn.execute(
                """SELECT ci.*, c.name as collection_name, c.display_name as collection_display_name
                   FROM collection_items_fts fts
                   JOIN collection_items ci ON ci.id = fts.rowid
                   JOIN collections c ON ci.collection_id = c.id
                   WHERE collection_items_fts MATCH ? AND ci.collection_id = ?
                   ORDER BY rank LIMIT 50""",
                (keyword, int(collection_id)),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT ci.*, c.name as collection_name, c.display_name as collection_display_name
                   FROM collection_items_fts fts
                   JOIN collection_items ci ON ci.id = fts.rowid
                   JOIN collections c ON ci.collection_id = c.id
                   WHERE collection_items_fts MATCH ?
                   ORDER BY rank LIMIT 50""",
                (keyword,),
            ).fetchall()
    except Exception:
        pass

    if not rows:
        rows = _search_items_like(conn, keyword, collection_id)

    result = [dict(row) for row in rows]
    _enrich_items(conn, result)

    conn.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


## ── Collection item relation commands ────────────────────────────────


def cmd_item_relate(data_json):
    """Create a relation from a collection item to another item, entry, or person."""
    data = json.loads(data_json)
    conn = get_connection()
    ensure_schema(conn)

    cursor = conn.execute(
        """INSERT INTO collection_item_relations
           (item_id, related_item_id, related_entry_id, related_person_id, relation_type)
           VALUES (?, ?, ?, ?, ?)""",
        (
            int(data["item_id"]),
            data.get("related_item_id"),
            data.get("related_entry_id"),
            data.get("related_person_id"),
            data["relation_type"],
        ),
    )
    rel_id = cursor.lastrowid
    conn.commit()
    conn.close()
    print(json.dumps({"status": "ok", "id": rel_id}))


def cmd_item_unrelate(relation_id):
    """Remove a relation."""
    conn = get_connection()
    ensure_schema(conn)
    conn.execute("DELETE FROM collection_item_relations WHERE id = ?", (int(relation_id),))
    conn.commit()
    conn.close()
    print(json.dumps({"status": "ok", "id": int(relation_id)}))


## ── Main ──────────────────────────────────────────────────────────────


def main():
    if len(sys.argv) < 2:
        print("Usage: secretary.py <command> [args...]")
        print("Commands: init, store, store_batch, query, search, update, delete, summary, list,")
        print("         entry_link, entry_unlink, person_entries,")
        print("         person_add, person_update, person_delete, person_get, person_list,")
        print("         person_search, person_tag_add, person_tag_remove,")
        print("         attr_set, attr_delete, attr_list, tags_list,")
        print("         col_create, col_list, col_get, col_update, col_delete,")
        print("         item_add, item_add_batch, item_get, item_update, item_delete,")
        print("         item_list, item_search, item_relate, item_unrelate")
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
        # Entry-person link commands
        elif command == "entry_link":
            cmd_entry_link(sys.argv[2], sys.argv[3])
        elif command == "entry_unlink":
            cmd_entry_unlink(sys.argv[2], sys.argv[3])
        elif command == "person_entries":
            cmd_person_entries(sys.argv[2])
        # Person commands
        elif command == "person_add":
            cmd_person_add(sys.argv[2])
        elif command == "person_update":
            cmd_person_update(sys.argv[2], sys.argv[3])
        elif command == "person_delete":
            cmd_person_delete(sys.argv[2])
        elif command == "person_get":
            cmd_person_get(sys.argv[2])
        elif command == "person_list":
            cmd_person_list(sys.argv[2] if len(sys.argv) > 2 else None)
        elif command == "person_search":
            cmd_person_search(sys.argv[2])
        # Person tag commands
        elif command == "person_tag_add":
            cmd_person_tag_add(sys.argv[2], sys.argv[3])
        elif command == "person_tag_remove":
            cmd_person_tag_remove(sys.argv[2], sys.argv[3])
        # Attribute commands
        elif command == "attr_set":
            cmd_attr_set(sys.argv[2], sys.argv[3])
        elif command == "attr_delete":
            cmd_attr_delete(sys.argv[2])
        elif command == "attr_list":
            cmd_attr_list(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
        # Tag listing
        elif command == "tags_list":
            cmd_tags_list(sys.argv[2] if len(sys.argv) > 2 else None)
        # Collection commands
        elif command == "col_create":
            cmd_col_create(sys.argv[2])
        elif command == "col_list":
            cmd_col_list()
        elif command == "col_get":
            cmd_col_get(sys.argv[2])
        elif command == "col_update":
            cmd_col_update(sys.argv[2], sys.argv[3])
        elif command == "col_delete":
            cmd_col_delete(sys.argv[2])
        # Collection item commands
        elif command == "item_add":
            cmd_item_add(sys.argv[2], sys.argv[3])
        elif command == "item_add_batch":
            cmd_item_add_batch(sys.argv[2], sys.argv[3])
        elif command == "item_get":
            cmd_item_get(sys.argv[2])
        elif command == "item_update":
            cmd_item_update(sys.argv[2], sys.argv[3])
        elif command == "item_delete":
            cmd_item_delete(sys.argv[2])
        elif command == "item_list":
            cmd_item_list(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
        elif command == "item_search":
            cmd_item_search(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
        # Collection item relation commands
        elif command == "item_relate":
            cmd_item_relate(sys.argv[2])
        elif command == "item_unrelate":
            cmd_item_unrelate(sys.argv[2])
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
