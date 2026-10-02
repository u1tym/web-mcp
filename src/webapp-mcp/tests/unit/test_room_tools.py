"""ROOM のツールの単体テスト（T-015）。

Web アプリの API は respx でモックする。実機の SwitchBot も、ROOM のバックエンドも動かさない。
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from mcp import Client
from mcp.server.mcpserver import MCPServer

from app.config import Config
from app.main import WebappMcp, build
from app.sites import SiteRegistry
from conftest import TEST_API_KEY, log_text

R = "http://webapp.test/room"

ROOM_TOOLS = {
    "room_get_state": "R",
    "room_set_device_state": "W",
    "room_run_scene": "W",
    "room_list_timers": "R",
    "room_create_timer": "W",
    "room_update_timer": "W",
    "room_set_timer_enabled": "W",
    "room_delete_timer": "D",
}
HINTS = {"R": (True, False, True), "W": (False, False, False), "D": (False, True, True)}

ROUTER = respx.MockRouter(assert_all_called=False)


@pytest.fixture()
def built(cfg: Config, registry: SiteRegistry) -> Iterator[WebappMcp]:
    app = build(cfg, registry)
    yield app
    app.store.close()


@pytest.fixture()
def mcp(built: WebappMcp) -> Iterator[MCPServer]:
    with ROUTER:
        yield built.server
    ROUTER.clear()


async def list_tools(mcp: MCPServer) -> dict[str, Any]:
    async with Client(mcp) as client:
        return {tool.name: tool for tool in (await client.list_tools()).tools}


async def call(mcp: MCPServer, name: str, args: dict[str, Any] | None = None) -> tuple[bool, Any]:
    async with Client(mcp) as client:
        result = await client.call_tool(name, args or {})
    if result.is_error:
        return True, result.content[0].text  # type: ignore[union-attr]
    return False, result.structured_content


def body_of(route: respx.Route) -> Any:
    return json.loads(route.calls.last.request.content)


STATE = {
    "fetched_at": "2026-10-01T10:15:30+09:00",
    "devices": {
        "ceiling_light": {"status": "ok", "state": "off", "implemented": False},
        "indirect_light": {"status": "ok", "state": "on"},
        "indoor_speaker": {"status": "error", "state": None},
        "bedside_speaker": {"status": "ok", "state": "off"},
        "front_door": {"status": "ok", "state": "locked", "battery": 35},
    },
}
TIMER = {
    "id": 3,
    "condition": "weekdays",
    "weekdays": [1, 3, 5],
    "holiday_mode": "none",
    "day_shift": "same",
    "run_time": "07:00",
    "scene": "indoor_speaker",
    "device": None,
    "state": None,
    "is_enabled": True,
    "last_run": None,
}
# 機器の個別切替の定期実行（scene は null）
DEVICE_TIMER = {
    "id": 4,
    "condition": "weekdays",
    "weekdays": [1, 2, 3, 4, 5],
    "holiday_mode": "exclude",
    "day_shift": "before",
    "run_time": "22:30",
    "scene": None,
    "device": "indirect_light",
    "state": "off",
    "is_enabled": True,
    "last_run": {"at": "2026-10-01T22:30:02+09:00", "result": "failure", "failed_devices": ["indirect_light"]},
}


def enum_of(prop: dict[str, Any]) -> list[str]:
    """入力スキーマの列挙。省略できる引数は anyOf（列挙と null）になる。"""
    if "enum" in prop:
        return list(prop["enum"])
    for option in prop.get("anyOf", []):
        if "enum" in option:
            return list(option["enum"])
    raise AssertionError(f"列挙が無い: {prop}")


# ---- ツール一覧・注釈・入力スキーマ ----


async def test_room_tools_exist_with_annotations(mcp: MCPServer) -> None:
    tools = await list_tools(mcp)
    assert set(ROOM_TOOLS) <= set(tools)
    for name, kind in ROOM_TOOLS.items():
        a = tools[name].annotations
        assert (a.read_only_hint, a.destructive_hint, a.idempotent_hint) == HINTS[kind], name
        assert "site" in tools[name].input_schema.get("properties", {}), name
    # 元に戻せない操作は、削除だけ
    destructive = {n for n in ROOM_TOOLS if tools[n].annotations.destructive_hint}
    assert destructive == {"room_delete_timer"}
    assert "元に戻せません" in (tools["room_delete_timer"].description or "")


async def test_total_tool_count_is_39(mcp: MCPServer) -> None:
    assert len(await list_tools(mcp)) == 39


async def test_no_tool_can_operate_the_front_door(mcp: MCPServer) -> None:
    """玄関ドアの施錠・開錠を求める手段は、どこにも無い（REQ-015）。"""
    tools = await list_tools(mcp)
    names = " ".join(tools)
    assert "door" not in names and "lock" not in names
    schema = tools["room_set_device_state"].input_schema
    devices = schema["properties"]["device"]["enum"]
    assert set(devices) == {"ceiling_light", "indirect_light", "indoor_speaker", "bedside_speaker"}
    assert "front_door" not in devices
    assert schema["properties"]["state"]["enum"] == ["on", "off"]  # locked / unlocked は無い
    # 一括切替・定期実行の選択肢にも、玄関ドアは無い
    for tool, prop in (("room_run_scene", "scene"), ("room_create_timer", "scene"), ("room_update_timer", "scene")):
        assert set(enum_of(tools[tool].input_schema["properties"][prop])) == {
            "indoor_speaker",
            "bedside_speaker",
            "ceiling_light",
            "indirect_light",
            "out",
        }


async def test_input_schemas(mcp: MCPServer) -> None:
    tools = await list_tools(mcp)
    create = tools["room_create_timer"].input_schema
    assert set(create["required"]) == {"condition", "run_time"}  # 実行内容は、どちらか一方（scene、または device + state）
    assert create["properties"]["condition"]["enum"] == ["daily", "weekdays"]  # 祝日だけの条件は無い
    update = tools["room_update_timer"].input_schema
    assert set(update["required"]) == {"schedule_id", "condition", "run_time"}
    for schema in (create, update):
        assert enum_of(schema["properties"]["holiday_mode"]) == ["none", "include", "exclude"]
        assert enum_of(schema["properties"]["day_shift"]) == ["same", "before", "after"]
        assert enum_of(schema["properties"]["state"]) == ["on", "off"]
        devices = enum_of(schema["properties"]["device"])
        assert set(devices) == {"ceiling_light", "indirect_light", "indoor_speaker", "bedside_speaker"}
        assert "front_door" not in devices  # 玄関ドアは、実行内容に指定できない
        for name in ("holiday_mode", "day_shift", "scene", "device", "state"):
            assert name not in schema["required"], name
    assert "is_enabled" not in update["required"]  # 省略すると現在の値のまま
    assert set(tools["room_set_timer_enabled"].input_schema["required"]) == {"schedule_id", "is_enabled"}
    assert tools["room_delete_timer"].input_schema["required"] == ["schedule_id"]
    assert tools["room_set_device_state"].input_schema["required"] == ["device", "state"]
    assert tools["room_run_scene"].input_schema["required"] == ["scene"]
    assert not tools["room_get_state"].input_schema.get("required")
    assert not tools["room_list_timers"].input_schema.get("required")


async def test_descriptions_warn_about_real_devices_and_distinguish_timers(mcp: MCPServer) -> None:
    tools = await list_tools(mcp)
    for name in ("room_set_device_state", "room_run_scene"):
        assert "実機が実際に動きます" in (tools[name].description or ""), name
        assert "電灯は未実装" in (tools[name].description or ""), name
    assert "玄関ドアは操作できません" in (tools["room_set_device_state"].description or "")
    assert "玄関ドアは変えません" in (tools["room_run_scene"].description or "")
    for name in ("room_list_timers", "room_create_timer", "room_update_timer", "room_set_timer_enabled", "room_delete_timer"):
        assert "schedule_*" in (tools[name].description or ""), name


async def test_timer_descriptions_explain_modes_and_defaults(mcp: MCPServer) -> None:
    tools = await list_tools(mcp)
    for name in ("room_create_timer", "room_update_timer"):
        text = tools[name].description or ""
        assert "基準日" in text and "の前の日" in text and "の次の日" in text, name
        assert "どちらか一方" in text and "玄関ドアは、どちらにも指定できません" in text, name
    # 更新で省略すると、現在の値のままではなく既定に戻る（誤解しやすいので、説明に明記する）
    update = tools["room_update_timer"].description or ""
    assert "現在の値のままではなく、既定" in update
    assert "holiday" not in tools["room_create_timer"].input_schema["properties"]["condition"]["enum"]


# ---- 参照 ----


async def test_get_state(mcp: MCPServer) -> None:
    route = ROUTER.get(f"{R}/state").mock(return_value=httpx.Response(200, json=STATE))
    error, out = await call(mcp, "room_get_state")
    assert not error, out
    assert out == STATE  # 項目名・値を変えない（取得できなかった機器は error のまま）
    assert route.calls.last.request.headers["authorization"] == f"Bearer {TEST_API_KEY}"
    assert not route.calls.last.request.content


async def test_list_timers(mcp: MCPServer) -> None:
    payload = {"schedules": [TIMER]}
    ROUTER.get(f"{R}/schedules").mock(return_value=httpx.Response(200, json=payload))
    error, out = await call(mcp, "room_list_timers")
    assert not error, out
    assert out == payload


# ---- 機器の操作 ----


@pytest.mark.parametrize(
    ("device", "state"),
    [
        ("indirect_light", "off"),
        ("indirect_light", "on"),
        ("indoor_speaker", "on"),
        ("bedside_speaker", "off"),
        ("ceiling_light", "on"),
    ],
)
async def test_set_device_state(mcp: MCPServer, device: str, state: str) -> None:
    payload = {"device": device, "applied": True, "fetched_at": "2026-10-01T10:15:33+09:00", "result": {"status": "ok", "state": state}}
    route = ROUTER.put(f"{R}/devices/{device}/state").mock(return_value=httpx.Response(200, json=payload))
    error, out = await call(mcp, "room_set_device_state", {"device": device, "state": state})
    assert not error, out
    assert out == payload
    assert body_of(route) == {"state": state}  # 目標の状態を明示する（「反転」は送らない）


async def test_set_device_state_ceiling_light_is_not_applied(mcp: MCPServer) -> None:
    payload = {"device": "ceiling_light", "applied": False, "fetched_at": "x", "result": {"status": "ok", "state": "off", "implemented": False}}
    ROUTER.put(f"{R}/devices/ceiling_light/state").mock(return_value=httpx.Response(200, json=payload))
    error, out = await call(mcp, "room_set_device_state", {"device": "ceiling_light", "state": "on"})
    assert not error
    assert out["applied"] is False


@pytest.mark.parametrize(
    "args",
    [
        {"device": "front_door", "state": "unlocked"},
        {"device": "front_door", "state": "locked"},
        {"device": "front_door", "state": "off"},
        {"device": "indirect_light", "state": "locked"},
        {"device": "indirect_light", "state": "toggle"},
        {"device": "indirect_light"},
        {"state": "on"},
        {"device": "kitchen", "state": "on"},
    ],
)
async def test_set_device_state_invalid_arguments_do_not_call_webapp(mcp: MCPServer, args: dict[str, Any]) -> None:
    route = ROUTER.route(url__regex=rf"{R}/.*").mock(return_value=httpx.Response(200, json={}))
    error, _ = await call(mcp, "room_set_device_state", args)
    assert error
    assert route.call_count == 0


async def test_set_device_state_502_has_a_specific_message(mcp: MCPServer) -> None:
    ROUTER.put(f"{R}/devices/indirect_light/state").mock(return_value=httpx.Response(502, json={"detail": "機器を操作できませんでした"}))
    error, text = await call(mcp, "room_set_device_state", {"device": "indirect_light", "state": "on"})
    assert error
    assert "サイト home の ROOM が機器を操作できませんでした" in text
    assert "room_get_state" in text
    assert TEST_API_KEY not in text and "webapp.test" not in text


async def test_set_device_state_is_not_retried(mcp: MCPServer) -> None:
    route = ROUTER.put(f"{R}/devices/indirect_light/state").mock(return_value=httpx.Response(502, json={"detail": "x"}))
    await call(mcp, "room_set_device_state", {"device": "indirect_light", "state": "on"})
    assert route.call_count == 1  # 失敗した操作を自動で再実行しない


async def test_set_device_state_404(mcp: MCPServer) -> None:
    ROUTER.put(f"{R}/devices/indirect_light/state").mock(return_value=httpx.Response(404, json={"detail": "対象がありません"}))
    error, text = await call(mcp, "room_set_device_state", {"device": "indirect_light", "state": "on"})
    assert error and "機器が見つかりません" in text


# ---- 一括切替 ----


@pytest.mark.parametrize("scene", ["indoor_speaker", "bedside_speaker", "ceiling_light", "indirect_light", "out"])
async def test_run_scene(mcp: MCPServer, scene: str) -> None:
    payload = {"scene": scene, "outcome": "success", "results": [], "fetched_at": "x", "devices": STATE["devices"]}
    route = ROUTER.post(f"{R}/scenes/{scene}").mock(return_value=httpx.Response(200, json=payload))
    error, out = await call(mcp, "room_run_scene", {"scene": scene})
    assert not error, out
    assert out == payload
    assert not route.calls.last.request.content  # 本文なし


async def test_run_scene_partial_failure_is_returned_as_is(mcp: MCPServer) -> None:
    payload = {
        "scene": "indoor_speaker",
        "outcome": "partial",
        "results": [
            {"device": "indoor_speaker", "target": "on", "outcome": "success"},
            {"device": "bedside_speaker", "target": "off", "outcome": "failure"},
        ],
        "fetched_at": "x",
        "devices": STATE["devices"],
    }
    ROUTER.post(f"{R}/scenes/indoor_speaker").mock(return_value=httpx.Response(200, json=payload))
    error, out = await call(mcp, "room_run_scene", {"scene": "indoor_speaker"})
    assert not error  # 一部失敗は、エラーにしない
    assert out["outcome"] == "partial"
    assert [r["outcome"] for r in out["results"]] == ["success", "failure"]


@pytest.mark.parametrize("scene", ["front_door", "lock", "unlock", "door", "", "all"])
async def test_run_scene_invalid_scene_does_not_call_webapp(mcp: MCPServer, scene: str) -> None:
    route = ROUTER.route(url__regex=rf"{R}/.*").mock(return_value=httpx.Response(200, json={}))
    error, _ = await call(mcp, "room_run_scene", {"scene": scene})
    assert error
    assert route.call_count == 0


# ---- 定期実行 ----


async def test_create_timer_weekdays(mcp: MCPServer) -> None:
    route = ROUTER.post(f"{R}/schedules").mock(return_value=httpx.Response(201, json=TIMER))
    error, out = await call(
        mcp,
        "room_create_timer",
        {"condition": "weekdays", "weekdays": [1, 3, 5], "run_time": "07:00", "scene": "indoor_speaker"},
    )
    assert not error, out
    assert out == TIMER
    assert body_of(route) == {
        "condition": "weekdays",
        "weekdays": [1, 3, 5],
        "run_time": "07:00",
        "scene": "indoor_speaker",
        "is_enabled": True,  # 既定は有効
    }


async def test_create_timer_daily_sends_empty_weekdays(mcp: MCPServer) -> None:
    route = ROUTER.post(f"{R}/schedules").mock(return_value=httpx.Response(201, json=TIMER))
    error, _ = await call(
        mcp, "room_create_timer", {"condition": "daily", "run_time": "22:30", "scene": "out", "is_enabled": False}
    )
    assert not error
    assert body_of(route) == {
        "condition": "daily",
        "weekdays": [],
        "run_time": "22:30",
        "scene": "out",
        "is_enabled": False,
    }


@pytest.mark.parametrize(
    "override",
    [
        {"weekdays": [0]},
        {"weekdays": [8]},
        {"weekdays": [1, 1]},
        {"weekdays": ["mon"]},
        {"run_time": "7:00"},
        {"run_time": "24:00"},
        {"run_time": "12:60"},
        {"run_time": "07:00:30"},
        {"run_time": "abc"},
        {"scene": "front_door"},
        {"scene": "unlock"},
        {"condition": "monthly"},
        {"condition": "holiday"},  # 祝日だけの条件は無い
        {"holiday_mode": "all"},
        {"day_shift": "tomorrow"},
        {"scene": None, "device": "front_door", "state": "on"},  # 玄関ドアは対象外
        {"scene": None, "device": "indirect_light", "state": "toggle"},
        {"scene": None, "device": "locked", "state": "on"},
    ],
)
async def test_create_timer_invalid_arguments_do_not_call_webapp(mcp: MCPServer, override: dict[str, Any]) -> None:
    route = ROUTER.route(url__regex=rf"{R}/.*").mock(return_value=httpx.Response(200, json={}))
    args = {"condition": "weekdays", "weekdays": [1], "run_time": "07:00", "scene": "out", **override}
    error, _ = await call(mcp, "room_create_timer", args)
    assert error
    assert route.call_count == 0


async def test_create_timer_missing_weekdays_is_decided_by_webapp(mcp: MCPServer) -> None:
    """曜日の指定なのに曜日が無い、などの組み合わせの検査は Web アプリが行い、400 の共通エラー文で返る。"""
    ROUTER.post(f"{R}/schedules").mock(return_value=httpx.Response(400, json={"detail": "入力が不正です"}))
    error, text = await call(mcp, "room_create_timer", {"condition": "weekdays", "run_time": "07:00", "scene": "out"})
    assert error
    assert "入力が不正です" in text


async def test_update_timer_sends_all_fields(mcp: MCPServer) -> None:
    route = ROUTER.put(f"{R}/schedules/3").mock(return_value=httpx.Response(200, json=TIMER))
    error, out = await call(
        mcp,
        "room_update_timer",
        {
            "schedule_id": 3,
            "condition": "weekdays",
            "weekdays": [2, 4],
            "run_time": "08:15",
            "scene": "out",
            "is_enabled": False,
        },
    )
    assert not error, out
    assert out == TIMER
    assert body_of(route) == {
        "condition": "weekdays",
        "weekdays": [2, 4],
        "run_time": "08:15",
        "scene": "out",
        "is_enabled": False,
    }


async def test_update_timer_omitting_is_enabled_keeps_it(mcp: MCPServer) -> None:
    route = ROUTER.put(f"{R}/schedules/3").mock(return_value=httpx.Response(200, json=TIMER))
    error, _ = await call(
        mcp, "room_update_timer", {"schedule_id": 3, "condition": "daily", "run_time": "08:15", "scene": "out"}
    )
    assert not error
    body = body_of(route)
    assert "is_enabled" not in body  # 送らない（Web アプリが現在の値を保つ）
    assert body["weekdays"] == []


async def test_set_timer_enabled(mcp: MCPServer) -> None:
    route = ROUTER.put(f"{R}/schedules/3/enabled").mock(return_value=httpx.Response(200, json={**TIMER, "is_enabled": False}))
    error, out = await call(mcp, "room_set_timer_enabled", {"schedule_id": 3, "is_enabled": False})
    assert not error, out
    assert out["is_enabled"] is False
    assert body_of(route) == {"is_enabled": False}


async def test_delete_timer(mcp: MCPServer) -> None:
    route = ROUTER.delete(f"{R}/schedules/3").mock(return_value=httpx.Response(204))
    error, out = await call(mcp, "room_delete_timer", {"schedule_id": 3})
    assert not error, out
    assert out == {"deleted": True, "id": 3}
    assert route.call_count == 1


@pytest.mark.parametrize(
    ("tool", "args", "method"),
    [
        ("room_update_timer", {"schedule_id": 99, "condition": "daily", "run_time": "07:00", "scene": "out"}, "PUT"),
        ("room_set_timer_enabled", {"schedule_id": 99, "is_enabled": True}, "PUT"),
        ("room_delete_timer", {"schedule_id": 99}, "DELETE"),
    ],
)
async def test_timer_404_message(mcp: MCPServer, tool: str, args: dict[str, Any], method: str) -> None:
    ROUTER.route(method=method, url__regex=rf"{R}/schedules/99.*").mock(
        return_value=httpx.Response(404, json={"detail": "対象がありません"})
    )
    error, text = await call(mcp, tool, args)
    assert error
    assert "定期実行が見つかりません。ID を room_list_timers で確かめてください。" in text


@pytest.mark.parametrize(
    ("tool", "args"),
    [
        ("room_update_timer", {"schedule_id": 0, "condition": "daily", "run_time": "07:00", "scene": "out"}),
        ("room_set_timer_enabled", {"schedule_id": 0, "is_enabled": True}),
        ("room_delete_timer", {"schedule_id": -1}),
        ("room_set_timer_enabled", {"schedule_id": 3, "is_enabled": "maybe"}),
    ],
)
async def test_timer_invalid_ids_do_not_call_webapp(mcp: MCPServer, tool: str, args: dict[str, Any]) -> None:
    route = ROUTER.route(url__regex=rf"{R}/.*").mock(return_value=httpx.Response(200, json={}))
    error, _ = await call(mcp, tool, args)
    assert error
    assert route.call_count == 0


# ---- 共通エラー・サイト ----


@pytest.mark.parametrize(
    ("status", "fragment"),
    [
        (401, "API キーが無効です"),
        (403, "この機能を利用する権限がありません"),
        (500, "接続できないか、処理に失敗しました"),
    ],
)
async def test_common_errors(mcp: MCPServer, status: int, fragment: str) -> None:
    ROUTER.get(f"{R}/state").mock(return_value=httpx.Response(status, json={"detail": "x"}))
    error, text = await call(mcp, "room_get_state")
    assert error
    assert fragment in text
    assert TEST_API_KEY not in text and "webapp.test" not in text


async def test_site_without_room_cannot_use_room_tools(mcp: MCPServer) -> None:
    """サイト office には room の接続先が無い。ROOM のツールだけが使えない。"""
    error, text = await call(mcp, "room_get_state", {"site": "office"})
    assert error and "サイト office では、この機能を利用できません" in text
    error, text = await call(mcp, "room_run_scene", {"scene": "out", "site": "office"})
    assert error and "サイト office では、この機能を利用できません" in text


async def test_unknown_site(mcp: MCPServer) -> None:
    error, text = await call(mcp, "room_get_state", {"site": "nowhere"})
    assert error and "サイト nowhere は登録されていません" in text


@pytest.mark.parametrize("mode", ["none", "include", "exclude"])
@pytest.mark.parametrize("shift", ["same", "before", "after"])
async def test_create_timer_sends_holiday_mode_and_day_shift_as_given(mcp: MCPServer, mode: str, shift: str) -> None:
    route = ROUTER.post(f"{R}/schedules").mock(return_value=httpx.Response(201, json=TIMER))
    error, _ = await call(
        mcp,
        "room_create_timer",
        {"condition": "weekdays", "weekdays": [1], "run_time": "07:00", "scene": "out", "holiday_mode": mode, "day_shift": shift},
    )
    assert not error
    body = body_of(route)
    assert body["holiday_mode"] == mode and body["day_shift"] == shift


async def test_create_timer_omits_holiday_mode_and_day_shift_when_not_given(mcp: MCPServer) -> None:
    route = ROUTER.post(f"{R}/schedules").mock(return_value=httpx.Response(201, json=TIMER))
    await call(mcp, "room_create_timer", {"condition": "daily", "run_time": "07:00", "scene": "out"})
    body = body_of(route)
    assert "holiday_mode" not in body and "day_shift" not in body  # 省略時の既定は Web アプリが決める


@pytest.mark.parametrize(("device", "state"), [("ceiling_light", "on"), ("indirect_light", "off"), ("indoor_speaker", "on"), ("bedside_speaker", "off")])
async def test_create_timer_device_action_sends_device_and_state_without_scene(mcp: MCPServer, device: str, state: str) -> None:
    route = ROUTER.post(f"{R}/schedules").mock(return_value=httpx.Response(201, json=DEVICE_TIMER))
    error, out = await call(
        mcp, "room_create_timer", {"condition": "daily", "run_time": "06:30", "device": device, "state": state}
    )
    assert not error, out
    assert out == DEVICE_TIMER
    assert body_of(route) == {
        "condition": "daily",
        "weekdays": [],
        "run_time": "06:30",
        "device": device,
        "state": state,
        "is_enabled": True,
    }  # scene は送らない


async def test_scene_timer_does_not_send_device_or_state(mcp: MCPServer) -> None:
    route = ROUTER.post(f"{R}/schedules").mock(return_value=httpx.Response(201, json=TIMER))
    await call(mcp, "room_create_timer", {"condition": "daily", "run_time": "06:30", "scene": "out"})
    body = body_of(route)
    assert "device" not in body and "state" not in body


@pytest.mark.parametrize(
    "extra",
    [
        {"scene": "out", "device": "indirect_light", "state": "on"},  # 両方
        {"device": "indirect_light"},  # 状態が無い
        {"state": "on"},  # 機器が無い
        {},  # どちらも無い
        {"condition": "daily", "scene": "out", "holiday_mode": "exclude"},  # 毎日なのに祝日の扱い
    ],
)
async def test_create_timer_inconsistent_combinations_are_decided_by_webapp(mcp: MCPServer, extra: dict[str, Any]) -> None:
    """scene と device + state の整合などは、MCP は検査せず、Web アプリを呼び、その 400 を共通エラー文で返す。"""
    route = ROUTER.post(f"{R}/schedules").mock(return_value=httpx.Response(400, json={"detail": "入力が不正です"}))
    args = {"condition": "weekdays", "weekdays": [1], "run_time": "07:00", **extra}
    error, text = await call(mcp, "room_create_timer", args)
    assert error
    assert "入力が不正です" in text
    assert route.call_count == 1  # Web アプリを呼んだ（MCP は拒否していない）


async def test_update_timer_sends_new_fields_and_switches_to_device(mcp: MCPServer) -> None:
    route = ROUTER.put(f"{R}/schedules/4").mock(return_value=httpx.Response(200, json=DEVICE_TIMER))
    error, out = await call(
        mcp,
        "room_update_timer",
        {
            "schedule_id": 4,
            "condition": "weekdays",
            "weekdays": [1, 2, 3, 4, 5],
            "holiday_mode": "exclude",
            "day_shift": "before",
            "run_time": "22:30",
            "device": "indirect_light",
            "state": "off",
        },
    )
    assert not error, out
    assert out == DEVICE_TIMER
    assert body_of(route) == {
        "condition": "weekdays",
        "weekdays": [1, 2, 3, 4, 5],
        "holiday_mode": "exclude",
        "day_shift": "before",
        "run_time": "22:30",
        "device": "indirect_light",
        "state": "off",
    }


async def test_update_timer_omitting_modes_sends_nothing_so_webapp_resets_defaults(mcp: MCPServer) -> None:
    route = ROUTER.put(f"{R}/schedules/3").mock(return_value=httpx.Response(200, json=TIMER))
    await call(mcp, "room_update_timer", {"schedule_id": 3, "condition": "weekdays", "weekdays": [1], "run_time": "08:15", "scene": "out"})
    body = body_of(route)
    assert "holiday_mode" not in body and "day_shift" not in body  # 現在の値は送らない。Web アプリが既定に戻す


async def test_list_timers_returns_device_timers_as_is(mcp: MCPServer) -> None:
    payload = {"schedules": [TIMER, DEVICE_TIMER]}
    ROUTER.get(f"{R}/schedules").mock(return_value=httpx.Response(200, json=payload))
    error, out = await call(mcp, "room_list_timers")
    assert not error, out
    assert out == payload
    assert out["schedules"][1]["scene"] is None and out["schedules"][1]["device"] == "indirect_light"
    assert out["schedules"][1]["last_run"]["failed_devices"] == ["indirect_light"]


# ---- ログ ----


async def test_logs_do_not_contain_secrets_or_timer_bodies(mcp: MCPServer, log_dir: Path) -> None:
    ROUTER.put(f"{R}/devices/indirect_light/state").mock(return_value=httpx.Response(200, json={"device": "indirect_light", "applied": True, "fetched_at": "x", "result": {"status": "ok", "state": "on"}}))
    ROUTER.post(f"{R}/scenes/out").mock(return_value=httpx.Response(200, json={"scene": "out", "outcome": "success", "results": [], "fetched_at": "x", "devices": {}}))
    ROUTER.post(f"{R}/schedules").mock(return_value=httpx.Response(201, json=TIMER))
    await call(mcp, "room_set_device_state", {"device": "indirect_light", "state": "on"})
    await call(mcp, "room_run_scene", {"scene": "out"})
    await call(
        mcp,
        "room_create_timer",
        {
            "condition": "weekdays",
            "weekdays": [1, 3],
            "run_time": "06:45",
            "holiday_mode": "exclude",
            "day_shift": "before",
            "device": "indirect_light",
            "state": "off",
        },
    )

    log = log_text(log_dir)
    assert "tool=room_set_device_state" in log and "device=indirect_light" in log and "state=on" in log
    assert "tool=room_run_scene" in log and "scene=out" in log
    assert "tool=room_create_timer" in log and "condition=weekdays" in log
    assert "holiday_mode=exclude" in log and "day_shift=before" in log
    assert "device=indirect_light" in log and "state=off" in log
    assert TEST_API_KEY not in log
    assert "06:45" not in log  # 定期実行の本文（時刻・曜日）は出さない
