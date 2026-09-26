"""結合テスト: 起動した MCP サーバに OAuth で接続し、開発環境の Web アプリに対してツールを呼ぶ。

前提:
- 開発環境の Web アプリの 4 機能のバックエンドが起動していること
  （既定: schedule=8002, goods-management=8006, knowhow-management=8005, expense-management=8177。
   WEBAPP_TEST_<FEATURE>_URL で変更できる）
- `api-key-management` の画面で発行した API キーを、環境変数 WEBAPP_TEST_API_KEY で渡すこと
  （キーの持ち主に 4 機能が割り当てられていること）。無いときはこのテストをスキップする。

準備データ（カテゴリ・人物・アーティスト・媒体・支出方法）は、テストの中で Web アプリの API を直接呼んで作り、最後に削除する。
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import re
import secrets
import socket
import threading
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import httpx2
import pytest
import uvicorn
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

from app.config import load_config
from app.main import WebappMcp, build
from app.sites import load_sites
from conftest import TEST_PASSPHRASE, log_text, write_env

pytestmark = pytest.mark.integration

API_KEY = os.environ.get("WEBAPP_TEST_API_KEY", "")
FEATURE_URLS = {
    "schedule": os.environ.get("WEBAPP_TEST_SCHEDULE_URL", "http://127.0.0.1:8002"),
    "goods-management": os.environ.get("WEBAPP_TEST_GOODS_MANAGEMENT_URL", "http://127.0.0.1:8006"),
    "knowhow-management": os.environ.get("WEBAPP_TEST_KNOWHOW_MANAGEMENT_URL", "http://127.0.0.1:8005"),
    "expense-management": os.environ.get("WEBAPP_TEST_EXPENSE_MANAGEMENT_URL", "http://127.0.0.1:8177"),
}
CLAUDE_CALLBACK = "https://claude.ai/api/mcp/auth_callback"

if not API_KEY:
    pytest.skip("WEBAPP_TEST_API_KEY が無いため結合テストをスキップします", allow_module_level=True)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@dataclass
class Running:
    base: str
    built: WebappMcp
    log_dir: Path


@pytest.fixture()
def running(tmp_path: Path, log_dir: Path) -> Iterator[Running]:
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    sites = "\n".join(
        ['default_site = "dev"', "", "[sites.dev]", 'title = "開発環境"', 'kind = "claude_webapp"', "", "[sites.dev.api]"]
        + [f'{feature} = "{url}"' for feature, url in FEATURE_URLS.items()]
        + ["", "[sites.broken]", 'title = "誤ったキー"', 'kind = "claude_webapp"', "", "[sites.broken.api]"]
        + [f'schedule = "{FEATURE_URLS["schedule"]}"']
    )
    (tmp_path / "sites.toml").write_text(sites + "\n", encoding="utf-8")
    cfg = load_config(
        write_env(
            tmp_path,
            MCP_PUBLIC_URL=base,
            SITE_DEV_API_KEY=API_KEY,
            SITE_BROKEN_API_KEY="wak_" + secrets.token_urlsafe(32),
            SITE_HOME_API_KEY=None,  # type: ignore[arg-type]
            SITE_OFFICE_API_KEY=None,  # type: ignore[arg-type]
        )
    )
    built = build(cfg, load_sites(cfg))
    server = uvicorn.Server(uvicorn.Config(built.app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 15
    while not server.started:
        if time.time() > deadline:
            raise RuntimeError("MCP サーバが起動しませんでした")
        time.sleep(0.05)
    yield Running(base, built, log_dir)
    server.should_exit = True
    thread.join(timeout=10)
    built.store.close()


def oauth_tokens(base: str) -> tuple[str, dict[str, Any]]:
    """登録 → 認可 → サインイン → トークン。クライアント ID とトークンを返す。"""
    with httpx.Client(base_url=base, follow_redirects=False, timeout=10) as http:
        assert http.post("/mcp", json={}).status_code == 401
        prm = http.get("/.well-known/oauth-protected-resource/mcp").json()
        assert prm["authorization_servers"] == [base]
        client = http.post(
            "/register",
            json={
                "client_name": "結合テスト",
                "redirect_uris": [CLAUDE_CALLBACK],
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "token_endpoint_auth_method": "none",
            },
        ).json()
        verifier = secrets.token_urlsafe(48)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        location = http.get(
            "/authorize",
            params={
                "response_type": "code",
                "client_id": client["client_id"],
                "redirect_uri": CLAUDE_CALLBACK,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "state": "it",
                "resource": f"{base}/mcp",
            },
        ).headers["location"]
        request_id = parse_qs(urlsplit(location).query)["request"][0]
        page = http.get("/signin", params={"request": request_id}).text
        csrf = re.search(r'name="csrf" value="([^"]+)"', page).group(1)  # type: ignore[union-attr]
        signed = http.post(
            "/signin", data={"request": request_id, "csrf": csrf, "passphrase": TEST_PASSPHRASE, "action": "allow"}
        )
        code = parse_qs(urlsplit(signed.headers["location"]).query)["code"][0]
        tokens = http.post(
            "/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": CLAUDE_CALLBACK,
                "client_id": client["client_id"],
                "code_verifier": verifier,
                "resource": f"{base}/mcp",
            },
        ).json()
        return client["client_id"], tokens


class McpCaller:
    def __init__(self, session: ClientSession):
        self.session = session

    async def ok(self, name: str, args: dict[str, Any] | None = None) -> Any:
        result = await self.session.call_tool(name, args or {})
        assert not result.is_error, f"{name}: {result.content}"
        return result.structured_content

    async def error(self, name: str, args: dict[str, Any] | None = None) -> str:
        result = await self.session.call_tool(name, args or {})
        assert result.is_error, name
        return result.content[0].text  # type: ignore[union-attr]


async def with_session(base: str, access_token: str, body: Any) -> None:
    async with httpx2.AsyncClient(headers={"Authorization": f"Bearer {access_token}"}, timeout=30) as http:
        async with streamable_http_client(f"{base}/mcp", http_client=http) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()
                await body(McpCaller(session))


class Seed:
    """準備データを Web アプリの API で直接作り、最後に消す。"""

    def __init__(self) -> None:
        self.http = httpx.Client(headers={"Authorization": f"Bearer {API_KEY}"}, timeout=10)
        self.created: list[str] = []
        self.suffix = uuid.uuid4().hex[:8]

    def post(self, feature: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
        res = self.http.post(f"{FEATURE_URLS[feature]}{path}", json=body)
        assert res.status_code == 201, f"{path}: {res.status_code} {res.text}"
        data = res.json()
        self.created.append(f"{FEATURE_URLS[feature]}{path}/{data['id']}")
        return data

    def cleanup(self) -> None:
        for url in reversed(self.created):
            self.http.delete(url)
        self.http.close()


def test_oauth_then_tools_against_webapp(running: Running) -> None:
    client_id, tokens = oauth_tokens(running.base)

    # リフレッシュのローテーション
    with httpx.Client(base_url=running.base, timeout=10) as http:
        data = {"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"], "client_id": client_id}
        rotated = http.post("/token", data=data)
        assert rotated.status_code == 200
        assert http.post("/token", data=data).json()["error"] == "invalid_grant"
    access = rotated.json()["access_token"]

    seed = Seed()
    try:
        category = seed.post("schedule", "/categories", {"name": f"結合テスト{seed.suffix}", "color": "#4DA3FF"})
        person = seed.post("goods-management", "/persons", {"name": f"人物{seed.suffix}"})
        artist = seed.post("goods-management", "/artists", {"name": f"アーティスト{seed.suffix}", "person_ids": [person["id"]]})
        media = seed.post("goods-management", "/media", {"name": f"媒体{seed.suffix}"})
        method = seed.post(
            "expense-management",
            "/payment-methods",
            {
                "name": f"カード{seed.suffix}",
                "closing_day": 15,
                "closing_day_shift_direction": "earlier",
                "closing_day_exclusions": [],
                "payment_month_offset": 1,
                "payment_day": 10,
                "payment_day_shift_direction": "later",
                "payment_day_exclusions": [],
                "display_order": 99,
            },
        )

        async def scenario(mcp: McpCaller) -> None:
            sites = await mcp.ok("list_sites")
            assert sites["default_site"] == "dev"

            # スケジュール
            created = await mcp.ok(
                "schedule_create_schedule",
                {"title": "結合テスト", "kind": "todo", "granularity": "day", "start_date": "2026-10-01",
                 "end_date": "2026-10-01", "category_id": category["id"]},
            )
            listed = await mcp.ok("schedule_list_schedules", {"start_date": "2026-10-01", "end_date": "2026-10-01"})
            assert any(item["id"] == created["id"] for item in listed["items"])
            updated = await mcp.ok(
                "schedule_update_schedule",
                {"schedule_id": created["id"], "title": "結合テスト（更新）", "kind": "todo", "granularity": "time",
                 "start_date": "2026-10-01", "end_date": "2026-10-01", "start_time": "09:00", "end_time": "10:00",
                 "category_id": category["id"], "needs_notification": False, "location": None, "detail": None},
            )
            assert updated["start_time"] == "09:00"
            assert (await mcp.ok("schedule_set_todo_completion", {"schedule_id": created["id"], "is_completed": True}))["is_completed"] is True
            assert await mcp.ok("schedule_delete_schedule", {"schedule_id": created["id"]}) == {"deleted": True, "id": created["id"]}
            assert "対象が見つかりません" in await mcp.error("schedule_delete_schedule", {"schedule_id": created["id"]})

            # グッズ
            goods = await mcp.ok("goods_create_goods", {"media_id": media["id"], "artist_id": artist["id"], "title": "結合テストのグッズ"})
            listed = await mcp.ok("goods_list_goods", {"person_id": person["id"]})
            assert [item["goods_id"] for item in listed["items"]] == [goods["id"]]
            detail = await mcp.ok("goods_get_goods", {"goods_id": goods["id"]})
            await mcp.ok(
                "goods_update_goods",
                {**{k: detail[k] for k in ("media_id", "artist_id", "title", "release_date", "memo", "code_number")},
                 "goods_id": goods["id"], "is_owned": True},
            )
            assert (await mcp.ok("goods_get_goods", {"goods_id": goods["id"]}))["is_owned"] is True
            await mcp.ok("goods_delete_goods", {"goods_id": goods["id"]})

            # ノウハウ
            word = f"結合{seed.suffix}"
            knowhow = await mcp.ok("knowhow_create_knowhow", {"title": word, "content": "本文"})
            found = await mcp.ok("knowhow_search_knowhows", {"keywords": [word]})
            assert [item["knowhow_id"] for item in found["items"]] == [knowhow["id"]]
            await mcp.ok(
                "knowhow_update_knowhow",
                {"knowhow_id": knowhow["id"], "title": word, "content": "本文（更新）", "keywords": None, "middle_category_id": None},
            )
            assert (await mcp.ok("knowhow_get_knowhow", {"knowhow_id": knowhow["id"]}))["content"] == "本文（更新）"
            await mcp.ok("knowhow_delete_knowhow", {"knowhow_id": knowhow["id"]})

            # 経費（支払日の省略で登録 → 算出された支払日と自動算出の印）
            expense = await mcp.ok(
                "expense_create_expense",
                {"usage_date": "2026-09-20", "purpose": "結合テスト", "amount": "123.00", "payment_method_id": method["id"]},
            )
            assert expense["payment_date_is_auto"] is True
            assert expense["payment_date"] > "2026-09-20"
            manual = await mcp.ok(
                "expense_update_expense",
                {"expense_id": expense["id"], "usage_date": "2026-09-20", "purpose": "結合テスト", "amount": "123.00",
                 "payment_method_id": method["id"], "budget_period_id": None, "budget_item_id": None, "memo": None,
                 "payment_date": "2026-12-01"},
            )
            assert manual["payment_date"] == "2026-12-01" and manual["payment_date_is_auto"] is False
            listed = await mcp.ok("expense_list_expenses", {"start_date": "2026-09-20", "end_date": "2026-09-20"})
            assert any(item["id"] == expense["id"] for item in listed["items"])
            await mcp.ok("expense_delete_expense", {"expense_id": expense["id"]})

            # 誤った API キーのサイト
            text = await mcp.error("schedule_list_categories", {"site": "broken"})
            assert "サイト broken の API キーが無効です" in text

        asyncio.run(with_session(running.base, access, scenario))
    finally:
        seed.cleanup()

    text = log_text(running.log_dir)
    for secret in (API_KEY, tokens["access_token"], tokens["refresh_token"], access, TEST_PASSPHRASE):
        assert secret not in text
    assert "結合テストのグッズ" not in text and "本文（更新）" not in text
    assert "ツール呼び出し tool=expense_create_expense site=dev" in text
    json.dumps(tokens)  # 形式の確認（JSON であること）
