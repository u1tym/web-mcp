from __future__ import annotations

from typing import Annotated, Any, Literal

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from app.tools import DELETE, READ, WRITE, SiteArg, ToolRunner, date_field, id_field, time_field
from app.webapp_client import ErrorMessages

FEATURE = "schedule"

Kind = Annotated[Literal["event", "todo"], Field(description="event（予定）または todo（TODO）")]
Granularity = Annotated[Literal["day", "time"], Field(description="day（日単位）または time（時間単位）")]

_UPDATE_NOTE = (
    "すべての項目を送る必要があります。先に schedule_list_schedules で現在の値を確かめ、"
    "変えない項目も現在の値のまま渡してください（location・detail を null にすると空になります）。"
)


def register(server: MCPServer, runner: ToolRunner) -> None:
    @server.tool(
        name="schedule_list_schedules",
        description="期間を指定して、その期間に重なる予定と TODO を返します。予定・TODO の更新や削除で使う ID もここで確かめます。",
        annotations=READ,
    )
    async def schedule_list_schedules(
        start_date: Annotated[str, date_field("期間の開始日")],
        end_date: Annotated[str, date_field("期間の終了日。開始日以降")],
        site: SiteArg = None,
    ) -> dict[str, Any]:
        tool = "schedule_list_schedules"
        target = runner.start(tool, site, start_date=start_date, end_date=end_date)
        return await runner.call(
            tool, target, FEATURE, "GET", "/schedules", params={"start_date": start_date, "end_date": end_date}
        )

    @server.tool(
        name="schedule_list_categories",
        description="予定・TODO のカテゴリの一覧を返します。予定・TODO の登録・更新で指定する category_id をここで確かめます。",
        annotations=READ,
    )
    async def schedule_list_categories(
        include_deleted: Annotated[bool, Field(description="true で削除済みのカテゴリも含める")] = False,
        site: SiteArg = None,
    ) -> dict[str, Any]:
        tool = "schedule_list_categories"
        target = runner.start(tool, site, include_deleted=include_deleted)
        return await runner.call(tool, target, FEATURE, "GET", "/categories", params={"include_deleted": include_deleted})

    @server.tool(
        name="schedule_create_schedule",
        description=(
            "予定または TODO を 1 件登録します。category_id は schedule_list_categories で確かめます。"
            "時間単位（granularity=time）のときは開始・終了の時刻が必要です。TODO は未実施で登録されます。"
        ),
        annotations=WRITE,
    )
    async def schedule_create_schedule(
        title: Annotated[str, Field(description="タイトル。空不可", min_length=1)],
        kind: Kind,
        granularity: Granularity,
        start_date: Annotated[str, date_field("開始日")],
        end_date: Annotated[str, date_field("終了日")],
        category_id: Annotated[int, id_field("カテゴリの ID")],
        start_time: Annotated[str, time_field("開始時刻。時間単位のとき必須。日単位のときは省略")] | None = None,
        end_time: Annotated[str, time_field("終了時刻。時間単位のとき必須。日単位のときは省略")] | None = None,
        needs_notification: Annotated[bool, Field(description="通知が要るか")] = False,
        location: Annotated[str | None, Field(description="場所")] = None,
        detail: Annotated[str | None, Field(description="詳細")] = None,
        site: SiteArg = None,
    ) -> dict[str, Any]:
        tool = "schedule_create_schedule"
        target = runner.start(
            tool, site, kind=kind, granularity=granularity, start_date=start_date, end_date=end_date, category_id=category_id
        )
        body = {
            "title": title,
            "location": location,
            "detail": detail,
            "kind": kind,
            "granularity": granularity,
            "start_date": start_date,
            "end_date": end_date,
            "start_time": start_time,
            "end_time": end_time,
            "category_id": category_id,
            "needs_notification": needs_notification,
        }
        return await runner.call(
            tool,
            target,
            FEATURE,
            "POST",
            "/schedules",
            json=body,
            messages=ErrorMessages(not_found="指定したカテゴリが見つかりません。schedule_list_categories で確かめてください。"),
        )

    @server.tool(
        name="schedule_update_schedule",
        description=(
            "登録済みの予定または TODO を更新します。"
            + _UPDATE_NOTE
            + "予定を TODO に変えると未実施になり、TODO を予定に変えると実施状態は消えます。"
        ),
        annotations=WRITE,
    )
    async def schedule_update_schedule(
        schedule_id: Annotated[int, id_field("更新する予定・TODO の ID")],
        title: Annotated[str, Field(description="タイトル。空不可", min_length=1)],
        kind: Kind,
        granularity: Granularity,
        start_date: Annotated[str, date_field("開始日")],
        end_date: Annotated[str, date_field("終了日")],
        start_time: Annotated[str, time_field("開始時刻。日単位のときは null")] | None,
        end_time: Annotated[str, time_field("終了時刻。日単位のときは null")] | None,
        category_id: Annotated[int, id_field("カテゴリの ID")],
        needs_notification: Annotated[bool, Field(description="通知が要るか")],
        location: Annotated[str | None, Field(description="場所。空にするときは null")],
        detail: Annotated[str | None, Field(description="詳細。空にするときは null")],
        site: SiteArg = None,
    ) -> dict[str, Any]:
        tool = "schedule_update_schedule"
        target = runner.start(tool, site, schedule_id=schedule_id, kind=kind, category_id=category_id)
        body = {
            "title": title,
            "location": location,
            "detail": detail,
            "kind": kind,
            "granularity": granularity,
            "start_date": start_date,
            "end_date": end_date,
            "start_time": start_time,
            "end_time": end_time,
            "category_id": category_id,
            "needs_notification": needs_notification,
        }
        return await runner.call(
            tool,
            target,
            FEATURE,
            "PATCH",
            f"/schedules/{schedule_id}",
            json=body,
            messages=ErrorMessages(not_found="予定・TODO またはカテゴリが見つかりません。ID を確かめてください。"),
        )

    @server.tool(
        name="schedule_set_todo_completion",
        description="TODO の実施済み／未実施を切り替えます。予定（kind=event）には使えません。",
        annotations=WRITE,
    )
    async def schedule_set_todo_completion(
        schedule_id: Annotated[int, id_field("対象の TODO の ID")],
        is_completed: Annotated[bool, Field(description="true で実施済み、false で未実施")],
        site: SiteArg = None,
    ) -> dict[str, Any]:
        tool = "schedule_set_todo_completion"
        target = runner.start(tool, site, schedule_id=schedule_id, is_completed=is_completed)
        return await runner.call(
            tool,
            target,
            FEATURE,
            "PATCH",
            f"/schedules/{schedule_id}/completion",
            json={"is_completed": is_completed},
            messages=ErrorMessages(conflict="予定（TODO でないもの）には実施状態を設定できません。"),
        )

    @server.tool(
        name="schedule_delete_schedule",
        description="予定または TODO を削除します。この操作は元に戻せません（MCP サーバからは復元できません）。",
        annotations=DELETE,
    )
    async def schedule_delete_schedule(
        schedule_id: Annotated[int, id_field("削除する予定・TODO の ID")],
        site: SiteArg = None,
    ) -> dict[str, Any]:
        tool = "schedule_delete_schedule"
        target = runner.start(tool, site, schedule_id=schedule_id)
        await runner.call(tool, target, FEATURE, "DELETE", f"/schedules/{schedule_id}")
        return ToolRunner.deleted(schedule_id)
