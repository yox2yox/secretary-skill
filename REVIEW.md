# データ構造レビュー

## レビュー対象

| ブランチ | 概要 |
|---|---|
| `claude/secretary-agent-sqlite-lhKB5` | entries + persons + person_attributes テーブル。タグはカンマ区切りテキスト |
| `claude/review-db-structure-FFGVC` | entries を改善（CHECK制約・FTS5・タグ正規化・新カラム追加）。persons 系テーブルなし |

最終的には両ブランチの改善を統合する前提でレビューする。

---

## 1. 現在のテーブル構成（統合後の想定）

### entries

```
id, category, title, content, entry_date, due_date, status, priority,
parent_id, location, url, recurrence, created_at, updated_at
```

### entry_tags
```
entry_id, tag  (複合PK)
```

### persons
```
id, person_type, name, relationship, organization, role,
birthday, email, notes, created_at, updated_at
```

### person_attributes
```
id, person_id, category, key, value, created_at, updated_at
```

### entries_fts (FTS5仮想テーブル)
```
title, content
```

---

## 2. 情報の網羅性（秘書として必要な情報をカバーできているか）

### 2.1 entries テーブル — 良い点

- category が6種類（event, plan, goal, task, decision, note）に分類されており、日常の情報整理に十分な粒度
- priority / status / due_date により、タスク管理の基本機能をカバー
- parent_id により、ゴールとサブタスクのような階層構造を表現可能（review branch）
- location, url, recurrence の追加により、イベント管理として実用的（review branch）

### 2.2 entries テーブル — 不足している情報

| 不足項目 | 影響 | 重要度 |
|---|---|---|
| **時刻情報（start_time / end_time）** | 「14:00からミーティング」「15:00-16:00で面談」のような時間帯を持つ予定を正確に管理できない。entry_date は日付のみのため、1日の中での順序や時間の重複検出が不可能 | **高** |
| **エントリと人物の紐付け** | 「田中さんとの打ち合わせ内容を全部見せて」のようなクエリに対応できない。content にテキストとして含まれていても、構造的な検索ができない | **高** |
| **完了日時（completed_at）** | status が completed になった日時が不明。「先週完了したタスク一覧」や、目標達成までの所要時間の分析ができない | **中** |
| **繰り返しの詳細** | recurrence は頻度のみ。繰り返し終了日（recurrence_until）、除外日、「第2火曜日」のような複雑なパターンに対応できない | **中** |
| **情報の出所（source）** | 「メールで聞いた」「Slackで共有された」「会議で決まった」など、情報の出所を記録できない。秘書として根拠を示す際に有用 | **低** |

### 2.3 persons テーブル — 良い点

- person_type で owner/contact を区別でき、ユーザー自身のプロファイルも管理可能
- person_attributes の EAV（Entity-Attribute-Value）方式により、人物に関するあらゆる情報を柔軟に格納可能
- UNIQUE制約（person_id, category, key）により、同一属性の重複を防止

### 2.4 persons テーブル — 不足している情報

| 不足項目 | 影響 | 重要度 |
|---|---|---|
| **複数の連絡先** | email が1カラムのみ。電話番号、複数のメールアドレス、SNSアカウント（LINE, Slack, X 等）を構造的に保持できない。person_attributes に入れることは可能だが、検索性が下がる | **中** |
| **最終接触日（last_contacted_at）** | 「最近連絡を取っていない人」のような検索に対応できない。秘書として人間関係の維持をサポートする際に重要 | **中** |
| **グループ/タグ** | 人物をグループ化する仕組みがない。「プロジェクトXのメンバー全員」「家族」などのグルーピングが構造的にできない | **低** |

### 2.5 テーブル間の関係 — 主要な欠落

**entries と persons を結ぶ中間テーブルがない。** これが最大の構造的欠陥。

秘書の典型的なユースケース：
- 「佐藤さんとの最近の打ち合わせ内容は？」→ 人物でエントリを検索
- 「来週のミーティング、誰と会う予定？」→ エントリから関連人物を取得
- 「この決定に関わった人は？」→ decision エントリから関係者を特定

これらは現在の構造では不可能。content のテキスト内に名前が含まれていても、同姓や表記揺れに対応できない。

**提案：entry_persons 中間テーブル**
```sql
CREATE TABLE entry_persons (
    entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
    person_id INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    role TEXT DEFAULT '',  -- 例: 'attendee', 'assignee', 'reporter', 'related'
    PRIMARY KEY (entry_id, person_id)
);
```

---

## 3. 検索時の取り出しやすさ

### 3.1 良い点

| 項目 | 詳細 |
|---|---|
| FTS5 全文検索 | title と content に対する高速な日本語含むキーワード検索（review branch） |
| タグの正規化 | entry_tags テーブルで完全一致検索が可能。カンマ区切り LIKE 検索より高速で正確（review branch） |
| 複合インデックス | `(category, status)`, `(status, due_date)` で頻出クエリパターンをカバー（review branch） |
| CHECK制約 | 不正な category / status / priority の挿入を防止。データ整合性を保証（review branch） |
| EAV属性検索 | person_attributes で category + key による柔軟な属性検索が可能 |

### 3.2 問題点と改善案

#### 問題1: FTS5 の対象範囲が狭い

現在 FTS5 は entries の title と content のみ。以下が検索対象外：

- タグ（entry_tags）
- 人物名（persons.name）
- 人物の属性値（person_attributes.value）

**改善案:** FTS5 の対象カラムを拡張するか、persons 用の FTS テーブルを別途作成する。

```sql
CREATE VIRTUAL TABLE IF NOT EXISTS persons_fts USING fts5(
    name, organization, role, notes,
    content=persons, content_rowid=id
);
```

#### 問題2: 日付検索の OR 条件

`entry_date` と `due_date` が別カラムのため、「ある期間に関連するエントリ」の検索が常に OR 条件になる：

```sql
WHERE (entry_date BETWEEN ? AND ?) OR (due_date BETWEEN ? AND ?)
```

これはインデックスが効きにくい。ただし、エントリ数が数万件を超えない限り実用上の問題は小さい。現状の設計で許容可能。

#### 問題3: person_attributes の N+1 クエリ

`person_list` や `person_search` で人物一覧を取得する際、各人物ごとに属性を別クエリで取得している（N+1問題）：

```python
for row in rows:
    person = dict(row)
    attrs = conn.execute(
        "SELECT * FROM person_attributes WHERE person_id = ? ...",
        (person["id"],),
    ).fetchall()
```

**改善案:** 一括で取得して Python 側でグルーピングする：

```python
person_ids = [row["id"] for row in rows]
placeholders = ",".join("?" for _ in person_ids)
all_attrs = conn.execute(
    f"SELECT * FROM person_attributes WHERE person_id IN ({placeholders}) ORDER BY person_id, category, key",
    person_ids,
).fetchall()
# dict でグルーピング
```

#### 問題4: entries の entry_date が NULL の場合のソート

review branch では `COALESCE(entry_date, '9999-12-31')` で対処しているが、entry_date が NULL のエントリ（例：期限未定のゴール）は常に最後に来る。ユースケースによっては created_at でソートした方が適切な場合もある。

#### 問題5: タグの正規化が不完全（sqlite branch）

sqlite branch ではタグがカンマ区切りテキストのまま entries.tags カラムに保存されている。`LIKE '%,tag,%'` での検索は、部分一致による誤検索のリスクがある（例：tag "work" を検索して "network" がヒット）。

→ review branch の entry_tags テーブルで解決済み。統合時にこの改善を取り込むべき。

---

## 4. ブランチ統合時の注意点

review-db-structure ブランチには persons / person_attributes テーブルが含まれていない。統合する際：

1. review branch の entries 改善（CHECK制約, FTS5, entry_tags, 新カラム）をベースにする
2. sqlite branch の persons + person_attributes テーブルを追加する
3. persons テーブルにも CHECK制約や FTS を適用する
4. entry_persons 中間テーブルを新規追加する
5. persons 関連のコマンド（person_add, person_update 等）を review branch の構造に合わせてマージする

---

## 5. 優先度付き改善提案まとめ

| 優先度 | 改善内容 | 理由 |
|---|---|---|
| **P0** | entry_persons 中間テーブルの追加 | 秘書として「誰の」情報かを構造的に追跡する基本機能。これがないと人物ベースの検索が不可能 |
| **P0** | 両ブランチの統合 | entries の改善と persons テーブルの両方が必要 |
| **P1** | 時刻情報の追加（start_time / end_time、または entry_date を datetime 化） | 1日の中のスケジュール管理に必須 |
| **P1** | completed_at カラムの追加 | 完了日の追跡。振り返りや分析に必要 |
| **P1** | N+1 クエリの解消 | 人物一覧取得のパフォーマンス改善 |
| **P2** | persons 用 FTS テーブルの追加 | 人物の全文検索の高速化 |
| **P2** | 複数連絡先の構造化 | email 以外の連絡手段の管理 |
| **P2** | recurrence の詳細化（終了日、除外日） | 繰り返し予定の実用的な管理 |
| **P3** | source カラムの追加 | 情報の出所追跡 |
| **P3** | 人物のグループ/タグ機能 | 人物のグルーピング |
