# MCP サーバの実装方式

> `src/**/server/**/*.py` を編集するとき

MCP サーバは `src/<server-name>/server/` に置く。

## 利用技術

- 言語: **python**（引数・戻り値に型ヒントを付ける）
- MCP の実装: 公式の Python SDK（パッケージ `mcp`）。独自に JSON-RPC を実装しない。
- 通信方式（トランスポート）: **Streamable HTTP**。サーバとして常駐させ、ネットワーク越しに MCP クライアントから接続させる。stdio は使わない。
- Web アプリの API の呼び出し: **httpx**（詳細は `rules/13-webapp-api.md`）
- MCP クライアントの認証: 公式 SDK の認可サーバの仕組みで、組み込みの OAuth 認可サーバを動かす（詳細は `rules/14-security.md`）
- 認証の状態（クライアント登録・トークンのハッシュ・サインインの失敗回数）の保存: **SQLite**（Python 標準の `sqlite3`）。ファイルは `server/data/` に置く
- 仮想環境は、**このディレクトリ配下** に `venv/` として作る。システム Python に直接依存しない。
- その venv を有効化し、このディレクトリをカレントにして起動する（ASGI アプリとして **uvicorn** で起動する。例: `uvicorn app.main:app --port 9001`）。

```python
# ❌ BAD
def list_items(client):
    ...

# ✅ GOOD
async def list_items(client: WebappClient) -> list[Item]:
    ...
```

## ツール

- ツール名は snake_case で、`<機能の短縮名>_<動詞>_<対象>` とする（例: `schedule_list_categories`、`goods_create_person`）。
- ツールの説明（description）は、MCP クライアントの AI が読んで使い分けられるように、何をするか・いつ使うか・注意点を日本語で書く。
- 入力は型付きの引数で定義し、SDK に入力スキーマを生成させる。必須・任意と、値の形式（日付の書式など）を説明に書く。
- 1 つのツールは、原則として Web アプリの API 1 つに対応させる。複数の API をまとめるときは `tool-design.md` にその理由と呼び出す順序を書く。
- ツールには注釈（annotations）を付ける。
  - 参照だけのツール: `readOnlyHint=true`
  - 削除など、元に戻せない変更をするツール: `destructiveHint=true`
  - 同じ入力で何度呼んでも結果が同じツール: `idempotentHint=true`
- 出力は、Web アプリの API の応答を元に、AI が読みやすい JSON（構造化出力）で返す。応答の項目名・値を勝手に言い換えない。

## エラーの返し方

- Web アプリの API の失敗（入力不正・対象なし・重複・権限なしなど）は、MCP のプロトコルエラーではなく、**ツールの実行結果のエラー**（`isError`）として返す。AI が読んで次の行動を決められる日本語の一文にする。
- 内部の詳細（例外のスタック、URL、ヘッダ）はエラー文に含めない。ログにだけ残す（`rules/16-logging.md`）。

## 設定値

このサーバの `server/.env` から取得する。コードに平文で埋め込まない。

代表的なもの:

- 待ち受けるホストとポート（`MCP_HOST`、`MCP_PORT`）
- 許可する Origin（`MCP_ALLOWED_ORIGINS`。後述）
- 公開 URL（`MCP_PUBLIC_URL`。OAuth の発行者・トークンの対象・メタデータの URL の基準）
- OAuth の設定（`MCP_SIGNIN_PASSPHRASE_HASH`、`MCP_SIGNIN_MAX_FAILURES`、`MCP_SIGNIN_LOCK_MINUTES`、`MCP_ACCESS_TOKEN_TTL_MINUTES`、`MCP_REFRESH_TOKEN_TTL_DAYS`、`MCP_ALLOWED_REDIRECT_URIS`。`rules/14-security.md`）
- 認証の状態の保存先（`MCP_DATA_DIR`。既定 `data`）
- サイトの構成ファイルの場所（`MCP_SITES_FILE`）と、サイトごとの API キー（`SITE_<SITE>_API_KEY`。`rules/13-webapp-api.md`）
- Web アプリの API 呼び出しのタイムアウト（`WEBAPP_TIMEOUT_SECONDS`）
- ログのローテーション（`LOG_MAX_BYTES`、`LOG_BACKUP_COUNT`。`rules/16-logging.md`）

ひな型は `specs/templates/server.env.example`。

サイトの構成（識別子・表示名・種別・各機能の API 基点 URL）は `server/sites.toml` に書く（ひな型は `specs/templates/sites.example.toml`）。API キーは `sites.toml` に書かない。

## サインイン画面

MCP サーバは原則として画面を持たない。例外として、OAuth のサインイン画面（`rules/14-security.md`）だけを持つ。

- サーバ側で HTML を組み立てて返す 1 枚のページとする。フロントエンドの SPA・ビルドの仕組みは作らない。
- 外部の CSS・JavaScript・フォントを読み込まない。スタイルはページ内に書き、JavaScript は使わない。
- 置くもの: 要求しているクライアントの名前、リダイレクト先のホスト名、パスフレーズの入力欄、許可ボタン、拒否ボタン、失敗時のメッセージ（内部理由を含まない一文）。
- スマートフォンの幅でも操作できるようにする（`viewport` の指定、入力欄とボタンの高さ 44px 以上）。
- 文言は日本語とする。

## 運用コマンド

- 画面の代わりに、`server/scripts/` にコマンドラインの運用コマンドを置く。
  - パスフレーズのハッシュを作るコマンド（入力は画面に表示しない）
  - すべてのトークンとクライアント登録を失効させるコマンド
- 運用コマンドは、MCP サーバと同じ venv と `.env` を使う。

## Origin の検証

- Streamable HTTP では、DNS リバインディング対策として、要求の `Origin` ヘッダを検証する。`Origin` があり、かつ `MCP_ALLOWED_ORIGINS` に含まれないときは拒否する。
- `*` は使わない。
- 開発時は `127.0.0.1` で待ち受ける。
