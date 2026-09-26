# SPEC開発ルール（MCPサーバ版）

このリポジトリは、Web アプリケーション（`D:\claude_code\claude_webapp`。以下「Web アプリ」）の API を、MCP（Model Context Protocol）のツールとして提供する MCP サーバを作る。

ルールは Web アプリの SPEC 開発ルールを元に、MCP サーバ向けに作り直したものである。MCP サーバには画面と DB が無いため、画面・DB・nginx のフロント配置に関するルールは持たない。

## ルール一覧

- @rules/02-project.md — フォルダ構成
- @rules/12-server.md — MCP サーバの実装方式
- @rules/13-webapp-api.md — Web アプリの API の呼び出し方
- @rules/14-security.md — セキュリティ方式
- @rules/16-logging.md — ログ出力方針
- @rules/17-deploy.md — サーバの配置（nginx 経由の公開）
- @rules/21-requirements.md — 要件作成
- @rules/22-design.md — 全体設計作成
- @rules/22a-tool-design.md — ツール設計作成
- @rules/23-tasks.md — タスク分解

## SPEC開発

実装前に以下の順で成果物を作る。

1. requirements.md
2. design.md
3. tool-design.md
4. tasks.md

- 作成時はテンプレートを用いる。テンプレートの格納先フォルダ・作成した成果物の格納先フォルダは `rules/02-project.md` を参照する。
- SPEC（requirements.md / design.md / tool-design.md / tasks.md）は**見出しも本文も日本語**で書く。
- ファイル名、ディレクトリ名、コードパス、環境変数名、ツール名、API パス、要件 ID（`REQ-001`）は英語のままでよい。

### Requirements Phase

- requirements.md を最初に作成する
- テンプレート: `requirements-template.md`
- 要件は EARS の意味を保ち、日本語の文で記述する
- 受け入れ条件を必須とする
- 詳細は `rules/21-requirements.md`

### Design Phase

requirements.md のユーザ承認後に、次の順で作成する。
直前のファイルが承認されるまで、次を作成しない。

1. `design.md`（全体構成）
   - テンプレート: `design-template.md`
   - ツールごとの入力・出力・エラーは書かない（`tool-design.md`）
   - 詳細は `rules/22-design.md`
2. `tool-design.md`（ツールの契約。`design.md` のユーザ承認後）
   - テンプレート: `tool-design-template.md`
   - 詳細は `rules/22a-tool-design.md`

要件に存在しない機能（ツール）を追加しない。

### Tasks Phase

- tasks.md を作成する（`design.md` / `tool-design.md` がすべて承認された後）
- テンプレート: `tasks-template.md`
- 2 つの設計書を元にタスクへ分解する
- タスクは実装可能な粒度にする
- 実装は、ユーザが tasks.md を承認した後に開始する
- 詳細は `rules/23-tasks.md`

### Implementation Phase

- tasks.md に記載されたタスクのみ実装する
- 実装前に requirements.md と 2 つの設計書を確認する
- 要件と設計にない機能を勝手に追加しない
- コードは `src/<server-name>/{server,tests}` に置く
- 実装方式は `rules/12-server.md`（MCP サーバ）、`rules/13-webapp-api.md`（Web アプリの API）、`rules/14-security.md`（セキュリティ）、`rules/16-logging.md`（ログ）、`rules/17-deploy.md`（配置）に従う

## Web アプリとの関係

- MCP サーバは、接続先（サイト）ごとに保持した API キーで、Web アプリの API を呼ぶだけとする。Web アプリの DB に直接接続しない。Web アプリの Python を import しない。
- MCP クライアントは、MCP サーバに組み込んだ OAuth 認可サーバで認証する（`rules/14-security.md`）。MCP サーバの画面は、OAuth のサインイン画面だけとする。
- 呼び出す API の契約の正は、Web アプリの各機能の `api-design.md`（`D:\claude_code\claude_webapp\specs\<feature>\api-design.md`）である。MCP 側の SPEC で API の契約を変えない。
- Web アプリの API に無い操作は、MCP サーバでは提供しない。必要なら Web アプリ側の SPEC を先に改訂する。

## レビューと承認

### レビュー

- **レビューとは、ユーザがその成果物を承認することである。**
- Claude は承認を推測しない。ユーザが対象成果物を承認する旨を明示するまで、次フェーズに進まない。「このファイルを承認する」「承認」「OK」は有効。対象ファイルが不明なときは確認する。
- 各成果物末尾の `承認` は **履歴** とする。行を消したり、過去行の日時・状態・変更概要を書き換えたりしない。
- **現在の状態** は表の最終行の状態と一致させる。ユーザ承認後にだけ、承認済みの行を追記する。

### 承認

承認欄の形式:

```
## 承認

現在の状態: 未承認

| 日時 | 状態 | 変更概要 |
|------|------|----------|
| 2026-08-22 08:42 | 未承認 | 初版 |
```

- 日時は日本時間 `YYYY-MM-DD HH:mm`（日付しか分からない過去分は `YYYY-MM-DD` 可）。
- 状態は `未承認` または `承認済み`。
- 変更概要は、その行が指す改訂の内容（初版、何を変えたか、何を承認したか）。

追記のタイミング:

- 新規作成: 未承認の行を 1 件（変更概要は「初版」）。
- 承認済みファイルの本文を変える: 未承認の行を追記し、現在の状態を未承認にする。
- ユーザが承認した: 承認済みの行を追記し、現在の状態を承認済みにする。

### 承認済みSPECの改訂

承認済みの成果物を変えるときは、変更を当該ファイルに反映し、承認欄へ未承認の行を追記する。ユーザが再承認するまで、後続成果物の更新や実装に進まない。影響する後続ファイルも更新し、再承認を得る。
