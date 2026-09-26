from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx
from mcp.server.mcpserver.exceptions import ToolError

from app.logger import key_prefix, write
from app.sites import FeatureNotConfiguredError, Site, SiteNotFoundError, SiteRegistry

QueryValue = str | int | bool | list[str]


@dataclass(frozen=True)
class ErrorMessages:
    """ツールごとに差し替えるエラー文（tool-design.md の個別のエラー）。未指定は共通の文を使う。"""

    not_found: str | None = None
    conflict: str | None = None
    extra: dict[int, str] = field(default_factory=dict)


def _common_message(status: int, site_id: str, detail: str | None) -> str:
    if status == 400:
        return f"入力が不正です。引数の形式・必須項目・組み合わせを確認してください。（Web アプリ: {detail or '入力が不正です'}）"
    if status == 401:
        return f"サイト {site_id} の API キーが無効です（失効・期限切れを含む）。MCP サーバの設定で API キーを見直してください。"
    if status == 403:
        return f"サイト {site_id} で、この機能を利用する権限がありません。Web アプリで機能の割り当てを確認してください。"
    if status == 404:
        return "対象が見つかりません。ID を確認してください（削除済みのものも見つかりません）。"
    if status == 409:
        return f"Web アプリが処理を受け付けませんでした。（Web アプリ: {detail or '処理できませんでした'}）"
    return unreachable_message(site_id)


def unreachable_message(site_id: str) -> str:
    return (
        f"サイト {site_id} の Web アプリに接続できないか、処理に失敗しました。"
        "登録・更新・削除の場合は、反映されたかどうかを取得系のツールで確かめてから、必要ならやり直してください。"
    )


def site_not_found_message(site_id: str) -> str:
    return f"サイト {site_id} は登録されていません。list_sites で確かめてください。"


def feature_not_configured_message(site_id: str) -> str:
    return f"サイト {site_id} では、この機能を利用できません（接続先が設定されていません）。"


def _detail(response: httpx.Response) -> str | None:
    try:
        body = response.json()
    except ValueError:
        return None
    detail = body.get("detail") if isinstance(body, dict) else None
    return detail if isinstance(detail, str) else None


def _count(body: Any) -> str:
    if isinstance(body, dict) and isinstance(body.get("items"), list):
        return f" 件数={len(body['items'])}"
    return ""


class WebappClient:
    """Web アプリの API を、サイトの API キーで呼ぶ。自動で再試行しない。"""

    def __init__(self, registry: SiteRegistry, timeout_seconds: float, transport: httpx.AsyncBaseTransport | None = None):
        self.registry = registry
        self._client = httpx.AsyncClient(timeout=timeout_seconds, transport=transport, follow_redirects=False)

    async def aclose(self) -> None:
        await self._client.aclose()

    def resolve_site(self, site_id: str | None, tool: str) -> Site:
        try:
            return self.registry.resolve(site_id)
        except SiteNotFoundError as exc:
            write("WRN", f"ツール失敗 tool={tool} site={exc.site_id} 理由=サイトなし")
            raise ToolError(site_not_found_message(exc.site_id)) from None

    async def request(
        self,
        *,
        tool: str,
        site: Site,
        feature: str,
        method: str,
        path: str,
        params: dict[str, QueryValue | None] | None = None,
        json: dict[str, Any] | None = None,
        messages: ErrorMessages | None = None,
    ) -> Any:
        """呼び出して本文を返す（204 は None）。失敗は ToolError（tool-design.md の文）を送出する。"""
        try:
            base = site.base_url(feature)
        except FeatureNotConfiguredError:
            write("WRN", f"ツール失敗 tool={tool} site={site.id} 理由=機能の接続先なし feature={feature}")
            raise ToolError(feature_not_configured_message(site.id)) from None

        query = {key: value for key, value in (params or {}).items() if value is not None}
        query = {key: (str(value).lower() if isinstance(value, bool) else value) for key, value in query.items()}
        label = f"{method} {path}"
        try:
            response = await self._client.request(
                method,
                f"{base}{path}",
                params=query or None,
                json=json,
                headers={"Authorization": f"Bearer {site.api_key}"},
            )
        except httpx.TimeoutException:
            write("ERR", f"Web アプリ応答 tool={tool} site={site.id} {label} 理由=タイムアウト key={key_prefix(site.api_key)}")
            raise ToolError(unreachable_message(site.id)) from None
        except httpx.HTTPError as exc:
            write("ERR", f"Web アプリ応答 tool={tool} site={site.id} {label} 理由=接続失敗 type={type(exc).__name__}")
            raise ToolError(unreachable_message(site.id)) from None

        status = response.status_code
        if 200 <= status < 300:
            body = None if status == 204 or not response.content else response.json()
            write("INF", f"Web アプリ応答 tool={tool} site={site.id} {label} status={status}{_count(body)}")
            return body

        detail = _detail(response)
        level = "ERR" if status >= 500 else "WRN"
        write(level, f"Web アプリ応答 tool={tool} site={site.id} {label} status={status} 理由={detail or '-'} key={key_prefix(site.api_key)}")
        custom = messages or ErrorMessages()
        if status in custom.extra:
            raise ToolError(custom.extra[status])
        if status == 404 and custom.not_found:
            raise ToolError(custom.not_found)
        if status == 409 and custom.conflict:
            raise ToolError(custom.conflict)
        raise ToolError(_common_message(status, site.id, detail))
