# NoSQL vs SQLite 評価レポート

## 現状分析

### データモデルの実態

現在のスキーマは4テーブル（`collections`, `collection_items`, `collection_item_tags`, `tag_schemas`）＋FTS仮想テーブルで構成されているが、実質的に**ドキュメントストアをSQLiteの上に自前実装している**状態。

根拠：

1. **汎用エンティティテーブル**: すべてのデータが `collection_items` という1つのテーブルに格納される。`persons` も `events` も `tasks` も同じテーブル
2. **スキーマレスの `data` フィールド**: コアデータはJSON blob。`fields_schema` は「ヒント」であり強制されない
3. **リレーションがJSON内**: FK制約ではなく `data` フィールド内のID参照（`related_persons: [3, 5]`）で関係を表現
4. **コレクション＝ドキュメントの型**: `collections` テーブルは実質的にドキュメントタイプの定義

### クエリパターン

| 操作 | 頻度 | 内容 |
|------|------|------|
| コレクション内のアイテム一覧 | 高 | `collection_id` でフィルタ |
| ID でアイテム取得 | 高 | 単純なキールックアップ |
| テキスト検索 | 中 | FTS5 / LIKE フォールバック |
| タグでフィルタ | 中 | junction テーブル経由 |
| ステータスでフィルタ | 中 | 単純な等値条件 |
| 複数テーブルの JOIN | **無** | データの集約クエリが無い |
| トランザクション的な複数テーブル更新 | **無** | 基本的に単一アイテムの CRUD |
| 集計・レポート | **無** | GROUP BY / SUM 等が無い |

**特徴的なのは、RDBの強みであるJOIN・集計・複雑なトランザクションを一切使っていない点。**

---

## 評価

### NoSQL が適している理由（ユーザーの指摘は正しい）

#### 1. データモデルとの自然な適合

```
現状（SQLite）:
collection_items.data = '{"event_date": "2025-01-15", "related_persons": [3, 5]}'
                         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                         → JSONをTEXTカラムに文字列として格納

NoSQL（ドキュメントDB）:
{
  "_id": "item_123",
  "collection": "events",
  "title": "チームミーティング",
  "event_date": "2025-01-15",       ← トップレベルのフィールドとして自然に格納
  "related_persons": [3, 5]          ← ネイティブな配列型
}
```

ドキュメントDBでは `data` フィールドに押し込む必要がなく、各フィールドがファーストクラスの値になる。これにより：
- `data` フィールドの JSON パース/シリアライズが不要
- フィールド単位のインデックスが可能（例: `event_date` で直接クエリ）
- `data` のマージロジック（`item_update` の既存データとの dict merge）が不要

#### 2. スキーマの柔軟性がネイティブ

現在の設計思想は「コレクションごとに異なるフィールドを持ち、スキーマは強制しない」。これはまさにドキュメントDBの設計思想そのもの。SQLiteでこれを実現するために `TEXT NOT NULL DEFAULT '{}'` という妥協をしている。

#### 3. コードの簡素化

現在のコードには SQLite の上にドキュメントストアを模倣するためのボイラーレートが多い：
- `json.dumps()` / `json.loads()` の頻繁な変換（`collections_mod.py` に10箇所以上）
- `_enrich_items()` での手動 JSON パース
- `item_update` での `data` フィールドのマージロジック
- `fields_schema` の JSON 文字列としての格納と復元

#### 4. 参照（リレーション）の扱い

現在の参照はJSON内のIDで、参照整合性は無い。これはドキュメントDBの標準的なパターンと同じ。SQLiteのFK機能を使っていないため、SQLiteを使うメリットがここでも活かされていない。

### SQLite を維持する理由

#### 1. ゼロ依存・組み込み

SQLiteはPython標準ライブラリに含まれる。追加のインストールやプロセス管理が不要。個人用ツールとしてこれは大きな利点。

#### 2. FTS5（全文検索）

SQLiteのFTS5はtrigramトークナイザーを使用しており、日本語検索にも対応。NoSQLに移行した場合、同等の全文検索を実現するには追加の工夫が必要。

#### 3. データ量が小さい

個人用秘書ツールのデータ量は多くても数千〜数万件。この規模ではSQLiteもNoSQLもパフォーマンス差は無視できる。

#### 4. ACID トランザクション

`item_add_batch` のような一括操作でのアトミック性がSQLiteでは簡単に保証される。ただし現在の使用パターンでは複雑なトランザクションは無い。

#### 5. 単一ファイル

`~/.secretary/data.db` という1ファイルで完結。バックアップもコピー1つで済む。

---

## 具体的な選択肢

### 選択肢 A: SQLite を維持（現状維持）

- **変更コスト**: なし
- **メリット**: 動いているものを壊さない
- **デメリット**: JSON変換のボイラープレートが残る

### 選択肢 B: TinyDB に移行

- **概要**: Pure Python のドキュメントDB。JSON ファイルベース
- **変更コスト**: 中（db.py + collections_mod.py の書き換え）
- **メリット**:
  - pip install のみで追加可能（`pip install tinydb`）
  - ドキュメント指向でデータモデルとの親和性が高い
  - JSON変換のボイラープレートが大幅に削減
  - 単一 JSON ファイルで保存（バックアップが容易）
- **デメリット**:
  - FTS が無い（検索はフィールド走査になる）
  - Python 標準ライブラリではない（外部依存追加）
  - 大量データでのパフォーマンスは SQLite に劣る
  - WAL のような並行読み取り最適化が無い

### 選択肢 C: SQLite + JSON1 拡張の活用を強化

- **概要**: 現在の SQLite を維持しつつ、`json_extract()` 等を活用してクエリを改善
- **変更コスト**: 小
- **メリット**:
  - 依存関係の変更なし
  - `data` フィールド内のフィールドに対する直接クエリが可能
  - `json_extract(data, '$.event_date')` でインデックス作成可能
  - FTS5 をそのまま維持
- **デメリット**:
  - ボイラープレートは多少残る
  - データモデルとストレージの不一致は解消されない

### 選択肢 D: UnQLite（組み込みドキュメントDB）

- **概要**: C ベースの組み込みドキュメントDB。Key-Value + ドキュメントストア
- **変更コスト**: 中〜大
- **メリット**:
  - 組み込み型（サーバー不要）
  - ドキュメントネイティブ
  - 単一ファイル
- **デメリット**:
  - Python バインディング（`unqlite-python`）のメンテナンスが不安定
  - FTS サポートが限定的
  - コミュニティが小さい

---

## 結論

**ユーザーの直感は正しい。** データモデルは本質的にドキュメント指向であり、SQLite のリレーショナル機能（JOIN、FK制約、正規化）をほぼ使っていない。SQLite の上にドキュメントストアを模倣している現状は、アーキテクチャとしてやや不自然。

### 推奨

**短期（実用的）**: 選択肢 C — SQLite + JSON1 拡張の活用強化

- 移行リスクがゼロ
- `json_extract()` を使えば `data` 内のフィールドに対するクエリ・インデックスが可能になり、現在の `LIKE` 検索よりも効率的
- FTS5 をそのまま維持できる

**中長期（もしリファクタリングするなら）**: 選択肢 B — TinyDB への移行を検討

- データモデルとの親和性が最も高い
- コードが大幅に簡素化される
- ただし FTS の代替（例: Whoosh や独自のインデックス）の検討が必要
- データ量が小さいため、パフォーマンスの懸念は低い

**避けるべき**: MongoDB 等のサーバー型 NoSQL は個人用ツールにはオーバースペック。

---

## 補足: TinyDB 移行時の FTS 代替調査

現在の SQLite FTS5 は `tokenize='trigram'` を使用しており、日本語テキストを3文字ずつの
部分文字列に分割してインデックスする方式。TinyDB に移行する場合の FTS 代替選択肢を調査した。

### TinyDB の組み込み検索機能

TinyDB には FTS 機能が**存在しない**。専用プラグインも見つからない。
組み込みで使えるのは以下のみ：

- `Query().field.search('regex')` — 正規表現マッチ
- `Query().field.test(callable)` — カスタム関数によるフィルタ

これらはインデックスを使わない全走査であり、FTS5 の代替にはならない。

### 選択肢 1: Whoosh / Whoosh-Reloaded（Pure Python FTS）

| 項目 | 内容 |
|------|------|
| インストール | `pip install whoosh-reloaded` |
| 日本語対応 | N-gram トークナイザーで対応可能（真の形態素解析ではない） |
| Pure Python | Yes（外部バイナリ不要） |
| メンテナンス | **ほぼ停止** — オリジナル Whoosh は開発終了、Whoosh-Reloaded も過去12ヶ月リリースなし |
| ファイルベース | Yes（インデックスディレクトリを生成） |

**問題点**: メンテナンスが実質停止しているライブラリに依存するリスクがある。

### 選択肢 2: tantivy-py（Rust ベース FTS）

| 項目 | 内容 |
|------|------|
| インストール | `pip install tantivy` |
| 日本語対応 | Rust 側では lindera/Vaporetto で対応可能だが、**Python バインディングからは日本語トークナイザーが使えない**（default トークナイザーのみ公開） |
| Pure Python | No（Rust バイナリ） |
| メンテナンス | 活発（quickwit-oss が管理） |
| パフォーマンス | Lucene の約2倍 |

**問題点**: 日本語トークナイザーを Python から使うには、カスタム Rust バインディングのビルドが必要。オーバースペック。

### 選択肢 3: 自前 trigram インデックス（Pure Python、依存なし）

現在の FTS5 が `tokenize='trigram'` を使っていることを踏まえると、同じロジックを
Pure Python で実装するのが最もシンプルな代替。

```python
# 概念実装（~50行で実現可能）
class TrigramIndex:
    def __init__(self):
        self.index = {}  # trigram -> set of doc_ids

    def _trigrams(self, text):
        """テキストから全3文字部分文字列を抽出"""
        text = text.lower()
        return {text[i:i+3] for i in range(len(text) - 2)}

    def add(self, doc_id, text):
        for tri in self._trigrams(text):
            self.index.setdefault(tri, set()).add(doc_id)

    def search(self, query, documents):
        """候補をtrigramで絞り込み、部分文字列マッチで検証"""
        trigrams = self._trigrams(query)
        if not trigrams:
            return []
        # 全trigramを含むドキュメントを候補に
        candidates = set.intersection(*(self.index.get(t, set()) for t in trigrams))
        # 実際の部分文字列マッチで検証（false positive 除去）
        query_lower = query.lower()
        return [doc_id for doc_id in candidates
                if query_lower in documents[doc_id].lower()]
```

日本語での動作例：
```python
idx = TrigramIndex()
idx.add(1, "チームミーティング")
# → trigrams: {"チーム", "ームミ", "ムミー", "ミーテ", "ーティ", "ティン", "ィング"}

idx.search("ミーティング", docs)
# → trigrams {"ミーテ","ーティ","ティン","ィング"} で候補を絞り込み → [1]
```

| 項目 | 内容 |
|------|------|
| インストール | 不要（標準ライブラリのみ） |
| 日本語対応 | Python の Unicode 処理でそのまま動作 |
| Pure Python | Yes |
| メンテナンス | 自前コードなので自分で管理 |
| パフォーマンス | 数千件なら問題なし。メモリ上にインデックス保持（永続化は JSON で可能） |
| 実装コスト | ~50行 |

**利点**: 現在の FTS5 trigram と同じアルゴリズムなので、検索品質が同等。
**欠点**: ランキング（BM25等）が無い（ただし現在の使用パターンでは不要）。インデックスの永続化を自前で管理する必要がある。

### 選択肢 4: SQLite FTS5 を検索専用に併用

TinyDB をメインストレージにしつつ、検索用途だけ SQLite FTS5 を使うハイブリッド構成。

| 項目 | 内容 |
|------|------|
| メインストレージ | TinyDB（ドキュメント指向） |
| 検索インデックス | SQLite FTS5（trigram、現在と同じ） |
| 同期 | アイテムの追加/更新/削除時に FTS テーブルも更新 |

**利点**: FTS5 の検索品質をそのまま維持。TinyDB のドキュメント指向の利点も得られる。
**欠点**: 2つのストレージを同期する複雑さ。「SQLite をやめたい」という動機と矛盾。

### FTS 代替の比較まとめ

| 選択肢 | 日本語 | 依存 | メンテ | 実装コスト | 検索品質 |
|--------|--------|------|--------|-----------|----------|
| Whoosh-Reloaded | N-gram で対応 | 外部1個 | 停滞 | 低 | 高（ランキング有） |
| tantivy-py | 困難 | 外部1個+Rust | 活発 | 高 | 最高 |
| 自前 trigram | そのまま動作 | なし | 自前 | 低（~50行） | 中（ランキング無） |
| SQLite FTS5 併用 | そのまま動作 | なし | 安定 | 中 | 高 |

### FTS 観点での結論

**TinyDB に移行する場合の最も現実的な FTS 代替は「自前 trigram インデックス」**。
現在の FTS5 trigram と同じアルゴリズムを ~50行で実装でき、外部依存も不要。
データ量が数千件の個人ツールでは十分な性能。

ただし、**FTS5 が SQLite に留まる最大の理由の一つ**であることも事実。
FTS5 trigram は安定しており、インデックスの永続化・更新・同期を自動で行ってくれる。
自前実装ではこれらを手動で管理する必要がある。

---

## 補足2: ベクトル検索を前提とした場合の再評価

ベクトル検索（Embedding によるセマンティック検索）の導入を前提とすると、各選択肢の評価が大きく変わる。
ここでは「キーワード検索（FTS）+ ベクトル検索」の両方を実現する観点で再評価する。

### ベクトル検索の想定ユースケース

秘書スキルにおけるベクトル検索の活用例：

- 「キャリアに関係する情報を全部見せて」→ goals, tasks, notes, events を横断してセマンティック検索
- 「Aさんとの関係で重要なこと」→ 人物に関連する情報を意味的に検索
- 「最近ストレスに感じていること」→ 感情・文脈を理解した検索
- あいまいな記憶からの情報検索（「前に誰かが言ってたプロジェクトの話」）

これらは FTS（キーワードマッチ）では対応が難しく、Embedding ベースの類似度検索が必要。

### 各選択肢のベクトル検索対応

#### 選択肢 A/C: SQLite + sqlite-vec

[sqlite-vec](https://github.com/asg017/sqlite-vec) は Alex Garcia が開発する SQLite 拡張で、ベクトル検索を SQLite に追加する。

```python
import sqlite3
import sqlite_vec

db = sqlite3.connect("data.db")
db.enable_load_extension(True)
sqlite_vec.load(db)

# ベクトルテーブルの作成
db.execute("""
    CREATE VIRTUAL TABLE IF NOT EXISTS item_embeddings USING vec0(
        item_id INTEGER PRIMARY KEY,
        embedding float[1536]   -- OpenAI text-embedding-3-small の次元数
    )
""")

# 検索（コサイン類似度で上位5件）
db.execute("""
    SELECT item_id, distance
    FROM item_embeddings
    WHERE embedding MATCH ?
    ORDER BY distance
    LIMIT 5
""", [query_embedding])
```

| 項目 | 内容 |
|------|------|
| インストール | `pip install sqlite-vec` |
| メンテナンス | **活発**（Alex Garcia による継続的開発、SQLite 公式エコシステムの一部） |
| ストレージ | 既存の `data.db` に統合可能（**単一ファイル維持**） |
| FTS5 との共存 | **完全に共存可能**（同一 DB 内で FTS5 + vec0 を併用） |
| クエリ統合 | SQL の JOIN で通常データ・FTS結果・ベクトル結果を統合可能 |
| アルゴリズム | Exhaustive KNN（小規模データに最適）、パーティション対応 |
| 次元数 | 任意（1536, 768 等） |

**アーキテクチャ図:**

```
┌─────────────────────────────────────────┐
│              data.db (単一ファイル)        │
│                                         │
│  ┌─────────────────┐  ┌──────────────┐  │
│  │ collection_items │  │ collections  │  │
│  │ (通常テーブル)     │  │ tag_schemas  │  │
│  └────────┬────────┘  └──────────────┘  │
│           │                              │
│  ┌────────┴────────┐  ┌──────────────┐  │
│  │ collection_     │  │ item_        │  │
│  │ items_fts       │  │ embeddings   │  │
│  │ (FTS5 trigram)  │  │ (vec0)       │  │
│  │ キーワード検索    │  │ セマンティック  │  │
│  └─────────────────┘  └──────────────┘  │
└─────────────────────────────────────────┘
```

**最大の利点**: FTS5（キーワード）+ vec0（セマンティック）+ JSON1（ドキュメントクエリ）が **すべて同一DB・同一SQL で統合**される。ハイブリッド検索が SQL の JOIN だけで実現可能。

#### 選択肢 B: TinyDB + 外部ベクトルインデックス

TinyDB にはベクトル検索機能が**一切存在しない**。別途ベクトルインデックスライブラリが必要。

| ベクトルライブラリ | 概要 | 問題点 |
|-------------------|------|--------|
| FAISS (`faiss-cpu`) | Meta 製。高性能 ANN | C++ バイナリ依存、個人ツールにはオーバースペック |
| Annoy | Spotify 製。読み取り専用インデックス | 更新のたびにインデックス全再構築 |
| hnswlib | 軽量 HNSW | C++ 依存 |
| NumPy cosine similarity | 自前実装 | インデックスなし、全走査 |

**TinyDB + ベクトル検索の場合のアーキテクチャ:**

```
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│   TinyDB     │  │ 自前 trigram  │  │  FAISS /     │
│  (JSON file) │  │   index      │  │  hnswlib     │
│  メインDB     │  │  キーワード    │  │  ベクトル      │
└──────┬───────┘  └──────┬───────┘  └──────┬───────┘
       │                 │                 │
       └─────────────────┴─────────────────┘
              3つのストレージを手動で同期
```

**問題点:**
1. **3つのストレージの同期管理** — アイテムの追加・更新・削除のたびに TinyDB、trigram インデックス、ベクトルインデックスの3箇所を更新
2. **整合性リスク** — いずれかの更新が失敗した場合、データ不整合が発生
3. **バックアップの複雑化** — 単一ファイルではなく複数ファイル/ディレクトリの管理
4. **クエリの統合が困難** — 「FTS で絞り込んだ結果をベクトルでリランキング」のようなハイブリッド検索を実装するのが煩雑

#### 選択肢 E（新規）: ChromaDB

ベクトル検索に特化した埋め込みDB。ドキュメント + メタデータ + Embedding を統合管理。

```python
import chromadb

client = chromadb.PersistentClient(path="~/.secretary/chroma")
collection = client.get_or_create_collection("items")

collection.add(
    ids=["item_1"],
    documents=["チームミーティングの議事録"],
    metadatas=[{"collection": "events", "status": "active"}],
)

# セマンティック検索
results = collection.query(query_texts=["キャリアに関する情報"], n_results=5)
```

| 項目 | 内容 |
|------|------|
| インストール | `pip install chromadb`（依存が多い: numpy, onnxruntime 等） |
| メンテナンス | 活発（VC 資金あり） |
| ストレージ | ディレクトリベース（SQLite + Parquet 内部使用） |
| ドキュメント指向 | Yes（メタデータフィルタリング対応） |
| FTS | **限定的**（`where_document` フィルタのみ、trigram 検索なし） |
| 組み込みEmbedding | Yes（デフォルトで all-MiniLM-L6-v2） |

**利点:** Embedding の生成・管理を自動化してくれる。ベクトル検索のセットアップが最も簡単。
**欠点:**
- 依存パッケージが非常に多い（onnxruntime だけで 200MB 超）
- FTS が弱い（日本語 trigram 検索は不可能）
- 「ベクトル検索ファースト」の設計で、通常の CRUD 操作には向かない
- 内部で SQLite を使っているが、直接操作はできない

#### 選択肢 F（新規）: LanceDB

組み込み型のベクトル＋カラムナーDB。

| 項目 | 内容 |
|------|------|
| インストール | `pip install lancedb` |
| メンテナンス | 活発（LanceDB Inc.） |
| ストレージ | Lance 形式ファイル |
| FTS | あり（tantivy ベース。ただし日本語トークナイザーは要確認） |
| スキーマ | PyArrow スキーマベース（動的フィールドには不向き） |

**問題点:** スキーマレスなドキュメント指向の設計ではない。カラムナー形式のため、secretary-skill のような動的 `data` フィールドとの相性が悪い。

### ベクトル検索前提での比較まとめ

| 項目 | SQLite + sqlite-vec | TinyDB + 外部 | ChromaDB | LanceDB |
|------|---------------------|---------------|----------|---------|
| キーワード検索 (FTS) | FTS5 trigram | 自前実装 | 弱い | tantivy（日本語△） |
| ベクトル検索 | sqlite-vec (vec0) | FAISS等が必要 | ネイティブ | ネイティブ |
| ストレージ統合 | **単一ファイル** | 3つに分散 | ディレクトリ | ディレクトリ |
| ドキュメント指向 | JSON1 で部分対応 | ネイティブ | メタデータのみ | スキーマ必須 |
| 依存の軽さ | `sqlite-vec` のみ | 2つ以上 | 重い (200MB+) | 中程度 |
| ハイブリッド検索 | SQL JOIN で統合 | 手動実装 | 限定的 | 対応 |
| データ同期の複雑さ | なし（同一DB） | **高い** | なし | なし |
| 既存コードからの移行コスト | **小** | 大 | 大 | 大 |

### ベクトル検索前提での結論

**ベクトル検索の導入を前提とすると、SQLite（選択肢 C 拡張版）が明確に最適解になる。**

理由：

1. **検索機能の統合**: FTS5（キーワード）+ sqlite-vec（セマンティック）+ JSON1（構造化クエリ）が同一 DB 内で共存。ハイブリッド検索（キーワードで候補絞り込み → ベクトルでリランキング）が SQL だけで完結する

2. **単一ファイルの維持**: `~/.secretary/data.db` の1ファイルにすべてが収まる。バックアップ・移行が容易

3. **同期問題の回避**: TinyDB 案では3つのストレージを手動同期する必要があり、整合性リスクが大きい。SQLite なら TRIGGER で自動同期可能

4. **移行コスト最小**: 既存コードに sqlite-vec の仮想テーブルとEmbedding生成ロジックを追加するだけ。既存のテーブル・FTS5・クエリはそのまま維持

5. **段階的導入が可能**: ベクトル検索は既存機能に影響を与えずに追加できる。Embedding 生成は非同期・バッチで対応可能

**前回の結論（C → B の段階移行）からの変更点:**

前回は「短期: SQLite + JSON1、中長期: TinyDB」と結論づけたが、ベクトル検索を前提とすると **TinyDB への移行メリットが大幅に減少**する。TinyDB のドキュメント指向の利点よりも、SQLite のストレージ統合・検索統合の利点が上回る。

**改訂推奨:**

- **短期**: 選択肢 C — SQLite + JSON1 拡張の活用強化（変更なし）
- **中長期**: 選択肢 C 拡張 — SQLite + JSON1 + sqlite-vec の統合アーキテクチャ
  - FTS5 trigram でキーワード検索（既存）
  - sqlite-vec でセマンティック検索（追加）
  - JSON1 でドキュメントクエリの改善（追加）
  - すべて単一 DB ファイル内で完結

**TinyDB への移行は見送り**が妥当。JSON ボイラープレートの問題は JSON1 拡張の活用と、ヘルパー関数の改善で対処可能。
