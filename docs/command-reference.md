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
| `data` | object | タイプの `fields_schema` に基づく構造化データ（JSON）。refフィールドは自動的に `item_relations` テーブルに保存される |
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
| `offset` | integer | 先頭からスキップする件数（デフォルト: 0、ページネーション用） |
| `sort` | string | ソート列: `created_at`（デフォルト）, `updated_at`, `title`, `status`, `type` |
| `sort_order` | string | ソート順: `asc` または `desc`（デフォルト: `desc`） |
| `created_at_after` | string | 作成日時の下限（`YYYY-MM-DD` or `YYYY-MM-DD HH:MM:SS`） |
| `created_at_before` | string | 作成日時の上限 |
| `updated_at_after` | string | 更新日時の下限 |
| `updated_at_before` | string | 更新日時の上限 |
| `data_filters` | object | データフィールドによる絞り込み（後述） |

**`data_filters` の書式:**

`data` JSON内のフィールドで絞り込みます。キーはフィールド名、値はスカラー値（完全一致）またはオブジェクト（比較演算子）です。

| 演算子 | 説明 | 例 |
|---|---|---|
| スカラー値 | 完全一致 | `"priority": "high"` |
| `eq` | 完全一致（明示的） | `"priority": {"eq": "high"}` |
| `contains` | 部分一致（LIKE） | `"location": {"contains": "東京"}` |
| `before` | 以下（日付等に有用） | `"due_date": {"before": "2025-02-01"}` |
| `after` | 以上（日付等に有用） | `"due_date": {"after": "2025-01-01"}` |

演算子は組み合わせ可能です（例: `{"after": "2025-01-01", "before": "2025-03-01"}` で範囲指定）。

**例:**
```bash
# 基本的な使い方
python3 SCRIPT item_list
python3 SCRIPT item_list '{"type": "task"}'
python3 SCRIPT item_list '{"type": "event", "status": "active"}'
python3 SCRIPT item_list '{"parent_id": null}'
python3 SCRIPT item_list '{"type": "task", "limit": 10}'

# ソート
python3 SCRIPT item_list '{"type": "task", "sort": "updated_at", "sort_order": "desc"}'
python3 SCRIPT item_list '{"sort": "title", "sort_order": "asc"}'

# 日付範囲フィルタ
python3 SCRIPT item_list '{"created_at_after": "2025-01-01", "created_at_before": "2025-01-31"}'

# データフィールドフィルタ
python3 SCRIPT item_list '{"type": "task", "data_filters": {"priority": "high"}}'
python3 SCRIPT item_list '{"type": "task", "data_filters": {"due_date": {"before": "2025-02-01"}}}'
python3 SCRIPT item_list '{"type": "event", "data_filters": {"location": {"contains": "東京"}}}'
python3 SCRIPT item_list '{"type": "plan", "data_filters": {"priority": "high", "planned_date": {"after": "2025-01-01", "before": "2025-03-31"}}}'

# ページネーション
python3 SCRIPT item_list '{"type": "task", "limit": 10, "offset": 10}'
```

**ポリモーフィックフィルタリング:**
`{"type": "event"}` を指定すると、`event` タイプだけでなく `event` を継承するすべての子孫タイプのアイテムも返されます。詳細は [タイプシステム](type-system.md) を参照。

## item_search

キーワードでアイテムを全文検索します。FTS5（trigram）を使用し、利用できない場合はLIKE検索にフォールバックします。

**関連アイテム横断検索:** 検索はアイテム自体だけでなく、`item_relations` で
関連付けされたアイテムの内容も対象とします。例えば「田中」で検索すると、
田中さんの人物アイテムに関連付けされたタスクやイベントも結果に含まれます。

```bash
python3 SCRIPT item_search '<keyword>' [type_or_json_filter]
```

**引数:**
- `keyword`（必須）: 検索キーワード
- `type_or_json_filter`（任意）: タイプ名（後方互換）またはJSONフィルタオブジェクト

**JSONフィルタオプション:**

第2引数にJSONオブジェクトを渡すと、検索結果をさらに絞り込み・ソートできます。

| フィルタ | 型 | 説明 |
|---|---|---|
| `type` | string | タイプ名で絞り込み（ポリモーフィック） |
| `status` | string | ステータスで絞り込み |
| `limit` | integer | 最大件数（デフォルト: 50） |
| `sort` | string | ソート列: `created_at`, `updated_at`, `title`, `status`, `type` |
| `sort_order` | string | ソート順: `asc` or `desc`（デフォルト: FTSランク順、`sort` 指定時は `desc`） |
| `created_at_after` / `created_at_before` | string | 作成日時の範囲 |
| `updated_at_after` / `updated_at_before` | string | 更新日時の範囲 |
| `data_filters` | object | データフィールドフィルタ（`item_list` と同じ書式） |

**検索対象:** `title`, `content`, `data` フィールド、および関連アイテムの全フィールド

**例:**
```bash
# 基本的な使い方（後方互換）
python3 SCRIPT item_search 'ミーティング'
python3 SCRIPT item_search '佐藤' person
python3 SCRIPT item_search '会議' event
python3 SCRIPT item_search '田中' task    # 田中さんに関連付けされたタスクも返される

# JSONフィルタで高度な絞り込み
python3 SCRIPT item_search 'ミーティング' '{"type": "event", "status": "active"}'
python3 SCRIPT item_search '設計' '{"type": "task", "data_filters": {"priority": "high"}}'
python3 SCRIPT item_search '会議' '{"created_at_after": "2025-01-01", "sort": "created_at", "sort_order": "asc"}'
python3 SCRIPT item_search '報告' '{"type": "task", "data_filters": {"due_date": {"before": "2025-02-01"}}, "limit": 20}'
```

デフォルトで最大50件を返します（`limit` で変更可能）。

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
