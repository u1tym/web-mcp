# webapp-mcp（Web アプリ連携 MCP サーバ）全体設計

> ツールごとの入力スキーマ・出力・エラーは書かない → `tool-design.md`

## 全体構成

本設計は `requirements.md` の REQ-001〜REQ-018 を満たす。

```
MCP クライアント                         MCP サーバ（webapp-mcp）                        Web アプリ（サイトごと）
 Claude（Web/Desktop/モバイル）─┐        ┌───────────────────────────────┐           ┌ schedule
 Claude Code ───────────────────┼─https─▶│ nginx ─▶ uvicorn（127.0.0.1:9001）│─API キー─▶├ goods-management
 Microsoft 365 Copilot ─────────┘ OAuth   │  ├ OAuth 認可サーバ＋サインイン画面 │  Bearer   ├ knowhow-management
                                  トークン │  ├ MCP（/mcp）＋ツール             │           ├ expense-management
                                          │  └ SQLite（認証の状態）            │           ├ room
                                          └───────────────────────────────┘           └ contract-management
```

- MCP サーバは 1 プロセス。公式 Python SDK（`mcp` 2.x）の `MCPServer` で、MCP のエンドポイント・OAuth 認可サーバ・サインイン画面を 1 つの ASGI アプリとして提供する。
- MCP クライアントは OAuth のアクセストークンで MCP サーバに接続する。MCP サーバは、サイトごとに保持した Web アプリの API キーで Web アプリの API を呼ぶ。受け取ったアクセストークンを Web アプリへ渡さない。
- 公開は専用ホスト名のルート（`rules/17-deploy.md`）。例: `https://mcp.example.com`（以下「公開 URL」）。MCP のエンドポイントは `<公開 URL>/mcp`。
- 認証の状態（クライアント登録・トークンのハッシュ・サインインの失敗回数）は SQLite に保存する。業務データは持たない。

関連ドキュメント: `requirements.md` / `tool-design.md`

## 利用する Web アプリの機能

| 機能（`sites.toml` のキー） | 契約（Web アプリの SPEC） |
|------------------------------|----------------------------|
| `schedule` | `claude_webapp/specs/schedule/api-design.md` |
| `goods-management` | `claude_webapp/specs/goods-management/api-design.md` |
| `knowhow-management` | `claude_webapp/specs/knowhow-management/api-design.md` |
| `expense-management` | `claude_webapp/specs/expense-management/api-design.md` |
| `room` | `claude_webapp/specs/room/api-design.md` |
| `contract-management` | `claude_webapp/specs/contract-management/api-design.md` |

各機能の API は「対象機能の API キー認証」（`claude_webapp/specs/api-key-management/api-design.md`）で呼ぶ。サイトの構成（`sites.toml`）と API キー（`.env`）の扱いは `rules/13-webapp-api.md`。

## サーバ設計

### 起動

- 作業ディレクトリ: `src/webapp-mcp/server`
- 仮想環境: `venv/`（Python 3.11 以上）
- 依存: `mcp`（2.x）、`httpx`、`python-dotenv`、`uvicorn`。テストに `pytest`、`pytest-asyncio`、`respx`
- 起動: `uvicorn app.main:app --host 127.0.0.1 --port 9001`
- 本番: systemd のサービスとして常駐させる（配置例 `server/webapp-mcp.service.example`）。nginx の配置例は `server/nginx.example.conf`
- 起動時の確認（失敗したら起動しない。理由はログと標準エラーに出す。秘密の値は出さない）
  - `.env` の必須項目（`MCP_PUBLIC_URL`、`MCP_SIGNIN_PASSPHRASE_HASH`）がある
  - `sites.toml` を読め、`default_site` が存在し、各サイトの種別が `claude_webapp` である
  - 各サイトの `SITE_<SITE>_API_KEY` が `.env` にある
  - `MCP_DATA_DIR` に SQLite のファイルを作成・更新できる（無ければテーブルを作る）

### 設定

`server/.env`（ひな型 `specs/templates/server.env.example`）:

| 項目 | 本サーバでの値・既定 |
|------|------------------------|
| `MCP_HOST` / `MCP_PORT` | `127.0.0.1` / `9001` |
| `MCP_PUBLIC_URL` | 公開 URL（開発時は `http://127.0.0.1:9001`） |
| `MCP_ALLOWED_ORIGINS` | 許可する `Origin`（後述） |
| `MCP_SIGNIN_PASSPHRASE_HASH` | パスフレーズの scrypt ハッシュ（運用コマンドで作る） |
| `MCP_SIGNIN_MAX_FAILURES` / `MCP_SIGNIN_LOCK_MINUTES` | `5` / `15` |
| `MCP_ACCESS_TOKEN_TTL_MINUTES` | `60` |
| `MCP_REFRESH_TOKEN_TTL_DAYS` | `90`（REQ-002。0 は無期限） |
| `MCP_ALLOWED_REDIRECT_URIS` | 後述の許可リスト |
| `MCP_DATA_DIR` | `data` |
| `MCP_SITES_FILE` | `sites.toml` |
| `SITE_<SITE>_API_KEY` | サイトごとの Web アプリの API キー |
| `WEBAPP_TIMEOUT_SECONDS` | `10` |
| `LOG_MAX_BYTES` / `LOG_BACKUP_COUNT` | `1048576` / `5` |

`server/sites.toml`（ひな型 `specs/templates/sites.example.toml`）: 既定のサイトと、サイトごとの識別子・表示名・種別・6 機能の API 基点 URL。MCP サーバと Web アプリを同じホストに置くときは、Web アプリの各バックエンドの `http://127.0.0.1:<port>` を書いてよい（通信がホストの外に出ないため）。別のホストのときは https の URL を書く。

### モジュール構成

| ファイル | 役割 |
|----------|------|
| `app/main.py` | 起動時の確認、`MCPServer` の生成（ツール・認可サーバ・サインイン画面の登録）、ASGI アプリ `app`（`streamable_http_app()`）の公開 |
| `app/config.py` | `.env` の読み込みと検証 |
| `app/sites.py` | `sites.toml` の読み込みと検証、サイトの解決（識別子 → 表示名・API 基点 URL・API キー）、既定のサイト |
| `app/logger.py` | ファイルログの初期化と出力。サイズによるローテーション。秘密の値を出さない補助（API キーの先頭 12 文字） |
| `app/webapp_client.py` | Web アプリの API の呼び出し（httpx の非同期クライアント。Bearer の付与、タイムアウト、再試行しない）。応答の状態コードを、ツールのエラー（SDK の `ToolError`）へ対応付ける |
| `app/tools/common.py` | サイトの一覧のツール |
| `app/tools/schedule.py` | スケジュールのツール |
| `app/tools/goods.py` | グッズ管理のツール |
| `app/tools/knowhow.py` | ノウハウ管理のツール |
| `app/tools/expense.py` | 経費管理のツール |
| `app/tools/room.py` | ROOM のツール |
| `app/tools/contract.py` | 契約管理のツール |
| `app/auth/store.py` | SQLite による認証の状態の保存（後述のテーブル）。トークンは SHA-256 のハッシュで保存・照合する |
| `app/auth/provider.py` | SDK の `OAuthAuthorizationServerProvider` の実装。クライアント登録（リダイレクト URI の許可リストの照合）、認可（サインイン画面への誘導）、認可コード・アクセストークン・リフレッシュトークンの発行・照合・ローテーション・失効 |
| `app/auth/passphrase.py` | パスフレーズの scrypt ハッシュの作成と、定数時間での照合 |
| `app/auth/signin.py` | サインイン画面（`custom_route`）。表示・CSRF の値・許可／拒否の処理・ロック |
| `scripts/hash_passphrase.py` | パスフレーズのハッシュを作る運用コマンド（入力を画面に表示しない） |
| `scripts/revoke_all.py` | すべてのトークンとクライアント登録を失効させる運用コマンド |
| `log/` | ログの出力先（リポジトリに含めない） |
| `data/` | SQLite のファイル（リポジトリに含めない） |

### 処理の流れ

#### MCP の要求（ツールの呼び出し）

1. MCP クライアントが `<公開 URL>/mcp` へ、`Authorization: Bearer <アクセストークン>` を付けて要求する。
2. SDK の認証処理が、`provider` を通してアクセストークンのハッシュを SQLite で照合する。無い・期限切れ・失効済み・対象（公開 URL）違いは 401（`WWW-Authenticate` に保護リソースメタデータの URL）。
3. SDK の `Origin` の検証（DNS リバインディング対策）を通す。
4. ツールを実行する。ツールは引数 `site` を `sites.py` で解決し（省略時は既定のサイト）、`webapp_client` でそのサイトの API を呼ぶ。
5. Web アプリの応答が 2xx なら、その本文を構造化出力として返す。それ以外は `ToolError` で、`tool-design.md` のエラー文を返す（`isError`）。
6. ログに、ツール名・サイト・判断に使う引数・呼んだ API・状態コード・結果を出す。

#### 初回の接続（サインイン）

1. MCP クライアントが `<公開 URL>/mcp` に要求し、401 と保護リソースメタデータの URL を受け取る。
2. 保護リソースメタデータ（`/.well-known/oauth-protected-resource/mcp`）と認可サーバメタデータ（`/.well-known/oauth-authorization-server`）を読む。
3. `/register` でクライアントを登録する（DCR）。`provider` は、リダイレクト URI がすべて許可リストに一致するときだけ登録する。
4. 利用者のブラウザが `/authorize` を開く。SDK が要求を検証し、`provider.authorize()` が要求の内容（クライアント・リダイレクト URI・`state`・PKCE のチャレンジ・対象）を「保留中の認可」として SQLite に保存し、`/signin?request=<保留中の認可の ID>` へ転送する。
5. サインイン画面に、クライアント名とリダイレクト先のホスト名を示す。利用者がパスフレーズを入れて「許可」すると、ロック中でなければパスフレーズを照合し、成功なら認可コードを発行してリダイレクト URI へ戻す。「拒否」なら `error=access_denied` で戻す。失敗は連続失敗回数に数え、上限でロックする。
6. MCP クライアントが `/token` で認可コード（と PKCE の検証値）をアクセストークン・リフレッシュトークンに交換する。以後、期限前後に `/token` でリフレッシュする（リフレッシュトークンはローテーション）。

### 認証の状態（SQLite）

`data/webapp-mcp.sqlite3`。トークン類はすべて SHA-256 のハッシュで保存する。

| テーブル | 内容 |
|----------|------|
| `oauth_clients` | 登録されたクライアント（クライアント ID、クライアント名、リダイレクト URI、登録日時、登録情報の JSON） |
| `pending_authorizations` | サインイン待ちの認可要求（ID、クライアント ID、リダイレクト URI、`state`、PKCE のチャレンジ、対象、スコープ、CSRF の値のハッシュ、期限（10 分）） |
| `authorization_codes` | 認可コードのハッシュ、クライアント ID、リダイレクト URI、PKCE のチャレンジ、対象、期限（5 分）、使用済みか |
| `access_tokens` | アクセストークンのハッシュ、クライアント ID、対象、スコープ、期限、失効済みか |
| `refresh_tokens` | リフレッシュトークンのハッシュ、クライアント ID、対象、スコープ、期限（無期限なら NULL）、失効済みか |
| `signin_state` | 連続失敗回数、ロックの期限（1 行） |

期限切れ・失効済みの行は、起動時と一定間隔で削除する。

## ツール一覧

ツール名と概要だけ。詳細は `tool-design.md`。ツールはすべて任意の引数 `site` を持つ（`list_sites` を除く）。

| ツール名 | 概要 | 対応 REQ |
|----------|------|----------|
| `list_sites` | 登録済みのサイトの識別子・表示名・既定か | REQ-003 |
| `schedule_list_schedules` | 期間を指定して予定・TODO を取得 | REQ-004 |
| `schedule_list_categories` | カテゴリの一覧 | REQ-004 |
| `schedule_create_schedule` | 予定・TODO の登録 | REQ-005 |
| `schedule_update_schedule` | 予定・TODO の更新 | REQ-005 |
| `schedule_set_todo_completion` | TODO の実施済み／未実施の切り替え | REQ-005 |
| `schedule_delete_schedule` | 予定・TODO の削除 | REQ-005 |
| `goods_list_goods` | グッズの一覧 | REQ-006 |
| `goods_get_goods` | グッズ 1 件の詳細 | REQ-006 |
| `goods_list_persons` | 人物の一覧 | REQ-006 |
| `goods_list_artists` | アーティストの一覧 | REQ-006 |
| `goods_list_media` | 媒体の一覧 | REQ-006 |
| `goods_create_goods` | グッズの登録 | REQ-007 |
| `goods_update_goods` | グッズの更新 | REQ-007 |
| `goods_delete_goods` | グッズの削除 | REQ-007 |
| `knowhow_search_knowhows` | キーワードでノウハウを検索 | REQ-008 |
| `knowhow_get_knowhow` | ノウハウ 1 件の詳細 | REQ-008 |
| `knowhow_list_major_categories` | 大項目の一覧 | REQ-008 |
| `knowhow_list_middle_categories` | 大項目ごとの中項目の一覧 | REQ-008 |
| `knowhow_create_knowhow` | ノウハウの登録 | REQ-009 |
| `knowhow_update_knowhow` | ノウハウの更新 | REQ-009 |
| `knowhow_delete_knowhow` | ノウハウの削除 | REQ-009 |
| `expense_list_expenses` | 支出記録の一覧 | REQ-010 |
| `expense_list_budget_periods` | 予算期間の一覧 | REQ-010 |
| `expense_get_usage_date_report` | 予算対実績（利用日基準。売掛を含めるかどうかを選べる） | REQ-010 |
| `expense_get_payment_date_report` | 支払日毎の集計（支払日ごと・売掛区分ごとの合計） | REQ-010 |
| `expense_list_payment_methods` | 支出方法の一覧（売掛区分を含む） | REQ-010 |
| `expense_list_budget_items` | 予算期間ごとの予算項目の一覧 | REQ-010 |
| `expense_create_expense` | 支出記録の登録（支払日の省略時は算出してから登録） | REQ-011 |
| `expense_update_expense` | 支出記録の更新（支払日の省略時は算出してから更新） | REQ-011 |
| `expense_delete_expense` | 支出記録の削除 | REQ-011 |
| `room_get_state` | ROOM の 5 機器の状態（ON/OFF、施錠中/開錠中、玄関ドアの電池残量）と取得日時 | REQ-014 |
| `room_set_device_state` | ROOM の機器 1 つの ON/OFF の切り替え（間接照明・屋内スピーカー・枕元スピーカー・電灯。玄関ドアは受け付けない） | REQ-015 |
| `room_run_scene` | ROOM の一括切替の実行（屋内スピーカー選択、枕元スピーカー選択、電灯選択、間接照明選択、お出かけ。玄関ドアは変えない） | REQ-015 |
| `room_list_timers` | ROOM の定期実行（タイマー）の一覧（実行条件、祝日の扱い、実行日の取り方、実行内容、最終実行の結果） | REQ-016 |
| `room_create_timer` | 定期実行の登録（実行内容は、一括切替、または機器 1 つの個別切替） | REQ-016 |
| `room_update_timer` | 定期実行の更新（全項目の置き換え） | REQ-016 |
| `room_set_timer_enabled` | 定期実行の有効／無効の切り替え | REQ-016 |
| `room_delete_timer` | 定期実行の削除 | REQ-016 |
| `contract_list_contracts` | 契約管理の契約の一覧（キーワード・区分・ステータス・契約の有無・パスワード未設定で絞り込み） | REQ-017 |
| `contract_get_contract` | 契約 1 件の詳細（依存契約・支払方法・逆引きを含む） | REQ-017 |
| `contract_list_categories` | 契約の区分の一覧（金融機関の区分かどうかを含む） | REQ-017 |
| `contract_get_cancellation_plan` | 解約順（解約の対象とその順序、解約方法、警告） | REQ-017 |
| `contract_create_contract` | 契約の登録（パスワードの値は指定できない） | REQ-018 |
| `contract_update_contract` | 契約の更新（全項目の置き換え。パスワードの値は指定できない） | REQ-018 |

支出記録の登録・更新のツールは、支払日が省略されたとき、先に Web アプリの支払日の算出 API を呼び、その結果を支払日として登録・更新の API を呼ぶ（1 つのツールで 2 つの API を順に呼ぶ）。算出に失敗したときは登録・更新しない。

ROOM のツールの考え方:

- 玄関ドアは、状態の参照（`room_get_state`）だけを提供する。施錠・開錠のツールは作らず、`room_set_device_state` の引数 `device` の選択肢にも玄関ドアを含めない（REQ-015）。一括切替と定期実行にも、玄関ドアを対象とするものは無い（Web アプリ側の定義による）。
- 定期実行は、ROOM の用語が「定期実行」、Web アプリの API 上の名称が `schedules` である。スケジュール機能の予定（`schedule_*`）と、MCP クライアントの AI が取り違えないよう、ツール名には `timer` を使い、説明にも、スケジュール機能の予定とは別のものであることを書く。
- 機器の操作（`room_set_device_state`、`room_run_scene`）は、実機が動く。ツールの説明に、そのことと、電灯が未実装であること、一括切替で一部の機器が失敗しうることを書く。
- 定期実行の定義は、Web アプリの API の項目（`condition`、`weekdays`、`holiday_mode`、`day_shift`、`run_time`、`scene` または `device` + `state`、`is_enabled`）をそのまま、ツールの引数・出力にする。実行内容は、`scene`（一括切替）か、`device` と `state`（機器の個別切替）の、どちらか一方だけを指定させる。入力の組み合わせの検査（どちらも無い、両方、片方だけ、毎日なのに祝日の扱いがある、など）は、Web アプリが行い、本システムは、その拒否の理由を示す（REQ-016）。玄関ドアは、実行内容の選択肢に含めない。
- 祝日・曜日の判定と、定期実行の自動の実行は、Web アプリの ROOM が行う。本システムは、定義の管理だけを行い、判定の規則（基準日の考え方）を持たない。ツールの説明に、祝日の扱いと実行日の取り方の意味を、AI が読み違えない書き方で示す。

契約管理のツールの考え方:

- 契約管理のツールは、Web アプリの契約管理機能の API キー認証で許可されている操作（契約の一覧・詳細・登録・更新、区分の一覧、解約順の取得）だけを呼ぶ。契約の削除、パスワードの値の取得、アカウント一覧、区分の追加・変更・削除、解約順の保存は、Web アプリが API キーでは拒否するため、ツールを作らない（REQ-018）。
- **パスワードの値は、入力にも出力にも無い。** 登録・更新のツールに、パスワードの引数を持たせない。Web アプリは、API キーで `password` を含む要求を拒否するので、ツールは `password` を送らない。出力は、Web アプリの応答のまま（値は無く、`has_password` と `password_unset` だけが入る）。
- 登録した契約は、パスワードが未設定になる。AI が登録したあと、人が Web アプリの画面で、パスワードを入力する。ツールの説明に、そのことと、`password_unset` が `true` の契約が、人の入力待ちであることを書く。
- 契約は、「契約を伴う」と「契約を伴わない」の別がある。契約を伴わない契約に、契約を伴う契約だけの項目（維持費、更新日、契約日、解約方法、依存契約、支払方法など）を指定すると、Web アプリが拒否する。ツールは検査せず、拒否の理由を示す。ツールの説明に、この区別を書く。
- 支払方法に選べるのは、金融機関の区分の契約だけ。ツールの説明に書き、`contract_list_categories` の `is_financial` で、金融機関の区分を確かめられるようにする。
- 契約の更新は、Web アプリの更新 API が、パスワード以外の全項目を受け取り、送らなかった任意の項目を空にする。更新のツールの説明に、先に `contract_get_contract` で現在の値を確かめ、変えない項目も現在の値のまま渡すことを書く（共通の考え方は `tool-design.md`）。更新しても、保存済みのパスワードは変わらない。
- 契約の入力の組み合わせの検査（契約を伴わないなのに契約の項目がある、維持費の金額と周期の片方だけ、契約日と精度の不整合、2 段階認証の送付先と方式の不一致、依存の循環など）は、Web アプリが行い、本システムは、その拒否の理由を示す。
- 契約の名称、ユーザ名、登録メールアドレス、2 段階認証の送付先、解約方法などの内容は、ログに出さない（REQ-013）。出すのは、ツール名、サイト、契約の ID、件数、絞り込み条件の種類（キーワードの有無など）、状態コード。

注釈: 取得・一覧・検索のツールは `readOnlyHint=true`。削除のツールは `destructiveHint=true`。登録・更新・切り替え（ROOM の機器の操作・一括切替を含む）は `readOnlyHint=false`、`destructiveHint=false`。

## 認証

`rules/14-security.md` に従う。

### OAuth のエンドポイント

| パス | 役割 | 提供 |
|------|------|------|
| `/.well-known/oauth-protected-resource/mcp` | 保護リソースメタデータ（RFC 9728） | SDK |
| `/.well-known/oauth-authorization-server` | 認可サーバメタデータ（RFC 8414）。発行者は公開 URL | SDK |
| `/register` | 動的クライアント登録（DCR） | SDK＋`provider`（許可リストの照合） |
| `/authorize` | 認可要求の受付。サインイン画面へ転送 | SDK＋`provider` |
| `/signin` | サインイン画面（GET: 表示、POST: 許可／拒否） | 本サーバ（`custom_route`） |
| `/token` | 認可コードの交換、リフレッシュ | SDK＋`provider` |
| `/revoke` | トークンの失効 | SDK＋`provider` |

- PKCE は `S256` のみ。
- アクセストークンは公開 URL の `/mcp` 向け（リソースインジケータ）とし、SDK の `validate_token_resource` を有効にして対象違いを拒否する。
- スコープは 1 つ（`webapp`）とし、すべてのツールに同じスコープを求める。

### リダイレクト URI の許可リスト（`MCP_ALLOWED_REDIRECT_URIS`）

| クライアント | リダイレクト URI |
|--------------|------------------|
| Claude（Web・Desktop・モバイル） | `https://claude.ai/api/mcp/auth_callback` |
| Claude Code | `http://localhost/callback`、`http://127.0.0.1/callback`（ポート番号は問わない） |
| Microsoft 365 Copilot（Copilot Studio） | 未決事項を参照 |

### サインイン画面

- 1 枚の HTML（サーバで生成。外部リソースと JavaScript なし）。スマートフォンの幅で操作できる。
- 表示: タイトル「webapp-mcp へのアクセスの許可」、クライアント名、リダイレクト先のホスト名、パスフレーズの入力欄、「許可」「拒否」ボタン、失敗時の一文（「パスフレーズが違います。」「しばらく時間をおいてから、もう一度お試しください。」「この要求は期限切れです。もう一度接続し直してください。」）。
- フォームには保留中の認可ごとの CSRF の値を埋め込み、POST 時に照合する。
- 応答ヘッダ: `X-Frame-Options: DENY`、`Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'; form-action 'self'`、`Cache-Control: no-store`、`Referrer-Policy: no-referrer`。

### Origin の検証

SDK の DNS リバインディング対策（`TransportSecuritySettings`）を有効にする。許可するホストは公開 URL のホスト、許可する `Origin` は `MCP_ALLOWED_ORIGINS`（既定は公開 URL のオリジン）。`Origin` の無い要求（サーバ間の通信）は許可する。

### 運用コマンド

- `python scripts/hash_passphrase.py`: パスフレーズを 2 回入力させ（表示しない）、`.env` に書く値を出力する。
- `python scripts/revoke_all.py`: すべてのトークン・保留中の認可・クライアント登録を削除する。実行後、各クライアントで再接続が必要になる（REQ-002）。

## ログ

`rules/16-logging.md` に従う。出力先は `server/log/webapp-mcp.log`。

| 契機 | 出す値 |
|------|--------|
| クライアント登録 | クライアント名、リダイレクト URI、許可リストとの照合結果 |
| サインイン | クライアント名、成功・失敗（理由: 不一致・ロック中・期限切れ・拒否）、連続失敗回数 |
| トークンの発行・更新・失効 | クライアント ID、種類 |
| アクセストークンの検証失敗 | 理由（なし・無効・期限切れ・対象違い） |
| ツール呼び出し | ツール名、サイト、判断に使う引数（識別子・日付・件数・キーワードの数）、API キーの先頭 12 文字。契約管理は、契約の ID、絞り込み条件の種類（キーワードの有無など）まで |
| Web アプリの応答 | ツール名、サイト、メソッド・パス、状態コード、件数、失敗の理由 |
| 運用コマンド | 実行と結果（件数） |

本文・メモ・タイトル・キーワードの文字列、契約の名称・ユーザ名・登録メールアドレス・2 段階認証の送付先・解約方法、パスフレーズ、トークン類、API キー全体は出さない。

## 配置

- 公開: 専用ホスト名のルート（`rules/17-deploy.md`）。MCP クライアントに登録する URL は `<公開 URL>/mcp`。
- 常駐: systemd。`Restart=on-failure`。`server/.env` と `server/data/` は、サービスを動かす OS ユーザだけが読み書きできる権限にする。

## テスト

- 単体テスト（`tests/unit/`）: Web アプリの API を `respx` でモックし、各ツールの引数の検証・呼ぶ API・応答とエラーの変換を確かめる。`provider` と `store` の、登録（許可リスト）・認可コード・PKCE・リフレッシュのローテーション・失効・ロックを確かめる。
- 結合テスト（`tests/integration/`）: 開発環境の Web アプリ（5 機能のバックエンド）と、`api-key-management` で発行した API キーを使い、OAuth のフロー（登録 → 認可 → サインイン → トークン）を経て MCP クライアント（SDK のクライアント）からツールを呼び出す。

## 要件トレーサビリティ

| 要件 | 設計 |
|------|------|
| REQ-001 | OAuth のエンドポイント、サインイン画面、`passphrase`、`signin_state`、リダイレクト URI の許可リスト |
| REQ-002 | トークンの有効期間（`MCP_REFRESH_TOKEN_TTL_DAYS`）、リフレッシュのローテーション、`scripts/revoke_all.py` |
| REQ-003 | `sites.py`、`sites.toml`、`list_sites`、引数 `site`、起動時の確認 |
| REQ-004〜REQ-005 | `tools/schedule.py` |
| REQ-006〜REQ-007 | `tools/goods.py` |
| REQ-008〜REQ-009 | `tools/knowhow.py` |
| REQ-010〜REQ-011 | `tools/expense.py` |
| REQ-014〜REQ-016 | `tools/room.py` |
| REQ-017〜REQ-018 | `tools/contract.py` |
| REQ-012 | `webapp_client.py` の状態コードの対応付け、再試行しない |
| REQ-013 | `logger.py`、ログの表 |

## 未決事項

- Microsoft 365 Copilot（Copilot Studio）がクライアント登録で使うリダイレクト URI。Copilot Studio でコネクタを作成するときに表示される値を確認し、`MCP_ALLOWED_REDIRECT_URIS` に追加する（コードの変更は不要）。確認できるまで、Copilot からの登録は拒否される。

## 承認

現在の状態: 承認済み

| 日時 | 状態 | 変更概要 |
|------|------|----------|
| 2026-09-26 02:50 | 未承認 | 初版 |
| 2026-09-26 02:53 | 承認済み | 初版を承認 |
| 2026-09-26 02:56 | 未承認 | ツール `expense_list_budget_items` を追加（31 個）。支出記録の登録・更新で、支払日の省略時に算出 API を先に呼ぶ流れを追加 |
| 2026-09-26 03:00 | 承認済み | expense_list_budget_items の追加と支払日の算出の流れを承認 |
| 2026-09-27 | 未承認 | Web アプリの経費管理機能の改訂に合わせ、ツール一覧を更新。`expense_get_payment_month_report` を `expense_get_payment_date_report`（支払日毎・売掛区分ごとの集計）に置き換え、`expense_get_usage_date_report` と `expense_list_payment_methods` の概要に売掛区分の扱いを追記（REQ-010） |
| 2026-09-27 | 承認済み | ツール一覧の更新を承認 |
| 2026-10-01 13:13 | 未承認 | ROOM の追加（REQ-014〜REQ-016）に合わせ、利用する機能に `room` を追加。モジュール `tools/room.py` と、ROOM のツール 8 個（合計 39 個）を追加。玄関ドアは参照のみとし、操作のツールを作らない方針を明記 |
| 2026-10-01 13:13 | 承認済み | ROOM の追加（ツール 8 個、玄関ドアは参照のみ）を承認 |
| 2026-10-02 11:12 | 未承認 | REQ-016 の改訂に合わせ、定期実行のツールの説明を更新し、ROOM のツールの考え方に、定期実行の項目（個別切替、祝日の扱い、実行日の取り方）の扱いを追記 |
| 2026-10-02 11:13 | 承認済み | 定期実行のツールの改訂方針を承認 |
| 2026-10-03 12:47 | 未承認 | 契約管理の追加（REQ-017、REQ-018）に合わせ、利用する機能に `contract-management` を追加。モジュール `tools/contract.py` と、契約管理のツール 6 個（合計 45 個）を追加。パスワードの値は入出力せず、削除・区分の管理・解約順の保存・アカウント一覧のツールは作らない方針を明記。ログに出さない値を追加 |
| 2026-10-03 12:49 | 承認済み | 契約管理のツールの追加（6 個、パスワードの値は扱わない）を承認 |
