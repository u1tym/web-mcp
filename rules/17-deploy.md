# サーバの配置（nginx 経由の公開）

> 常時適用（公開URLと配置）

## 公開 URL

- MCP サーバは nginx の背後で動かし、https で公開する。公開 URL はインターネットから届くものとする（MCP クライアントは Anthropic や Microsoft のクラウドから接続する）。
- MCP サーバごとに**専用のホスト名**（例: `mcp.example.com`）を割り当て、そのホストの**ルート**で公開する。パスの下（例: `/mcp/<server-name>/`）には置かない。
  - 理由: OAuth のメタデータ（`/.well-known/oauth-authorization-server`、`/.well-known/oauth-protected-resource/...`）はホストの直下で探される。SDK もこれらをアプリのルートに置くため、ホストのルートで公開すれば nginx で経路を書き換えずに済む。
- MCP のエンドポイントは `/mcp`（例: `https://mcp.example.com/mcp`）とする。MCP クライアントにはこの URL を登録する。
- `.env` の `MCP_PUBLIC_URL` は、公開するホストのルートの URL（例: `https://mcp.example.com`。末尾の `/` は付けない）と完全に一致させる。OAuth の発行者（issuer）とトークンの対象の基準に使うため。
- MCP サーバ自身は `127.0.0.1` の `MCP_PORT` で待ち受け、外部から直接接続させない。

## nginx

Streamable HTTP は応答をストリーム（Server-Sent Events）で返すことがあるため、バッファリングを無効にする。`Authorization` ヘッダは消さずに渡す（nginx の既定の動作で渡る）。ホスト全体を MCP サーバへ渡す。

```nginx
server {
    listen 443 ssl;
    server_name <MCP サーバのホスト名>;
    # ssl_certificate / ssl_certificate_key は環境に合わせる

    location / {
        proxy_pass http://127.0.0.1:<MCP_PORT>;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 3600s;
    }
}
```

配置例は、各サーバの `server/nginx.example.conf` に書く。

## 常駐

- 本番では、OS のサービス（systemd など）として常駐させ、異常終了時に再起動させる。
- 起動コマンドは `design.md` に書く。
- `server/data/`（認証の状態）はバックアップの対象とする。失っても、各クライアントで再接続（サインイン）すれば復旧できる。
