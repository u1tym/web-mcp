"""ROOM（自室の機器の状態と操作）のツール。

玄関ドアは、状態の参照（room_get_state）だけを提供する。施錠・開錠のツールは作らず、
room_set_device_state の device の選択肢にも含めない（requirements.md REQ-015）。
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from mcp.server.mcpserver import MCPServer
from pydantic import AfterValidator, Field

from app.tools import DELETE, READ, WRITE, SiteArg, ToolRunner, id_field
from app.webapp_client import ErrorMessages

FEATURE = "room"

# 時刻は HH:MM（00:00〜23:59）。Web アプリは秒つきや範囲外を受け付けない
ROOM_TIME_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"

# 玄関ドア（front_door）は含めない
ControlDevice = Annotated[
    Literal["ceiling_light", "indirect_light", "indoor_speaker", "bedside_speaker"],
    Field(
        description=(
            "操作する機器。ceiling_light（電灯。未実装）、indirect_light（間接照明）、"
            "indoor_speaker（屋内スピーカー）、bedside_speaker（枕元スピーカー）。玄関ドアは選べません"
        )
    ),
]
OnOff = Annotated[Literal["on", "off"], Field(description="目標の状態。on（ON）または off（OFF）")]
Scene = Annotated[
    Literal["indoor_speaker", "bedside_speaker", "ceiling_light", "indirect_light", "out"],
    Field(
        description=(
            "一括切替。indoor_speaker（屋内スピーカー選択）、bedside_speaker（枕元スピーカー選択）、"
            "ceiling_light（電灯選択）、indirect_light（間接照明選択）、out（お出かけ）"
        )
    ),
]
Condition = Annotated[
    Literal["daily", "weekdays", "holiday"],
    Field(description="実行条件。daily（毎日）、weekdays（曜日の指定）、holiday（祝日の指定）"),
]
RunTime = Annotated[
    str,
    Field(description="実行する時刻（HH:MM、24 時間、日本標準時）", pattern=ROOM_TIME_PATTERN),
]


def _unique(values: list[int]) -> list[int]:
    if len(set(values)) != len(values):
        raise ValueError("曜日が重複しています")
    return values


Weekdays = Annotated[
    list[Annotated[int, Field(ge=1, le=7)]],
    AfterValidator(_unique),
    Field(
        description=(
            "曜日（1〜7。1 = 月曜、…、7 = 日曜。重複なし）。condition が weekdays のとき必須。"
            "daily・holiday のときは省略または空"
        )
    ),
]

_TIMER_NOTE = "スケジュール機能の予定・TODO（schedule_*）とは別のものです。"
_TIMER_NOT_FOUND = "定期実行が見つかりません。ID を room_list_timers で確かめてください。"


def register(server: MCPServer, runner: ToolRunner) -> None:
    @server.tool(
        name="room_get_state",
        description=(
            "ROOM の 5 つの機器（電灯、間接照明、屋内スピーカー、枕元スピーカー、玄関ドア）の現在の状態と、"
            "状態を取得した日時を返します。機器の ON/OFF、玄関ドアの施錠中/開錠中と電池残量が分かります。"
            "実機に問い合わせるため、数秒かかることがあります。取得できなかった機器は status が error になり、"
            "他の機器の状態は返ります。電灯は未実装のため、常に OFF（implemented が false）です。"
            "機器を操作する前後の確認に使います。"
        ),
        annotations=READ,
    )
    async def room_get_state(site: SiteArg = None) -> dict[str, Any]:
        tool = "room_get_state"
        target = runner.start(tool, site)
        return await runner.call(tool, target, FEATURE, "GET", "/state")

    @server.tool(
        name="room_set_device_state",
        description=(
            "ROOM の機器を 1 つ、ON または OFF にします。実機が実際に動きます。"
            "対象は、電灯、間接照明、屋内スピーカー、枕元スピーカーです。玄関ドアは操作できません（状態の参照だけです）。"
            "現在の状態の反転ではなく、目標の状態（on か off）を指定してください。"
            "電灯は未実装のため、何も起きず、結果の applied が false になります。"
            "結果の result は、操作のあとに、その機器の状態を取得し直したものです"
            "（実機の反映が遅れて、目標と食い違うことがあります）。"
            "複数の機器を決まった組み合わせで切り替えるときは、room_run_scene を使います。"
        ),
        annotations=WRITE,
    )
    async def room_set_device_state(
        device: ControlDevice,
        state: OnOff,
        site: SiteArg = None,
    ) -> dict[str, Any]:
        tool = "room_set_device_state"
        target = runner.start(tool, site, device=device, state=state)
        return await runner.call(
            tool,
            target,
            FEATURE,
            "PUT",
            f"/devices/{device}/state",
            json={"state": state},
            messages=ErrorMessages(
                not_found=(
                    "機器が見つかりません。device は、電灯、間接照明、屋内スピーカー、枕元スピーカーの"
                    "いずれかを指定してください。"
                ),
                extra={
                    502: (
                        f"サイト {target.id} の ROOM が機器を操作できませんでした"
                        "（SwitchBot に接続できないか、機器がエラーを返しました）。"
                        "実際の状態を room_get_state で確かめてください。"
                    )
                },
            ),
        )

    @server.tool(
        name="room_run_scene",
        description=(
            "ROOM の一括切替を実行します。実機が実際に動きます。scene は次の 5 種です。"
            "いずれも、玄関ドアは変えません。電灯は未実装のため、電灯への指示は行われず、結果が skipped になります。"
            "indoor_speaker（屋内スピーカー選択）: 屋内スピーカーを ON、枕元スピーカーを OFF。"
            "bedside_speaker（枕元スピーカー選択）: 屋内スピーカーを OFF、枕元スピーカーを ON。"
            "ceiling_light（電灯選択）: 電灯を ON、間接照明を OFF（電灯は未実装のため、間接照明の OFF だけが行われます）。"
            "indirect_light（間接照明選択）: 電灯を OFF、間接照明を ON。"
            "out（お出かけ）: 電灯・間接照明・屋内スピーカー・枕元スピーカーをすべて OFF。"
            "一部の機器が失敗しても、エラーにはならず、機器ごとの結果（results）が返ります。"
            "成功した機器は元に戻りません。実行のあとの、全機器の状態（devices）も返ります。"
        ),
        annotations=WRITE,
    )
    async def room_run_scene(scene: Scene, site: SiteArg = None) -> dict[str, Any]:
        tool = "room_run_scene"
        target = runner.start(tool, site, scene=scene)
        return await runner.call(tool, target, FEATURE, "POST", f"/scenes/{scene}")

    @server.tool(
        name="room_list_timers",
        description=(
            "ROOM の定期実行（タイマー）の一覧を返します。定期実行は、指定した日（毎日、曜日、祝日）と時刻に、"
            "一括切替を自動で行う仕組みです。実行条件、曜日、時刻、実行する一括切替、有効／無効、"
            "最終実行の結果が分かります。" + _TIMER_NOTE + "更新・有効／無効の切り替え・削除で使う ID も、ここで確かめます。"
        ),
        annotations=READ,
    )
    async def room_list_timers(site: SiteArg = None) -> dict[str, Any]:
        tool = "room_list_timers"
        target = runner.start(tool, site)
        return await runner.call(tool, target, FEATURE, "GET", "/schedules")

    @server.tool(
        name="room_create_timer",
        description=(
            "ROOM の定期実行（タイマー）を 1 件登録します。実行条件、時刻、実行する一括切替を指定します。"
            "実行条件が weekdays（曜日の指定）のときは、曜日が必要です。"
            "実行する一括切替（scene）は room_run_scene と同じ 5 種で、玄関ドアを変えるものはありません。"
            "登録した定期実行は、既定で有効です。" + _TIMER_NOTE
        ),
        annotations=WRITE,
    )
    async def room_create_timer(
        condition: Condition,
        run_time: RunTime,
        scene: Scene,
        weekdays: Weekdays | None = None,
        is_enabled: Annotated[bool, Field(description="有効にするか。既定 true")] = True,
        site: SiteArg = None,
    ) -> dict[str, Any]:
        tool = "room_create_timer"
        target = runner.start(tool, site, condition=condition, scene=scene, is_enabled=is_enabled)
        body = {
            "condition": condition,
            "weekdays": weekdays or [],
            "run_time": run_time,
            "scene": scene,
            "is_enabled": is_enabled,
        }
        return await runner.call(tool, target, FEATURE, "POST", "/schedules", json=body)

    @server.tool(
        name="room_update_timer",
        description=(
            "登録済みの ROOM の定期実行（タイマー）を更新します。実行条件・曜日・時刻・一括切替を、すべて送る必要があります"
            "（送らなかった曜日は空になります）。先に room_list_timers で現在の値を確かめ、"
            "変えない項目も現在の値のまま渡してください。有効／無効は、省略すると現在の値のままです。"
            "最終実行の結果は変わりません。" + _TIMER_NOTE
        ),
        annotations=WRITE,
    )
    async def room_update_timer(
        schedule_id: Annotated[int, id_field("更新する定期実行の ID")],
        condition: Condition,
        run_time: RunTime,
        scene: Scene,
        weekdays: Weekdays | None = None,
        is_enabled: Annotated[bool | None, Field(description="有効／無効。省略すると現在の値のまま")] = None,
        site: SiteArg = None,
    ) -> dict[str, Any]:
        tool = "room_update_timer"
        target = runner.start(tool, site, schedule_id=schedule_id, condition=condition, scene=scene)
        body: dict[str, Any] = {
            "condition": condition,
            "weekdays": weekdays or [],
            "run_time": run_time,
            "scene": scene,
        }
        if is_enabled is not None:
            body["is_enabled"] = is_enabled
        return await runner.call(
            tool,
            target,
            FEATURE,
            "PUT",
            f"/schedules/{schedule_id}",
            json=body,
            messages=ErrorMessages(not_found=_TIMER_NOT_FOUND),
        )

    @server.tool(
        name="room_set_timer_enabled",
        description=(
            "ROOM の定期実行（タイマー）の有効／無効だけを切り替えます。無効にした定期実行は、自動で実行されません。"
            "他の項目と、最終実行の結果は変わりません。" + _TIMER_NOTE
        ),
        annotations=WRITE,
    )
    async def room_set_timer_enabled(
        schedule_id: Annotated[int, id_field("対象の定期実行の ID")],
        is_enabled: Annotated[bool, Field(description="true で有効、false で無効")],
        site: SiteArg = None,
    ) -> dict[str, Any]:
        tool = "room_set_timer_enabled"
        target = runner.start(tool, site, schedule_id=schedule_id, is_enabled=is_enabled)
        return await runner.call(
            tool,
            target,
            FEATURE,
            "PUT",
            f"/schedules/{schedule_id}/enabled",
            json={"is_enabled": is_enabled},
            messages=ErrorMessages(not_found=_TIMER_NOT_FOUND),
        )

    @server.tool(
        name="room_delete_timer",
        description=(
            "ROOM の定期実行（タイマー）を削除します。この操作は元に戻せません（MCP サーバからは復元できません）。"
            "一時的に止めたいだけのときは、room_set_timer_enabled で無効にしてください。" + _TIMER_NOTE
        ),
        annotations=DELETE,
    )
    async def room_delete_timer(
        schedule_id: Annotated[int, id_field("削除する定期実行の ID")],
        site: SiteArg = None,
    ) -> dict[str, Any]:
        tool = "room_delete_timer"
        target = runner.start(tool, site, schedule_id=schedule_id)
        await runner.call(
            tool,
            target,
            FEATURE,
            "DELETE",
            f"/schedules/{schedule_id}",
            messages=ErrorMessages(not_found=_TIMER_NOT_FOUND),
        )
        return runner.deleted(schedule_id)
