from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx
from mcp.server.mcpserver.exceptions import ToolError

from app.sites import SiteRegistry
from app.webapp_client import ErrorMessages, WebappClient
from conftest import TEST_API_KEY, log_text

BASE = "http://webapp.test/schedule"


@pytest.fixture()
async def client(registry: SiteRegistry):
    c = WebappClient(registry, timeout_seconds=1)
    yield c
    await c.aclose()


async def _call(client: WebappClient, registry: SiteRegistry, **kwargs: object) -> object:
    return await client.request(
        tool="t", site=registry.resolve(None), feature="schedule", method="GET", path="/categories", **kwargs
    )


@respx.mock
async def test_success_sends_bearer_and_returns_body(client: WebappClient, registry: SiteRegistry, log_dir: Path) -> None:
    route = respx.get(f"{BASE}/categories").mock(return_value=httpx.Response(200, json={"items": [{"id": 1}]}))
    body = await _call(client, registry, params={"include_deleted": False, "x": None})
    assert body == {"items": [{"id": 1}]}
    request = route.calls.last.request
    assert request.headers["authorization"] == f"Bearer {TEST_API_KEY}"
    assert "cookie" not in request.headers
    assert request.url.params["include_deleted"] == "false"
    assert "x" not in request.url.params
    text = log_text(log_dir)
    assert "status=200 件数=1" in text
    assert TEST_API_KEY not in text


@respx.mock
async def test_204_returns_none(client: WebappClient, registry: SiteRegistry) -> None:
    respx.get(f"{BASE}/categories").mock(return_value=httpx.Response(204))
    assert await _call(client, registry) is None


@pytest.mark.parametrize(
    ("status", "fragment"),
    [
        (400, "入力が不正です。引数の形式・必須項目・組み合わせを確認してください。（Web アプリ: 入力が不正です）"),
        (401, "サイト home の API キーが無効です"),
        (403, "サイト home で、この機能を利用する権限がありません"),
        (404, "対象が見つかりません。ID を確認してください"),
        (409, "Web アプリが処理を受け付けませんでした。（Web アプリ: 保存できませんでした）"),
        (500, "サイト home の Web アプリに接続できないか、処理に失敗しました"),
    ],
)
@respx.mock
async def test_status_mapping(client: WebappClient, registry: SiteRegistry, log_dir: Path, status: int, fragment: str) -> None:
    detail = {400: "入力が不正です", 409: "保存できませんでした"}.get(status, "x")
    route = respx.get(f"{BASE}/categories").mock(return_value=httpx.Response(status, json={"detail": detail}))
    with pytest.raises(ToolError) as exc:
        await _call(client, registry)
    assert fragment in str(exc.value)
    assert route.call_count == 1  # 再試行しない
    assert TEST_API_KEY not in str(exc.value)
    assert "webapp.test" not in str(exc.value)
    assert f"status={status}" in log_text(log_dir)


@respx.mock
async def test_custom_messages(client: WebappClient, registry: SiteRegistry) -> None:
    respx.get(f"{BASE}/categories").mock(return_value=httpx.Response(404, json={"detail": "対象がありません"}))
    with pytest.raises(ToolError) as exc:
        await _call(client, registry, messages=ErrorMessages(not_found="カテゴリが見つかりません。"))
    assert str(exc.value) == "カテゴリが見つかりません。"


@pytest.mark.parametrize("error", [httpx.ConnectError("x"), httpx.ReadTimeout("x")])
@respx.mock
async def test_network_failures(client: WebappClient, registry: SiteRegistry, error: Exception) -> None:
    route = respx.get(f"{BASE}/categories").mock(side_effect=error)
    with pytest.raises(ToolError) as exc:
        await _call(client, registry)
    assert "接続できないか" in str(exc.value)
    assert route.call_count == 1


async def test_feature_not_configured(client: WebappClient, registry: SiteRegistry) -> None:
    with pytest.raises(ToolError) as exc:
        await client.request(
            tool="t", site=registry.resolve("office"), feature="goods-management", method="GET", path="/persons"
        )
    assert str(exc.value) == "サイト office では、この機能を利用できません（接続先が設定されていません）。"


def test_unknown_site(client: WebappClient) -> None:
    with pytest.raises(ToolError) as exc:
        client.resolve_site("nowhere", "t")
    assert str(exc.value) == "サイト nowhere は登録されていません。list_sites で確かめてください。"
