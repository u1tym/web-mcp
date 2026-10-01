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

S = "http://webapp.test/schedule"
G = "http://webapp.test/goods"
K = "http://webapp.test/knowhow"
E = "http://webapp.test/expense"


@pytest.fixture()
def built(cfg: Config, registry: SiteRegistry) -> Iterator[WebappMcp]:
    app = build(cfg, registry)
    yield app
    app.store.close()


# Web アプリの API のモック（呼ばれないことを確かめるルートもあるので assert_all_called=False）
ROUTER = respx.MockRouter(assert_all_called=False)


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


# ---- ツール一覧・注釈 ----

EXPECTED = {
    "list_sites": "R",
    "schedule_list_schedules": "R", "schedule_list_categories": "R", "schedule_create_schedule": "W",
    "schedule_update_schedule": "W", "schedule_set_todo_completion": "W", "schedule_delete_schedule": "D",
    "goods_list_persons": "R", "goods_list_artists": "R", "goods_list_media": "R", "goods_list_goods": "R",
    "goods_get_goods": "R", "goods_create_goods": "W", "goods_update_goods": "W", "goods_delete_goods": "D",
    "knowhow_list_major_categories": "R", "knowhow_list_middle_categories": "R", "knowhow_search_knowhows": "R",
    "knowhow_get_knowhow": "R", "knowhow_create_knowhow": "W", "knowhow_update_knowhow": "W", "knowhow_delete_knowhow": "D",
    "expense_list_budget_periods": "R", "expense_list_budget_items": "R", "expense_list_payment_methods": "R",
    "expense_list_expenses": "R", "expense_get_usage_date_report": "R", "expense_get_payment_date_report": "R",
    "expense_create_expense": "W", "expense_update_expense": "W", "expense_delete_expense": "D",
    "room_get_state": "R", "room_set_device_state": "W", "room_run_scene": "W", "room_list_timers": "R",
    "room_create_timer": "W", "room_update_timer": "W", "room_set_timer_enabled": "W", "room_delete_timer": "D",
}
HINTS = {"R": (True, False, True), "W": (False, False, False), "D": (False, True, True)}


async def test_tool_list_and_annotations(mcp: MCPServer) -> None:
    tools = await list_tools(mcp)
    assert set(tools) == set(EXPECTED)
    for name, kind in EXPECTED.items():
        a = tools[name].annotations
        assert (a.read_only_hint, a.destructive_hint, a.idempotent_hint) == HINTS[kind], name
        props = tools[name].input_schema.get("properties", {})
        assert ("site" in props) == (name != "list_sites"), name
        if kind == "D":
            assert "元に戻せません" in (tools[name].description or "")


async def test_update_tools_require_all_fields(mcp: MCPServer) -> None:
    tools = await list_tools(mcp)
    required = {
        "schedule_update_schedule": {"location", "detail", "start_time", "end_time", "needs_notification"},
        "goods_update_goods": {"release_date", "memo", "code_number", "is_owned"},
        "knowhow_update_knowhow": {"keywords", "middle_category_id"},
        "expense_update_expense": {"budget_period_id", "budget_item_id", "memo"},
    }
    for name, fields in required.items():
        assert fields <= set(tools[name].input_schema["required"]), name
    assert "payment_date" not in tools["expense_update_expense"].input_schema["required"]


# ---- 共通 ----


async def test_list_sites(mcp: MCPServer) -> None:
    error, out = await call(mcp, "list_sites")
    assert not error
    assert out == {
        "default_site": "home",
        "sites": [
            {"id": "home", "title": "自宅", "is_default": True},
            {"id": "office", "title": "事務所", "is_default": False},
        ],
    }
    assert TEST_API_KEY not in json.dumps(out) and "webapp.test" not in json.dumps(out)


async def test_unknown_site_and_missing_feature(mcp: MCPServer) -> None:
    error, text = await call(mcp, "goods_list_persons", {"site": "nowhere"})
    assert error and "サイト nowhere は登録されていません" in text
    error, text = await call(mcp, "goods_list_persons", {"site": "office"})
    assert error and "サイト office では、この機能を利用できません" in text


# ---- 参照系（呼ぶ API と出力） ----

READ_CASES = [
    ("schedule_list_schedules", {"start_date": "2026-09-01", "end_date": "2026-09-30"}, f"{S}/schedules", {"start_date": "2026-09-01", "end_date": "2026-09-30"}),
    ("schedule_list_categories", {}, f"{S}/categories", {"include_deleted": "false"}),
    ("goods_list_persons", {}, f"{G}/persons", {}),
    ("goods_list_artists", {}, f"{G}/artists", {}),
    ("goods_list_media", {}, f"{G}/media", {}),
    ("goods_list_goods", {"person_id": 1, "media_id": 3}, f"{G}/goods", {"person_id": "1", "media_id": "3"}),
    ("knowhow_list_major_categories", {}, f"{K}/major-categories", {}),
    ("knowhow_list_middle_categories", {"major_category_id": 2}, f"{K}/major-categories/2/middle-categories", {}),
    ("knowhow_get_knowhow", {"knowhow_id": 5}, f"{K}/knowhows/5", {}),
    ("expense_list_budget_periods", {}, f"{E}/budget-periods", {}),
    ("expense_list_budget_items", {"budget_period_id": 4}, f"{E}/budget-items", {"budget_period_id": "4"}),
    ("expense_list_payment_methods", {}, f"{E}/payment-methods", {}),
    ("expense_list_expenses", {"budget_period_id": 4}, f"{E}/expenses", {"budget_period_id": "4"}),
    ("expense_list_expenses", {"start_date": "2026-09-01", "end_date": "2026-09-30"}, f"{E}/expenses", {"start_date": "2026-09-01", "end_date": "2026-09-30"}),
    ("expense_list_expenses", {"unassigned": True}, f"{E}/expenses", {"unassigned": "true"}),
    ("expense_get_usage_date_report", {"budget_period_id": 4}, f"{E}/reports/usage-date", {"budget_period_id": "4", "include_credit": "false"}),
    ("expense_get_usage_date_report", {"budget_period_id": 4, "include_credit": True}, f"{E}/reports/usage-date", {"budget_period_id": "4", "include_credit": "true"}),
    ("expense_get_payment_date_report", {"year_month": "2026-09"}, f"{E}/reports/payment-date", {"year_month": "2026-09"}),
]


@pytest.mark.parametrize(("tool", "args", "url", "query"), READ_CASES)
async def test_read_tools(mcp: MCPServer, tool: str, args: dict[str, Any], url: str, query: dict[str, str]) -> None:
    payload = {"items": [{"id": 1, "name": "x"}]}
    route = ROUTER.get(url).mock(return_value=httpx.Response(200, json=payload))
    error, out = await call(mcp, tool, args)
    assert not error, out
    assert out == payload
    assert dict(route.calls.last.request.url.params) == query
    assert route.calls.last.request.headers["authorization"] == f"Bearer {TEST_API_KEY}"


async def test_expense_list_payment_methods_includes_credit_fields(mcp: MCPServer) -> None:
    payload = {"items": [{"id": 1, "name": "売掛カード", "is_credit": True, "is_credit_payment": False}]}
    ROUTER.get(f"{E}/payment-methods").mock(return_value=httpx.Response(200, json=payload))
    error, out = await call(mcp, "expense_list_payment_methods")
    assert not error
    assert out == payload


async def test_knowhow_search_repeats_keyword(mcp: MCPServer, log_dir: Path) -> None:
    route = ROUTER.get(f"{K}/knowhows/search").mock(return_value=httpx.Response(200, json={"items": []}))
    error, _ = await call(mcp, "knowhow_search_knowhows", {"keywords": ["バックアップ", "手順"]})
    assert not error
    assert route.calls.last.request.url.params.get_list("keyword") == ["バックアップ", "手順"]
    assert "バックアップ" not in log_text(log_dir)  # キーワードの文字列はログに出さない
    error, _ = await call(mcp, "knowhow_search_knowhows", {"keywords": []})
    assert error


async def test_goods_outputs_exclude_image_data(mcp: MCPServer) -> None:
    ROUTER.get(f"{G}/goods").mock(
        return_value=httpx.Response(
            200,
            json={"items": [{"goods_id": 1, "title": "t", "thumbnail_image_type": "image/jpeg", "thumbnail_image_data": "QUJD"}]},
        )
    )
    ROUTER.get(f"{G}/goods/1").mock(
        return_value=httpx.Response(
            200,
            json={"id": 1, "title": "t", "images": [{"id": 9, "image_type": "image/png", "image_data": "QUJD", "display_order": 1}]},
        )
    )
    _, listed = await call(mcp, "goods_list_goods", {"person_id": 1})
    assert listed == {"items": [{"goods_id": 1, "title": "t", "thumbnail_image_type": "image/jpeg"}]}
    _, detail = await call(mcp, "goods_get_goods", {"goods_id": 1})
    assert detail["images"] == [{"id": 9, "image_type": "image/png", "display_order": 1}]


async def test_invalid_arguments_do_not_call_webapp(mcp: MCPServer) -> None:
    route = ROUTER.get(f"{S}/schedules").mock(return_value=httpx.Response(200, json={"items": []}))
    error, _ = await call(mcp, "schedule_list_schedules", {"start_date": "2026/09/01", "end_date": "2026-09-30"})
    assert error and route.call_count == 0


# ---- スケジュールの更新系 ----

SCHEDULE_ITEM = {"id": 7, "title": "打合せ", "kind": "event"}


async def test_schedule_create_defaults(mcp: MCPServer, log_dir: Path) -> None:
    route = ROUTER.post(f"{S}/schedules").mock(return_value=httpx.Response(201, json=SCHEDULE_ITEM))
    error, out = await call(
        mcp,
        "schedule_create_schedule",
        {"title": "打合せ", "kind": "event", "granularity": "day", "start_date": "2026-10-01", "end_date": "2026-10-01", "category_id": 2},
    )
    assert not error and out == SCHEDULE_ITEM
    assert body_of(route) == {
        "title": "打合せ", "location": None, "detail": None, "kind": "event", "granularity": "day",
        "start_date": "2026-10-01", "end_date": "2026-10-01", "start_time": None, "end_time": None,
        "category_id": 2, "needs_notification": False,
    }
    assert "打合せ" not in log_text(log_dir)


async def test_schedule_create_category_not_found(mcp: MCPServer) -> None:
    ROUTER.post(f"{S}/schedules").mock(return_value=httpx.Response(404, json={"detail": "対象がありません"}))
    error, text = await call(
        mcp,
        "schedule_create_schedule",
        {"title": "x", "kind": "todo", "granularity": "day", "start_date": "2026-10-01", "end_date": "2026-10-01", "category_id": 99},
    )
    assert error and "指定したカテゴリが見つかりません。schedule_list_categories で確かめてください。" in text


async def test_schedule_update_sends_all_fields(mcp: MCPServer) -> None:
    route = ROUTER.patch(f"{S}/schedules/7").mock(return_value=httpx.Response(200, json=SCHEDULE_ITEM))
    args = {
        "schedule_id": 7, "title": "打合せ", "kind": "event", "granularity": "time", "start_date": "2026-10-01",
        "end_date": "2026-10-01", "start_time": "09:00", "end_time": "10:00", "category_id": 2,
        "needs_notification": True, "location": None, "detail": "議題",
    }
    error, _ = await call(mcp, "schedule_update_schedule", args)
    assert not error
    sent = body_of(route)
    assert sent["start_time"] == "09:00" and sent["location"] is None and sent["detail"] == "議題" and "schedule_id" not in sent


async def test_schedule_completion_and_delete(mcp: MCPServer) -> None:
    completion = ROUTER.patch(f"{S}/schedules/7/completion").mock(return_value=httpx.Response(409, json={"detail": "保存できませんでした"}))
    error, text = await call(mcp, "schedule_set_todo_completion", {"schedule_id": 7, "is_completed": True})
    assert error and "予定（TODO でないもの）には実施状態を設定できません。" in text
    assert body_of(completion) == {"is_completed": True}
    ROUTER.delete(f"{S}/schedules/7").mock(return_value=httpx.Response(204))
    error, out = await call(mcp, "schedule_delete_schedule", {"schedule_id": 7})
    assert not error and out == {"deleted": True, "id": 7}


# ---- グッズ・ノウハウの更新系 ----


async def test_goods_create_update_delete(mcp: MCPServer) -> None:
    created = ROUTER.post(f"{G}/goods").mock(return_value=httpx.Response(201, json={"id": 3, "title": "t", "images": []}))
    error, out = await call(mcp, "goods_create_goods", {"media_id": 1, "artist_id": 2, "title": "t"})
    assert not error and out == {"id": 3, "title": "t", "images": []}
    assert body_of(created) == {
        "media_id": 1, "artist_id": 2, "title": "t", "release_date": None, "memo": None, "is_owned": False, "code_number": None,
    }
    ROUTER.patch(f"{G}/goods/3").mock(return_value=httpx.Response(404, json={"detail": "対象がありません"}))
    error, text = await call(
        mcp,
        "goods_update_goods",
        {"goods_id": 3, "media_id": 1, "artist_id": 2, "title": "t", "release_date": None, "memo": None, "is_owned": True, "code_number": None},
    )
    assert error and "グッズ・媒体・アーティストのいずれかが見つかりません。" in text
    ROUTER.delete(f"{G}/goods/3").mock(return_value=httpx.Response(204))
    assert (await call(mcp, "goods_delete_goods", {"goods_id": 3}))[1] == {"deleted": True, "id": 3}


async def test_knowhow_create_update_delete(mcp: MCPServer) -> None:
    item = {"id": 5, "title": "手順", "keywords": None, "content": "本文", "middle_category_id": None, "display_order": 1}
    created = ROUTER.post(f"{K}/knowhows").mock(return_value=httpx.Response(201, json=item))
    error, out = await call(mcp, "knowhow_create_knowhow", {"title": "手順", "content": "本文"})
    assert not error and out == item
    assert body_of(created) == {"title": "手順", "keywords": None, "content": "本文", "middle_category_id": None}
    updated = ROUTER.patch(f"{K}/knowhows/5").mock(return_value=httpx.Response(200, json=item))
    error, _ = await call(
        mcp, "knowhow_update_knowhow", {"knowhow_id": 5, "title": "手順", "content": "本文", "keywords": "k", "middle_category_id": 10}
    )
    assert not error and body_of(updated)["middle_category_id"] == 10
    ROUTER.delete(f"{K}/knowhows/5").mock(return_value=httpx.Response(204))
    assert (await call(mcp, "knowhow_delete_knowhow", {"knowhow_id": 5}))[1] == {"deleted": True, "id": 5}


# ---- 経費: 支払日の算出 ----

EXPENSE_ARGS = {"usage_date": "2026-09-05", "purpose": "ランチ代", "amount": "980.00", "payment_method_id": 1}
EXPENSE_ITEM = {"id": 100, "usage_date": "2026-09-05", "payment_date": "2026-10-10", "payment_date_is_auto": True}


async def test_expense_create_computes_payment_date(mcp: MCPServer) -> None:
    estimate = ROUTER.get(f"{E}/payment-methods/1/estimated-payment-date").mock(
        return_value=httpx.Response(200, json={"payment_date": "2026-10-10"})
    )
    created = ROUTER.post(f"{E}/expenses").mock(return_value=httpx.Response(201, json=EXPENSE_ITEM))
    error, out = await call(mcp, "expense_create_expense", EXPENSE_ARGS)
    assert not error and out == EXPENSE_ITEM
    assert dict(estimate.calls.last.request.url.params) == {"usage_date": "2026-09-05"}
    assert body_of(created) == {
        "usage_date": "2026-09-05", "budget_period_id": None, "budget_item_id": None, "purpose": "ランチ代",
        "amount": "980.00", "payment_method_id": 1, "memo": None, "payment_date": "2026-10-10", "payment_date_is_auto": True,
    }


async def test_expense_create_with_given_payment_date(mcp: MCPServer) -> None:
    estimate = ROUTER.get(f"{E}/payment-methods/1/estimated-payment-date").mock(
        return_value=httpx.Response(200, json={"payment_date": "2026-10-10"})
    )
    created = ROUTER.post(f"{E}/expenses").mock(return_value=httpx.Response(201, json=EXPENSE_ITEM))
    error, _ = await call(mcp, "expense_create_expense", {**EXPENSE_ARGS, "payment_date": "2026-09-30", "budget_period_id": 4, "budget_item_id": 10})
    assert not error
    assert estimate.call_count == 0
    sent = body_of(created)
    assert sent["payment_date"] == "2026-09-30" and sent["payment_date_is_auto"] is False
    assert sent["budget_period_id"] == 4 and sent["budget_item_id"] == 10


@pytest.mark.parametrize(
    ("status", "fragment"),
    [
        (404, "指定した支出方法が見つかりません。expense_list_payment_methods で確かめてください。（登録していません）"),
        (500, "支払日を算出できませんでした。（登録していません）"),
    ],
)
async def test_expense_create_estimate_failure_does_not_register(mcp: MCPServer, status: int, fragment: str) -> None:
    ROUTER.get(f"{E}/payment-methods/1/estimated-payment-date").mock(return_value=httpx.Response(status, json={"detail": "x"}))
    created = ROUTER.post(f"{E}/expenses").mock(return_value=httpx.Response(201, json=EXPENSE_ITEM))
    error, text = await call(mcp, "expense_create_expense", EXPENSE_ARGS)
    assert error and fragment in text
    assert created.call_count == 0


async def test_expense_update_recomputes_and_not_found(mcp: MCPServer) -> None:
    ROUTER.get(f"{E}/payment-methods/2/estimated-payment-date").mock(return_value=httpx.Response(200, json={"payment_date": "2026-11-10"}))
    updated = ROUTER.patch(f"{E}/expenses/100").mock(return_value=httpx.Response(200, json=EXPENSE_ITEM))
    args = {**EXPENSE_ARGS, "expense_id": 100, "payment_method_id": 2, "budget_period_id": None, "budget_item_id": None, "memo": None}
    error, _ = await call(mcp, "expense_update_expense", args)
    assert not error
    assert body_of(updated)["payment_date"] == "2026-11-10" and body_of(updated)["payment_date_is_auto"] is True
    ROUTER.patch(f"{E}/expenses/100").mock(return_value=httpx.Response(404, json={"detail": "対象がありません"}))
    error, text = await call(mcp, "expense_update_expense", {**args, "payment_date": "2026-11-01"})
    assert error and "支出記録が見つかりません。ID を確かめてください。" in text


async def test_expense_amount_format_and_delete(mcp: MCPServer) -> None:
    error, _ = await call(mcp, "expense_create_expense", {**EXPENSE_ARGS, "amount": "-5"})
    assert error
    ROUTER.delete(f"{E}/expenses/100").mock(return_value=httpx.Response(204))
    assert (await call(mcp, "expense_delete_expense", {"expense_id": 100}))[1] == {"deleted": True, "id": 100}
