# webapp-mcp（Web アプリ連携 MCP サーバ）ツール設計

> 起動・モジュール構成は書かない（`design.md`）。呼び出す API の契約の正は、Web アプリの各機能の `api-design.md`（`D:\claude_code\claude_webapp\specs\<feature>\api-design.md`）。

## 共通事項

### 認証

- MCP クライアントは、OAuth のアクセストークンで MCP サーバに接続する（`rules/14-security.md`、`design.md` の「認証」）。すべてのツールは同じスコープ（`webapp`）を求める。
- ツールは、選んだサイトの API キーを `Authorization: Bearer` で Web アプリへ送る（`rules/13-webapp-api.md`）。

### サイトの指定

- `list_sites` 以外のツールは、任意の引数 `site`（string。サイトの識別子）を持つ。省略時は既定のサイト。
- 以下の各ツールの「入力」の表では `site` を省略する。

### 形式

| 項目 | 形式 |
|------|------|
| 日付 | `YYYY-MM-DD`（日本標準時の年月日） |
| 時刻 | `HH:MM`（24 時間） |
| 年月 | `YYYY-MM` |
| 金額 | 小数点以下 2 桁までの数値を表す文字列（例: `"980.00"`）。Web アプリと同じ |
| ID | 整数 |

形式は入力スキーマ（`pattern` など）でも示す。形式の最終的な検査は Web アプリが行う。

### 出力

- 取得・一覧・登録・更新のツールは、Web アプリの応答本文を、項目名と値を変えずに構造化出力として返す。例外は各ツールに書く（グッズの画像データを除くなど）。
- 削除のツールは、Web アプリが本文を返さないため `{ "deleted": true, "id": <ID> }` を返す。

### 更新のツールの考え方

Web アプリの更新 API は全項目を受け取り、送らなかった項目を空にする。そのため、更新のツールは Web アプリが求める項目をすべて必須の引数とする（値として `null` を許す項目は `null` を渡せる）。ツールの説明に「先に取得系のツールで現在の値を確かめ、変えない項目も現在の値のまま渡すこと」と書く。

### 共通エラー

Web アプリの応答（`rules/13-webapp-api.md`）を、ツールのエラー（`isError`）として次の文で返す。`<site>` はサイトの識別子、`<detail>` は Web アプリの応答本文の `detail`。

| 条件 | ツールのエラー文 |
|------|------------------|
| 400 | 入力が不正です。引数の形式・必須項目・組み合わせを確認してください。（Web アプリ: `<detail>`） |
| 401 | サイト `<site>` の API キーが無効です（失効・期限切れを含む）。MCP サーバの設定で API キーを見直してください。 |
| 403 | サイト `<site>` で、この機能を利用する権限がありません。Web アプリで機能の割り当てを確認してください。 |
| 404 | 対象が見つかりません。ID を確認してください（削除済みのものも見つかりません）。 |
| 409 | Web アプリが処理を受け付けませんでした。（Web アプリ: `<detail>`） |
| 5xx・タイムアウト・接続失敗 | サイト `<site>` の Web アプリに接続できないか、処理に失敗しました。登録・更新・削除の場合は、反映されたかどうかを取得系のツールで確かめてから、必要ならやり直してください。 |
| 存在しないサイト | サイト `<site>` は登録されていません。`list_sites` で確かめてください。 |
| サイトに機能の接続先が無い | サイト `<site>` では、この機能を利用できません（接続先が設定されていません）。 |

- エラー文に API キー、接続先の URL、例外の内容は含めない（REQ-012）。
- 自動で再試行しない。
- 引数の型・必須の違反は、SDK の入力検証によるエラーとして返る（Web アプリは呼ばない）。

## ツール一覧

注釈の略記: R = `readOnlyHint=true`、W = `readOnlyHint=false, destructiveHint=false`、D = `readOnlyHint=false, destructiveHint=true`。`idempotentHint` は取得・一覧（R）と削除（D）で `true`、それ以外は `false`。

| ツール名 | 注釈 | 呼び出す API（機能） | 対応 REQ |
|----------|------|----------------------|----------|
| `list_sites` | R | なし | REQ-003 |
| `schedule_list_schedules` | R | `GET /schedules`（schedule） | REQ-004 |
| `schedule_list_categories` | R | `GET /categories`（schedule） | REQ-004 |
| `schedule_create_schedule` | W | `POST /schedules`（schedule） | REQ-005 |
| `schedule_update_schedule` | W | `PATCH /schedules/{schedule_id}`（schedule） | REQ-005 |
| `schedule_set_todo_completion` | W | `PATCH /schedules/{schedule_id}/completion`（schedule） | REQ-005 |
| `schedule_delete_schedule` | D | `DELETE /schedules/{schedule_id}`（schedule） | REQ-005 |
| `goods_list_persons` | R | `GET /persons`（goods-management） | REQ-006 |
| `goods_list_artists` | R | `GET /artists`（goods-management） | REQ-006 |
| `goods_list_media` | R | `GET /media`（goods-management） | REQ-006 |
| `goods_list_goods` | R | `GET /goods`（goods-management） | REQ-006 |
| `goods_get_goods` | R | `GET /goods/{goods_id}`（goods-management） | REQ-006 |
| `goods_create_goods` | W | `POST /goods`（goods-management） | REQ-007 |
| `goods_update_goods` | W | `PATCH /goods/{goods_id}`（goods-management） | REQ-007 |
| `goods_delete_goods` | D | `DELETE /goods/{goods_id}`（goods-management） | REQ-007 |
| `knowhow_list_major_categories` | R | `GET /major-categories`（knowhow-management） | REQ-008 |
| `knowhow_list_middle_categories` | R | `GET /major-categories/{major_category_id}/middle-categories`（knowhow-management） | REQ-008 |
| `knowhow_search_knowhows` | R | `GET /knowhows/search`（knowhow-management） | REQ-008 |
| `knowhow_get_knowhow` | R | `GET /knowhows/{knowhow_id}`（knowhow-management） | REQ-008 |
| `knowhow_create_knowhow` | W | `POST /knowhows`（knowhow-management） | REQ-009 |
| `knowhow_update_knowhow` | W | `PATCH /knowhows/{knowhow_id}`（knowhow-management） | REQ-009 |
| `knowhow_delete_knowhow` | D | `DELETE /knowhows/{knowhow_id}`（knowhow-management） | REQ-009 |
| `expense_list_budget_periods` | R | `GET /budget-periods`（expense-management） | REQ-010 |
| `expense_list_budget_items` | R | `GET /budget-items`（expense-management） | REQ-010 |
| `expense_list_payment_methods` | R | `GET /payment-methods`（expense-management） | REQ-010 |
| `expense_list_expenses` | R | `GET /expenses`（expense-management） | REQ-010 |
| `expense_get_usage_date_report` | R | `GET /reports/usage-date`（expense-management） | REQ-010 |
| `expense_get_payment_date_report` | R | `GET /reports/payment-date`（expense-management） | REQ-010 |
| `expense_create_expense` | W | （支払日の省略時）`GET /payment-methods/{payment_method_id}/estimated-payment-date` → `POST /expenses`（expense-management） | REQ-011 |
| `expense_update_expense` | W | （支払日の省略時）`GET /payment-methods/{payment_method_id}/estimated-payment-date` → `PATCH /expenses/{expense_id}`（expense-management） | REQ-011 |
| `expense_delete_expense` | D | `DELETE /expenses/{expense_id}`（expense-management） | REQ-011 |
| `room_get_state` | R | `GET /state`（room） | REQ-014 |
| `room_set_device_state` | W | `PUT /devices/{device}/state`（room） | REQ-015 |
| `room_run_scene` | W | `POST /scenes/{scene}`（room） | REQ-015 |
| `room_list_timers` | R | `GET /schedules`（room） | REQ-016 |
| `room_create_timer` | W | `POST /schedules`（room） | REQ-016 |
| `room_update_timer` | W | `PUT /schedules/{schedule_id}`（room） | REQ-016 |
| `room_set_timer_enabled` | W | `PUT /schedules/{schedule_id}/enabled`（room） | REQ-016 |
| `room_delete_timer` | D | `DELETE /schedules/{schedule_id}`（room） | REQ-016 |

## ツール詳細

### 共通

#### `list_sites`

- **説明**: 接続先として登録されているサイト（Web アプリ）の一覧を返します。ほかのツールの引数 `site` に指定できる識別子と、既定のサイトが分かります。
- **注釈**: R
- **呼び出す API**: なし（`sites.toml` から返す）
- **入力**: なし
- **出力**

```json
{
  "default_site": "home",
  "sites": [
    { "id": "home", "title": "自宅", "is_default": true }
  ]
}
```

URL と API キーは含めない。

- **エラー**: なし

### スケジュール（schedule）

#### `schedule_list_schedules`

- **説明**: 期間を指定して、その期間に重なる予定と TODO を返します。予定・TODO の更新や削除で使う ID もここで確かめます。
- **注釈**: R
- **呼び出す API**: `GET /schedules?start_date=&end_date=`
- **入力**

| 引数 | 型 | 必須 | 説明 |
|------|----|------|------|
| `start_date` | string（日付） | 必須 | 期間の開始日 |
| `end_date` | string（日付） | 必須 | 期間の終了日。開始日以降 |

- **出力**: Web アプリの応答（`{ "items": [ { "id", "title", "location", "detail", "kind", "granularity", "start_date", "end_date", "start_time", "end_time", "category_id", "is_completed", "routine_id", "needs_notification" } ] }`）
- **エラー**: 共通エラーのみ

#### `schedule_list_categories`

- **説明**: 予定・TODO のカテゴリの一覧を返します。予定・TODO の登録・更新で指定する `category_id` をここで確かめます。
- **注釈**: R
- **呼び出す API**: `GET /categories`
- **入力**

| 引数 | 型 | 必須 | 説明 |
|------|----|------|------|
| `include_deleted` | boolean | 任意 | `true` で削除済みのカテゴリも含める。既定 `false` |

- **出力**: Web アプリの応答（`{ "items": [ { "id", "name", "color", "is_deleted" } ] }`）
- **エラー**: 共通エラーのみ

#### `schedule_create_schedule`

- **説明**: 予定または TODO を 1 件登録します。`category_id` は `schedule_list_categories` で確かめます。時間単位（`granularity=time`）のときは開始・終了の時刻が必要です。TODO は未実施で登録されます。
- **注釈**: W
- **呼び出す API**: `POST /schedules`
- **入力**

| 引数 | 型 | 必須 | 説明 |
|------|----|------|------|
| `title` | string | 必須 | タイトル。空不可 |
| `kind` | `"event"` \| `"todo"` | 必須 | 予定か TODO か |
| `granularity` | `"day"` \| `"time"` | 必須 | 日単位か時間単位か |
| `start_date` | string（日付） | 必須 | 開始日 |
| `end_date` | string（日付） | 必須 | 終了日 |
| `start_time` | string（時刻）\| null | 条件付き | 時間単位のとき必須。日単位のときは省略 |
| `end_time` | string（時刻）\| null | 条件付き | 同上 |
| `category_id` | integer | 必須 | カテゴリ |
| `needs_notification` | boolean | 任意 | 通知が要るか。既定 `false` |
| `location` | string \| null | 任意 | 場所 |
| `detail` | string \| null | 任意 | 詳細 |

- **出力**: 登録された 1 件（`schedule_list_schedules` の `items` の要素と同じ形）
- **エラー**: 共通エラーのほか

| 条件 | ツールのエラー文 |
|------|------------------|
| 404 | 指定したカテゴリが見つかりません。`schedule_list_categories` で確かめてください。 |

#### `schedule_update_schedule`

- **説明**: 登録済みの予定または TODO を更新します。すべての項目を送る必要があります。先に `schedule_list_schedules` で現在の値を確かめ、変えない項目も現在の値のまま渡してください（`location`・`detail` を `null` にすると空になります）。予定を TODO に変えると未実施になり、TODO を予定に変えると実施状態は消えます。
- **注釈**: W
- **呼び出す API**: `PATCH /schedules/{schedule_id}`
- **入力**

| 引数 | 型 | 必須 | 説明 |
|------|----|------|------|
| `schedule_id` | integer | 必須 | 更新する予定・TODO |
| `title` | string | 必須 | |
| `kind` | `"event"` \| `"todo"` | 必須 | |
| `granularity` | `"day"` \| `"time"` | 必須 | |
| `start_date` | string（日付） | 必須 | |
| `end_date` | string（日付） | 必須 | |
| `start_time` | string（時刻）\| null | 必須 | 日単位のときは `null` |
| `end_time` | string（時刻）\| null | 必須 | 日単位のときは `null` |
| `category_id` | integer | 必須 | |
| `needs_notification` | boolean | 必須 | |
| `location` | string \| null | 必須 | 空にするときは `null` |
| `detail` | string \| null | 必須 | 空にするときは `null` |

- **出力**: 更新後の 1 件
- **エラー**: 共通エラーのほか

| 条件 | ツールのエラー文 |
|------|------------------|
| 404 | 予定・TODO またはカテゴリが見つかりません。ID を確かめてください。 |

#### `schedule_set_todo_completion`

- **説明**: TODO の実施済み／未実施を切り替えます。予定（`kind=event`）には使えません。
- **注釈**: W
- **呼び出す API**: `PATCH /schedules/{schedule_id}/completion`
- **入力**

| 引数 | 型 | 必須 | 説明 |
|------|----|------|------|
| `schedule_id` | integer | 必須 | 対象の TODO |
| `is_completed` | boolean | 必須 | `true` で実施済み、`false` で未実施 |

- **出力**: 更新後の 1 件
- **エラー**: 共通エラーのほか

| 条件 | ツールのエラー文 |
|------|------------------|
| 409 | 予定（TODO でないもの）には実施状態を設定できません。 |

#### `schedule_delete_schedule`

- **説明**: 予定または TODO を削除します。**この操作は元に戻せません**（MCP サーバからは復元できません）。
- **注釈**: D
- **呼び出す API**: `DELETE /schedules/{schedule_id}`
- **入力**

| 引数 | 型 | 必須 | 説明 |
|------|----|------|------|
| `schedule_id` | integer | 必須 | 削除する予定・TODO |

- **出力**: `{ "deleted": true, "id": <schedule_id> }`
- **エラー**: 共通エラーのみ

### グッズ管理（goods-management）

#### `goods_list_persons` / `goods_list_artists` / `goods_list_media`

- **説明**:
  - `goods_list_persons`: 人物の一覧を返します。グッズの一覧（`goods_list_goods`）には人物の指定が必要なので、先にこれで `person_id` を確かめます。
  - `goods_list_artists`: アーティストの一覧を返します。グッズの登録・更新で指定する `artist_id` を確かめます。
  - `goods_list_media`: 媒体の一覧を返します。グッズの登録・更新で指定する `media_id` を確かめます。
- **注釈**: R
- **呼び出す API**: それぞれ `GET /persons`、`GET /artists`、`GET /media`
- **入力**: なし
- **出力**: Web アプリの応答（`{ "items": [ { "id", "name" } ] }`）
- **エラー**: 共通エラーのみ

#### `goods_list_goods`

- **説明**: 人物を起点に、グッズの一覧を返します（発売日の新しい順）。アーティスト・媒体で絞り込めます。人物・アーティスト・媒体の ID は、それぞれの一覧のツールで確かめます。画像のデータは含みません。
- **注釈**: R
- **呼び出す API**: `GET /goods?person_id=&artist_id=&media_id=`
- **入力**

| 引数 | 型 | 必須 | 説明 |
|------|----|------|------|
| `person_id` | integer | 必須 | 起点の人物 |
| `artist_id` | integer | 任意 | 絞り込むアーティスト（その人物に紐づくもの） |
| `media_id` | integer | 任意 | 絞り込む媒体 |

- **出力**: Web アプリの応答から、各要素の `thumbnail_image_data` を除いたもの（`thumbnail_image_type` は残す。画像が無ければ `null`）。

```json
{
  "items": [
    {
      "goods_id": 100, "media_id": 1, "media_name": "1stシングル", "artist_id": 1, "artist_name": "サンプルズ",
      "title": "サンプルグッズ", "release_date": "2026-01-01", "is_owned": true, "code_number": "ABC-123",
      "thumbnail_image_type": "image/jpeg"
    }
  ]
}
```

- **エラー**: 共通エラーのほか

| 条件 | ツールのエラー文 |
|------|------------------|
| 404 | 人物・アーティスト・媒体のいずれかが見つからないか、アーティストがその人物に紐づいていません。 |

#### `goods_get_goods`

- **説明**: グッズ 1 件の詳細（メモを含む）を返します。更新の前に現在の値を確かめるのにも使います。画像のデータは含みません。
- **注釈**: R
- **呼び出す API**: `GET /goods/{goods_id}`
- **入力**

| 引数 | 型 | 必須 | 説明 |
|------|----|------|------|
| `goods_id` | integer | 必須 | 対象のグッズ |

- **出力**: Web アプリの応答から、`images` の各要素の `image_data` を除いたもの。

```json
{
  "id": 100, "media_id": 1, "artist_id": 1, "title": "サンプルグッズ", "release_date": "2026-01-01",
  "memo": "メモ", "is_owned": true, "code_number": "ABC-123",
  "images": [ { "id": 1, "image_type": "image/jpeg", "display_order": 1 } ]
}
```

- **エラー**: 共通エラーのみ

#### `goods_create_goods`

- **説明**: グッズを 1 件登録します。`artist_id`・`media_id` はそれぞれの一覧のツールで確かめます。画像はこのツールでは登録できません。
- **注釈**: W
- **呼び出す API**: `POST /goods`
- **入力**

| 引数 | 型 | 必須 | 説明 |
|------|----|------|------|
| `media_id` | integer | 必須 | 媒体 |
| `artist_id` | integer | 必須 | アーティスト |
| `title` | string | 必須 | タイトル。空不可 |
| `release_date` | string（日付）\| null | 任意 | 発売日。省略すると登録日になる |
| `memo` | string \| null | 任意 | メモ |
| `is_owned` | boolean | 任意 | 所持済みか。既定 `false` |
| `code_number` | string \| null | 任意 | 品番 |

- **出力**: 登録された 1 件（`goods_get_goods` と同じ形。`images` は空配列）
- **エラー**: 共通エラーのほか

| 条件 | ツールのエラー文 |
|------|------------------|
| 404 | 指定した媒体またはアーティストが見つかりません。 |

#### `goods_update_goods`

- **説明**: 登録済みのグッズを更新します。すべての項目を送る必要があります。先に `goods_get_goods` で現在の値を確かめ、変えない項目も現在の値のまま渡してください（`memo`・`code_number` を `null` にすると空になります。`release_date` を `null` にすると現在の発売日のままになります）。画像は変わりません。
- **注釈**: W
- **呼び出す API**: `PATCH /goods/{goods_id}`
- **入力**

| 引数 | 型 | 必須 | 説明 |
|------|----|------|------|
| `goods_id` | integer | 必須 | 更新するグッズ |
| `media_id` | integer | 必須 | |
| `artist_id` | integer | 必須 | |
| `title` | string | 必須 | |
| `release_date` | string（日付）\| null | 必須 | `null` で現在の値のまま |
| `memo` | string \| null | 必須 | |
| `is_owned` | boolean | 必須 | |
| `code_number` | string \| null | 必須 | |

- **出力**: 更新後の 1 件（`goods_get_goods` と同じ形）
- **エラー**: 共通エラーのほか

| 条件 | ツールのエラー文 |
|------|------------------|
| 404 | グッズ・媒体・アーティストのいずれかが見つかりません。 |

#### `goods_delete_goods`

- **説明**: グッズを削除します。**この操作は元に戻せません**（MCP サーバからは復元できません）。
- **注釈**: D
- **呼び出す API**: `DELETE /goods/{goods_id}`
- **入力**: `goods_id`（integer、必須）
- **出力**: `{ "deleted": true, "id": <goods_id> }`
- **エラー**: 共通エラーのみ

### ノウハウ管理（knowhow-management）

#### `knowhow_list_major_categories`

- **説明**: ノウハウの大項目の一覧を返します。
- **注釈**: R
- **呼び出す API**: `GET /major-categories`
- **入力**: なし
- **出力**: Web アプリの応答（`{ "items": [ { "id", "name", "display_order" } ] }`）
- **エラー**: 共通エラーのみ

#### `knowhow_list_middle_categories`

- **説明**: 指定した大項目に属する中項目の一覧を返します。ノウハウの登録・更新で指定する `middle_category_id` をここで確かめます。
- **注釈**: R
- **呼び出す API**: `GET /major-categories/{major_category_id}/middle-categories`
- **入力**: `major_category_id`（integer、必須）
- **出力**: Web アプリの応答（`{ "items": [ { "id", "major_category_id", "name", "display_order" } ] }`）
- **エラー**: 共通エラーのほか

| 条件 | ツールのエラー文 |
|------|------------------|
| 404 | 指定した大項目が見つかりません。 |

#### `knowhow_search_knowhows`

- **説明**: キーワードでノウハウを検索します。すべてのキーワードを含む（タイトル・キーワード・本文のいずれかに部分一致。大文字小文字は区別しない）ノウハウを返します。本文は含まないので、内容は `knowhow_get_knowhow` で取得します。
- **注釈**: R
- **呼び出す API**: `GET /knowhows/search?keyword=...&keyword=...`
- **入力**

| 引数 | 型 | 必須 | 説明 |
|------|----|------|------|
| `keywords` | string の配列 | 必須 | 1 つ以上。空文字は不可 |

- **出力**: Web アプリの応答（`{ "items": [ { "knowhow_id", "title", "display_order", "major_category_id", "major_category_name", "middle_category_id", "middle_category_name" } ] }`）
- **エラー**: 共通エラーのみ

#### `knowhow_get_knowhow`

- **説明**: ノウハウ 1 件の詳細（タイトル・キーワード・本文・所属する中項目）を返します。
- **注釈**: R
- **呼び出す API**: `GET /knowhows/{knowhow_id}`
- **入力**: `knowhow_id`（integer、必須）
- **出力**: Web アプリの応答（`{ "id", "title", "keywords", "content", "middle_category_id", "display_order" }`）
- **エラー**: 共通エラーのみ

#### `knowhow_create_knowhow`

- **説明**: ノウハウを 1 件登録します。中項目を指定しないと未分類になります。
- **注釈**: W
- **呼び出す API**: `POST /knowhows`
- **入力**

| 引数 | 型 | 必須 | 説明 |
|------|----|------|------|
| `title` | string | 必須 | 空不可 |
| `content` | string | 必須 | 本文。空不可 |
| `keywords` | string \| null | 任意 | キーワード（自由記述） |
| `middle_category_id` | integer \| null | 任意 | 所属する中項目。省略・`null` で未分類 |

- **出力**: 登録された 1 件（`knowhow_get_knowhow` と同じ形）
- **エラー**: 共通エラーのほか

| 条件 | ツールのエラー文 |
|------|------------------|
| 404 | 指定した中項目が見つかりません。 |

#### `knowhow_update_knowhow`

- **説明**: 登録済みのノウハウを更新します。すべての項目を送る必要があります。先に `knowhow_get_knowhow` で現在の値を確かめ、変えない項目も現在の値のまま渡してください（`keywords` を `null` にすると空に、`middle_category_id` を `null` にすると未分類になります）。
- **注釈**: W
- **呼び出す API**: `PATCH /knowhows/{knowhow_id}`
- **入力**

| 引数 | 型 | 必須 | 説明 |
|------|----|------|------|
| `knowhow_id` | integer | 必須 | 更新するノウハウ |
| `title` | string | 必須 | |
| `content` | string | 必須 | |
| `keywords` | string \| null | 必須 | |
| `middle_category_id` | integer \| null | 必須 | |

- **出力**: 更新後の 1 件
- **エラー**: 共通エラーのほか

| 条件 | ツールのエラー文 |
|------|------------------|
| 404 | ノウハウまたは中項目が見つかりません。 |

#### `knowhow_delete_knowhow`

- **説明**: ノウハウを削除します。**この操作は元に戻せません**（MCP サーバからは復元できません）。
- **注釈**: D
- **呼び出す API**: `DELETE /knowhows/{knowhow_id}`
- **入力**: `knowhow_id`（integer、必須）
- **出力**: `{ "deleted": true, "id": <knowhow_id> }`
- **エラー**: 共通エラーのみ

### 経費管理（expense-management）

#### `expense_list_budget_periods`

- **説明**: 予算期間の一覧（開始日の新しい順。予算項目の金額合計つき）を返します。
- **注釈**: R
- **呼び出す API**: `GET /budget-periods`
- **入力**: なし
- **出力**: Web アプリの応答（`{ "items": [ { "id", "title", "start_date", "end_date", "total_amount" } ] }`）
- **エラー**: 共通エラーのみ

#### `expense_list_budget_items`

- **説明**: 指定した予算期間の予算項目の一覧を返します。支出記録を予算に割り当てるときの `budget_item_id` をここで確かめます。
- **注釈**: R
- **呼び出す API**: `GET /budget-items?budget_period_id=`
- **入力**: `budget_period_id`（integer、必須）
- **出力**: Web アプリの応答（`{ "items": [ { "id", "budget_period_id", "name", "amount", "display_order", "memo" } ] }`）
- **エラー**: 共通エラーのほか

| 条件 | ツールのエラー文 |
|------|------------------|
| 404 | 指定した予算期間が見つかりません。 |

#### `expense_list_payment_methods`

- **説明**: 支出方法（現金・カードなど）の一覧を、締め日・支払日のルールや売掛区分とともに返します。支出記録の登録・更新で指定する `payment_method_id` をここで確かめます。`is_credit`・`is_credit_payment` がともに `false` なら通常、`is_credit` が `true` なら売掛（後日精算する支出）、`is_credit_payment` が `true` なら売掛支払（売掛の精算）です。
- **注釈**: R
- **呼び出す API**: `GET /payment-methods`
- **入力**: なし
- **出力**: Web アプリの応答（`{ "items": [ { "id", "name", "closing_day", "closing_day_shift_direction", "closing_day_exclusions", "payment_month_offset", "payment_day", "payment_day_shift_direction", "payment_day_exclusions", "display_order", "is_credit", "is_credit_payment" } ] }`）
- **エラー**: 共通エラーのみ

#### `expense_list_expenses`

- **説明**: 支出記録の一覧（利用日の新しい順）を返します。絞り込みは次のいずれか 1 つです: 利用日の期間（`start_date` と `end_date`）、予算期間（`budget_period_id`）、予算なしの記録だけ（`unassigned=true`）。
- **注釈**: R
- **呼び出す API**: `GET /expenses`
- **入力**

| 引数 | 型 | 必須 | 説明 |
|------|----|------|------|
| `start_date` | string（日付） | 条件付き | `budget_period_id` も `unassigned` も指定しないとき必須 |
| `end_date` | string（日付） | 条件付き | 同上 |
| `budget_period_id` | integer | 任意 | この予算期間の記録だけ |
| `unassigned` | boolean | 任意 | `true` で予算なしの記録だけ。`budget_period_id` と同時には指定できない |

- **出力**: Web アプリの応答（`{ "items": [ { "id", "usage_date", "budget_period_id", "budget_item_id", "purpose", "amount", "payment_method_id", "memo", "payment_date", "payment_date_is_auto", "created_at" } ] }`）
- **エラー**: 共通エラーのみ（組み合わせの誤りは 400）

#### `expense_get_usage_date_report`

- **説明**: 予算期間を指定して、予算項目ごとの予算と実績（利用日が期間内の支出の合計）と差額を返します。`include_credit` で、売掛（後日精算する支出）を実績に含めるかどうかを選べます。売掛支払（売掛の精算）は、`include_credit` の値に関わらず実績に含みません。
- **注釈**: R
- **呼び出す API**: `GET /reports/usage-date?budget_period_id=&include_credit=`
- **入力**

| 引数 | 型 | 必須 | 説明 |
|------|----|------|------|
| `budget_period_id` | integer | 必須 | 予算期間 |
| `include_credit` | boolean | 任意（既定 `false`） | `true` で売掛を実績に含める |

- **出力**: Web アプリの応答（`{ "budget_period": { "id", "title", "start_date", "end_date" }, "items": [ { "budget_item_id", "name", "budget_amount", "actual_amount", "difference" } ] }`）
- **エラー**: 共通エラーのほか

| 条件 | ツールのエラー文 |
|------|------------------|
| 404 | 指定した予算期間が見つかりません。 |

#### `expense_get_payment_date_report`

- **説明**: 年月を指定して、その年月に支払日を持つ支出を、支払日ごと・売掛区分（通常・売掛・売掛支払）ごとに合計して返します。締め日が 0（即時支払）の支出方法によるものは対象外です。予算項目による内訳はありません。
- **注釈**: R
- **呼び出す API**: `GET /reports/payment-date?year_month=`
- **入力**: `year_month`（string（年月）、必須）
- **出力**: Web アプリの応答（`{ "items": [ { "payment_date", "normal_amount", "credit_amount", "credit_payment_amount" } ] }`。`normal_amount` は通常、`credit_amount` は売掛、`credit_payment_amount` は売掛支払の、その支払日における合計金額）
- **エラー**: 共通エラーのみ

#### `expense_create_expense`

- **説明**: 支出記録を 1 件登録します。`payment_method_id` は `expense_list_payment_methods` で確かめます。予算に割り当てるときは `budget_period_id` と `budget_item_id` の両方を指定します（`expense_list_budget_items` で確かめる）。どちらも省略すると「予算なし」になります。`payment_date`（支払日）を省略すると、支出方法と利用日から自動で算出します。
- **注釈**: W
- **呼び出す API**: `payment_date` の省略時は `GET /payment-methods/{payment_method_id}/estimated-payment-date?usage_date=` を呼び、その `payment_date` を使って `payment_date_is_auto=true` で `POST /expenses`。指定時は `payment_date_is_auto=false` で `POST /expenses` だけを呼ぶ。
- **入力**

| 引数 | 型 | 必須 | 説明 |
|------|----|------|------|
| `usage_date` | string（日付） | 必須 | 利用日 |
| `purpose` | string | 必須 | 用途。空不可 |
| `amount` | string（金額） | 必須 | 金額。0 以上 |
| `payment_method_id` | integer | 必須 | 支出方法 |
| `budget_period_id` | integer \| null | 任意 | 予算期間。`budget_item_id` と組で指定 |
| `budget_item_id` | integer \| null | 任意 | 予算項目。`budget_period_id` の予算項目 |
| `memo` | string \| null | 任意 | メモ |
| `payment_date` | string（日付）\| null | 任意 | 支払日。省略すると自動で算出する |

- **出力**: 登録された 1 件（`expense_list_expenses` の `items` の要素と同じ形）
- **エラー**: 共通エラーのほか

| 条件 | ツールのエラー文 |
|------|------------------|
| 支払日の算出で 404 | 指定した支出方法が見つかりません。`expense_list_payment_methods` で確かめてください。（登録していません） |
| 支払日の算出で 400・5xx など | 支払日を算出できませんでした。（登録していません）＋共通エラーの文 |
| 登録で 400 | 共通の 400 の文（予算期間と予算項目の組み合わせ、支出方法の誤りもここに含まれる） |

算出に失敗したときは、登録の API を呼ばない。

#### `expense_update_expense`

- **説明**: 登録済みの支出記録を更新します。支払日以外のすべての項目を送る必要があります。先に `expense_list_expenses` で現在の値を確かめ、変えない項目も現在の値のまま渡してください（`budget_period_id`・`budget_item_id` を `null` にすると予算なしに、`memo` を `null` にすると空になります）。`payment_date` を省略すると、支出方法と利用日から支払日を算出し直します。
- **注釈**: W
- **呼び出す API**: `expense_create_expense` と同じ流れで、登録の代わりに `PATCH /expenses/{expense_id}`
- **入力**

| 引数 | 型 | 必須 | 説明 |
|------|----|------|------|
| `expense_id` | integer | 必須 | 更新する支出記録 |
| `usage_date` | string（日付） | 必須 | |
| `purpose` | string | 必須 | |
| `amount` | string（金額） | 必須 | |
| `payment_method_id` | integer | 必須 | |
| `budget_period_id` | integer \| null | 必須 | |
| `budget_item_id` | integer \| null | 必須 | |
| `memo` | string \| null | 必須 | |
| `payment_date` | string（日付）\| null | 任意 | 省略すると算出し直す（自動算出として記録）。指定すると手入力として記録 |

- **出力**: 更新後の 1 件
- **エラー**: `expense_create_expense` と同じ（「登録していません」を「更新していません」と読み替える）。ほかに

| 条件 | ツールのエラー文 |
|------|------------------|
| 更新で 404 | 支出記録が見つかりません。ID を確かめてください。 |

#### `expense_delete_expense`

- **説明**: 支出記録を削除します。**この操作は元に戻せません**（MCP サーバからは復元できません）。
- **注釈**: D
- **呼び出す API**: `DELETE /expenses/{expense_id}`
- **入力**: `expense_id`（integer、必須）
- **出力**: `{ "deleted": true, "id": <expense_id> }`
- **エラー**: 共通エラーのみ

### ROOM（room）

ROOM は、自室の機器（電灯、間接照明、屋内スピーカー、枕元スピーカー、玄関ドア）の状態を示し、操作する機能である。機器の実体は SwitchBot 製品で、Web アプリの ROOM が SwitchBot を呼ぶ。MCP サーバは SwitchBot を直接呼ばない。

- **玄関ドアは参照のみ**。施錠・開錠のツールは無く、`room_set_device_state` の `device` の選択肢にも含めない（REQ-015）。一括切替・定期実行にも、玄関ドアを変えるものは無い。
- 機器の値は、`device`（`ceiling_light`、`indirect_light`、`indoor_speaker`、`bedside_speaker`、`front_door`）と、`state`（`on`・`off`、玄関ドアは `locked`・`unlocked`）で表す。Web アプリと同じ。
- 機器の操作のツール（`room_set_device_state`、`room_run_scene`）は、**実機が動く**。
- 定期実行のツールは、名前に `timer` を使う。スケジュール機能の予定（`schedule_*`）とは別のもの。

機器の状態（`device_state`）の形（Web アプリの応答のまま）:

```json
{ "status": "ok", "state": "on" }
```

- `status`: `ok`（取得できた）または `error`（取得できなかった）。`error` のとき `state` は `null`（状態を推測した値は返らない）。
- 玄関ドアは、さらに `battery`（電池残量。0〜100 の整数。取得できなければ `null`）を持つ。
- 電灯は、さらに `implemented`（常に `false`。未実装）を持つ。

ROOM の 502（機器を操作できなかった）は、次のエラー文で返す。これは `room_set_device_state` に適用する。`room_run_scene` は、一部の機器が失敗しても 200 で返るため、結果の `results` で示す。

| 条件 | ツールのエラー文 |
|------|------------------|
| 502 | サイト `<site>` の ROOM が機器を操作できませんでした（SwitchBot に接続できないか、機器がエラーを返しました）。実際の状態を `room_get_state` で確かめてください。 |

#### `room_get_state`

- **説明**: ROOM の 5 つの機器（電灯、間接照明、屋内スピーカー、枕元スピーカー、玄関ドア）の現在の状態と、状態を取得した日時を返します。機器の ON/OFF、玄関ドアの施錠中/開錠中と電池残量が分かります。実機に問い合わせるため、数秒かかることがあります。取得できなかった機器は `status` が `error` になり、他の機器の状態は返ります。電灯は未実装のため、常に OFF（`implemented` が `false`）です。機器を操作する前後の確認に使います。
- **注釈**: R
- **呼び出す API**: `GET /state`
- **入力**: なし
- **出力**: Web アプリの応答

```json
{
  "fetched_at": "2026-10-01T10:15:30+09:00",
  "devices": {
    "ceiling_light": { "status": "ok", "state": "off", "implemented": false },
    "indirect_light": { "status": "ok", "state": "on" },
    "indoor_speaker": { "status": "error", "state": null },
    "bedside_speaker": { "status": "ok", "state": "off" },
    "front_door": { "status": "ok", "state": "locked", "battery": 35 }
  }
}
```

- **エラー**: 共通エラーのみ（機器ごとの取得の失敗は、エラーではなく、出力の `status` で示される）

#### `room_set_device_state`

- **説明**: ROOM の機器を 1 つ、ON または OFF にします。**実機が実際に動きます。** 対象は、電灯、間接照明、屋内スピーカー、枕元スピーカーです。**玄関ドアは操作できません**（状態の参照だけです）。現在の状態の反転ではなく、**目標の状態**（`on` か `off`）を指定してください。電灯は未実装のため、何も起きず、結果の `applied` が `false` になります。結果の `result` は、操作のあとに、その機器の状態を取得し直したものです（実機の反映が遅れて、目標と食い違うことがあります）。複数の機器を決まった組み合わせで切り替えるときは、`room_run_scene` を使います。
- **注釈**: W
- **呼び出す API**: `PUT /devices/{device}/state`（本文 `{ "state": "on" | "off" }`）
- **入力**

| 引数 | 型 | 必須 | 説明 |
|------|----|------|------|
| `device` | `"ceiling_light"` \| `"indirect_light"` \| `"indoor_speaker"` \| `"bedside_speaker"` | 必須 | 操作する機器。玄関ドア（`front_door`）は選べない |
| `state` | `"on"` \| `"off"` | 必須 | 目標の状態 |

- **出力**: Web アプリの応答

```json
{
  "device": "indirect_light",
  "applied": true,
  "fetched_at": "2026-10-01T10:15:33+09:00",
  "result": { "status": "ok", "state": "on" }
}
```

- `applied`: 機器へ指示を送ったか。電灯は `false`。
- `result`: 操作のあとの、その機器の状態（`device_state`）。指示が成功しても、取得し直しに失敗したときは `status` が `error`。

- **エラー**: 共通エラーと、上記の 502 のほか

| 条件 | ツールのエラー文 |
|------|------------------|
| 404 | 機器が見つかりません。`device` は、電灯、間接照明、屋内スピーカー、枕元スピーカーのいずれかを指定してください。 |

`device` と `state` は、入力スキーマの列挙で検査される（誤った値は SDK の入力検証のエラー）。

#### `room_run_scene`

- **説明**: ROOM の一括切替を実行します。**実機が実際に動きます。** `scene` は次の 5 種です。いずれも、玄関ドアは変えません。電灯は未実装のため、電灯への指示は行われず、結果が `skipped` になります。
  - `indoor_speaker`（屋内スピーカー選択）: 屋内スピーカーを ON、枕元スピーカーを OFF
  - `bedside_speaker`（枕元スピーカー選択）: 屋内スピーカーを OFF、枕元スピーカーを ON
  - `ceiling_light`（電灯選択）: 電灯を ON、間接照明を OFF（電灯は未実装のため、間接照明の OFF だけが行われます）
  - `indirect_light`（間接照明選択）: 電灯を OFF、間接照明を ON
  - `out`（お出かけ）: 電灯・間接照明・屋内スピーカー・枕元スピーカーをすべて OFF

  一部の機器が失敗しても、エラーにはならず、機器ごとの結果が返ります。成功した機器は元に戻りません。実行のあとの、全機器の状態も返ります。
- **注釈**: W
- **呼び出す API**: `POST /scenes/{scene}`
- **入力**

| 引数 | 型 | 必須 | 説明 |
|------|----|------|------|
| `scene` | `"indoor_speaker"` \| `"bedside_speaker"` \| `"ceiling_light"` \| `"indirect_light"` \| `"out"` | 必須 | 実行する一括切替 |

- **出力**: Web アプリの応答

```json
{
  "scene": "ceiling_light",
  "outcome": "success",
  "results": [
    { "device": "ceiling_light", "target": "on", "outcome": "skipped" },
    { "device": "indirect_light", "target": "off", "outcome": "success" }
  ],
  "fetched_at": "2026-10-01T10:15:36+09:00",
  "devices": {
    "ceiling_light": { "status": "ok", "state": "off", "implemented": false },
    "indirect_light": { "status": "ok", "state": "off" },
    "indoor_speaker": { "status": "ok", "state": "off" },
    "bedside_speaker": { "status": "ok", "state": "off" },
    "front_door": { "status": "ok", "state": "locked", "battery": 35 }
  }
}
```

- `results`: 機器ごとの結果。`outcome` は `success`、`failure`、`skipped`（電灯。未実装）。
- `outcome`（全体）: 指示した機器（`skipped` を除く）がすべて成功なら `success`、すべて失敗なら `failure`、混在なら `partial`。
- `devices`: 実行のあとに、全機器の状態を取得し直した結果。

- **エラー**: 共通エラーのみ

`scene` は、入力スキーマの列挙で検査される。

#### `room_list_timers`

- **説明**: ROOM の定期実行（タイマー）の一覧を返します。定期実行は、指定した日（毎日、または曜日の指定）と時刻に、実行内容（一括切替、または機器 1 つの個別切替）を自動で行う仕組みです。実行条件、曜日、祝日の扱い、実行日の取り方、時刻、実行内容（`scene`、または `device` と `state`）、有効／無効、最終実行の結果が分かります。**スケジュール機能の予定・TODO（`schedule_*`）とは別のものです。** 更新・有効／無効の切り替え・削除で使う ID も、ここで確かめます。
- **注釈**: R
- **呼び出す API**: `GET /schedules`
- **入力**: なし
- **出力**: Web アプリの応答

```json
{
  "schedules": [
    {
      "id": 1,
      "condition": "weekdays",
      "weekdays": [1, 3, 5],
      "holiday_mode": "none",
      "day_shift": "same",
      "run_time": "07:00",
      "scene": "indoor_speaker",
      "device": null,
      "state": null,
      "is_enabled": true,
      "last_run": {
        "at": "2026-10-01T07:00:02+09:00",
        "result": "partial",
        "failed_devices": ["bedside_speaker"]
      }
    },
    {
      "id": 2,
      "condition": "weekdays",
      "weekdays": [1, 2, 3, 4, 5],
      "holiday_mode": "exclude",
      "day_shift": "before",
      "run_time": "22:30",
      "scene": null,
      "device": "indirect_light",
      "state": "off",
      "is_enabled": true,
      "last_run": null
    }
  ]
}
```

- `condition`: `daily`（毎日）、`weekdays`（曜日の指定）。祝日だけの条件は無い。
- `holiday_mode`、`day_shift`: `condition` が `weekdays` のときに意味を持つ。`daily` のときは、常に `none`、`same`。値の意味は、`room_create_timer` の入力の説明のとおり。
- 実行内容: 一括切替のときは `scene` が値を持ち、`device` と `state` は `null`。機器の個別切替のときは `device` と `state` が値を持ち、`scene` は `null`。
- `weekdays`: `condition` が `weekdays` のときは 1 件以上。1 = 月曜、…、7 = 日曜。それ以外は空配列。
- `last_run`: 未実行は `null`。`result` は `success`、`partial`、`failure`。機器の個別切替は、`success` か `failure` のみ（`failure` のとき、`failed_devices` は、その機器 1 つ）。
- 並びは、時刻の昇順。

- **エラー**: 共通エラーのみ

#### `room_create_timer`

- **説明**: ROOM の定期実行（タイマー）を 1 件登録します。実行条件、時刻、実行内容を指定します。実行条件が `weekdays`（曜日の指定）のときは、曜日が必要で、祝日の扱い（`holiday_mode`）と実行日の取り方（`day_shift`）も指定できます（省略すると、それぞれ指定した曜日のみ、当日）。`holiday_mode`（祝日の扱い）は、`none`（指定した曜日のみ。既定）、`include`（指定した曜日に加えて祝日にも実行）、`exclude`（指定した曜日のうち祝日は実行しない）。`day_shift`（実行日の取り方）は、`same`（当日。既定）、`before`（の前の日）、`after`（の次の日）。曜日と祝日の扱いで決まる日を「基準日」とし、`before` は基準日の前日に、`after` は基準日の翌日に実行します。実行内容は、一括切替（`scene`。`room_run_scene` と同じ 5 種）か、機器 1 つの個別切替（`device` と `state`）の、**どちらか一方だけ**を指定します。玄関ドアは、どちらにも指定できません。登録した定期実行は、既定で有効です。**スケジュール機能の予定の登録ではありません。**
- **注釈**: W
- **呼び出す API**: `POST /schedules`
- **入力**

| 引数 | 型 | 必須 | 説明 |
|------|----|------|------|
| `condition` | `"daily"` \| `"weekdays"` | 必須 | 実行条件。毎日、曜日の指定 |
| `weekdays` | integer[]（1〜7） | 条件付き | `condition` が `weekdays` のとき必須。1 = 月曜、…、7 = 日曜。重複なし。`daily` のときは省略または空 |
| `holiday_mode` | `"none"` \| `"include"` \| `"exclude"` | 任意 | 祝日の扱い。`none` = 指定した曜日のみ（省略時）、`include` = 祝日も実行、`exclude` = 祝日は実行しない。`condition` が `daily` のときは、省略または `none` |
| `day_shift` | `"same"` \| `"before"` \| `"after"` | 任意 | 実行日の取り方。`same` = 当日（省略時）、`before` = の前の日、`after` = の次の日。`condition` が `daily` のときは、省略または `same` |
| `run_time` | string（時刻 `HH:MM`、日本標準時） | 必須 | 実行する時刻 |
| `scene` | `"indoor_speaker"` \| `"bedside_speaker"` \| `"ceiling_light"` \| `"indirect_light"` \| `"out"` | 条件付き | 一括切替。実行内容が一括切替のとき必須。個別切替のときは省略 |
| `device` | `"ceiling_light"` \| `"indirect_light"` \| `"indoor_speaker"` \| `"bedside_speaker"` | 条件付き | 個別切替の機器（電灯は未実装で、指示は何も行われず、成功として扱われる）。実行内容が個別切替のとき必須。玄関ドアは選べない。一括切替のときは省略 |
| `state` | `"on"` \| `"off"` | 条件付き | 個別切替の状態。`device` を指定するとき必須。一括切替のときは省略 |
| `is_enabled` | boolean | 任意 | 有効にするか。既定 `true` |

- **出力**: 登録された 1 件（`room_list_timers` の `schedules` の要素と同じ形。`last_run` は `null`）
- **エラー**: 共通エラーのみ（入力不正は 400 の共通エラー文で返る。`scene` と `device` の両方、どちらも無い、`device` だけ・`state` だけ、毎日なのに祝日の扱い・実行日の取り方がある、などは、Web アプリが 400 で拒否する）
- **注意**: 引数は、`scene` と `device` + `state` の整合を、ツールの入力スキーマでは検査せず、Web アプリの検査に任せる（`design.md`）。`scene`・`device`・`state`・`holiday_mode`・`day_shift` の値の範囲（列挙）は、入力スキーマで検査される。

#### `room_update_timer`

- **説明**: 登録済みの ROOM の定期実行（タイマー）を更新します。実行条件・曜日・祝日の扱い・実行日の取り方・時刻・実行内容を、すべて送る必要があります（送らなかった曜日は空になり、**送らなかった祝日の扱いと実行日の取り方は、現在の値のままではなく、既定（`none`、`same`）に戻ります**）。先に `room_list_timers` で現在の値を確かめ、変えない項目も現在の値のまま渡してください。実行内容は、一括切替（`scene`）か、個別切替（`device` と `state`）かを、変えられます。有効／無効は、省略すると現在の値のままです。最終実行の結果は変わりません。
- **注釈**: W
- **呼び出す API**: `PUT /schedules/{schedule_id}`
- **入力**

| 引数 | 型 | 必須 | 説明 |
|------|----|------|------|
| `schedule_id` | integer | 必須 | 更新する定期実行 |
| `condition` | `"daily"` \| `"weekdays"` | 必須 | |
| `weekdays` | integer[]（1〜7） | 条件付き | `condition` が `weekdays` のとき必須。それ以外のときは省略または空 |
| `holiday_mode` | `"none"` \| `"include"` \| `"exclude"` | 任意 | 省略すると `none`（現在の値のままではない） |
| `day_shift` | `"same"` \| `"before"` \| `"after"` | 任意 | 省略すると `same`（現在の値のままではない） |
| `run_time` | string（時刻 `HH:MM`） | 必須 | |
| `scene` | `"indoor_speaker"` \| `"bedside_speaker"` \| `"ceiling_light"` \| `"indirect_light"` \| `"out"` | 条件付き | 一括切替。実行内容が一括切替のとき必須 |
| `device` | `"ceiling_light"` \| `"indirect_light"` \| `"indoor_speaker"` \| `"bedside_speaker"` | 条件付き | 個別切替の機器。実行内容が個別切替のとき必須。玄関ドアは選べない |
| `state` | `"on"` \| `"off"` | 条件付き | 個別切替の状態。`device` を指定するとき必須 |
| `is_enabled` | boolean | 任意 | 省略すると、現在の値のまま |

- **出力**: 更新後の 1 件
- **エラー**: 共通エラーのほか

| 条件 | ツールのエラー文 |
|------|------------------|
| 404 | 定期実行が見つかりません。ID を `room_list_timers` で確かめてください。 |

#### `room_set_timer_enabled`

- **説明**: ROOM の定期実行（タイマー）の有効／無効だけを切り替えます。無効にした定期実行は、自動で実行されません。他の項目と、最終実行の結果は変わりません。
- **注釈**: W
- **呼び出す API**: `PUT /schedules/{schedule_id}/enabled`
- **入力**

| 引数 | 型 | 必須 | 説明 |
|------|----|------|------|
| `schedule_id` | integer | 必須 | 対象の定期実行 |
| `is_enabled` | boolean | 必須 | `true` で有効、`false` で無効 |

- **出力**: 更新後の 1 件
- **エラー**: 共通エラーのほか

| 条件 | ツールのエラー文 |
|------|------------------|
| 404 | 定期実行が見つかりません。ID を `room_list_timers` で確かめてください。 |

#### `room_delete_timer`

- **説明**: ROOM の定期実行（タイマー）を削除します。**この操作は元に戻せません**（MCP サーバからは復元できません）。一時的に止めたいだけのときは、`room_set_timer_enabled` で無効にしてください。
- **注釈**: D
- **呼び出す API**: `DELETE /schedules/{schedule_id}`
- **入力**

| 引数 | 型 | 必須 | 説明 |
|------|----|------|------|
| `schedule_id` | integer | 必須 | 削除する定期実行 |

- **出力**: `{ "deleted": true, "id": <schedule_id> }`
- **エラー**: 共通エラーのほか

| 条件 | ツールのエラー文 |
|------|------------------|
| 404 | 定期実行が見つかりません。ID を `room_list_timers` で確かめてください。 |

## 要件トレーサビリティ

| 要件 | ツール・節 |
|------|------------|
| REQ-001〜REQ-002 | 共通事項の「認証」（詳細は `design.md`） |
| REQ-003 | `list_sites`、共通事項の「サイトの指定」、共通エラー（存在しないサイト・接続先なし） |
| REQ-004 | `schedule_list_schedules`、`schedule_list_categories` |
| REQ-005 | `schedule_create_schedule`、`schedule_update_schedule`、`schedule_set_todo_completion`、`schedule_delete_schedule` |
| REQ-006 | `goods_list_persons`、`goods_list_artists`、`goods_list_media`、`goods_list_goods`、`goods_get_goods` |
| REQ-007 | `goods_create_goods`、`goods_update_goods`、`goods_delete_goods` |
| REQ-008 | `knowhow_list_major_categories`、`knowhow_list_middle_categories`、`knowhow_search_knowhows`、`knowhow_get_knowhow` |
| REQ-009 | `knowhow_create_knowhow`、`knowhow_update_knowhow`、`knowhow_delete_knowhow` |
| REQ-010 | `expense_list_budget_periods`、`expense_list_budget_items`、`expense_list_payment_methods`、`expense_list_expenses`、`expense_get_usage_date_report`、`expense_get_payment_date_report` |
| REQ-011 | `expense_create_expense`、`expense_update_expense`、`expense_delete_expense` |
| REQ-012 | 共通エラー、削除のツールの説明（元に戻せない）、ROOM の 502 のエラー文 |
| REQ-013 | `design.md` の「ログ」 |
| REQ-014 | `room_get_state` |
| REQ-015 | `room_set_device_state`、`room_run_scene`（玄関ドアのツールは無い） |
| REQ-016 | `room_list_timers`、`room_create_timer`、`room_update_timer`、`room_set_timer_enabled`、`room_delete_timer` |

## 承認

現在の状態: 承認済み

| 日時 | 状態 | 変更概要 |
|------|------|----------|
| 2026-09-26 03:02 | 未承認 | 初版 |
| 2026-09-26 03:07 | 承認済み | 初版を承認 |
| 2026-09-27 | 未承認 | `expense_list_payment_methods` の出力に `is_credit`・`is_credit_payment` を追加。`expense_get_usage_date_report` に `include_credit` 引数を追加。`expense_get_payment_month_report` を `expense_get_payment_date_report`（`GET /reports/payment-date`、支払日ごと・売掛区分ごとの集計）に置き換え（REQ-010） |
| 2026-09-27 | 承認済み | 上記の改訂を承認 |
| 2026-10-01 13:15 | 未承認 | ROOM のツール 8 個（room_get_state、room_set_device_state、room_run_scene、room_list_timers、room_create_timer、room_update_timer、room_set_timer_enabled、room_delete_timer）を追加。玄関ドアのツールは作らない |
| 2026-10-01 13:17 | 承認済み | ROOM のツール 8 個の追加を承認 |
| 2026-10-02 11:13 | 未承認 | REQ-016 の改訂に合わせ、`room_list_timers`・`room_create_timer`・`room_update_timer` に、祝日の扱い（`holiday_mode`）、実行日の取り方（`day_shift`）、機器の個別切替（`device`・`state`）を追加し、実行条件から `holiday` を廃止。個別切替の結果の扱い、更新で省略したときの既定への復帰を追記 |
| 2026-10-02 11:14 | 承認済み | 定期実行のツールの改訂（個別切替、祝日の扱い、実行日の取り方）を承認 |
