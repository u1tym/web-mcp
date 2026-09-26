from __future__ import annotations

import base64
import hashlib
import re
import secrets
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from starlette.testclient import TestClient

from app.auth.passphrase import hash_passphrase, verify_passphrase
from app.auth.provider import redirect_uri_allowed
from app.auth.store import AuthStore
from app.config import Config
from app.main import WebappMcp, build
from app.sites import SiteRegistry
from conftest import TEST_PASSPHRASE, log_text

CLAUDE_CALLBACK = "https://claude.ai/api/mcp/auth_callback"
RESOURCE = "http://127.0.0.1:9001/mcp"


@pytest.fixture()
def mcp_app(cfg: Config, registry: SiteRegistry) -> Iterator[WebappMcp]:
    built = build(cfg, registry)
    yield built
    built.store.close()


@pytest.fixture()
def http(mcp_app: WebappMcp) -> Iterator[TestClient]:
    with TestClient(mcp_app.app, base_url="http://127.0.0.1:9001") as client:
        yield client


def _pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    return verifier, challenge


def register(http: TestClient, redirect_uri: str = CLAUDE_CALLBACK) -> dict[str, str]:
    res = http.post(
        "/register",
        json={
            "client_name": "Claude",
            "redirect_uris": [redirect_uri],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def start_authorization(http: TestClient, client: dict[str, str], challenge: str, redirect_uri: str = CLAUDE_CALLBACK) -> str:
    """/authorize を呼び、サインイン画面の request の値を返す。"""
    res = http.get(
        "/authorize",
        params={
            "response_type": "code",
            "client_id": client["client_id"],
            "redirect_uri": redirect_uri,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "st-1",
            "resource": RESOURCE,
            "scope": "webapp",
        },
        follow_redirects=False,
    )
    assert res.status_code == 302, res.text
    location = res.headers["location"]
    assert location.startswith("http://127.0.0.1:9001/signin?request=")
    return parse_qs(urlsplit(location).query)["request"][0]


def open_signin(http: TestClient, request_id: str) -> str:
    res = http.get("/signin", params={"request": request_id})
    assert res.status_code == 200
    return re.search(r'name="csrf" value="([^"]+)"', res.text).group(1)  # type: ignore[union-attr]


def submit(http: TestClient, request_id: str, csrf: str, passphrase: str, action: str = "allow"):
    return http.post(
        "/signin",
        data={"request": request_id, "csrf": csrf, "passphrase": passphrase, "action": action},
        follow_redirects=False,
    )


def obtain_tokens(http: TestClient) -> tuple[dict[str, str], dict[str, str]]:
    client = register(http)
    verifier, challenge = _pkce()
    request_id = start_authorization(http, client, challenge)
    res = submit(http, request_id, open_signin(http, request_id), TEST_PASSPHRASE)
    assert res.status_code == 302
    query = parse_qs(urlsplit(res.headers["location"]).query)
    assert query["state"] == ["st-1"]
    token = http.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "code": query["code"][0],
            "redirect_uri": CLAUDE_CALLBACK,
            "client_id": client["client_id"],
            "code_verifier": verifier,
            "resource": RESOURCE,
        },
    )
    assert token.status_code == 200, token.text
    return client, token.json()


def mcp_initialize(http: TestClient, access_token: str | None, **headers: str):
    base = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    if access_token:
        base["Authorization"] = f"Bearer {access_token}"
    base.update(headers)
    return http.post(
        "/mcp",
        headers=base,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}},
        },
    )


# ---- パスフレーズ・保存 ----


def test_passphrase_hash_roundtrip() -> None:
    stored = hash_passphrase("secret passphrase")
    assert "secret passphrase" not in stored
    assert verify_passphrase("secret passphrase", stored)
    assert not verify_passphrase("wrong", stored)
    assert not verify_passphrase("secret passphrase", "broken")


def test_store_persists_and_holds_only_hashes(tmp_path: Path, cfg: Config) -> None:
    store = AuthStore(tmp_path / "db")
    store.save_tokens("ACCESS-RAW", {"a": 1}, 9999999999, "REFRESH-RAW", {"b": 1}, None, "c1")
    store.close()
    reopened = AuthStore(tmp_path / "db")
    assert reopened.get_access("ACCESS-RAW") is not None
    reopened.close()
    raw = (tmp_path / "db" / "webapp-mcp.sqlite3").read_bytes()
    assert b"ACCESS-RAW" not in raw and b"REFRESH-RAW" not in raw


def test_redirect_allowlist() -> None:
    allow = [CLAUDE_CALLBACK, "http://localhost/callback", "http://127.0.0.1/callback"]
    assert redirect_uri_allowed(CLAUDE_CALLBACK, allow)
    assert redirect_uri_allowed("http://localhost:3118/callback", allow)
    assert redirect_uri_allowed("http://127.0.0.1:50000/callback", allow)
    assert not redirect_uri_allowed("https://claude.ai/api/mcp/auth_callback/x", allow)
    assert not redirect_uri_allowed("https://evil.example.com/callback", allow)
    assert not redirect_uri_allowed("http://localhost:3118/other", allow)
    assert not redirect_uri_allowed("https://localhost/callback", allow)


# ---- OAuth のフロー ----


def test_unauthenticated_mcp_is_401_with_metadata(http: TestClient) -> None:
    res = mcp_initialize(http, None)
    assert res.status_code == 401
    assert 'resource_metadata="http://127.0.0.1:9001/.well-known/oauth-protected-resource/mcp"' in res.headers[
        "www-authenticate"
    ]
    meta = http.get("/.well-known/oauth-authorization-server").json()
    assert meta["code_challenge_methods_supported"] == ["S256"]
    assert meta["registration_endpoint"] == "http://127.0.0.1:9001/register"


def test_register_rejects_unlisted_redirect(http: TestClient, log_dir: Path) -> None:
    res = http.post("/register", json={"client_name": "Evil", "redirect_uris": ["https://evil.example.com/cb"]})
    assert res.status_code == 400
    assert res.json()["error"] == "invalid_redirect_uri"
    assert "クライアント登録拒否 client=Evil" in log_text(log_dir)


def test_full_flow_and_mcp_access(http: TestClient, log_dir: Path) -> None:
    _client, tokens = obtain_tokens(http)
    assert tokens["token_type"] == "Bearer"
    assert tokens["scope"] == "webapp"
    res = mcp_initialize(http, tokens["access_token"])
    assert res.status_code == 200, res.text
    assert mcp_initialize(http, "not-a-token").status_code == 401
    text = log_text(log_dir)
    assert "サインイン成功 client=Claude" in text
    for secret in (tokens["access_token"], tokens["refresh_token"], TEST_PASSPHRASE):
        assert secret not in text


def test_signin_page_shows_client_and_headers(http: TestClient) -> None:
    client = register(http)
    request_id = start_authorization(http, client, _pkce()[1])
    res = http.get("/signin", params={"request": request_id})
    assert "Claude" in res.text and "claude.ai" in res.text
    assert res.headers["x-frame-options"] == "DENY"
    assert "form-action 'self' https://claude.ai" in res.headers["content-security-policy"]
    assert res.headers["cache-control"] == "no-store"
    assert 'name="viewport"' in res.text
    assert "<script" not in res.text


def test_wrong_passphrase_then_lock(http: TestClient, mcp_app: WebappMcp, log_dir: Path) -> None:
    client = register(http)
    request_id = start_authorization(http, client, _pkce()[1])
    csrf = open_signin(http, request_id)
    first = submit(http, request_id, csrf, "wrong")
    assert first.status_code == 400 and "パスフレーズが違います。" in first.text
    csrf = re.search(r'name="csrf" value="([^"]+)"', first.text).group(1)  # type: ignore[union-attr]
    for _ in range(2):  # MCP_SIGNIN_MAX_FAILURES=3
        res = submit(http, request_id, csrf, "wrong")
        csrf = re.search(r'name="csrf" value="([^"]+)"', res.text).group(1)  # type: ignore[union-attr]
    assert "しばらく時間をおいてから" in res.text
    locked = submit(http, request_id, csrf, TEST_PASSPHRASE)
    assert locked.status_code == 400 and "しばらく時間をおいてから" in locked.text
    assert mcp_app.store.get_signin_state().locked_until > 0
    assert "ロック開始" in log_text(log_dir)


def test_csrf_and_expired_request(http: TestClient) -> None:
    client = register(http)
    request_id = start_authorization(http, client, _pkce()[1])
    open_signin(http, request_id)
    bad = submit(http, request_id, "forged", TEST_PASSPHRASE)
    assert bad.status_code == 400 and "要求が正しくありません" in bad.text
    expired = http.get("/signin", params={"request": "unknown"})
    assert expired.status_code == 400 and "期限切れ" in expired.text


def test_deny_redirects_with_access_denied(http: TestClient) -> None:
    client = register(http)
    request_id = start_authorization(http, client, _pkce()[1])
    res = submit(http, request_id, open_signin(http, request_id), "", action="deny")
    assert res.status_code == 302
    query = parse_qs(urlsplit(res.headers["location"]).query)
    assert query["error"] == ["access_denied"] and query["state"] == ["st-1"]


def test_code_is_single_use_and_requires_pkce(http: TestClient) -> None:
    client = register(http)
    verifier, challenge = _pkce()
    request_id = start_authorization(http, client, challenge)
    location = submit(http, request_id, open_signin(http, request_id), TEST_PASSPHRASE).headers["location"]
    code = parse_qs(urlsplit(location).query)["code"][0]
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": CLAUDE_CALLBACK,
        "client_id": client["client_id"],
        "code_verifier": "wrong-verifier-" + "x" * 40,
    }
    assert http.post("/token", data=data).status_code == 400
    data["code_verifier"] = verifier
    assert http.post("/token", data=data).status_code == 200
    again = http.post("/token", data=data)
    assert again.status_code == 400 and again.json()["error"] == "invalid_grant"


def test_refresh_rotation(http: TestClient) -> None:
    client, tokens = obtain_tokens(http)
    data = {"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"], "client_id": client["client_id"]}
    rotated = http.post("/token", data=data)
    assert rotated.status_code == 200
    new = rotated.json()
    assert new["refresh_token"] != tokens["refresh_token"]
    reuse = http.post("/token", data=data)
    assert reuse.status_code == 400 and reuse.json()["error"] == "invalid_grant"
    assert mcp_initialize(http, tokens["access_token"]).status_code == 401  # 古いアクセストークンも失効
    assert mcp_initialize(http, new["access_token"]).status_code == 200


def test_resource_mismatch_is_rejected(http: TestClient) -> None:
    client = register(http)
    res = http.get(
        "/authorize",
        params={
            "response_type": "code",
            "client_id": client["client_id"],
            "redirect_uri": CLAUDE_CALLBACK,
            "code_challenge": _pkce()[1],
            "code_challenge_method": "S256",
            "state": "s",
            "resource": "https://other.example.com/mcp",
        },
        follow_redirects=False,
    )
    assert res.status_code == 302
    assert "error=invalid_target" in res.headers["location"]


def test_revoke_all(http: TestClient, mcp_app: WebappMcp) -> None:
    _client, tokens = obtain_tokens(http)
    counts = mcp_app.store.revoke_all()
    assert counts["oauth_clients"] == 1
    assert mcp_initialize(http, tokens["access_token"]).status_code == 401


def test_disallowed_origin_is_rejected(http: TestClient) -> None:
    _client, tokens = obtain_tokens(http)
    res = mcp_initialize(http, tokens["access_token"], Origin="https://evil.example.com")
    assert res.status_code == 403
