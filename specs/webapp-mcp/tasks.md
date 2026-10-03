# webapp-mcp（Web アプリ連携 MCP サーバ）タスク分解

> `design.md` / `tool-design.md` がすべて承認された後に作成する。
> タスクは 1〜4 時間程度で完了できる粒度にする。

## 概要

- ソース配置: `src/webapp-mcp/server`（MCP サーバ）、`src/webapp-mcp/tests`（`unit/`、`integration/`）
- 起動: `uvicorn app.main:app --host 127.0.0.1 --port 9001`（作業ディレクトリ `src/webapp-mcp/server`、venv は `server/venv`）
- SDK: `mcp` 2.x（`MCPServer`）。Web アプリの Python は import しない。Web アプリの DB に接続しない。
- 結合テストは、開発環境の Web アプリ（6 機能のバックエンド）と、`api-key-management` の画面で発行した API キーを使う。API キーは環境変数 `WEBAPP_TEST_API_KEY` で渡し、無いときは結合テストをスキップする。

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
| T-014 | 経費管理ツールの改訂（売掛区分・支払日毎の集計への対応） | REQ-010 / design.md §ツール一覧、tool-design.md §経費管理 | `src/webapp-mcp/server/app/tools/expense.py`、`tests/unit/test_tools.py`、`tests/integration/test_end_to_end.py` | 2h | 下記 T-014 |
| T-015 | ROOM のツールの追加（サイトの機能 `room`、ツール 8 個、単体テスト） | REQ-012〜REQ-016 / design.md §利用する Web アプリの機能・§モジュール構成・§ツール一覧、tool-design.md §ROOM | `src/webapp-mcp/server/app/sites.py`、`server/app/tools/room.py`、`server/app/main.py`、`tests/conftest.py`、`tests/unit/test_tools.py`、`tests/unit/test_config_sites.py` | 4h | 下記 T-015 |
| T-016 | ROOM の結合テストと、手順書・設定の更新 | REQ-003、REQ-014〜REQ-016 / design.md §テスト・§配置 | `tests/integration/test_end_to_end.py`、`src/webapp-mcp/README.md`、`server/sites.toml`（運用の設定。リポジトリに含めない） | 3h | 下記 T-016 |
| T-017 | ROOM の定期実行のツールの改訂（個別切替・祝日の扱い・実行日の取り方）と、手順書の更新 | REQ-016 / design.md §ROOM のツールの考え方、tool-design.md §`room_list_timers`・`room_create_timer`・`room_update_timer` | `server/app/tools/room.py`、`tests/unit/test_room_tools.py`、`tests/integration/test_end_to_end.py`、`src/webapp-mcp/README.md` | 3h | 下記 T-017 |
| T-018 | 契約管理のツールの追加（サイトの機能 `contract-management`、ツール 6 個、単体テスト） | REQ-012、REQ-013、REQ-017、REQ-018 / design.md §利用する Web アプリの機能・§モジュール構成・§ツール一覧・§契約管理のツールの考え方、tool-design.md §契約管理 | `server/app/sites.py`、`server/app/tools/contract.py`、`server/app/main.py`、`tests/conftest.py`、`tests/unit/test_contract_tools.py`、`tests/unit/test_config_sites.py` | 4h | 下記 T-018 |
| T-019 | 契約管理の結合テストと、手順書・設定の更新 | REQ-003、REQ-017、REQ-018 / design.md §テスト・§配置 | `tests/integration/test_end_to_end.py`、`src/webapp-mcp/README.md`、`specs/templates/sites.example.toml`、`server/sites.toml`（運用の設定。リポジトリに含めない） | 3h | 下記 T-019 |

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

## T-014: 経費管理ツールの改訂（売掛区分・支払日毎の集計への対応）

**実装パス**: `server/app/tools/expense.py`、`tests/unit/test_tools.py`、`tests/integration/test_end_to_end.py`

**内容**

Web アプリの経費管理機能の改訂（`payment_methods` への `is_credit`・`is_credit_payment` の追加、`GET /reports/payment-month` の廃止と `GET /reports/payment-date` への置き換え）に、ツールを合わせる。

- `expense_get_usage_date_report` に任意引数 `include_credit`（boolean、既定 `false`）を追加し、`GET /reports/usage-date` のクエリへそのまま渡す。
- `expense_get_payment_month_report` を削除し、`expense_get_payment_date_report`（`GET /reports/payment-date?year_month=`）を追加する。ツール名の変更に伴い、ログに出す `tool` の値もこれに合わせる。
- `expense_list_payment_methods` の説明文を、`tool-design.md` のとおり売掛区分に触れる内容に更新する（呼び出し・応答の組み立ては変更しない。Web アプリの応答をそのまま返すため `is_credit`・`is_credit_payment` は自動的に含まれる）。
- 単体テスト（`test_tools.py`）を、`expense_get_payment_month_report` の呼び出し確認から `expense_get_payment_date_report`（`/reports/payment-date` を呼ぶこと、`year_month` を渡すこと、応答をそのまま返すこと）に置き換える。`expense_get_usage_date_report` のテストに、`include_credit` 省略時（クエリに `false` が渡ること）と指定時の確認を追加する。
- 結合テスト（`test_end_to_end.py`）の `payment-month` 関連の呼び出しを `payment-date` に置き換える。

**完了条件**

- [ ] `expense_get_payment_date_report` が `GET /reports/payment-date` を呼び、`tool-design.md` どおりの出力を返す
- [ ] `expense_get_payment_month_report` はツール一覧・実装・テストのいずれからも無くなっている
- [ ] `expense_get_usage_date_report` が、`include_credit` 省略時は `false`、指定時はその値をクエリへ渡す
- [ ] `expense_list_payment_methods` の応答に `is_credit`・`is_credit_payment` が含まれることを単体テストで確かめる
- [ ] `server/venv` の pytest（単体）と、`WEBAPP_TEST_API_KEY` を設定した結合テストが全件成功する

## T-015: ROOM のツールの追加

**実装パス**: `server/app/sites.py`、`server/app/tools/room.py`、`server/app/main.py`、`tests/conftest.py`、`tests/unit/test_tools.py`、`tests/unit/test_config_sites.py`

**内容**

- `sites.py`: サイトの機能名（`FEATURES`）に `room` を足す。`sites.toml` に `room` の接続先が無いサイトは、従来どおり起動でき、ROOM のツールだけが「このサイトでは、この機能を利用できません（接続先が設定されていません）」を返す。
- `tools/room.py`: ツール 8 個（`room_get_state`、`room_set_device_state`、`room_run_scene`、`room_list_timers`、`room_create_timer`、`room_update_timer`、`room_set_timer_enabled`、`room_delete_timer`）を、`tool-design.md` のとおりに実装する。`main.py` で `room.register` を呼ぶ。
  - 名前・説明・注釈（`READ`・`WRITE`・`DELETE`）・入力（型・必須・`pattern`・列挙）・出力・エラー文を、`tool-design.md` と一致させる。引数 `site` を持たせる。
  - `room_set_device_state` の `device` は、`ceiling_light`・`indirect_light`・`indoor_speaker`・`bedside_speaker` の列挙とする。**`front_door` を含めない**。`state` は `on`・`off` の列挙。
  - `room_run_scene` の `scene`、`room_create_timer`・`room_update_timer` の `condition` と `scene` は、列挙とする。`weekdays` は 1〜7 の整数の配列。`run_time` は `HH:MM` の `pattern`。
  - `room_set_device_state` の 502 は、`ErrorMessages(extra={502: …})` で、`tool-design.md` の ROOM のエラー文（サイトの識別子を含む）にする。他のツールの 502 は、共通の文のまま。
  - 出力は、Web アプリの応答の項目名・値を変えない。削除は `{ "deleted": true, "id": … }`。
  - ログ: ツール名・サイト・判断に使う引数（`device`・`state`・`scene`・`condition`・`schedule_id`）。定期実行の本文（曜日・時刻）は、識別子ではないので出さない。
- 単体テスト: `respx` のモックで確かめる。実機は動かさない。
- `tests/conftest.py` のテスト用 `sites.toml` に、`room` の接続先を足す。

**完了条件**

- [ ] `respx` のモックで、8 個のツールが呼ぶメソッド・パス・本文が、`tool-design.md` と、`claude_webapp/specs/room/api-design.md` に一致する（`PUT /devices/{device}/state` の本文は `{ "state": … }`、`POST /scenes/{scene}` は本文なし、`PUT /schedules/{id}` と `PUT /schedules/{id}/enabled` は本文あり）
- [ ] 各ツールの成功時の出力と、個別のエラー文（`room_set_device_state` の 502 と 404、`room_update_timer`・`room_set_timer_enabled`・`room_delete_timer` の 404）が、`tool-design.md` と一致する
- [ ] 注釈（`readOnlyHint`・`destructiveHint`・`idempotentHint`）が、`tool-design.md` と一致する（`room_delete_timer` だけが破壊的）
- [ ] `room_set_device_state` の入力スキーマに `front_door` が無く、`front_door` を渡すと、Web アプリを呼ばずに入力検証のエラーになる。玄関ドアを操作するツールは、ツール一覧のどこにも無い
- [ ] `room_run_scene` が、`results` に `failure` を含む 200 の応答を、エラーにせず、そのまま返す
- [ ] `weekdays`（0 や 8、重複）・`run_time`（`7:00` など）・列挙の誤りが、Web アプリを呼ばずに、入力検証のエラーになる
- [ ] `room` の接続先が無いサイトで、ROOM のツールが「接続先が設定されていません」を返し、他の機能のツールは動く
- [ ] ログに、API キー全体、機器の識別子、定期実行の本文が出ていない
- [ ] `server/venv` の pytest（単体）が、既存のテストを含めて、全件成功する

## T-016: ROOM の結合テストと、手順書・設定の更新

**実装パス**: `tests/integration/test_end_to_end.py`、`src/webapp-mcp/README.md`、`server/sites.toml`（運用の設定。リポジトリに含めない）

**内容**

- 結合テスト: 開発環境の Web アプリの ROOM（`room` のバックエンド）に対して、MCP クライアント（SDK のクライアント）からツールを呼ぶ。
  - `room_get_state`: 5 機器が返ること。玄関ドアに `battery` があること（実機への**読み取りだけ**を行う）。
  - 定期実行: `room_create_timer`（**無効**で、`condition` は `daily`、時刻は深夜）→ `room_list_timers` → `room_update_timer` → `room_set_timer_enabled` → `room_delete_timer` を 1 巡し、**失敗しても、作った定期実行を削除して終える**。
  - **機器を操作するツール（`room_set_device_state`、`room_run_scene`）は、結合テストでは呼ばない**。開発環境の ROOM が実機の SwitchBot を操作するため。これらは、単体テスト（T-015）と、利用者による実機の確認で確かめる。
- `README.md`: 「4 機能」の記述を 5 機能（`room` を含む）に直す。API キーの持ち主に、`room` の割当が必要なことを足す。ROOM のツールの説明（玄関ドアは参照のみ、機器の操作は実機が動く、定期実行のツール名が `timer` であること）を足す。結合テストの前提に、ROOM のバックエンドの起動と、`room` の割当を足す。
- `server/sites.toml`: 運用の設定に、`room` の接続先を足す（開発では `http://127.0.0.1:8011`）。API キーは、既存のものを使う（持ち主に `room` が割り当てられていること）。

**完了条件**

- [ ] 結合テストで、`room_get_state` が 5 機器を返し、定期実行の登録・一覧・更新・有効／無効の切り替え・削除が行え、削除後は一覧から消える
- [ ] 結合テストが、途中で失敗しても、作った定期実行を残さない
- [ ] 結合テストが、機器を操作するツールを呼ばない（実機が動かない）
- [ ] `WEBAPP_TEST_API_KEY` が無いときは、ROOM の結合テストもスキップされる
- [ ] `README.md` が、5 機能と ROOM のツールの注意（玄関ドアは参照のみ、機器の操作は実機が動く）を示し、秘密の値の実例を含まない
- [ ] `server/venv` の pytest（単体）と、`WEBAPP_TEST_API_KEY` を設定した結合テストが、全件成功する

## T-017: ROOM の定期実行のツールの改訂

**実装パス**: `server/app/tools/room.py`、`tests/unit/test_room_tools.py`、`tests/integration/test_end_to_end.py`、`README.md`

**内容**

- `tools/room.py`: 次の 3 つのツールを、`tool-design.md` の改訂のとおりに直す。
  - `room_create_timer`・`room_update_timer`: 引数に `holiday_mode`（`none`・`include`・`exclude`）、`day_shift`（`same`・`before`・`after`）、`device`（`ceiling_light`・`indirect_light`・`indoor_speaker`・`bedside_speaker`。**`front_door` を含めない**）、`state`（`on`・`off`）を足す。`condition` から `holiday` を外す。`scene` は、必須でなくなる（個別切替では省略）。
  - 送る本文は、渡された引数だけを、Web アプリの `POST` / `PUT /schedules` の項目名のまま送る（省略した項目は送らない。`scene` と `device` + `state` の整合は、検査せず、Web アプリに任せる）。
  - `room_list_timers`: 出力は、Web アプリの応答のまま（`holiday_mode`・`day_shift`・`device`・`state` が含まれる）。
  - 3 つのツールの説明を、`tool-design.md` のとおりにする（祝日の扱い、実行日の取り方、基準日の考え方、実行内容はどちらか一方、更新で省略すると既定に戻ること、玄関ドアは指定できないこと）。
  - ログ: 判断に使う引数（`condition`・`holiday_mode`・`day_shift`・`device`・`state`・`scene`・`schedule_id`）。曜日・時刻は、これまでどおり出さない。
- 単体テスト（`respx` のモック。実機は動かさない）と、結合テスト（開発環境の ROOM。**無効**の定期実行の登録・更新・削除だけで、機器は動かさない）を直す。
- `README.md`: 定期実行のツールの説明に、個別切替・祝日の扱い・実行日の取り方を足し、`holiday` の記述を除く。

**完了条件**

- [ ] 3 つのツールの入力スキーマが、`tool-design.md` と一致する。`device` に `front_door` が無く、`condition` に `holiday` が無い。列挙の誤り（`holiday_mode`・`day_shift`・`device`・`state`・`condition`）が、Web アプリを呼ばずに、入力検証のエラーになる
- [ ] `room_create_timer` が、`holiday_mode` と `day_shift` を指定したとき、その値のまま本文に載せて `POST /schedules` を呼ぶ。指定しないときは、本文に載せない
- [ ] 個別切替（`device` + `state`、`scene` なし）の登録・更新で、`scene` を本文に載せない。一括切替では、`device`・`state` を載せない
- [ ] `scene` と `device` の両方、`device` だけ、毎日なのに `holiday_mode` を指定した場合は、ツールは検査せず Web アプリを呼び、Web アプリの 400 を、共通エラー文として返す
- [ ] `room_list_timers` が、`scene` が `null`・`device`・`state` が値を持つ個別切替の要素を、そのまま返す
- [ ] `room_update_timer` の説明に、「省略した祝日の扱いと実行日の取り方は既定に戻る」と、基準日の考え方が書かれている
- [ ] 結合テストで、個別切替・祝日の扱い・実行日の取り方を指定した定期実行の登録・一覧・更新・有効／無効の切り替え・削除が行え、途中で失敗しても、作った定期実行を残さない。機器は動かない
- [ ] ログに、定期実行の曜日・時刻が出ていない
- [ ] `server/venv` の pytest（単体）が、既存のテストを含めて、全件成功する。`WEBAPP_TEST_API_KEY` を設定した結合テストも、全件成功する

## T-018: 契約管理のツールの追加

**実装パス**: `server/app/sites.py`、`server/app/tools/contract.py`、`server/app/main.py`、`tests/conftest.py`、`tests/unit/test_contract_tools.py`、`tests/unit/test_config_sites.py`

**内容**

- `sites.py`: サイトの機能名（`FEATURES`）に `contract-management` を足す。`sites.toml` に `contract-management` の接続先が無いサイトは、従来どおり起動でき、契約管理のツールだけが「このサイトでは、この機能を利用できません（接続先が設定されていません）」を返す。
- `tools/contract.py`: ツール 6 個（`contract_list_contracts`、`contract_get_contract`、`contract_list_categories`、`contract_get_cancellation_plan`、`contract_create_contract`、`contract_update_contract`）を、`tool-design.md` のとおりに実装する。`main.py` で `contract.register` を呼ぶ。
  - 名前・説明・注釈（`READ`・`WRITE`）・入力（型・必須・列挙）・出力・エラー文を、`tool-design.md` と一致させる。引数 `site` を持たせる。
  - **`password` の引数を、どのツールにも持たせない。** `contract_create_contract`・`contract_update_contract` に `password` が渡されても、Web アプリへ送らない。出力は、Web アプリの応答のまま（パスワードの値は、そもそも応答に無い）。
  - 送る本文は、渡された引数だけを、Web アプリの `POST` / `PATCH /contracts` の項目名のまま送る（省略した項目は送らない。契約を伴うか伴わないかと、項目の組み合わせの整合は、検査せず、Web アプリに任せる）。`contract_update_contract` の `contract_id` は、パスに入れ、本文には入れない。
  - `contract_list_contracts` の絞り込みは、渡された引数だけを、クエリ（`keyword`、`category_id`、`status`、`has_contract`、`password_unset`）に載せる。真偽は `true` / `false` の文字列。
  - `status`・`fee_cycle`・`contract_date_precision`・`login_methods` の要素は、列挙とする。`fee_amount` などの整数は `integer`。
  - 404 は、契約のツール（`contract_get_contract`・`contract_update_contract`）で、`tool-design.md` の専用の文（`contract_list_contracts` を案内）にする。`contract_update_contract` の 409 は、専用の文（Web アプリの `detail` を含む）にする。他は共通の文のまま。
  - 出力は、Web アプリの応答の項目名・値を変えない。
  - ログ: ツール名・サイト・判断に使う引数（`contract_id`、`category_id`、`status`、`has_contract`、`password_unset`、`keyword` の有無）。**契約の名称、ユーザ名、登録メールアドレス、2 段階認証の送付先、解約方法、メモは出さない。**
- 単体テスト: `respx` のモックで確かめる。
- `tests/conftest.py` のテスト用 `sites.toml` に、`contract-management` の接続先を足す。

**完了条件**

- [ ] `respx` のモックで、6 個のツールが呼ぶメソッド・パス・クエリ・本文が、`tool-design.md` と、`claude_webapp/specs/contract-management/api-design.md` に一致する（`GET /contracts` のクエリ、`POST /contracts` と `PATCH /contracts/{id}` の本文）
- [ ] 各ツールの成功時の出力と、個別のエラー文（`contract_get_contract`・`contract_update_contract` の 404、`contract_update_contract` の 409）が、`tool-design.md` と一致する
- [ ] 注釈（`readOnlyHint`・`destructiveHint`・`idempotentHint`）が、`tool-design.md` と一致する（参照の 4 個は読み取り専用。登録・更新は書き込みで、破壊的でない）
- [ ] どのツールの入力スキーマにも `password` が無く、`contract_create_contract`・`contract_update_contract` に `password` を渡しても、Web アプリへの要求の本文に `password` が含まれない。削除・パスワードの取得・アカウント一覧・区分の管理・解約順の保存のツールは、ツール一覧のどこにも無い
- [ ] 列挙の誤り（`status`・`fee_cycle`・`contract_date_precision`・`login_methods`）と、型の誤りが、Web アプリを呼ばずに、入力検証のエラーになる
- [ ] 省略した引数が、本文・クエリに載らない。`contract_update_contract` が `contract_id` を本文に載せない
- [ ] 契約を伴わないのに契約の項目を渡す、維持費の金額だけを渡す、などの場合は、ツールは検査せず Web アプリを呼び、Web アプリの 400 を、共通エラー文として返す
- [ ] `contract-management` の接続先が無いサイトで、契約管理のツールが「接続先が設定されていません」を返し、他の機能のツールは動く
- [ ] ログに、API キー全体と、契約の名称・ユーザ名・登録メールアドレス・2 段階認証の送付先・解約方法・メモが出ていない
- [ ] `server/venv` の pytest（単体）が、既存のテストを含めて、全件成功する

## T-019: 契約管理の結合テストと、手順書・設定の更新

**実装パス**: `tests/integration/test_end_to_end.py`、`src/webapp-mcp/README.md`、`specs/templates/sites.example.toml`、`server/sites.toml`（運用の設定。リポジトリに含めない）

**内容**

- 結合テスト: 開発環境の Web アプリの契約管理（`contract-management` のバックエンド）に対して、MCP クライアント（SDK のクライアント）からツールを呼ぶ。
  - `contract_list_categories`: 「その他」が先頭にあること。
  - 契約: 結合テスト用の契約（名称を固定。例「webapp-mcp 結合テスト用」）を、**一覧で探し、無ければ `contract_create_contract` で登録する**（API キーでは契約を削除できないため、毎回は作らず、1 件を使い回す）。`contract_get_contract` → `contract_update_contract`（全項目を渡す）→ `contract_list_contracts`（絞り込み）の順に確かめる。
  - **パスワードの値が、どの応答にも無い**こと。登録した契約が `password_unset` を持つこと。`contract_update_contract` で更新しても、`has_password` が変わらないこと。
  - `contract_get_cancellation_plan`: 取得できること（読み取りだけ）。
  - 契約を削除するツールは無いため、結合テスト用の契約は、テストのあとも 1 件残る（運用者が、Web アプリの画面で削除できる）。
- `README.md`: 「5 機能」の記述を 6 機能（`contract-management` を含む）に直す。API キーの持ち主に、`contract-management` の割当が必要なことを足す。契約管理のツールの説明（パスワードの値は入出力しない、パスワードは人が画面で入力する、更新は全項目の置き換えで先に取得して渡す、削除・区分の管理・解約順の保存は人が画面で行う）を足す。結合テストの前提に、契約管理のバックエンドの起動と、`contract-management` の割当を足す。
- `specs/templates/sites.example.toml`: `contract-management` の接続先の例を足す。
- `server/sites.toml`: 運用の設定に、`contract-management` の接続先を足す（開発では `http://127.0.0.1:8012`）。API キーは、既存のものを使う（持ち主に `contract-management` が割り当てられていること）。

**完了条件**

- [ ] 結合テストで、`contract_list_categories` が「その他」を返し、契約の登録（または、既存のテスト用の契約の再利用）・取得・更新・一覧の絞り込みが行える
- [ ] 結合テストで、どの応答にもパスワードの値が無く、更新しても `has_password` が変わらない
- [ ] 結合テストが、2 回続けて実行しても、テスト用の契約を増やさない（1 件を使い回す）
- [ ] `WEBAPP_TEST_API_KEY` が無いときは、契約管理の結合テストもスキップされる
- [ ] `README.md` が、6 機能と契約管理のツールの注意（パスワードの値は入出力しない、削除はできない）を示し、秘密の値の実例を含まない
- [ ] `server/venv` の pytest（単体）と、`WEBAPP_TEST_API_KEY` を設定した結合テストが、全件成功する

## 承認

現在の状態: 承認済み

| 日時 | 状態 | 変更概要 |
|------|------|----------|
| 2026-09-26 03:08 | 未承認 | 初版 |
| 2026-09-26 03:08 | 承認済み | 初版を承認 |
| 2026-09-27 | 未承認 | 経費管理ツールの改訂（T-014。売掛区分の追加、`expense_get_payment_month_report` を `expense_get_payment_date_report` に置き換え）を追加（REQ-010） |
| 2026-09-27 | 承認済み | T-014 を承認 |
| 2026-10-01 13:18 | 未承認 | ROOM のツール追加（REQ-014〜REQ-016）のタスク T-015（サイトの機能・ツール 8 個・単体テスト）と T-016（結合テスト・手順書・設定）を追加。結合テストでは、実機が動く機器の操作のツールを呼ばない |
| 2026-10-01 13:19 | 承認済み | ROOM のツール追加のタスク（T-015・T-016）を承認 |
| 2026-10-02 11:15 | 未承認 | ROOM の定期実行のツールの改訂のタスク T-017 を追加（REQ-016 の改訂への対応） |
| 2026-10-02 11:15 | 承認済み | T-017 を承認 |
| 2026-10-03 12:56 | 未承認 | 契約管理のツール追加（REQ-017、REQ-018）のタスク T-018（サイトの機能・ツール 6 個・単体テスト）と T-019（結合テスト・手順書・設定）を追加。パスワードの引数は持たせない。結合テストは、契約を削除できないため、テスト用の契約 1 件を使い回す |
| 2026-10-03 12:59 | 承認済み | 契約管理のツール追加のタスク（T-018・T-019）を承認 |
