"""Database connection, schema definitions, and shared helpers."""

import os
import sqlite3

DB_DIR = os.path.expanduser("~/.secretary")
DB_PATH = os.path.join(DB_DIR, "data.db")

SCHEMA_SQL = """
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
    status TEXT DEFAULT 'active',
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

CREATE TABLE IF NOT EXISTS tag_schemas (
    tag TEXT PRIMARY KEY,
    kind TEXT NOT NULL DEFAULT 'tag' CHECK(kind IN ('tag', 'type')),
    display_name TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    fields_schema TEXT NOT NULL DEFAULT '[]',
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT DEFAULT (datetime('now', 'localtime'))
);
"""

FTS_SQL = """
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


DEFAULT_COLLECTIONS = [
    {
        "name": "persons",
        "display_name": "人物",
        "description": "ユーザー（オーナー）と周囲の人々のプロフィール",
        "fields_schema": [
            {"name": "person_type", "type": "string", "description": "owner（ユーザー自身）または contact（連絡先）"},
            {"name": "relationship", "type": "string", "description": "関係性（上司、同僚、家族など）"},
            {"name": "organization", "type": "string", "description": "所属組織"},
            {"name": "role", "type": "string", "description": "役職"},
            {"name": "birthday", "type": "date", "description": "誕生日"},
            {"name": "email", "type": "string", "description": "メールアドレス"},
            {"name": "phone", "type": "string", "description": "電話番号"},
            {"name": "personality", "type": "string", "description": "性格特性"},
            {"name": "preferences", "type": "string", "description": "好み"},
            {"name": "communication_style", "type": "string", "description": "コミュニケーションスタイル"},
            {"name": "work_style", "type": "string", "description": "仕事のスタイル"},
            {"name": "last_contacted_at", "type": "date", "description": "最終連絡日"},
        ],
    },
    {
        "name": "events",
        "display_name": "イベント",
        "description": "起こった出来事や進行中の出来事",
        "fields_schema": [
            {"name": "event_date", "type": "date", "description": "イベントの日付"},
            {"name": "start_time", "type": "time", "description": "開始時刻 (HH:MM)"},
            {"name": "end_time", "type": "time", "description": "終了時刻 (HH:MM)"},
            {"name": "location", "type": "string", "description": "場所"},
            {"name": "source", "type": "string", "description": "情報の出所"},
            {"name": "related_persons", "type": "ref", "ref_collection": "persons", "multiple": True, "description": "関連人物のアイテムID"},
        ],
    },
    {
        "name": "plans",
        "display_name": "計画",
        "description": "将来の予定された活動",
        "fields_schema": [
            {"name": "planned_date", "type": "date", "description": "予定日"},
            {"name": "start_time", "type": "time", "description": "開始時刻 (HH:MM)"},
            {"name": "end_time", "type": "time", "description": "終了時刻 (HH:MM)"},
            {"name": "due_date", "type": "date", "description": "締め切り"},
            {"name": "priority", "type": "string", "description": "優先度 (high/medium/low)"},
            {"name": "location", "type": "string", "description": "場所"},
            {"name": "recurrence", "type": "string", "description": "繰り返しパターン (daily/weekly/monthly/yearly)"},
            {"name": "recurrence_until", "type": "date", "description": "繰り返し終了日"},
            {"name": "related_persons", "type": "ref", "ref_collection": "persons", "multiple": True, "description": "関連人物のアイテムID"},
        ],
    },
    {
        "name": "goals",
        "display_name": "目標",
        "description": "目標と抱負",
        "fields_schema": [
            {"name": "due_date", "type": "date", "description": "達成期限"},
            {"name": "priority", "type": "string", "description": "優先度 (high/medium/low)"},
            {"name": "progress", "type": "string", "description": "進捗状況"},
        ],
    },
    {
        "name": "tasks",
        "display_name": "タスク",
        "description": "実行すべきアクション項目",
        "fields_schema": [
            {"name": "due_date", "type": "date", "description": "締め切り"},
            {"name": "priority", "type": "string", "description": "優先度 (high/medium/low)"},
            {"name": "assignee", "type": "ref", "ref_collection": "persons", "description": "担当者のアイテムID"},
            {"name": "related_goal", "type": "ref", "ref_collection": "goals", "description": "関連目標のアイテムID"},
        ],
    },
    {
        "name": "decisions",
        "display_name": "決定事項",
        "description": "決定済みまたは保留中の決定事項",
        "fields_schema": [
            {"name": "decided_date", "type": "date", "description": "決定日"},
            {"name": "context", "type": "string", "description": "決定の背景"},
            {"name": "related_persons", "type": "ref", "ref_collection": "persons", "multiple": True, "description": "関係者のアイテムID"},
        ],
    },
    {
        "name": "notes",
        "display_name": "メモ",
        "description": "記憶しておく価値のある一般的な情報",
        "fields_schema": [
            {"name": "note_date", "type": "date", "description": "メモの日付"},
            {"name": "source", "type": "string", "description": "情報の出所"},
        ],
    },
]


def get_connection():
    """Get a database connection, creating the directory if needed."""
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _migrate_tag_schemas_kind(conn):
    """Add 'kind' column to tag_schemas if it doesn't exist (migration)."""
    cols = [row[1] for row in conn.execute("PRAGMA table_info(tag_schemas)").fetchall()]
    if "kind" not in cols:
        conn.execute("ALTER TABLE tag_schemas ADD COLUMN kind TEXT NOT NULL DEFAULT 'tag' CHECK(kind IN ('tag', 'type'))")


def ensure_schema(conn):
    """Ensure the database schema exists."""
    conn.executescript(SCHEMA_SQL)
    _migrate_tag_schemas_kind(conn)
    try:
        conn.executescript(FTS_SQL)
    except Exception:
        # FTS5 may not be available on all systems; degrade gracefully
        pass


def seed_default_collections(conn):
    """Insert default collections if they don't already exist."""
    import json as _json

    for col in DEFAULT_COLLECTIONS:
        existing = conn.execute(
            "SELECT id FROM collections WHERE name = ?", (col["name"],)
        ).fetchone()
        if existing:
            continue
        conn.execute(
            """INSERT INTO collections (name, display_name, description, fields_schema)
               VALUES (?, ?, ?, ?)""",
            (
                col["name"],
                col["display_name"],
                col["description"],
                _json.dumps(col["fields_schema"], ensure_ascii=False),
            ),
        )
    conn.commit()


def parse_tags(tags_input):
    """Parse tags from string or list input."""
    if isinstance(tags_input, list):
        return [t.strip() for t in tags_input if t.strip()]
    if isinstance(tags_input, str) and tags_input.strip():
        return [t.strip() for t in tags_input.split(",") if t.strip()]
    return []
