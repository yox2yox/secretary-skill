# コマンドリファレンス

秘書スクリプト (`secretary.py`) の全コマンド一覧です。

すべてのコマンドはJSON形式で結果を返します。

## init

データベースを初期化し、デフォルトタイプを作成します。

```bash
python3 SCRIPT init
```

- データベースは `~/.secretary/data.db` に保存される
- 冪等（複数回実行しても安全）
- デフォルトタイプが存在しない場合のみ作成される

## item_add

アイテムを1件追加します。

```bash
python3 SCRIPT item_add '<json>'
```

**必須フィールド:** `title`

**任意フィールド:**

| フィールド | 型 | 説明 |
|---|---|---|
| `type` | string | アイテムのタイプ名（事前に `type_set` で定義が必要） |
| `title` | string | タイトル（必須） |
| `content` | string | 本文・詳細テキスト |
| `data` | object | タイプの `fields_schema` に基づく構造化データ（JSON） |
| `parent_id` | integer | 親アイテムのID（階層構造用） |
| `status` | string | ステータス（デフォルト: `"active"`） |

**例:**
```bash
python3 SCRIPT item_add '{
  "type": "event",
  "title": "チーム定例ミーティング",
  "content": "Q1ロードマップについて議論した。",
  "data": {
    "event_date": "2025-01-15",
    "start_time": "14:00",
    "end_time": "15:00",
    "location": "会議室A",
    "related_persons": [3, 5]
  }
}'
```

**レスポンス:**
```json
{"status": "ok", "id": 1}
```

**注意:**
- 抽象タイプ（`abstract: true`）を指定するとエラーになる
- 存在しないタイプを指定するとエラーになる

## item_add_batch

複数のアイテムを一括で追加します。

```bash
python3 SCRIPT item_add_batch '<json_array>'
```

**例:**
```bash
python3 SCRIPT item_add_batch '[
  {"type": "task", "title": "API設計書を仕上げる", "data": {"due_date": "2025-01-22", "priority": "high"}},
  {"type": "task", "title": "テスト環境の構築", "data": {"due_date": "2025-01-25", "priority": "medium"}}
]'
```

**レスポンス:**
```json
{"status": "ok", "ids": [1, 2], "count": 2}
```

## item_get

アイテムの詳細を取得します。子アイテムも含まれます。

```bash
python3 SCRIPT item_get <item_id>
```

**レスポンス例:**
```json
{
  "id": 1,
  "type": "event",
  "title": "チーム定例ミーティング",
  "content": "Q1ロードマップについて議論した。",
  "data": {"event_date": "2025-01-15", "start_time": "14:00"},
  "parent_id": null,
  "status": "active",
  "created_at": "2025-01-15 14:30:00",
  "updated_at": "2025-01-15 14:30:00",
  "children": []
}
```

## item_update

アイテムを更新します。

```bash
python3 SCRIPT item_update <item_id> '<json>'
```

**更新可能フィールド:** `title`, `content`, `data`, `parent_id`, `status`, `type`

**`data` フィールドの挙動:**
- `data` はマージ方式で更新される（既存のキーに加えて新しいキーが追加される）
- 既存キーを上書きするには新しい値を指定
- 既存キーを削除するには `null` を指定

**例:**
```bash
python3 SCRIPT item_update 1 '{"status": "completed"}'
python3 SCRIPT item_update 1 '{"data": {"priority": "high", "due_date": "2025-02-01"}}'
python3 SCRIPT item_update 1 '{"type": "task"}'
```

## item_delete

アイテムを削除します。

```bash
python3 SCRIPT item_delete <item_id>
```

子アイテムの `parent_id` は `null` に設定されます。

## item_list

アイテムを一覧表示します。フィルタを指定できます。

```bash
python3 SCRIPT item_list ['<json_filter>']
```

**フィルタオプション:**

| フィルタ | 型 | 説明 |
|---|---|---|
| `type` | string | タイプ名でフィルタ（ポリモーフィック: 子孫タイプも含む） |
| `status` | string | ステータスでフィルタ |
| `parent_id` | integer/null | 親アイテムIDでフィルタ（`null` でルートアイテムのみ） |
| `limit` | integer | 最大件数（デフォルト: 100） |

**例:**
```bash
python3 SCRIPT item_list
python3 SCRIPT item_list '{"type": "task"}'
python3 SCRIPT item_list '{"type": "event", "status": "active"}'
python3 SCRIPT item_list '{"parent_id": null}'
python3 SCRIPT item_list '{"type": "task", "limit": 10}'
```

**ポリモーフィックフィルタリング:**
`{"type": "event"}` を指定すると、`event` タイプだけでなく `event` を継承するすべての子孫タイプのアイテムも返されます。詳細は [タイプシステム](type-system.md) を参照。

## item_search

キーワードでアイテムを全文検索します。FTS5（trigram）を使用し、利用できない場合はLIKE検索にフォールバックします。

```bash
python3 SCRIPT item_search '<keyword>' [type]
```

**引数:**
- `keyword`（必須）: 検索キーワード
- `type`（任意）: タイプ名で絞り込み（ポリモーフィック: 子孫タイプも含む）

**検索対象:** `title`, `content`, `data` フィールド

**例:**
```bash
python3 SCRIPT item_search 'ミーティング'
python3 SCRIPT item_search '佐藤' person
python3 SCRIPT item_search '会議' event
```

最大50件を返します。

## type_set

タイプを定義または更新します。

```bash
python3 SCRIPT type_set '<json>'
```

**フィールド:**

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `name` | string | Yes | タイプ名（英語の単数形、主キー） |
| `display_name` | string | No | 表示名 |
| `description` | string | No | 説明 |
| `parent_type` | string | No | 親タイプ名（継承用） |
| `abstract` | boolean | No | 抽象タイプフラグ（`true` でアイテムに直接使用不可） |
| `fields_schema` | array | No | フィールド定義の配列 |

**`fields_schema` の各フィールド定義:**

| プロパティ | 型 | 説明 |
|---|---|---|
| `name` | string | フィールド名 |
| `type` | string | 型（`string`, `number`, `date`, `time`, `ref`） |
| `description` | string | 説明 |
| `ref_type` | string | 参照先タイプ名（`type: "ref"` の場合） |
| `multiple` | boolean | 配列参照（`type: "ref"` の場合、`true` でIDの配列） |

**フィールドの型一覧:**

| type | 説明 |
|---|---|
| `string` | テキスト値 |
| `number` | 数値 |
| `date` | 日付 (`YYYY-MM-DD`) |
| `time` | 時刻 (`HH:MM`) |
| `ref` | 他のアイテムへのID参照。`ref_type` で参照先タイプを指定。`"multiple": true` でIDの配列 |

**例:**
```bash
python3 SCRIPT type_set '{
  "name": "project",
  "display_name": "プロジェクト",
  "description": "社内プロジェクトに関するデータ",
  "fields_schema": [
    {"name": "status", "type": "string", "description": "進捗状態"},
    {"name": "deadline", "type": "date", "description": "期限"},
    {"name": "owner", "type": "ref", "ref_type": "person", "description": "責任者"}
  ]
}'
```

**注意:**
- 同名のタイプが既存の場合は上書き更新される
- `parent_type` の循環参照はエラーになる
- 継承と抽象タイプの詳細は [タイプシステム](type-system.md) を参照

## type_get

タイプの詳細を取得します。継承を解決した全フィールド（`resolved_fields`）も含まれます。

```bash
python3 SCRIPT type_get <type_name>
```

**レスポンスに含まれる情報:**
- タイプの基本情報（name, display_name, description, parent_type, abstract）
- `fields_schema`: そのタイプ自身で定義されたフィールド
- `resolved_fields`: 親タイプから継承したフィールドも含めた全フィールド
- `children`: 子タイプの一覧
- `parent`: 親タイプの情報（存在する場合）

## type_list

全タイプをフラットな一覧で表示します。

```bash
python3 SCRIPT type_list
```

## type_tree

タイプ階層をツリー構造で表示します。ルートタイプを起点に子タイプがネストされます。

```bash
python3 SCRIPT type_tree
```

## type_delete

タイプを削除します。

```bash
python3 SCRIPT type_delete <type_name>
```

**削除の影響:**
- そのタイプを持つアイテムの `type` は `null` になる
- 子タイプの `parent_type` は `null` になる
