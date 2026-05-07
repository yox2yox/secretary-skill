# タイプシステム

`type` はアイテムのデータスキーマを定義する仕組みです。`types` テーブルで定義され、
`items.type` から外部キーで参照されます。

## アーキテクチャ

すべてのデータは**タイプ**と**アイテム**で管理されます。

- **タイプ**: データのスキーマ（フィールド定義）を持つ型定義。継承とアブストラクトをサポート
- **アイテム**: 個々のデータレコード。タイプを1つだけ持つ（または未設定）
- **リレーション**: `item_relations` テーブルでアイテム同士を直接関連付ける

## 基本ルール

- アイテムにはタイプを1つだけ設定可能（または未設定）
- **アイテムにtypeを設定する前に、必ず `type_set` でタイプを定義してください**
- タイプを削除すると、そのタイプを持つアイテムの `type` は `null` になる

## 型の継承（Inheritance）

タイプは `parent_type` を指定して継承関係を構築できます。

- 子タイプは親タイプの `fields_schema` を**自動的に継承**する
- 子タイプ独自のフィールドを追加でき、親のフィールドをオーバーライドすることも可能
- `type_get` で取得すると、`resolved_fields`（継承を解決した全フィールド）が返される

**例: 継承を使ったタイプ定義**

```bash
# 抽象親タイプを定義（共通フィールドを持つ）
python3 SCRIPT type_set '{
  "name": "calendar_event",
  "display_name": "カレンダーイベント",
  "description": "日時を持つイベントの共通基底タイプ",
  "abstract": true,
  "fields_schema": [
    {"name": "event_date", "type": "date", "description": "日付"},
    {"name": "start_time", "type": "time", "description": "開始時刻"},
    {"name": "end_time", "type": "time", "description": "終了時刻"},
    {"name": "location", "type": "string", "description": "場所"},
    {"name": "related_persons", "type": "ref", "ref_type": "person", "multiple": true, "description": "関連人物"}
  ]
}'

# 具象子タイプ（親のフィールドを継承 + 独自フィールドを追加）
python3 SCRIPT type_set '{
  "name": "meeting",
  "display_name": "会議",
  "description": "会議・打ち合わせ",
  "parent_type": "calendar_event",
  "fields_schema": [
    {"name": "agenda", "type": "string", "description": "議題"},
    {"name": "minutes", "type": "string", "description": "議事録"}
  ]
}'

python3 SCRIPT type_set '{
  "name": "anniversary",
  "display_name": "記念日",
  "description": "誕生日・記念日などの年次イベント",
  "parent_type": "calendar_event",
  "fields_schema": [
    {"name": "recurrence", "type": "string", "description": "繰り返し (yearly)"},
    {"name": "category", "type": "string", "description": "種類（誕生日、結婚記念日など）"}
  ]
}'
```

## アブストラクトタイプ（Abstract）

`"abstract": true` を指定したタイプは直接アイテムに使用できません。
分類のためのグルーピング用タイプとして機能します。

- アブストラクトタイプをアイテムの `type` に指定するとエラーになる
- 子タイプ（具象型）のみがアイテムに使用可能
- アブストラクトタイプでフィルタリングすると、すべての子孫タイプのアイテムが返される

## ポリモーフィックフィルタリング

`item_list` や `item_search` でタイプを指定すると、そのタイプおよび
**すべての子孫タイプ**のアイテムが返されます。

例えば、以下のタイプ階層がある場合：

```
event (abstract)
├── meeting
├── anniversary
└── incident
```

`item_list '{"type": "event"}'` は `meeting`、`anniversary`、`incident`
のすべてのアイテムを返します。

```bash
# calendar_event 以下のすべてのアイテム（meeting, anniversary など）を検索
python3 SCRIPT item_list '{"type": "calendar_event"}'
python3 SCRIPT item_search '会議' calendar_event

# 特定の子タイプのみ
python3 SCRIPT item_list '{"type": "meeting"}'
```

## リレーション（データ間の関係）

アイテム間の関係は `item_relations` テーブルに保存されます。`fields_schema` の
`"type": "ref"` フィールドを使った互換動作も残っていますが、直接関連を作る場合は
`item_relation_add` / `item_relation_set` を使います。

```bash
python3 SCRIPT item_relation_add 1 7 assignee
python3 SCRIPT item_relation_add 1 10 related_goal
python3 SCRIPT item_relation_set 1 '[7, 10]'
python3 SCRIPT item_relations 1
```

関係名を省略すると `"related"` として保存されます。

### refフィールド互換

**保存時:** `data` にrefフィールドのIDを含めると、自動的に `item_relations` テーブルに
保存され、`data` JSON からは除外されます。

**取得時:** `item_get` や `item_list`、`item_search` のレスポンスでは、
`item_relations` テーブルから取得した関連IDが `data` に含まれた形で返されます。

```bash
# アイテム追加時にrefフィールドを指定
python3 SCRIPT item_add '{
  "type": "task",
  "title": "設計書作成",
  "data": {"due_date": "2025-01-22", "assignee": 7, "related_goal": 10}
}'
# assignee と related_goal は item_relations テーブルに保存される
# data JSON には due_date のみ保存される
```

- `ref_type` で参照先のタイプを明示
- `"multiple": true` の場合はIDの配列、そうでなければ単一のID
- 参照先のアイテムの詳細が必要な場合は `item_get` で取得

### 全文検索と関連アイテム

`item_search` はリレーションを横断して検索します。あるアイテムに直接キーワードが
含まれていなくても、関連付けされたアイテムにキーワードが含まれていれば検索結果に
含まれます。

例: タスクに関連付けされた人物の名前に「田中」があれば、「田中」で検索した際に
そのタスクも結果に含まれます。

## 階層構造

アイテムは `parent_id` による階層構造をサポートしています。

```bash
# 親アイテム
python3 SCRIPT item_add '{"type": "event", "title": "全社ミーティング", "data": {"event_date": "2025-01-15"}}'

# 子アイテム（parent_idで親を参照）
python3 SCRIPT item_add '{"type": "task", "title": "議事録を共有する", "data": {"due_date": "2025-01-16"}, "parent_id": 1}'
```

ルートアイテムのみ表示：

```bash
python3 SCRIPT item_list '{"parent_id": null}'
```
