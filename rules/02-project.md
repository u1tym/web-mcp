# フォルダ構成

> 常時適用（参考情報）

## SPECのテンプレート

```
specs
└ templates
  ├ requirements-template.md
  ├ design-template.md
  ├ tool-design-template.md
  ├ tasks-template.md
  ├ server.env.example
  └ sites.example.toml
```

## SPECのフォルダ構成

MCP サーバ毎にまとめて作成する。

```
specs
└ <server-name>
  ├ requirements.md
  ├ design.md
  ├ tool-design.md
  └ tasks.md
```

`<server-name>` は kebab-case（例: `webapp-mcp`）。

## 生成コードのフォルダ構成

```
src
└ <server-name>
  ├ server      # venv/、.env、sites.toml、data/、log/ を含む。Python パッケージは server/app/、運用コマンドは server/scripts/
  └ tests       # 同一サーバの server は import してよい。venv は server/venv を使う
```

- 1 つの MCP サーバは、1 つのプロセスとして動く。
- サーバ間で Python を import しない。

## リポジトリに含めないもの

`venv/`、`.env`、`sites.toml`（環境ごとに異なるため。ひな型だけを置く）、`data/`（認証の状態の SQLite）、`log/`、`__pycache__/`、`.pytest_cache/`。
