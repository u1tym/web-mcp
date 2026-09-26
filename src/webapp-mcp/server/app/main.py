"""webapp-mcp の起動口。`uvicorn app.main:app --host 127.0.0.1 --port 9001` で起動する。"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any

import httpx
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette

from app.auth.provider import SCOPE, WebappOAuthProvider
from app.auth.signin import SigninPage
from app.auth.store import AuthStore
from app.config import Config, ConfigError, load_config
from app.logger import setup_logging, write
from app.sites import SiteRegistry, load_sites
from app.tools import ToolRunner
from app.tools import common, expense, goods, knowhow, schedule
from app.webapp_client import WebappClient

INSTRUCTIONS = (
    "Web アプリ（スケジュール・グッズ管理・ノウハウ管理・経費管理）のデータを参照・登録・更新・削除するツールです。"
    "登録・更新で ID を指定するときは、先に一覧のツールで確かめてください。"
    "更新のツールはすべての項目を送る必要があるので、先に取得のツールで現在の値を確かめてください。"
    "接続先が複数あるときは list_sites で確かめ、引数 site で選びます。"
)


@dataclass
class WebappMcp:
    cfg: Config
    registry: SiteRegistry
    store: AuthStore
    provider: WebappOAuthProvider
    client: WebappClient
    server: MCPServer
    app: Starlette


def build(cfg: Config, registry: SiteRegistry, transport: httpx.AsyncBaseTransport | None = None) -> WebappMcp:
    store = AuthStore(cfg.data_dir)
    removed = store.purge_expired()
    provider = WebappOAuthProvider(cfg, store)
    client = WebappClient(registry, cfg.webapp_timeout_seconds, transport=transport)
    runner = ToolRunner(client)

    server = MCPServer(
        name="webapp-mcp",
        title="Web アプリ連携",
        instructions=INSTRUCTIONS,
        auth_server_provider=provider,
        auth=AuthSettings(
            issuer_url=cfg.public_url,
            resource_server_url=cfg.resource_url,
            required_scopes=[SCOPE],
            client_registration_options=ClientRegistrationOptions(
                enabled=True, valid_scopes=[SCOPE], default_scopes=[SCOPE]
            ),
            revocation_options=RevocationOptions(enabled=True),
            validate_token_resource=True,
        ),
    )

    common.register(server, registry)
    schedule.register(server, runner)
    goods.register(server, runner)
    knowhow.register(server, runner)
    expense.register(server, runner)

    signin = SigninPage(cfg, store, provider)
    server.custom_route("/signin", methods=["GET"], include_in_schema=False)(signin.get)
    server.custom_route("/signin", methods=["POST"], include_in_schema=False)(signin.post)

    local_hosts = ["127.0.0.1:*", "localhost:*", "[::1]:*"]
    app = server.streamable_http_app(
        streamable_http_path="/mcp",
        host=cfg.host,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=[cfg.public_host, *local_hosts],
            allowed_origins=list(dict.fromkeys([cfg.public_origin, *cfg.allowed_origins])),
        ),
    )
    write(
        "INF",
        f"起動 public_url={cfg.public_url} サイト数={len(registry.sites)} 既定のサイト={registry.default_id} "
        f"期限切れの認証情報の削除={removed}",
    )
    return WebappMcp(cfg, registry, store, provider, client, server, app)


def create_app() -> Starlette:
    """設定を読み、起動時の確認を行ってアプリを作る。確認に失敗したら終了する。"""
    try:
        cfg = load_config()
        setup_logging(max_bytes=cfg.log_max_bytes, backup_count=cfg.log_backup_count)
        registry = load_sites(cfg)
    except ConfigError as exc:
        write("ERR", f"起動失敗 理由={exc}")
        print(f"webapp-mcp を起動できません: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
    return build(cfg, registry).app


_app: Starlette | None = None


def __getattr__(name: str) -> Any:
    # uvicorn が `app.main:app` を読んだときに初めて組み立てる（テストで import しても設定を読まない）
    global _app
    if name == "app":
        if _app is None:
            _app = create_app()
        return _app
    raise AttributeError(name)
