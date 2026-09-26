# ツール設計作成（日本語）

> `specs/**/tool-design.md` を編集するとき。ツールの契約

見出しと本文は日本語で書くこと。

`specs/templates/tool-design-template.md` に従うこと。

ツールごとに、次を書くこと。

- ツール名（`rules/12-server.md` の命名規則）
- 説明（MCP クライアントの AI に渡す description。何をするか・いつ使うか・注意点）
- 注釈（`readOnlyHint` / `destructiveHint` / `idempotentHint`）
- 入力（引数名、型、必須・任意、説明・形式）
- 呼び出す Web アプリの API（機能、メソッド、パス）。Web アプリの `api-design.md` と一致させる
- 出力（構造化出力の形。Web アプリの応答との対応）
- エラー（Web アプリの応答ごとの、ツールのエラー文。`rules/13-webapp-api.md` の対応に従う）
- 対応する要件 ID

共通事項の節に、認証（`rules/14-security.md`）、共通のエラー文、日時などの形式を書くこと。

起動・モジュール構成は書かないこと（`design.md`）。

要件に存在しないツールを追加しないこと。Web アプリの API に存在しない操作を設計しないこと。

ユーザが `design.md` を承認するまで、このファイルを作成しないこと。
ユーザがこのファイルを承認するまで、`tasks.md` を作成しないこと。

承認欄は履歴形式とする（日時・状態・変更概要。詳細は `CLAUDE.md`）。
