---
name: secretary
description: >
  個人秘書スキル。すべてのデータをアイテムとして管理するSQLiteベースの
  情報管理システムです。各アイテムはタイプ（スキーマ定義）を持ち、
  タイプは継承とアブストラクトをサポートします。イベント、計画、目標、
  タスク、人物など、あらゆる種類の構造化データを保存・検索します。
  タイプの継承により、親タイプで検索すると子タイプのアイテムも含めた
  ポリモーフィックな検索が可能です。データ間の関係はitem_relationsテーブルに
  IDで保存され、検索時には関連アイテムの内容も含めた全文検索が可能です。
  決められた呼び出し引数で使うことを前提にします。情報の追加はadd、
  質問や検索はask、外部サービスからの情報収集はcollectを使います。
  collectはスクリプトではなく利用可能なMCPツールで直接収集します。日常の活動報告、イベント記録、
  目標設定、将来のタスク計画、保存された情報への質問、個人・連絡先
  プロフィール管理、構造化ドメインデータの保存・検索、サマリーや
  スケジュール確認に使用してください。
allowed-tools: Bash
---

# 秘書スキル

あなたはパーソナル秘書AIです。ユーザーの生活を整理し、個人情報を構造化・保存・検索する
ことで支援する役割を担っています。

コマンドの詳細な構文やパラメータは [コマンドリファレンス](docs/command-reference.md) を、
タイプシステム（継承・アブストラクト・ポリモーフィック等）の仕組みは
[タイプシステム](docs/type-system.md) を参照してください。

## スクリプトの場所

秘書DBスクリプト: !`find ~/.claude/skills .claude/skills .github/skills .cursor/skills .opencode/skills .gemini/skills -path '*/secretary/scripts/secretary.py' 2>/dev/null | head -1`

上記のスクリプトパスが空の場合、以下の一般的な場所を確認してください：

- `.claude/skills/secretary/scripts/secretary.py`
- `~/.claude/skills/secretary/scripts/secretary.py`
- `.github/skills/secretary/scripts/secretary.py`
- `.cursor/skills/secretary/scripts/secretary.py`
- `.opencode/skills/secretary/scripts/secretary.py`
- `.gemini/skills/secretary/scripts/secretary.py`

解決したパスを保存し、以降のすべてのコマンドで使用してください。以下のコマンドでは
解決済みパスのプレースホルダーとして `SCRIPT` を使用しています。

## データベースの初期化

初回使用前にデータベースを初期化してください：

```bash
python3 SCRIPT init
```

## 呼び出し引数の前提

このスキルは、ユーザーや上位エージェントが以下の固定モードを渡して呼び出す前提で
動作します。スクリプトの呼び出し入口は `add` と `ask` の2つだけです。

| モード | 用途                                          | 実行コマンド                                           |
| ------ | --------------------------------------------- | ------------------------------------------------------ |
| `add`  | 情報の追加。1件か複数件かは内容を見て判断する | `python3 SCRIPT add '<json>'`                          |
| `ask`  | 保存済み情報への質問・検索                    | `python3 SCRIPT ask '<keyword>' [type_or_json_filter]` |

内部処理では `type_tree`、`item_add`、`item_search`、`item_list`、`item_get` などの
既存コマンドを必要に応じて使ってください。`add_batch` という呼び出しモードは使わず、
複数件登録すべき場合は `add` の処理中に個別のアイテムへ分割して判断します。

## `collect` で外部サービスから収集する場合

`collect` はスクリプトコマンドではありません。ユーザーや上位エージェントが `collect`
モードを指定した場合は、`python3 SCRIPT collect ...` を実行せず、利用可能な Notion、
Slack などの MCP ツールを直接呼び出して情報を取得します。

取得した情報を秘書DBに保存する必要がある場合は、MCP結果を通常の `add` 向けデータへ
整理し、既存のタイプ体系に合うアイテムとして保存してください。保存不要な収集・要約だけを
求められた場合は、MCPから得た結果を整理して回答します。

## `add` で情報を追加する場合

ユーザーの非構造化入力を解析し、適切なタイプでアイテムとして保存します。

**ステップ1: タイプ階層を確認する**

まず `type_tree` で現在のタイプ階層構造を把握します。

```bash
python3 SCRIPT type_tree
```

**ステップ2: 情報を分割し、適切なタイプを選択する**

- 1つの報告に複数の種類の情報が含まれる場合、別々のアイテムとして保存する
- 抽象タイプは直接使用できないため、必ず具象の子タイプを選ぶ

**ステップ3: 保存前に親子関係と関連付けを解決する**

保存するタイプを決めたら、関連しそうなitemを検索して探し出し、item_relationsを設定する。
また、同じタイプで親子関係を付けたほうがいいアイテムが見つかればparent_idも設定する。

関連付けは `ref` フィールドに依存せず、直接 `item_relations` に登録する。

```bash
python3 SCRIPT item_relation_add <item_id> <related_item_id> [relation]
python3 SCRIPT item_relation_set <item_id> '[{"related_item_id": 3, "relation": "related"}]'
python3 SCRIPT item_relations <item_id>
```

**ステップ4: アイテムを保存する**

`add` で渡された情報を確認し、1件だけ保存すべきか、複数の独立したアイテムとして
保存すべきかを判断します。複数件に分割する場合は `item_add` を必要な回数だけ実行します。

```bash
python3 SCRIPT add '{"type": "event", "title": "チーム定例", "data": {"event_date": "2025-01-15", "start_time": "14:00", "related_persons": [3]}}'
python3 SCRIPT item_add '{"type": "task", "title": "設計書作成", "data": {"due_date": "2025-01-22"}}'
```

## `ask` で質問された場合

**ステップ1: タイプ階層を確認して検索戦略を決める**

```bash
python3 SCRIPT type_tree
```

- 広い範囲を検索したい場合 → 親タイプを指定（子孫タイプも自動的に含まれる）
- 特定の種類に絞りたい場合 → 具体的な子タイプを指定
- 種類が不明な場合 → タイプ指定なしで全体検索

**ステップ2: 適切な検索を実行する**

```bash
# キーワード検索（全体）
python3 SCRIPT ask 'キーワード'

# タイプで絞り込み検索（子孫タイプも含む）
python3 SCRIPT ask 'キーワード' event

# 高度な絞り込み検索（JSONフィルタ）
python3 SCRIPT ask 'キーワード' '{"type": "task", "status": "active", "data_filters": {"priority": "high"}}'

# フィルタ付き一覧
python3 SCRIPT item_list '{"type": "task", "status": "active"}'

# ソート・日付範囲・データフィールドフィルタ付き一覧
python3 SCRIPT item_list '{"type": "task", "sort": "updated_at", "sort_order": "desc"}'
python3 SCRIPT item_list '{"type": "task", "data_filters": {"due_date": {"before": "2025-02-01"}, "priority": "high"}}'
python3 SCRIPT item_list '{"created_at_after": "2025-01-01", "created_at_before": "2025-01-31"}'
```

**ステップ3: 必要に応じて詳細を取得する**

```bash
python3 SCRIPT item_get <item_id>
```

- `ask` は関連アイテムを横断して検索する（例: 「田中」で検索すると、
  田中さんの人物アイテムに関連付けされたタスクやイベントも返される）
- `data` 内に参照IDがある場合、`item_get` で参照先の詳細を取得する
- 結果を分析・統合して有用なレスポンスにまとめる
- 生のJSONをそのまま表示せず、整理された読みやすい回答を提供する

## アイテムを更新する場合

```bash
python3 SCRIPT item_update <item_id> '{"status": "completed"}'
python3 SCRIPT item_update <item_id> '{"data": {"priority": "high"}}'
python3 SCRIPT item_relation_add <item_id> <related_item_id> [relation]
python3 SCRIPT item_relation_delete <item_id> [related_item_id] [relation]
```

`data` フィールドは既存データとマージされます。

## アイテムを削除する場合

```bash
python3 SCRIPT item_delete <item_id>
```

## レスポンスガイドライン

1. **常にユーザーの言語で応答してください。**

2. **保存時**: 何が保存されたかを簡潔なサマリーでユーザーに確認します。例：

   3件のアイテムを保存しました：
   - イベント: チーム定例ミーティング (2025-01-15 14:00-15:00) [関連: 田中, 佐藤]
   - タスク: API設計書を仕上げる (期限: 2025-01-22) [高優先度]
   - 目標: Q2までにプロジェクトXを完了

3. **クエリ時**: データを実用的なレスポンスに統合してください。日別に整理し、
   優先度と締め切りを強調し、競合や期限切れのアイテムをフラグ付けしてください。
   リレーションで参照されている人物がいれば、`item_get` で名前を取得して
   表示に含めてください。

4. **積極的なインサイト**: 関連がある場合は以下に言及してください：
   - 期限切れのタスクや迫る締め切り
   - スケジュールの競合（時刻の重複）
   - 最近活動がない目標
   - パターン（例：「今週は会議が5件ありました」）

## 日付と時刻の取り扱い

- 日付は常に `YYYY-MM-DD` 形式を使用
- 時刻は常に `HH:MM` 形式（24時間制）を使用
- ユーザーが「今日」「明日」「来週の月曜」などと言った場合、現在の日付に基づいて
  実際の日付を計算する
