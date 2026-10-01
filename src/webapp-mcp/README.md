# webapp-mcp

Web アプリ（`claude_webapp`）の 5 機能（スケジュール・グッズ管理・ノウハウ管理・経費管理・ROOM）を、MCP のツールとして提供するサーバです。Claude（Web・Desktop・モバイル）、Claude Code、Microsoft 365 Copilot から使えます。ROOM では、機器の状態の参照と、機器の操作（玄関ドアを除く）もできます（注意点は「6. ROOM のツール」）。

仕様は `specs/webapp-mcp/`（requirements.md・design.md・tool-design.md・tasks.md）を参照してください。

```
MCP クライアント ──(OAuth のアクセストークン)──▶ nginx ─▶ webapp-mcp ──(サイトの API キー)──▶ Web アプリの API
```

## 1. 初期設定

作業はすべて `src/webapp-mcp/server` で行います。

### 1.1 仮想環境

```sh
python -m venv venv
venv/bin/pip install -r requirements.txt        # Windows: venv\Scripts\pip install -r requirements.txt
```

Python 3.11 以上が必要です。

### 1.2 Web アプリの API キーを発行する

1. Web アプリにログインし、メニューの「API キー管理」を開きます（機能が割り当てられていない場合は、ユーザ管理で割り当てます）。
2. 「新規」で API キーを発行し、表示されたキー全体をコピーします（この画面を閉じると二度と表示されません）。
3. キーの持ち主に、5 機能（schedule・goods-management・knowhow-management・expense-management・room）が割り当てられていることを確かめます。

接続先（サイト）が複数あるときは、サイトごとに発行します。

### 1.3 パスフレーズのハッシュを作る

MCP クライアントを接続するときのサインインに使うパスフレーズを決め、ハッシュを作ります（12 文字以上。入力は画面に表示されません）。

```sh
venv/bin/python scripts/hash_passphrase.py
# MCP_SIGNIN_PASSPHRASE_HASH=scrypt$...  ← これを .env に書く
```

### 1.4 `.env` と `sites.toml` を作る

ひな型をコピーして編集します。

```sh
cp ../../../specs/templates/server.env.example .env
cp ../../../specs/templates/sites.example.toml sites.toml
```

`.env` の主な項目:

| 項目 | 値 |
|------|-----|
| `MCP_PUBLIC_URL` | 公開 URL（例: `https://mcp.example.com`。末尾の `/` なし）。開発時は `http://127.0.0.1:9001` |
| `MCP_SIGNIN_PASSPHRASE_HASH` | 1.3 で作った値 |
| `MCP_ALLOWED_REDIRECT_URIS` | 接続を許すクライアントの戻り先（3.3 を参照） |
| `MCP_REFRESH_TOKEN_TTL_DAYS` | 再サインインまでの日数（既定 90。0 は無期限） |
| `SITE_<SITE>_API_KEY` | 1.2 で発行した API キー（`sites.toml` のサイトごと。例: `SITE_HOME_API_KEY`） |

`sites.toml` には、サイトごとに 5 機能（`schedule`・`goods-management`・`knowhow-management`・`expense-management`・`room`）の API の URL を書きます。MCP サーバと Web アプリが同じホストなら `http://127.0.0.1:<port>` を書けます。API キーは `sites.toml` に書きません。`room` の行が無いサイトでは、ROOM のツールだけが「このサイトでは、この機能を利用できません」を返します（他の機能のツールは使えます）。

### 1.5 権限

`.env` と `data/`（認証の状態）は、MCP サーバを動かすユーザだけが読み書きできるようにします。

```sh
chmod 600 .env
mkdir -p data && chmod 700 data
```

## 2. 起動

```sh
venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 9001
```

設定に不備があると、理由を表示して起動しません。ログは `log/webapp-mcp.log` に出ます。

本番では:

- nginx の設定例: `nginx.example.conf`（専用のホスト名のルートで https 公開）
- systemd のユニットの例: `webapp-mcp.service.example`

公開後、`https://<ホスト名>/.well-known/oauth-protected-resource/mcp` が JSON を返すことを確かめます。

## 3. MCP クライアントから接続する

どのクライアントも、最初の接続でブラウザにサインイン画面が開きます。クライアント名と戻り先を確かめ、パスフレーズを入力して「許可」を押します。以後は、リフレッシュトークンの期限（`MCP_REFRESH_TOKEN_TTL_DAYS`）まで再サインインは不要です。

### 3.1 Claude（Web・Desktop・モバイルアプリ）

1. PC の claude.ai（または Claude Desktop）で、設定のコネクタ画面から「カスタムコネクタを追加」を選びます。
2. URL に `https://<ホスト名>/mcp` を入力して追加し、「接続」を押します。
3. サインイン画面で許可します。
4. 同じ Claude アカウントのモバイルアプリからも、そのまま使えます（モバイルアプリからはコネクタを追加できません）。

### 3.2 Claude Code

```sh
claude mcp add --transport http webapp https://<ホスト名>/mcp
```

最初にツールを使うとき（または `/mcp` から認証するとき）に、ブラウザでサインイン画面が開きます。

### 3.3 Microsoft 365 Copilot（Copilot Studio）

1. Copilot Studio のエージェントで、ツールの追加から「Model Context Protocol」を選び、サーバの URL に `https://<ホスト名>/mcp`、認証に OAuth 2.0（動的検出）を選びます。
2. 画面に表示されるリダイレクト URI（コールバック URL）を、`.env` の `MCP_ALLOWED_REDIRECT_URIS` にカンマ区切りで追加し、MCP サーバを再起動します。追加するまで、Copilot からのクライアント登録は拒否されます（ログに「クライアント登録拒否」が出ます）。
3. 接続を作成し、サインイン画面で許可します。

## 4. 運用

### すべての接続を取り消す（端末の紛失時など）

```sh
venv/bin/python scripts/revoke_all.py
```

すべてのトークンとクライアント登録を削除します。各クライアントで再接続（サインイン）が必要になります。MCP サーバの再起動は不要です。

### パスフレーズ・API キーを変える

`.env` を書き換えて MCP サーバを再起動します。Web アプリの API キーを失効させたときも、新しいキーに書き換えて再起動します。

### サインインがロックされたとき

パスフレーズを続けて誤ると（既定 5 回）、一定時間（既定 15 分）サインインを受け付けません。時間をおいてから再度お試しください。

## 5. テスト

`src/webapp-mcp` で実行します。

```sh
server/venv/bin/python -m pytest tests/unit                       # 単体テスト（Web アプリは不要）
WEBAPP_TEST_API_KEY=<テスト用の API キー> server/venv/bin/python -m pytest tests/integration
```

結合テストには、開発環境の Web アプリの 5 機能のバックエンドの起動と、5 機能が割り当てられたユーザの API キーが必要です（接続先は `WEBAPP_TEST_<FEATURE>_URL` で変えられます。ROOM は `WEBAPP_TEST_ROOM_URL`、既定 `http://127.0.0.1:8011`）。テストは準備データを作ってから、終わりに削除します。`WEBAPP_TEST_API_KEY` が無いときはスキップされます。

ROOM の結合テスト（`test_room_tools_against_webapp`）は、ROOM のバックエンドだけを起動すれば実行できます（`-k room`）。**機器を操作するツール（`room_set_device_state`、`room_run_scene`）は呼びません**（開発環境の ROOM は、実機の SwitchBot を操作するため）。実機への読み取り（`room_get_state`）と、定期実行の登録・更新・有効／無効の切り替え・削除だけを行い、作った定期実行は、途中で失敗しても削除します。

## 6. ROOM のツール

ROOM は、自室の機器（電灯・間接照明・屋内スピーカー・枕元スピーカー・玄関ドア）の状態を示し、操作する機能です。次の 8 個のツールを提供します（引数 `site` で接続先を選べます）。

| ツール | 内容 |
|--------|------|
| `room_get_state` | 5 機器の状態（ON/OFF、施錠中/開錠中、玄関ドアの電池残量）と取得日時 |
| `room_set_device_state` | 機器 1 つを ON / OFF にする（電灯・間接照明・屋内スピーカー・枕元スピーカー） |
| `room_run_scene` | 一括切替（屋内スピーカー選択・枕元スピーカー選択・電灯選択・間接照明選択・お出かけ） |
| `room_list_timers` | 定期実行（タイマー）の一覧 |
| `room_create_timer` / `room_update_timer` / `room_set_timer_enabled` / `room_delete_timer` | 定期実行の登録・更新・有効／無効の切り替え・削除（削除は元に戻せない） |

注意:

- **玄関ドアは、状態の参照だけです**。施錠・開錠のツールは、ありません（`room_set_device_state` の選択肢にも、玄関ドアは含まれません）。AI が、他の内容に紛れた指示に従って、玄関を開錠してしまうことを防ぐためです。施錠・開錠は、ROOM の画面か SwitchBot のアプリで行います。
- **`room_set_device_state` と `room_run_scene` は、実機が実際に動きます**。電灯は未実装のため、電灯への指示は行われません（結果の `applied` が `false`、または `skipped`）。一括切替で一部の機器が失敗しても、エラーにはならず、機器ごとの結果が返ります。
- **定期実行のツールは、名前に `timer` を使います**。スケジュール機能の予定・TODO（`schedule_*`）とは別のものです。定期実行を自動で行うのは Web アプリの ROOM で、MCP は、定義の管理だけを行います。
- 機器を操作できなかったとき（SwitchBot に接続できない、機器がエラーを返した）は、操作の結果の確認を促す文が返ります。自動で再実行はしません。`room_get_state` で、実際の状態を確かめてください。

### 既存の環境へ ROOM を追加する

すでに動いている MCP サーバに ROOM のツールを加えるときの手順です。

1. MCP サーバのコードを更新する（`app/tools/room.py` などを含む）。
2. API キーの持ち主に、機能 `room` が割り当てられていることを確かめる（Web アプリの運用コマンド `menu assign <ユーザ名> room <表示順>`。ROOM 側の手順書を参照）。
3. `sites.toml` の、該当するサイトの `[sites.<サイト>.api]` に、ROOM の API の URL を足す。
   ```toml
   room = "http://127.0.0.1:8011"     # 同じホストなら。別ホストなら、そのホストの URL
   ```
4. MCP サーバを再起動する（`.env` と `sites.toml` は、起動時にだけ読まれます）。
5. MCP クライアントで、ツール一覧を取得し直す（Claude では、コネクタの再読み込みや、再接続が必要な場合があります）。`room_*` のツールが 8 個増えていれば完了です。
