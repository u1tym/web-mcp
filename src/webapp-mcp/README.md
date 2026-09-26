# webapp-mcp

Web アプリ（`claude_webapp`）の 4 機能（スケジュール・グッズ管理・ノウハウ管理・経費管理）を、MCP のツールとして提供するサーバです。Claude（Web・Desktop・モバイル）、Claude Code、Microsoft 365 Copilot から使えます。

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
3. キーの持ち主に、4 機能（schedule・goods-management・knowhow-management・expense-management）が割り当てられていることを確かめます。

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

`sites.toml` には、サイトごとに 4 機能の API の URL を書きます。MCP サーバと Web アプリが同じホストなら `http://127.0.0.1:<port>` を書けます。API キーは `sites.toml` に書きません。

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

結合テストには、開発環境の Web アプリの 4 機能のバックエンドの起動と、4 機能が割り当てられたユーザの API キーが必要です（接続先は `WEBAPP_TEST_<FEATURE>_URL` で変えられます）。テストは準備データを作ってから、終わりに削除します。`WEBAPP_TEST_API_KEY` が無いときはスキップされます。
