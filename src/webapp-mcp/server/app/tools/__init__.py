"""ツールで共通に使う型・注釈・呼び出しの補助。"""

from __future__ import annotations

from typing import Annotated, Any

from mcp.types import ToolAnnotations
from pydantic import Field

from app.logger import key_prefix, write
from app.sites import Site
from app.webapp_client import ErrorMessages, QueryValue, WebappClient

# ---- 注釈（tool-design.md の R / W / D） ----

READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False)
DELETE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True)

# ---- 引数の型 ----

DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"
TIME_PATTERN = r"^\d{2}:\d{2}$"
YEAR_MONTH_PATTERN = r"^\d{4}-\d{2}$"
AMOUNT_PATTERN = r"^\d+(\.\d{1,2})?$"

SiteArg = Annotated[
    str | None,
    Field(description="接続先のサイトの識別子。省略すると既定のサイト。list_sites で確かめられます。"),
]


def date_field(description: str) -> Any:
    return Field(description=f"{description}（YYYY-MM-DD）", pattern=DATE_PATTERN)


def time_field(description: str) -> Any:
    return Field(description=f"{description}（HH:MM、24 時間）", pattern=TIME_PATTERN)


def id_field(description: str) -> Any:
    return Field(description=description, ge=1)


# ---- 呼び出し ----


class ToolRunner:
    """ツールから Web アプリの API を呼ぶ。サイトの解決・ログ・エラーの変換をまとめる。"""

    def __init__(self, client: WebappClient):
        self.client = client

    def start(self, tool: str, site: str | None, **logged: object) -> Site:
        """ツール呼び出しを記録してサイトを解決する。logged には識別子・日付・件数だけを渡す（本文は渡さない）。"""
        resolved = self.client.resolve_site(site, tool)
        extra = "".join(f" {key}={value}" for key, value in logged.items() if value is not None)
        write("INF", f"ツール呼び出し tool={tool} site={resolved.id} key={key_prefix(resolved.api_key)}{extra}")
        return resolved

    async def call(
        self,
        tool: str,
        site: Site,
        feature: str,
        method: str,
        path: str,
        *,
        params: dict[str, QueryValue | None] | None = None,
        json: dict[str, Any] | None = None,
        messages: ErrorMessages | None = None,
    ) -> Any:
        return await self.client.request(
            tool=tool, site=site, feature=feature, method=method, path=path, params=params, json=json, messages=messages
        )

    @staticmethod
    def deleted(entity_id: int) -> dict[str, Any]:
        return {"deleted": True, "id": entity_id}
