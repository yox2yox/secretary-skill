"""Database connection, schema definitions, and shared helpers."""

import os
import sqlite3

DB_DIR = os.path.expanduser("~/.secretary")
DB_PATH = os.path.join(DB_DIR, "data.db")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS types (
    name TEXT PRIMARY KEY,
    display_name TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    parent_type TEXT REFERENCES types(name) ON DELETE SET NULL,
    abstract INTEGER NOT NULL DEFAULT 0,
    fields_schema TEXT NOT NULL DEFAULT '[]',
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_types_parent_type ON types(parent_type);

CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT REFERENCES types(name) ON DELETE SET NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    data TEXT NOT NULL DEFAULT '{}',
    parent_id INTEGER REFERENCES items(id) ON DELETE SET NULL,
    status TEXT DEFAULT 'active',
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_items_type ON items(type);
CREATE INDEX IF NOT EXISTS idx_items_parent_id ON items(parent_id);
CREATE INDEX IF NOT EXISTS idx_items_status ON items(status);
CREATE INDEX IF NOT EXISTS idx_items_type_status ON items(type, status);

CREATE TABLE IF NOT EXISTS item_relations (
    item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    related_item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    field_name TEXT NOT NULL,
    PRIMARY KEY (item_id, related_item_id, field_name)
);
CREATE INDEX IF NOT EXISTS idx_item_relations_item ON item_relations(item_id);
CREATE INDEX IF NOT EXISTS idx_item_relations_related ON item_relations(related_item_id);
"""

FTS_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS items_fts USING fts5(
    title, content, data,
    content=items, content_rowid=id,
    tokenize='trigram'
);

CREATE TRIGGER IF NOT EXISTS items_fts_ai AFTER INSERT ON items BEGIN
    INSERT INTO items_fts(rowid, title, content, data) VALUES (new.id, new.title, new.content, new.data);
END;
CREATE TRIGGER IF NOT EXISTS items_fts_ad AFTER DELETE ON items BEGIN
    INSERT INTO items_fts(items_fts, rowid, title, content, data) VALUES('delete', old.id, old.title, old.content, old.data);
END;
CREATE TRIGGER IF NOT EXISTS items_fts_au AFTER UPDATE ON items BEGIN
    INSERT INTO items_fts(items_fts, rowid, title, content, data) VALUES('delete', old.id, old.title, old.content, old.data);
    INSERT INTO items_fts(rowid, title, content, data) VALUES (new.id, new.title, new.content, new.data);
END;
"""


DEFAULT_TYPES = [
    {
        "name": "person",
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
        "name": "event",
        "display_name": "イベント",
        "description": "起こった出来事や進行中の出来事",
        "fields_schema": [
            {"name": "event_date", "type": "date", "description": "イベントの日付"},
            {"name": "start_time", "type": "time", "description": "開始時刻 (HH:MM)"},
            {"name": "end_time", "type": "time", "description": "終了時刻 (HH:MM)"},
            {"name": "location", "type": "string", "description": "場所"},
            {"name": "source", "type": "string", "description": "情報の出所"},
            {"name": "related_persons", "type": "ref", "ref_type": "person", "multiple": True, "description": "関連人物のアイテムID"},
        ],
    },
    {
        "name": "plan",
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
            {"name": "related_persons", "type": "ref", "ref_type": "person", "multiple": True, "description": "関連人物のアイテムID"},
        ],
    },
    {
        "name": "goal",
        "display_name": "目標",
        "description": "目標と抱負",
        "fields_schema": [
            {"name": "due_date", "type": "date", "description": "達成期限"},
            {"name": "priority", "type": "string", "description": "優先度 (high/medium/low)"},
            {"name": "progress", "type": "string", "description": "進捗状況"},
        ],
    },
    {
        "name": "task",
        "display_name": "タスク",
        "description": "実行すべきアクション項目",
        "fields_schema": [
            {"name": "due_date", "type": "date", "description": "締め切り"},
            {"name": "priority", "type": "string", "description": "優先度 (high/medium/low)"},
            {"name": "assignee", "type": "ref", "ref_type": "person", "description": "担当者のアイテムID"},
            {"name": "related_goal", "type": "ref", "ref_type": "goal", "description": "関連目標のアイテムID"},
        ],
    },
    {
        "name": "decision",
        "display_name": "決定事項",
        "description": "決定済みまたは保留中の決定事項",
        "fields_schema": [
            {"name": "decided_date", "type": "date", "description": "決定日"},
            {"name": "context", "type": "string", "description": "決定の背景"},
            {"name": "related_persons", "type": "ref", "ref_type": "person", "multiple": True, "description": "関係者のアイテムID"},
        ],
    },
    {
        "name": "note",
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


def get_ref_fields(conn, type_name):
    """Return a dict of ref field definitions for the given type.

    Keys are field names, values are dicts with 'ref_type' and 'multiple'.
    Uses resolved fields (including inherited ones).
    """
    if not type_name:
        return {}
    fields = get_resolved_fields(conn, type_name)
    return {
        f["name"]: {"ref_type": f.get("ref_type", ""), "multiple": f.get("multiple", False)}
        for f in fields
        if f.get("type") == "ref"
    }


def _migrate(conn):
    """Run all necessary migrations for existing databases."""
    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}

    # --- Legacy migration: tag_schemas -> types ---
    if "tag_schemas" in tables and "types" not in tables:
        conn.execute(
            """CREATE TABLE types (
                name TEXT PRIMARY KEY,
                display_name TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                parent_type TEXT REFERENCES types(name) ON DELETE SET NULL,
                abstract INTEGER NOT NULL DEFAULT 0,
                fields_schema TEXT NOT NULL DEFAULT '[]',
                created_at TEXT DEFAULT (datetime('now', 'localtime')),
                updated_at TEXT DEFAULT (datetime('now', 'localtime'))
            )"""
        )
        conn.execute(
            """INSERT INTO types (name, display_name, description, fields_schema, created_at, updated_at)
               SELECT tag, display_name, description, fields_schema, created_at, updated_at
               FROM tag_schemas"""
        )
        conn.execute("DROP TABLE tag_schemas")

    # --- Legacy migration: fields_schema from collections to types ---
    if "collections" in tables:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(collections)").fetchall()}
        if "fields_schema" in cols and "type" not in cols:
            conn.execute("ALTER TABLE collections ADD COLUMN type TEXT REFERENCES types(name) ON DELETE SET NULL")
            import json as _json
            rows = conn.execute("SELECT id, name, display_name, description, fields_schema FROM collections").fetchall()
            for row in rows:
                col_name = row[1]
                type_name = col_name.rstrip("s") if col_name.endswith("s") else col_name
                fs = row[4] or "[]"
                existing_type = conn.execute("SELECT 1 FROM types WHERE name = ?", (type_name,)).fetchone()
                if not existing_type:
                    conn.execute(
                        """INSERT INTO types (name, display_name, description, fields_schema)
                           VALUES (?, ?, ?, ?)""",
                        (type_name, row[2], row[3], fs),
                    )
                conn.execute("UPDATE collections SET type = ? WHERE id = ?", (type_name, row[0]))
            conn.commit()

    # --- Legacy migration: remove type column from collection_items ---
    if "collection_items" in tables:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(collection_items)").fetchall()}
        if "type" in cols:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS collection_items_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    collection_id INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL DEFAULT '',
                    data TEXT NOT NULL DEFAULT '{}',
                    parent_id INTEGER REFERENCES collection_items_new(id) ON DELETE SET NULL,
                    status TEXT DEFAULT 'active',
                    created_at TEXT DEFAULT (datetime('now', 'localtime')),
                    updated_at TEXT DEFAULT (datetime('now', 'localtime'))
                );
                INSERT INTO collection_items_new (id, collection_id, title, content, data, parent_id, status, created_at, updated_at)
                    SELECT id, collection_id, title, content, data, parent_id, status, created_at, updated_at FROM collection_items;
                DROP TABLE collection_items;
                ALTER TABLE collection_items_new RENAME TO collection_items;
            """)

    # --- Migrate from collections-based schema to flat items schema ---
    if "collection_items" in tables:
        if "collections" in tables:
            conn.execute(
                """INSERT OR IGNORE INTO items (id, type, title, content, data, parent_id, status, created_at, updated_at)
                    SELECT ci.id, c.type, ci.title, ci.content, ci.data, ci.parent_id, ci.status, ci.created_at, ci.updated_at
                    FROM collection_items ci
                    LEFT JOIN collections c ON ci.collection_id = c.id"""
            )
        else:
            conn.execute(
                """INSERT OR IGNORE INTO items (id, type, title, content, data, parent_id, status, created_at, updated_at)
                    SELECT id, NULL, title, content, data, parent_id, status, created_at, updated_at
                    FROM collection_items"""
            )

        # Drop old FTS table and triggers
        conn.execute("DROP TRIGGER IF EXISTS collection_items_fts_ai")
        conn.execute("DROP TRIGGER IF EXISTS collection_items_fts_ad")
        conn.execute("DROP TRIGGER IF EXISTS collection_items_fts_au")
        conn.execute("DROP TABLE IF EXISTS collection_items_fts")

        conn.execute("DROP TABLE IF EXISTS collection_item_tags")
        conn.execute("DROP TABLE IF EXISTS collection_items")
        conn.execute("DROP TABLE IF EXISTS collections")
        conn.commit()

    # --- Drop legacy tag tables ---
    if "item_tags" in tables:
        conn.execute("DROP TABLE item_tags")
    if "tags" in tables:
        conn.execute("DROP TABLE tags")
    conn.commit()

    # --- Add parent_type and abstract columns to existing types table ---
    if "types" in tables:
        type_cols = {row[1] for row in conn.execute("PRAGMA table_info(types)").fetchall()}
        if "parent_type" not in type_cols:
            conn.execute("ALTER TABLE types ADD COLUMN parent_type TEXT REFERENCES types(name) ON DELETE SET NULL")
        if "abstract" not in type_cols:
            conn.execute("ALTER TABLE types ADD COLUMN abstract INTEGER NOT NULL DEFAULT 0")
        conn.commit()

    # --- Migrate ref_collection -> ref_type in type field schemas ---
    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    if "types" in tables:
        import json as _json
        type_rows = conn.execute("SELECT name, fields_schema FROM types").fetchall()
        for row in type_rows:
            try:
                fs = _json.loads(row["fields_schema"]) if row["fields_schema"] else []
            except (_json.JSONDecodeError, TypeError):
                continue
            changed = False
            for field in fs:
                if "ref_collection" in field and "ref_type" not in field:
                    col_name = field.pop("ref_collection")
                    type_name = col_name.rstrip("s") if col_name.endswith("s") else col_name
                    field["ref_type"] = type_name
                    changed = True
            if changed:
                conn.execute(
                    "UPDATE types SET fields_schema = ? WHERE name = ?",
                    (_json.dumps(fs, ensure_ascii=False), row["name"]),
                )
        conn.commit()

    # --- Migrate ref data from items.data JSON to item_relations table ---
    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    if "item_relations" in tables and "types" in tables and "items" in tables:
        import json as _json
        # Only run if item_relations is empty (first-time migration)
        rel_count = conn.execute("SELECT COUNT(*) FROM item_relations").fetchone()[0]
        if rel_count == 0:
            # Build ref field map per type
            ref_map = {}  # type_name -> {field_name: {ref_type, multiple}}
            t_rows = conn.execute("SELECT name, fields_schema FROM types").fetchall()
            for t_row in t_rows:
                try:
                    fs = _json.loads(t_row["fields_schema"]) if t_row["fields_schema"] else []
                except (_json.JSONDecodeError, TypeError):
                    continue
                refs = {}
                for f in fs:
                    if f.get("type") == "ref":
                        refs[f["name"]] = {"multiple": f.get("multiple", False)}
                if refs:
                    ref_map[t_row["name"]] = refs

            if ref_map:
                item_rows = conn.execute(
                    "SELECT id, type, data FROM items WHERE type IS NOT NULL"
                ).fetchall()
                for item_row in item_rows:
                    itype = item_row["type"]
                    if itype not in ref_map:
                        continue
                    try:
                        data = _json.loads(item_row["data"]) if item_row["data"] else {}
                    except (_json.JSONDecodeError, TypeError):
                        continue
                    changed = False
                    for fname, finfo in ref_map[itype].items():
                        if fname not in data:
                            continue
                        val = data[fname]
                        ids = []
                        if finfo["multiple"] and isinstance(val, list):
                            ids = [int(v) for v in val if v is not None]
                        elif not finfo["multiple"] and val is not None:
                            ids = [int(val)]
                        for rid in ids:
                            conn.execute(
                                "INSERT OR IGNORE INTO item_relations (item_id, related_item_id, field_name) VALUES (?, ?, ?)",
                                (item_row["id"], rid, fname),
                            )
                        del data[fname]
                        changed = True
                    if changed:
                        conn.execute(
                            "UPDATE items SET data = ? WHERE id = ?",
                            (_json.dumps(data, ensure_ascii=False), item_row["id"]),
                        )
                conn.commit()


def ensure_schema(conn):
    """Ensure the database schema exists."""
    conn.executescript(SCHEMA_SQL)
    _migrate(conn)
    try:
        conn.executescript(FTS_SQL)
    except Exception:
        # FTS5 may not be available on all systems; degrade gracefully
        pass


def seed_defaults(conn):
    """Insert default types if they don't already exist."""
    import json as _json

    for t in DEFAULT_TYPES:
        existing = conn.execute("SELECT 1 FROM types WHERE name = ?", (t["name"],)).fetchone()
        if existing:
            continue
        conn.execute(
            """INSERT INTO types (name, display_name, description, parent_type, abstract, fields_schema)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (t["name"], t["display_name"], t["description"],
             t.get("parent_type"), 1 if t.get("abstract") else 0,
             _json.dumps(t["fields_schema"], ensure_ascii=False)),
        )
    conn.commit()


def get_type_descendants(conn, type_name):
    """Get all descendant type names (including the given type itself)."""
    result = [type_name]
    children = conn.execute(
        "SELECT name FROM types WHERE parent_type = ?", (type_name,)
    ).fetchall()
    for child in children:
        result.extend(get_type_descendants(conn, child["name"]))
    return result


def get_resolved_fields(conn, type_name):
    """Get the merged fields_schema for a type, including inherited fields from ancestors."""
    import json as _json

    row = conn.execute(
        "SELECT fields_schema, parent_type FROM types WHERE name = ?", (type_name,)
    ).fetchone()
    if not row:
        return []

    try:
        own_fields = _json.loads(row["fields_schema"]) if row["fields_schema"] else []
    except (_json.JSONDecodeError, TypeError):
        own_fields = []

    if row["parent_type"]:
        parent_fields = get_resolved_fields(conn, row["parent_type"])
        # Parent fields first, then own fields (own fields can override by name)
        own_names = {f["name"] for f in own_fields}
        merged = [f for f in parent_fields if f["name"] not in own_names]
        merged.extend(own_fields)
        return merged

    return own_fields
