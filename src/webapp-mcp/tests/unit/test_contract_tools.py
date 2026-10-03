"""契約管理のツールの単体テスト（T-018）。

Web アプリの API は respx でモックする。契約管理のバックエンドは動かさない。
パスワードの値が、入力にも出力にも無いことを確かめる（REQ-017、REQ-018）。
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

C = "http://webapp.test/contract"

CONTRACT_TOOLS = {
    "contract_list_contracts": "R",
    "contract_get_contract": "R",
    "contract_list_categories": "R",
    "contract_get_cancellation_plan": "R",
    "contract_create_contract": "W",
    "contract_update_contract": "W",
}
HINTS = {"R": (True, False, True), "W": (False, False, False)}

ROUTER = respx.MockRouter(assert_all_called=False)

CONTRACT = {
    "id": 12,
    "name": "ネット動画サービス",
    "has_contract": True,
    "category": {"id": 3, "name": "動画配信", "is_financial": False},
    "status": "active",
    "homepage": "https://video.example.com",
    "memo": None,
    "login_methods": ["password", "2fa_mail"],
    "twofa_mail_address": "me@example.com",
    "twofa_tel_number": None,
    "username": "taro@example.com",
    "has_password": True,
    "password_unset": False,
    "registered_email": "taro@example.com",
    "fee_amount": 990,
    "fee_cycle": "monthly",
    "renewal_date": "2026-11-05",
    "contract_date": "2020-04",
    "contract_date_precision": "month",
    "trial_end_date": None,
    "end_date": None,
    "auto_renewal": True,
    "holder_name": "山田 太郎",
    "member_number": "A-123456",
    "cancel_notice_days": 7,
    "cancellation_fee": "なし",
    "min_term_months": 12,
    "contact_phone": "0120-000-000",
    "contact_email": "support@example.com",
    "contact_hours": "平日 10:00-18:00",
    "cancellation_method": "マイページの設定から解約する",
    "depends_on": [{"id": 8, "name": "プロバイダ"}],
    "payment_contract": {"id": 5, "name": "Aカード"},
    "depended_by": [],
    "payment_for": [],
}
CATEGORIES = {
    "items": [
        {"id": 1, "name": "その他", "is_default": True, "is_financial": False},
        {"id": 4, "name": "銀行・カード", "is_default": False, "is_financial": True},
    ]
}
PLAN = {
    "items": [
        {
            "position": 1,
            "contract_id": 12,
            "name": "ネット動画サービス",
            "cancellation_method": "マイページの設定から解約する",
            "depends_on": [{"id": 8, "name": "プロバイダ"}],
        }
    ],
    "warnings": [
        {"contract_id": 12, "name": "ネット動画サービス", "depends_on_contract_id": 8, "depends_on_name": "プロバイダ"}
    ],
}


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
        text: str = result.content[0].text  # type: ignore[union-attr]
        # SDK は、ツールのエラー文の先頭に「Error executing tool <名前>: 」を付ける。ツールが返した文だけを比べる
        prefix = f"Error executing tool {name}: "
        return True, text.removeprefix(prefix)
    return False, result.structured_content


def body_of(route: respx.Route) -> Any:
    return json.loads(route.calls.last.request.content)


def has_key(value: Any, key: str) -> bool:
    """データのどこかに、名前が key の項目があるか（値の文字列は見ない）。"""
    if isinstance(value, dict):
        return key in value or any(has_key(v, key) for v in value.values())
    if isinstance(value, list):
        return any(has_key(v, key) for v in value)
    return False


def enum_of(prop: dict[str, Any]) -> list[str]:
    if "enum" in prop:
        return list(prop["enum"])
    for option in prop.get("anyOf", []):
        if "enum" in option:
            return list(option["enum"])
    raise AssertionError(f"列挙が無い: {prop}")


# ---- ツール一覧・注釈・入力スキーマ ----


async def test_contract_tools_exist_with_annotations(mcp: MCPServer) -> None:
    tools = await list_tools(mcp)
    assert set(CONTRACT_TOOLS) <= set(tools)
    for name, kind in CONTRACT_TOOLS.items():
        a = tools[name].annotations
        assert (a.read_only_hint, a.destructive_hint, a.idempotent_hint) == HINTS[kind], name
        assert "site" in tools[name].input_schema.get("properties", {}), name
    assert len(tools) == 45


async def test_only_allowed_operations_are_provided(mcp: MCPServer) -> None:
    """削除・パスワードの取得・アカウント一覧・区分の管理・解約順の保存のツールは、無い（API キーでは許可されない）。"""
    names = [n for n in await list_tools(mcp) if n.startswith("contract")]
    assert sorted(names) == sorted(CONTRACT_TOOLS)
    for forbidden in ("delete", "password", "account", "category_create", "plan_save", "set_cancellation", "pdf", "import"):
        assert not any(forbidden in n for n in names), forbidden


async def test_no_tool_has_a_password_argument(mcp: MCPServer) -> None:
    tools = await list_tools(mcp)
    for name in CONTRACT_TOOLS:
        assert "password" not in tools[name].input_schema.get("properties", {}), name
    for name in ("contract_create_contract", "contract_update_contract"):
        assert "パスワードの値は、指定できません" in (tools[name].description or ""), name


async def test_input_schemas(mcp: MCPServer) -> None:
    tools = await list_tools(mcp)
    create = tools["contract_create_contract"].input_schema
    update = tools["contract_update_contract"].input_schema
    assert create["required"] == ["name"]
    assert set(update["required"]) == {"contract_id", "name"}
    for schema in (create, update):
        props = schema["properties"]
        assert enum_of(props["status"]) == ["active", "paused", "cancelled"]
        assert enum_of(props["fee_cycle"]) == ["yearly", "monthly"]
        assert enum_of(props["contract_date_precision"]) == ["day", "month", "year", "unknown"]
        assert set(props["login_methods"]["anyOf"][0]["items"]["enum"]) == {"password", "passkey", "2fa_mail", "2fa_tel"}
        assert "password" not in props
    lst = tools["contract_list_contracts"].input_schema
    assert not lst.get("required")
    assert set(lst["properties"]) == {"keyword", "category_id", "status", "has_contract", "password_unset", "site"}
    assert tools["contract_get_contract"].input_schema["required"] == ["contract_id"]
    assert not tools["contract_list_categories"].input_schema.get("required")
    assert not tools["contract_get_cancellation_plan"].input_schema.get("required")


async def test_descriptions_explain_password_and_restrictions(mcp: MCPServer) -> None:
    tools = await list_tools(mcp)
    assert "パスワードの値は返りません" in (tools["contract_list_contracts"].description or "")
    assert "password_unset" in (tools["contract_list_contracts"].description or "")
    assert "パスワードの値は返りません" in (tools["contract_get_contract"].description or "")
    assert "is_financial" in (tools["contract_list_categories"].description or "")
    assert "warnings" in (tools["contract_get_cancellation_plan"].description or "")
    for name in ("contract_create_contract", "contract_update_contract"):
        d = tools[name].description or ""
        assert "契約を伴わない" in d and "金融機関" in d, name
        assert "人が Web アプリの画面でパスワードを入力・変更します" in d, name
    update = tools["contract_update_contract"].description or ""
    assert "contract_get_contract" in update and "空に更新されます" in update
    assert "保存済みのパスワードは変わりません" in update
    assert "パスワード未設定になります" in (tools["contract_create_contract"].description or "")


# ---- 参照 ----


async def test_list_contracts_without_filters(mcp: MCPServer) -> None:
    route = ROUTER.get(f"{C}/contracts").mock(return_value=httpx.Response(200, json={"total": 1, "items": [CONTRACT]}))
    is_error, out = await call(mcp, "contract_list_contracts")
    assert not is_error and out == {"total": 1, "items": [CONTRACT]}
    request = route.calls.last.request
    assert request.url.query == b""  # 絞り込みなしは、クエリなし
    assert request.headers["Authorization"] == f"Bearer {TEST_API_KEY}"
    assert not has_key(out, "password")  # パスワードの値の項目は無い（has_password などだけ）


async def test_list_contracts_with_filters(mcp: MCPServer) -> None:
    route = ROUTER.get(f"{C}/contracts").mock(return_value=httpx.Response(200, json={"total": 0, "items": []}))
    is_error, _ = await call(
        mcp,
        "contract_list_contracts",
        {"keyword": "動画", "category_id": 3, "status": "paused", "has_contract": False, "password_unset": True},
    )
    assert not is_error
    params = dict(route.calls.last.request.url.params)
    assert params == {
        "keyword": "動画",
        "category_id": "3",
        "status": "paused",
        "has_contract": "false",
        "password_unset": "true",
    }
    # false は、そのまま渡す（Web アプリが、password_unset の false を絞り込まないと扱う）
    await call(mcp, "contract_list_contracts", {"has_contract": True, "password_unset": False})
    assert dict(route.calls.last.request.url.params) == {"has_contract": "true", "password_unset": "false"}


async def test_get_contract_and_not_found(mcp: MCPServer) -> None:
    ROUTER.get(f"{C}/contracts/12").mock(return_value=httpx.Response(200, json=CONTRACT))
    is_error, out = await call(mcp, "contract_get_contract", {"contract_id": 12})
    assert not is_error and out == CONTRACT
    ROUTER.get(f"{C}/contracts/99").mock(return_value=httpx.Response(404, json={"detail": "対象がありません"}))
    is_error, text = await call(mcp, "contract_get_contract", {"contract_id": 99})
    assert is_error
    assert text == "契約が見つかりません。ID を contract_list_contracts で確かめてください（削除済みのものも見つかりません）。"


async def test_list_categories(mcp: MCPServer) -> None:
    route = ROUTER.get(f"{C}/categories").mock(return_value=httpx.Response(200, json=CATEGORIES))
    is_error, out = await call(mcp, "contract_list_categories")
    assert not is_error and out == CATEGORIES
    assert route.calls.last.request.url.query == b""


async def test_get_cancellation_plan(mcp: MCPServer) -> None:
    ROUTER.get(f"{C}/cancellation-plan").mock(return_value=httpx.Response(200, json=PLAN))
    is_error, out = await call(mcp, "contract_get_cancellation_plan")
    assert not is_error and out == PLAN
    assert out["warnings"][0]["depends_on_contract_id"] == 8


# ---- 登録・更新 ----


async def test_create_minimal_sends_only_given_fields(mcp: MCPServer) -> None:
    route = ROUTER.post(f"{C}/contracts").mock(return_value=httpx.Response(201, json=CONTRACT))
    is_error, out = await call(mcp, "contract_create_contract", {"name": "名称だけ"})
    assert not is_error and out == CONTRACT
    assert body_of(route) == {"name": "名称だけ"}  # 省略した項目は送らない
    assert route.calls.last.request.headers["Authorization"] == f"Bearer {TEST_API_KEY}"


async def test_create_sends_all_given_fields_with_api_names(mcp: MCPServer) -> None:
    route = ROUTER.post(f"{C}/contracts").mock(return_value=httpx.Response(201, json=CONTRACT))
    args = {
        "name": "ネット動画サービス",
        "has_contract": True,
        "category_id": 3,
        "status": "paused",
        "homepage": "https://video.example.com",
        "memo": "メモ",
        "login_methods": ["password", "2fa_mail"],
        "twofa_mail_address": "me@example.com",
        "username": "taro@example.com",
        "registered_email": "taro@example.com",
        "fee_amount": 0,
        "fee_cycle": "yearly",
        "renewal_date": "2026-11-05",
        "contract_date_precision": "month",
        "contract_date": "2020-04",
        "trial_end_date": "2026-10-31",
        "auto_renewal": False,
        "holder_name": "山田 太郎",
        "member_number": "A-123456",
        "cancel_notice_days": 0,
        "cancellation_fee": "なし",
        "min_term_months": 0,
        "contact_phone": "0120-000-000",
        "contact_email": "support@example.com",
        "contact_hours": "平日",
        "cancellation_method": "手順\n二行目",
        "depends_on_ids": [8, 9],
        "payment_contract_id": 5,
    }
    is_error, _ = await call(mcp, "contract_create_contract", args)
    assert not is_error
    assert body_of(route) == args  # 値のまま（0 と false も落とさない）


async def test_create_for_contractless_account(mcp: MCPServer) -> None:
    route = ROUTER.post(f"{C}/contracts").mock(return_value=httpx.Response(201, json=CONTRACT))
    await call(mcp, "contract_create_contract", {"name": "アカウント", "has_contract": False, "login_methods": ["password"], "username": "u"})
    assert body_of(route) == {"name": "アカウント", "has_contract": False, "login_methods": ["password"], "username": "u"}


async def test_password_is_never_sent(mcp: MCPServer) -> None:
    """password を渡されても、Web アプリへの要求の本文に含めない。"""
    create = ROUTER.post(f"{C}/contracts").mock(return_value=httpx.Response(201, json=CONTRACT))
    update = ROUTER.patch(f"{C}/contracts/12").mock(return_value=httpx.Response(200, json=CONTRACT))
    await call(mcp, "contract_create_contract", {"name": "x", "password": "S3cret-Pass"})
    await call(mcp, "contract_update_contract", {"contract_id": 12, "name": "x", "password": "S3cret-Pass"})
    for route in (create, update):
        assert route.called
        sent = route.calls.last.request.content.decode("utf-8")
        assert "password" not in sent and "S3cret-Pass" not in sent
        assert "password" not in body_of(route)


async def test_update_uses_patch_with_id_in_path_only(mcp: MCPServer) -> None:
    route = ROUTER.patch(f"{C}/contracts/12").mock(return_value=httpx.Response(200, json=CONTRACT))
    is_error, out = await call(
        mcp, "contract_update_contract", {"contract_id": 12, "name": "改名", "category_id": 3, "depends_on_ids": [8], "payment_contract_id": 5}
    )
    assert not is_error and out == CONTRACT
    assert route.calls.last.request.method == "PATCH"
    assert body_of(route) == {"name": "改名", "category_id": 3, "depends_on_ids": [8], "payment_contract_id": 5}
    assert "contract_id" not in body_of(route)


async def test_update_errors(mcp: MCPServer) -> None:
    ROUTER.patch(f"{C}/contracts/99").mock(return_value=httpx.Response(404, json={"detail": "対象がありません"}))
    is_error, text = await call(mcp, "contract_update_contract", {"contract_id": 99, "name": "x"})
    assert is_error and text.startswith("契約が見つかりません。ID を contract_list_contracts")
    ROUTER.patch(f"{C}/contracts/12").mock(return_value=httpx.Response(409, json={"detail": "保存できませんでした"}))
    is_error, text = await call(mcp, "contract_update_contract", {"contract_id": 12, "name": "x"})
    assert is_error
    assert text == (
        "Web アプリが更新を受け付けませんでした。依存契約の関係が循環している、または、"
        "他の契約の支払方法になっている契約の区分を、金融機関でない区分に変えようとした可能性があります。"
        "（Web アプリ: 保存できませんでした）"
    )


async def test_create_400_is_relayed_without_checking_combinations(mcp: MCPServer) -> None:
    """契約を伴わないのに契約の項目がある、維持費の金額だけ、などは、ツールは検査せず、Web アプリの 400 を返す。"""
    route = ROUTER.post(f"{C}/contracts").mock(return_value=httpx.Response(400, json={"detail": "入力が不正です"}))
    for args in (
        {"name": "x", "has_contract": False, "fee_amount": 1, "fee_cycle": "monthly"},
        {"name": "x", "fee_amount": 100},
        {"name": "x", "contract_date_precision": "day"},
    ):
        is_error, text = await call(mcp, "contract_create_contract", args)
        assert is_error
        assert text == "入力が不正です。引数の形式・必須項目・組み合わせを確認してください。（Web アプリ: 入力が不正です）"
    assert route.call_count == 3  # Web アプリを呼んでいる


@pytest.mark.parametrize(
    "tool,args",
    [
        ("contract_create_contract", {"name": "x", "status": "終了"}),
        ("contract_create_contract", {"name": "x", "fee_cycle": "weekly"}),
        ("contract_create_contract", {"name": "x", "contract_date_precision": "always"}),
        ("contract_create_contract", {"name": "x", "login_methods": ["sms"]}),
        ("contract_create_contract", {"name": "x", "fee_amount": "100"}),
        ("contract_create_contract", {"name": "x", "fee_amount": -1}),
        ("contract_create_contract", {"name": "x", "renewal_date": "20261105"}),
        ("contract_create_contract", {"name": "x", "contract_date": "2020/04"}),
        ("contract_create_contract", {"name": "x", "depends_on_ids": [0]}),
        ("contract_create_contract", {"name": "x", "cancel_notice_days": -1}),
        ("contract_create_contract", {}),
        ("contract_update_contract", {"contract_id": 12}),
        ("contract_update_contract", {"contract_id": 0, "name": "x"}),
        ("contract_update_contract", {"contract_id": 12, "name": "x", "status": "終了"}),
        ("contract_list_contracts", {"status": "終了"}),
        ("contract_list_contracts", {"category_id": 0}),
        ("contract_get_contract", {"contract_id": 0}),
        ("contract_get_contract", {}),
    ],
)
async def test_invalid_input_is_rejected_without_calling_webapp(mcp: MCPServer, tool: str, args: dict[str, Any]) -> None:
    is_error, _ = await call(mcp, tool, args)
    assert is_error
    assert not ROUTER.calls  # Web アプリは呼ばれない


# ---- サイト・エラー ----


async def test_site_argument_and_missing_feature(mcp: MCPServer) -> None:
    is_error, text = await call(mcp, "contract_list_categories", {"site": "office"})
    assert is_error
    assert text == "サイト office では、この機能を利用できません（接続先が設定されていません）。"
    is_error, text = await call(mcp, "contract_list_categories", {"site": "nowhere"})
    assert is_error and text == "サイト nowhere は登録されていません。list_sites で確かめてください。"
    # 他の機能のツールは、動く
    ROUTER.get("http://office.test/schedule/categories").mock(return_value=httpx.Response(200, json={"items": []}))
    is_error, _ = await call(mcp, "schedule_list_categories", {"site": "office"})
    assert not is_error


@pytest.mark.parametrize(
    "status,expected",
    [
        (401, "サイト home の API キーが無効です（失効・期限切れを含む）。MCP サーバの設定で API キーを見直してください。"),
        (403, "サイト home で、この機能を利用する権限がありません。Web アプリで機能の割り当てを確認してください。"),
    ],
)
async def test_common_errors(mcp: MCPServer, status: int, expected: str) -> None:
    ROUTER.get(f"{C}/contracts").mock(return_value=httpx.Response(status, json={"detail": "x"}))
    is_error, text = await call(mcp, "contract_list_contracts")
    assert is_error and text == expected
    assert TEST_API_KEY not in text and "webapp.test" not in text


async def test_unreachable_and_no_retry(mcp: MCPServer) -> None:
    route = ROUTER.post(f"{C}/contracts").mock(side_effect=httpx.ConnectError("boom: internal"))
    is_error, text = await call(mcp, "contract_create_contract", {"name": "x"})
    assert is_error and "接続できないか、処理に失敗しました" in text
    assert "internal" not in text and "webapp.test" not in text
    assert route.call_count == 1  # 自動で再試行しない
    route500 = ROUTER.patch(f"{C}/contracts/12").mock(return_value=httpx.Response(500, json={"detail": "x"}))
    is_error, text = await call(mcp, "contract_update_contract", {"contract_id": 12, "name": "x"})
    assert is_error and "接続できないか、処理に失敗しました" in text
    assert route500.call_count == 1


# ---- ログ ----


async def test_log_has_no_contract_contents_or_secrets(mcp: MCPServer, log_dir: Path) -> None:
    ROUTER.post(f"{C}/contracts").mock(return_value=httpx.Response(201, json=CONTRACT))
    ROUTER.patch(f"{C}/contracts/12").mock(return_value=httpx.Response(200, json=CONTRACT))
    ROUTER.get(f"{C}/contracts").mock(return_value=httpx.Response(200, json={"total": 1, "items": [CONTRACT]}))
    ROUTER.get(f"{C}/contracts/12").mock(return_value=httpx.Response(200, json=CONTRACT))
    secrets = ["秘密のユーザ名", "secret-user@example.com", "秘密の解約方法", "090-0000-1111", "S3cret-Pass", "秘密のキーワード", "秘密の名称"]
    await call(
        mcp,
        "contract_create_contract",
        {
            "name": "秘密の名称",
            "username": "秘密のユーザ名",
            "registered_email": "secret-user@example.com",
            "login_methods": ["2fa_tel"],
            "twofa_tel_number": "090-0000-1111",
            "cancellation_method": "秘密の解約方法",
            "memo": "秘密のメモ",
            "password": "S3cret-Pass",
        },
    )
    await call(mcp, "contract_update_contract", {"contract_id": 12, "name": "秘密の名称", "username": "秘密のユーザ名"})
    await call(mcp, "contract_list_contracts", {"keyword": "秘密のキーワード", "status": "active"})
    await call(mcp, "contract_get_contract", {"contract_id": 12})
    text = log_text(log_dir)
    for name in ("contract_create_contract", "contract_update_contract", "contract_list_contracts", "contract_get_contract"):
        assert f"tool={name}" in text, name
    assert "contract_id=12" in text and "keyword_given=True" in text and "status=active" in text
    assert "件数=1" in text
    for secret in secrets + ["秘密のメモ"]:
        assert secret not in text, secret
    assert TEST_API_KEY not in text
    # 契約の応答の内容（名称・メールアドレスなど）も、ログに出ない
    for content in ("ネット動画サービス", "taro@example.com", "山田 太郎", "A-123456", "マイページの設定から解約する"):
        assert content not in text, content
