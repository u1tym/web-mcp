# webapp-mcp（Web アプリ連携 MCP サーバ）タスク分解

> `design.md` / `tool-design.md` がすべて承認された後に作成する。
> タスクは 1〜4 時間程度で完了できる粒度にする。

## 概要

- ソース配置: `src/webapp-mcp/server`（MCP サーバ）、`src/webapp-mcp/tests`（`unit/`、`integration/`）
- 起動: `uvicorn app.main:app --host 127.0.0.1 --port 9001`（作業ディレクトリ `src/webapp-mcp/server`、venv は `server/venv`）
- SDK: `mcp` 2.x（`MCPServer`）。Web アプリの Python は import しない。Web アプリの DB に接続しない。
- 結合テストは、開発環境の Web アプリ（4 機能のバックエンド）と、`api-key-management` の画面で発行した API キーを使う。API キーは環境変数 `WEBAPP_TEST_API_KEY` で渡し、無いときは結合テストをスキップする。

## タスク一覧

| No | タスク | 対応する要件/設計 | 実装パス | 所要時間 | 完了条件 |
|----|--------|--------------------|----------|----------|----------|
| T-001 | 土台（venv・設定・サイト・ログ・起動時の確認） | REQ-003、REQ-013 / design.md §起動・§設定・§モジュール構成（`config`・`sites`・`logger`） | `src/webapp-mcp/server/` | 3h | 下記 T-001 |
| T-002 | Web アプリの API クライアント（エラーの対応付け） | REQ-012、REQ-013 / design.md §処理の流れ、tool-design.md §共通エラー | `src/webapp-mcp/server/app/webapp_client.py`、`tests/unit/` | 3h | 下記 T-002 |
| T-003 | 認証の状態の保存（SQLite）とパスフレーズ | REQ-001、REQ-002 / design.md §認証の状態・§運用コマンド | `src/webapp-mcp/server/app/auth/`、`server/scripts/hash_passphrase.py` | 3h | 下記 T-003 |
| T-004 | OAuth の provider（登録・認可・トークン・失効） | REQ-001、REQ-002 / design.md §OAuth のエンドポイント・§リダイレクト URI の許可リスト | `src/webapp-mcp/server/app/auth/provider.py` | 4h | 下記 T-004 |
| T-005 | サインイン画面 | REQ-001 / design.md §サインイン画面 | `src/webapp-mcp/server/app/auth/signin.py` | 3h | 下記 T-005 |
| T-006 | サーバの組み立てと一括失効のコマンド | REQ-001〜REQ-003 / design.md §処理の流れ・§Origin の検証・§運用コマンド | `src/webapp-mcp/server/app/main.py`、`server/scripts/revoke_all.py` | 2h | 下記 T-006 |
| T-007 | 認証の単体テスト | REQ-001、REQ-002、REQ-013 | `src/webapp-mcp/tests/unit/` | 3h | 下記 T-007 |
| T-008 | 共通・スケジュールのツール | REQ-003〜REQ-005 / tool-design.md §共通・§スケジュール | `src/webapp-mcp/server/app/tools/common.py`、`schedule.py`、`tests/unit/` | 3h | 下記 T-008〜T-011 |
| T-009 | グッズ管理のツール | REQ-006、REQ-007 / tool-design.md §グッズ管理 | `src/webapp-mcp/server/app/tools/goods.py`、`tests/unit/` | 3h | 下記 T-008〜T-011 |
| T-010 | ノウハウ管理のツール | REQ-008、REQ-009 / tool-design.md §ノウハウ管理 | `src/webapp-mcp/server/app/tools/knowhow.py`、`tests/unit/` | 2h | 下記 T-008〜T-011 |
| T-011 | 経費管理のツール（支払日の算出を含む） | REQ-010、REQ-011 / tool-design.md §経費管理 | `src/webapp-mcp/server/app/tools/expense.py`、`tests/unit/` | 3h | 下記 T-008〜T-011 |
| T-012 | 結合テスト（OAuth のフロー → ツール → Web アプリ） | REQ-001〜REQ-013 / design.md §テスト | `src/webapp-mcp/tests/integration/` | 4h | 下記 T-012 |
| T-013 | 配置の資料（nginx・systemd・手順書） | design.md §配置、rules/17-deploy.md | `src/webapp-mcp/server/nginx.example.conf`、`webapp-mcp.service.example`、`src/webapp-mcp/README.md` | 2h | 下記 T-013 |

---

## T-001: 土台（venv・設定・サイト・ログ・起動時の確認）

**実装パス**: `server/requirements.txt`、`server/app/config.py`、`server/app/sites.py`、`server/app/logger.py`、`server/.env`（ひな型 `specs/templates/server.env.example`）、`server/sites.toml`（ひな型 `specs/templates/sites.example.toml`）

**内容**

- `server/venv` を作り、`mcp`（2.x）、`httpx`、`python-dotenv`、`uvicorn`、`pytest`、`pytest-asyncio`、`respx` を入れる。
- `config.py`: `.env` の各項目を読み、型と必須を検証する。
- `sites.py`: `sites.toml` を `tomllib` で読み、既定のサイト・種別（`claude_webapp` のみ）・4 機能の URL・`SITE_<SITE>_API_KEY` の有無を検証する。サイトの解決（識別子 → 表示名・機能の URL・API キー）。
- `logger.py`: `log/webapp-mcp.log` へ「タイムスタンプ 区分 メッセージ」で出力し、サイズでローテーションする。API キーの先頭 12 文字を作る補助。

**完了条件**

- [ ] 必須項目の欠け、`default_site` の欠け、API キーの欠け、未知の種別で、理由（秘密の値を含まない）を示して失敗する
- [ ] 省略した `site` が既定のサイトに解決され、存在しないサイトは失敗になる
- [ ] ログが所定の形式で出て、`LOG_MAX_BYTES`・`LOG_BACKUP_COUNT` でローテーションする
- [ ] `.env`・`sites.toml`・`data/`・`log/`・`venv/` がリポジトリの対象外である

## T-002: Web アプリの API クライアント

**実装パス**: `server/app/webapp_client.py`、`tests/unit/test_webapp_client.py`

**内容**

- httpx の非同期クライアントで、サイト・機能・メソッド・パス・クエリ・本文を受けて Web アプリの API を呼ぶ。`Authorization: Bearer <サイトの API キー>` を付け、Cookie は送らない。タイムアウトは `WEBAPP_TIMEOUT_SECONDS`。再試行しない。
- 2xx は本文（204 は無し）を返す。それ以外は `tool-design.md` の共通エラーの文で `ToolError` を送出する。個別の文を差し込めるようにする（ツールごとの 404・409 の文）。
- ログ: 呼んだメソッド・パス・状態コード・件数・失敗の理由。API キーは先頭 12 文字だけ。

**完了条件**

- [ ] `respx` のモックで、200・201・204・400・401・403・404・409・500・タイムアウト・接続失敗の各場合の結果が `tool-design.md` と一致する
- [ ] 要求に API キーが付き、その送り先がそのサイトの URL だけである
- [ ] エラー文とログに API キー全体・URL が出ない

## T-003: 認証の状態の保存（SQLite）とパスフレーズ

**実装パス**: `server/app/auth/store.py`、`server/app/auth/passphrase.py`、`server/scripts/hash_passphrase.py`

**内容**

- `data/webapp-mcp.sqlite3` に `design.md` のテーブル（`oauth_clients`、`pending_authorizations`、`authorization_codes`、`access_tokens`、`refresh_tokens`、`signin_state`）を作る（無ければ作成）。
- トークン類は SHA-256 のハッシュで保存・照合する。期限切れ・失効済みの行を削除する処理。
- `passphrase.py`: scrypt（ソルト付き）のハッシュ文字列の作成と、定数時間の照合。
- `hash_passphrase.py`: パスフレーズを 2 回入力させ（表示しない）、一致したらハッシュ文字列を出力する。

**完了条件**

- [ ] テーブルが作られ、再起動しても状態が残る
- [ ] DB にトークン・パスフレーズの平文が無い
- [ ] 正しいパスフレーズだけが照合に成功する

## T-004: OAuth の provider

**実装パス**: `server/app/auth/provider.py`

**内容**

SDK の `OAuthAuthorizationServerProvider` を実装する。

- `register_client`: リダイレクト URI がすべて許可リスト（`MCP_ALLOWED_REDIRECT_URIS`。ループバックはポート番号を無視）に一致するときだけ登録する。一致しなければ `RegistrationError`。
- `authorize`: 保留中の認可（10 分）を保存し、`/signin?request=<ID>` を返す。
- 認可コード（5 分・1 回限り）、アクセストークン（`MCP_ACCESS_TOKEN_TTL_MINUTES`）、リフレッシュトークン（`MCP_REFRESH_TOKEN_TTL_DAYS`。0 は無期限）の発行・照合。リフレッシュはローテーションし、古いものは失効させる。無効なリフレッシュトークンは `invalid_grant`。
- アクセストークンに対象（公開 URL の `/mcp`）を記録し、`load_access_token` で返す（SDK の `validate_token_resource` で照合）。
- `revoke_token`。
- ログ: 登録（許可リストとの照合結果）、発行・更新・失効。

**完了条件**

- [ ] 許可リスト外のリダイレクト URI での登録が拒否される
- [ ] 認可コードは 1 回だけ、期限内だけ交換できる
- [ ] リフレッシュ後、古いリフレッシュトークンは使えない
- [ ] 期限切れ・失効済みのアクセストークンは照合に失敗する

## T-005: サインイン画面

**実装パス**: `server/app/auth/signin.py`

**内容**

- `GET /signin?request=<ID>`: 保留中の認可を読み、クライアント名とリダイレクト先のホスト名、パスフレーズの入力欄、「許可」「拒否」を 1 枚の HTML で返す。CSRF の値を発行してフォームに埋め込み、ハッシュを保存する。
- `POST /signin`: CSRF の値を照合する。「拒否」なら `error=access_denied` でリダイレクト URI へ戻す。「許可」なら、ロック中でなければパスフレーズを照合し、成功で認可コードを発行して `code` と `state` を付けて戻す。失敗は連続失敗回数に数え、`MCP_SIGNIN_MAX_FAILURES` で `MCP_SIGNIN_LOCK_MINUTES` の間ロックする。成功で回数を 0 に戻す。
- `design.md` の文言と応答ヘッダ（`X-Frame-Options`、CSP、`Cache-Control`、`Referrer-Policy`）。外部リソース・JavaScript なし。スマートフォンの幅で操作できる。
- ログ: サインインの成功・失敗（理由）・連続失敗回数。

**完了条件**

- [ ] 正しいパスフレーズで認可コード付きでリダイレクトされ、誤りでは画面に一文が出る
- [ ] 連続失敗の上限でロックされ、ロック中は正しいパスフレーズでも失敗する
- [ ] CSRF の値が無い・違う POST は拒否される
- [ ] 期限切れの保留中の認可では「期限切れ」の一文が出る

## T-006: サーバの組み立てと一括失効のコマンド

**実装パス**: `server/app/main.py`、`server/scripts/revoke_all.py`

**内容**

- 起動時の確認（T-001）を行い、`MCPServer` に provider・`AuthSettings`（発行者・対象の URL・DCR 有効・失効有効・スコープ `webapp`・`validate_token_resource=True`）を渡し、ツール（T-008〜T-011）とサインイン画面（T-005）を登録する。
- `streamable_http_app()` で ASGI アプリ `app` を公開する（MCP のエンドポイント `/mcp`）。`TransportSecuritySettings` で許可するホスト・`Origin` を設定する。
- 起動時と一定間隔で、期限切れの行を削除する。
- `revoke_all.py`: すべてのトークン・保留中の認可・クライアント登録を削除し、件数を出力・ログする。

**完了条件**

- [ ] `uvicorn app.main:app --port 9001` で起動し、`/.well-known/oauth-protected-resource/mcp` と `/.well-known/oauth-authorization-server` が `design.md` どおりの内容を返す
- [ ] トークンなしの `/mcp` が 401 と `WWW-Authenticate`（`resource_metadata`）を返す
- [ ] 許可していない `Origin` の要求が拒否される
- [ ] `revoke_all.py` の実行後、既存のトークンが使えない

## T-007: 認証の単体テスト

**実装パス**: `tests/unit/test_store.py`、`test_provider.py`、`test_signin.py`、`test_passphrase.py`

**完了条件**

- [ ] T-003〜T-006 の完了条件を自動テストで確かめる
- [ ] ログにパスフレーズ・トークン類が出ていないことを確かめる
- [ ] `server/venv` の pytest で全件成功する

## T-008〜T-011: ツール

各タスクで、担当するツールを `tool-design.md` のとおりに実装し、単体テストを書く。

| No | ツール |
|----|--------|
| T-008 | `list_sites`、`schedule_*`（6 個） |
| T-009 | `goods_*`（8 個） |
| T-010 | `knowhow_*`（7 個） |
| T-011 | `expense_*`（9 個） |

**内容**

- ツール名・説明・注釈・入力（型・必須・`pattern`）・出力・エラー文を `tool-design.md` と一致させる。引数 `site` を持たせる（`list_sites` を除く）。
- 出力は Web アプリの応答の項目名・値を変えない。例外: グッズの画像データを除く（T-009）、削除は `{ "deleted": true, "id": … }`。
- T-011: 支払日の省略時は、算出 API → 登録・更新 API の順に呼ぶ。算出に失敗したら登録・更新 API を呼ばない。`payment_date_is_auto` を、省略時 `true`・指定時 `false` にする。
- ログ: ツール名・サイト・判断に使う引数（本文・メモ・タイトル・キーワードの文字列は出さない）。

**完了条件（各タスク）**

- [ ] `respx` のモックで、各ツールが呼ぶメソッド・パス・クエリ・本文が `tool-design.md` と Web アプリの `api-design.md` に一致する
- [ ] 各ツールの成功時の出力と、個別のエラー文が `tool-design.md` と一致する
- [ ] 注釈（`readOnlyHint`・`destructiveHint`・`idempotentHint`）が `tool-design.md` と一致する
- [ ] T-009: 出力に `thumbnail_image_data`・`image_data` が含まれない
- [ ] T-011: 支払日の省略・指定・算出の失敗の 3 通りで、呼ぶ API と `payment_date_is_auto` が正しい

## T-012: 結合テスト

**実装パス**: `tests/integration/conftest.py`、`test_oauth_flow.py`、`test_tools.py`

**内容**

- テスト用の `.env`・`sites.toml` で MCP サーバを起動する（サイトは開発環境の Web アプリ。API キーは `WEBAPP_TEST_API_KEY`）。
- OAuth のフローを、HTTP で順に実行する: 401 → メタデータ → 登録（許可リストの URI）→ `/authorize` → サインイン画面の POST → 認可コード → `/token`（PKCE）→ リフレッシュ。
- 取得したアクセストークンで、SDK の MCP クライアント（Streamable HTTP）からツールを呼ぶ。4 機能それぞれで、登録 → 取得 → 更新 → 削除を 1 巡し、作ったデータを削除して終える。支出記録は支払日の省略で登録する。

**完了条件**

- [ ] OAuth のフローが通り、リフレッシュ後の古いリフレッシュトークンが使えない
- [ ] 4 機能で登録・取得・更新・削除がツールから行え、Web アプリの画面（または API）で結果が確かめられる
- [ ] 支払日を省略した支出記録に、Web アプリが算出した支払日と `payment_date_is_auto=true` が入る
- [ ] 誤った API キーのサイトでは、401 の共通エラー文が返る
- [ ] ログにパスフレーズ・トークン類・API キー全体・記録の本文が出ていない
- [ ] `WEBAPP_TEST_API_KEY` が無いときはスキップされる

## T-013: 配置の資料

**実装パス**: `server/nginx.example.conf`、`server/webapp-mcp.service.example`、`src/webapp-mcp/README.md`

**内容**

- nginx: `rules/17-deploy.md` の形（専用ホスト名・ルート・バッファリング無効）。
- systemd: 作業ディレクトリ、venv の uvicorn、`Restart=on-failure`、実行ユーザ。
- README: 初期設定の手順（venv、`.env` と `sites.toml` の作成、パスフレーズのハッシュの作成、API キーの発行と設定、`.env`・`data/` の権限）、起動、各クライアントでの接続手順（Claude の Web でのコネクタの追加 → モバイルでの利用、Claude Code、Microsoft 365 Copilot。Copilot のリダイレクト URI を許可リストに足す手順）、一括失効、テストの実行方法。

**完了条件**

- [ ] README の手順だけで、別の環境に配置して接続できる内容になっている
- [ ] 秘密の値の実例（本物のキー・トークン）を含まない

## 承認

現在の状態: 承認済み

| 日時 | 状態 | 変更概要 |
|------|------|----------|
| 2026-09-26 03:08 | 未承認 | 初版 |
| 2026-09-26 03:08 | 承認済み | 初版を承認 |
