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


def parse_tags(tags_input):
    """Parse tags from string or list input."""
    if isinstance(tags_input, list):
        return [t.strip() for t in tags_input if t.strip()]
    if isinstance(tags_input, str) and tags_input.strip():
        return [t.strip() for t in tags_input.split(",") if t.strip()]
    return []
