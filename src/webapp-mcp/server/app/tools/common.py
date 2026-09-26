from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer

from app.logger import write
from app.sites import SiteRegistry
from app.tools import READ


def register(server: MCPServer, registry: SiteRegistry) -> None:
    @server.tool(
        name="list_sites",
        description=(
            "接続先として登録されているサイト（Web アプリ）の一覧を返します。"
            "ほかのツールの引数 site に指定できる識別子と、既定のサイトが分かります。"
        ),
        annotations=READ,
    )
    async def list_sites() -> dict[str, Any]:
        write("INF", f"ツール呼び出し tool=list_sites 件数={len(registry.sites)}")
        return {
            "default_site": registry.default_id,
            "sites": [
                {"id": site.id, "title": site.title, "is_default": site.id == registry.default_id}
                for site in registry.sites.values()
            ],
        }
