"""結合テスト: 起動した MCP サーバに OAuth で接続し、開発環境の Web アプリに対してツールを呼ぶ。

前提:
- 開発環境の Web アプリの 6 機能のバックエンドが起動していること
  （既定: schedule=8002, goods-management=8006, knowhow-management=8005, expense-management=8177, room=8011,
   contract-management=8012。WEBAPP_TEST_<FEATURE>_URL で変更できる。ROOM のテスト（test_room_tools_against_webapp）は room だけ、
   契約管理のテスト（test_contract_tools_against_webapp）は contract-management だけでよい）
- `api-key-management` の画面で発行した API キーを、環境変数 WEBAPP_TEST_API_KEY で渡すこと
  （キーの持ち主に 6 機能が割り当てられていること）。無いときはこのテストをスキップする。

準備データ（カテゴリ・人物・アーティスト・媒体・支出方法）は、テストの中で Web アプリの API を直接呼んで作り、最後に削除する。

ROOM のテストでは、機器を操作するツール（room_set_device_state、room_run_scene）を呼ばない。
開発環境の ROOM は実機の SwitchBot を操作するため。実機への読み取り（room_get_state）と、
定期実行の管理（無効で登録し、最後に削除する）だけを行う。

契約管理のテストでは、API キーでは契約を削除できないため、名前を固定した結合テスト用の契約を 1 件だけ作り、
以後の実行でも使い回す（実行のたびに増やさない）。このテスト用の契約は、テストのあとも 1 件残る
（Web アプリの画面で削除できる）。
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
    "room": os.environ.get("WEBAPP_TEST_ROOM_URL", "http://127.0.0.1:8011"),
    "contract-management": os.environ.get("WEBAPP_TEST_CONTRACT_MANAGEMENT_URL", "http://127.0.0.1:8012"),
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


ROOM_DEVICES = {"ceiling_light", "indirect_light", "indoor_speaker", "bedside_speaker", "front_door"}


def test_room_tools_against_webapp(running: Running) -> None:
    """ROOM のツール: 状態の参照と、定期実行の管理。機器を操作するツールは呼ばない（実機が動くため）。"""
    _, tokens = oauth_tokens(running.base)
    created: list[int] = []
    http = httpx.Client(base_url=FEATURE_URLS["room"], headers={"Authorization": f"Bearer {API_KEY}"}, timeout=10)

    async def scenario(mcp: McpCaller) -> None:
        # 状態の参照（実機への読み取りだけ）。取得できなかった機器があっても、5 機器が返る
        state = await mcp.ok("room_get_state")
        assert set(state["devices"]) == ROOM_DEVICES
        assert state["fetched_at"].endswith("+09:00")
        assert state["devices"]["ceiling_light"] == {"status": "ok", "state": "off", "implemented": False}
        door = state["devices"]["front_door"]
        assert "battery" in door and door["status"] in {"ok", "error"}

        # 定期実行: 無効・深夜・お出かけ（万一、実行されても全機器を OFF にするだけ）で登録する
        timer = await mcp.ok(
            "room_create_timer", {"condition": "daily", "run_time": "03:07", "scene": "out", "is_enabled": False}
        )
        created.append(timer["id"])
        assert timer["is_enabled"] is False and timer["last_run"] is None and timer["weekdays"] == []
        assert (timer["holiday_mode"], timer["day_shift"]) == ("none", "same")  # 省略時の既定
        assert (timer["scene"], timer["device"], timer["state"]) == ("out", None, None)

        listed = await mcp.ok("room_list_timers")
        assert timer["id"] in [item["id"] for item in listed["schedules"]]

        updated = await mcp.ok(
            "room_update_timer",
            {"schedule_id": timer["id"], "condition": "weekdays", "weekdays": [5, 1], "run_time": "03:08", "scene": "out"},
        )
        assert updated["weekdays"] == [1, 5] and updated["run_time"] == "03:08"
        assert updated["is_enabled"] is False  # 省略した有効／無効は、現在の値のまま
        assert (updated["holiday_mode"], updated["day_shift"]) == ("none", "same")

        # 機器の個別切替・祝日の扱い・実行日の取り方（無効・深夜で登録するので、機器は動かない）
        device_timer = await mcp.ok(
            "room_create_timer",
            {
                "condition": "weekdays",
                "weekdays": [1, 2, 3, 4, 5],
                "holiday_mode": "exclude",
                "day_shift": "before",
                "run_time": "03:09",
                "device": "indirect_light",
                "state": "off",
                "is_enabled": False,
            },
        )
        created.append(device_timer["id"])
        assert device_timer["is_enabled"] is False and device_timer["last_run"] is None
        assert (device_timer["scene"], device_timer["device"], device_timer["state"]) == (None, "indirect_light", "off")
        assert (device_timer["holiday_mode"], device_timer["day_shift"]) == ("exclude", "before")
        assert device_timer["weekdays"] == [1, 2, 3, 4, 5]
        listed = await mcp.ok("room_list_timers")
        item = next(i for i in listed["schedules"] if i["id"] == device_timer["id"])
        assert (item["device"], item["state"], item["scene"]) == ("indirect_light", "off", None)

        # 更新: 祝日の扱いと実行日の取り方を省略すると、既定に戻る。個別切替から一括切替へも変えられる
        changed = await mcp.ok(
            "room_update_timer",
            {"schedule_id": device_timer["id"], "condition": "weekdays", "weekdays": [6, 7], "run_time": "03:10", "scene": "out"},
        )
        assert (changed["holiday_mode"], changed["day_shift"]) == ("none", "same")
        assert (changed["scene"], changed["device"], changed["state"]) == ("out", None, None)
        assert changed["is_enabled"] is False
        assert await mcp.ok("room_delete_timer", {"schedule_id": device_timer["id"]}) == {
            "deleted": True,
            "id": device_timer["id"],
        }
        created.remove(device_timer["id"])

        enabled = await mcp.ok("room_set_timer_enabled", {"schedule_id": timer["id"], "is_enabled": True})
        assert enabled["is_enabled"] is True
        disabled = await mcp.ok("room_set_timer_enabled", {"schedule_id": timer["id"], "is_enabled": False})
        assert disabled["is_enabled"] is False

        assert await mcp.ok("room_delete_timer", {"schedule_id": timer["id"]}) == {"deleted": True, "id": timer["id"]}
        created.remove(timer["id"])
        listed = await mcp.ok("room_list_timers")
        assert timer["id"] not in [item["id"] for item in listed["schedules"]]
        for tool, args in (
            ("room_delete_timer", {"schedule_id": timer["id"]}),
            ("room_set_timer_enabled", {"schedule_id": timer["id"], "is_enabled": True}),
        ):
            assert "定期実行が見つかりません" in await mcp.error(tool, args)

        # 入力の検査: 玄関ドアは操作できない（Web アプリを呼ぶ前に弾かれる）。曜日の指定で曜日が無いのは Web アプリが弾く
        await mcp.error("room_set_device_state", {"device": "front_door", "state": "unlocked"})
        await mcp.error("room_create_timer", {"condition": "daily", "run_time": "03:07", "device": "front_door", "state": "on"})
        await mcp.error("room_create_timer", {"condition": "holiday", "run_time": "03:07", "scene": "out"})
        # 実行内容の組み合わせの検査は Web アプリが行う（両方、片方だけ、毎日なのに祝日の扱い）
        for args in (
            {"condition": "daily", "run_time": "03:07", "scene": "out", "device": "indirect_light", "state": "on"},
            {"condition": "daily", "run_time": "03:07", "device": "indirect_light"},
            {"condition": "daily", "run_time": "03:07", "scene": "out", "holiday_mode": "exclude"},
        ):
            assert "入力が不正です" in await mcp.error("room_create_timer", {**args, "is_enabled": False})
        text = await mcp.error("room_create_timer", {"condition": "weekdays", "run_time": "03:07", "scene": "out"})
        assert "入力が不正です" in text

        # ROOM の接続先が無いサイトでは、ROOM のツールだけが使えない
        assert "サイト broken では、この機能を利用できません" in await mcp.error("room_get_state", {"site": "broken"})

    try:
        asyncio.run(with_session(running.base, tokens["access_token"], scenario))
    finally:
        for schedule_id in created:  # 途中で失敗しても、作った定期実行を残さない
            http.delete(f"/schedules/{schedule_id}")
        http.close()

    text = log_text(running.log_dir)
    assert API_KEY not in text and tokens["access_token"] not in text
    assert "ツール呼び出し tool=room_get_state site=dev" in text
    assert "ツール呼び出し tool=room_create_timer site=dev" in text
    # 機器を操作するツールは、Web アプリへの呼び出しまで進んでいない
    assert "tool=room_set_device_state site=dev" not in text
    assert "tool=room_run_scene" not in text
    assert "03:07" not in text and "03:08" not in text and "03:09" not in text  # 定期実行の本文（時刻）は出さない


CONTRACT_TEST_NAME = "webapp-mcp 結合テスト用"
CONTRACT_TEST_USERNAME = "webapp-mcp-integration-user"


def _has_key(value: Any, key: str) -> bool:
    """データのどこかに、名前が key の項目があるか（値の文字列は見ない）。"""
    if isinstance(value, dict):
        return key in value or any(_has_key(v, key) for v in value.values())
    if isinstance(value, list):
        return any(_has_key(v, key) for v in value)
    return False


def _contract_input(contract: dict[str, Any], **changes: Any) -> dict[str, Any]:
    """契約の応答から、更新の引数を作る（変えない項目も、現在の値のまま渡す。パスワードは含めない）。"""
    keys = (
        "name", "has_contract", "status", "homepage", "memo", "login_methods", "twofa_mail_address", "twofa_tel_number",
        "username", "registered_email", "fee_amount", "fee_cycle", "renewal_date", "contract_date", "contract_date_precision",
        "trial_end_date", "end_date", "auto_renewal", "holder_name", "member_number", "cancel_notice_days",
        "cancellation_fee", "min_term_months", "contact_phone", "contact_email", "contact_hours", "cancellation_method",
    )
    args: dict[str, Any] = {key: contract[key] for key in keys if contract[key] is not None and contract[key] != []}
    args["contract_id"] = contract["id"]
    args["category_id"] = contract["category"]["id"]
    if contract["depends_on"]:
        args["depends_on_ids"] = [d["id"] for d in contract["depends_on"]]
    if contract["payment_contract"]:
        args["payment_contract_id"] = contract["payment_contract"]["id"]
    args.update(changes)
    return args


def test_contract_tools_against_webapp(running: Running) -> None:
    """契約管理のツール: 参照・登録・更新。パスワードの値は、入力にも出力にも無い。

    API キーでは契約を削除できないため、名前を固定した結合テスト用の契約を 1 件だけ作り、使い回す。
    """
    _, tokens = oauth_tokens(running.base)

    async def scenario(mcp: McpCaller) -> None:
        # 区分: 「その他」が先頭
        categories = await mcp.ok("contract_list_categories")
        assert categories["items"][0]["name"] == "その他" and categories["items"][0]["is_default"] is True
        assert all({"id", "name", "is_default", "is_financial"} == set(c) for c in categories["items"])

        # 結合テスト用の契約を探す。無ければ、登録する（毎回は作らない）
        found = await mcp.ok("contract_list_contracts", {"keyword": CONTRACT_TEST_NAME})
        existing = [c for c in found["items"] if c["name"] == CONTRACT_TEST_NAME]
        assert len(existing) <= 1, "結合テスト用の契約が複数あります。Web アプリの画面で、余分なものを削除してください"
        if existing:
            contract = existing[0]
        else:
            contract = await mcp.ok(
                "contract_create_contract",
                {
                    "name": CONTRACT_TEST_NAME,
                    "login_methods": ["password"],
                    "username": CONTRACT_TEST_USERNAME,
                    "fee_amount": 100,
                    "fee_cycle": "monthly",
                    "cancellation_method": "結合テスト用。解約の手順は無い",
                },
            )
            # 登録した契約は、パスワード未設定（パスワードの値を指定する手段は無い）
            assert contract["has_password"] is False and contract["password_unset"] is True
        assert not _has_key(contract, "password")
        contract_id = contract["id"]

        # 詳細
        detail = await mcp.ok("contract_get_contract", {"contract_id": contract_id})
        assert detail["id"] == contract_id and detail["name"] == CONTRACT_TEST_NAME
        assert not _has_key(detail, "password")
        assert {"has_password", "password_unset", "depends_on", "payment_contract", "depended_by", "payment_for"} <= set(detail)

        # 更新（全項目を渡す）。メモだけを変える。更新しても、パスワードの設定の有無は変わらない
        memo = "結合テストの実行 B" if detail["memo"] == "結合テストの実行 A" else "結合テストの実行 A"
        updated = await mcp.ok("contract_update_contract", _contract_input(detail, memo=memo))
        assert updated["memo"] == memo
        assert updated["has_password"] == detail["has_password"]
        assert updated["password_unset"] == detail["password_unset"]
        assert updated["name"] == detail["name"] and updated["fee_amount"] == detail["fee_amount"]
        assert not _has_key(updated, "password")

        # password を渡しても、保存されない（引数が無い。エラーになるか、無視される）
        result = await mcp.session.call_tool(
            "contract_update_contract", {**_contract_input(updated), "password": "integration-test-secret"}
        )
        again = await mcp.ok("contract_get_contract", {"contract_id": contract_id})
        assert again["has_password"] == detail["has_password"]
        assert "integration-test-secret" not in json.dumps(result.structured_content or result.content, default=str, ensure_ascii=False)

        # 一覧の絞り込み
        listed = await mcp.ok("contract_list_contracts", {"keyword": CONTRACT_TEST_USERNAME})
        assert contract_id in [c["id"] for c in listed["items"]] and listed["total"] == len(listed["items"])
        assert not _has_key(listed, "password")
        by_status = await mcp.ok("contract_list_contracts", {"keyword": CONTRACT_TEST_NAME, "status": "active"})
        assert contract_id in [c["id"] for c in by_status["items"]]
        none_match = await mcp.ok("contract_list_contracts", {"keyword": CONTRACT_TEST_NAME, "has_contract": False})
        assert contract_id not in [c["id"] for c in none_match["items"]]  # 契約を伴う契約なので、含まれない
        unset = await mcp.ok("contract_list_contracts", {"keyword": CONTRACT_TEST_NAME, "password_unset": True})
        assert (contract_id in [c["id"] for c in unset["items"]]) == detail["password_unset"]

        # 実行のたびに、結合テスト用の契約が増えていない
        recount = await mcp.ok("contract_list_contracts", {"keyword": CONTRACT_TEST_NAME})
        assert len([c for c in recount["items"] if c["name"] == CONTRACT_TEST_NAME]) == 1

        # 解約順（取得だけ）
        plan = await mcp.ok("contract_get_cancellation_plan")
        assert set(plan) == {"items", "warnings"}
        assert not _has_key(plan, "password")
        for item in plan["items"]:
            assert set(item) == {"position", "contract_id", "name", "cancellation_method", "depends_on"}

        # 入力の検査: 列挙の誤りは、Web アプリを呼ぶ前に弾かれる。組み合わせの誤りは、Web アプリが弾く
        await mcp.error("contract_create_contract", {"name": "x", "status": "終了"})
        assert "入力が不正です" in await mcp.error(
            "contract_create_contract", {"name": "x", "has_contract": False, "fee_amount": 1, "fee_cycle": "monthly"}
        )
        assert "入力が不正です" in await mcp.error("contract_create_contract", {"name": "x", "fee_amount": 100})
        assert "契約が見つかりません" in await mcp.error("contract_get_contract", {"contract_id": 2147483000})
        assert "契約が見つかりません" in await mcp.error("contract_update_contract", {"contract_id": 2147483000, "name": "x"})
        # 契約管理の接続先が無いサイトでは、契約管理のツールだけが使えない
        assert "サイト broken では、この機能を利用できません" in await mcp.error("contract_list_categories", {"site": "broken"})

    asyncio.run(with_session(running.base, tokens["access_token"], scenario))

    text = log_text(running.log_dir)
    assert API_KEY not in text and tokens["access_token"] not in text
    assert "ツール呼び出し tool=contract_list_contracts site=dev" in text
    assert "ツール呼び出し tool=contract_update_contract site=dev" in text
    # 契約の内容（名称・ユーザ名・メモ・解約方法）と、渡されたパスワードは、ログに出ない
    for secret in (CONTRACT_TEST_NAME, CONTRACT_TEST_USERNAME, "結合テストの実行", "結合テスト用。解約の手順は無い", "integration-test-secret"):
        assert secret not in text, secret
