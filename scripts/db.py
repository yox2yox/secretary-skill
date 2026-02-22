"""Database connection, schema definitions, and shared helpers."""

import os
import sqlite3

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

CREATE TABLE IF NOT EXISTS tag_schemas (
    tag TEXT PRIMARY KEY,
    display_name TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    fields_schema TEXT NOT NULL DEFAULT '[]',
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT DEFAULT (datetime('now', 'localtime'))
);

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


def parse_tags(tags_input):
    """Parse tags from string or list input."""
    if isinstance(tags_input, list):
        return [t.strip() for t in tags_input if t.strip()]
    if isinstance(tags_input, str) and tags_input.strip():
        return [t.strip() for t in tags_input.split(",") if t.strip()]
    return []
