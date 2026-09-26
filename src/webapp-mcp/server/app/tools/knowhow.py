from __future__ import annotations

from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from app.tools import DELETE, READ, WRITE, SiteArg, ToolRunner, id_field
from app.webapp_client import ErrorMessages

FEATURE = "knowhow-management"


def register(server: MCPServer, runner: ToolRunner) -> None:
    @server.tool(name="knowhow_list_major_categories", description="ノウハウの大項目の一覧を返します。", annotations=READ)
    async def knowhow_list_major_categories(site: SiteArg = None) -> dict[str, Any]:
        tool = "knowhow_list_major_categories"
        target = runner.start(tool, site)
        return await runner.call(tool, target, FEATURE, "GET", "/major-categories")

    @server.tool(
        name="knowhow_list_middle_categories",
        description="指定した大項目に属する中項目の一覧を返します。ノウハウの登録・更新で指定する middle_category_id をここで確かめます。",
        annotations=READ,
    )
    async def knowhow_list_middle_categories(
        major_category_id: Annotated[int, id_field("大項目の ID")],
        site: SiteArg = None,
    ) -> dict[str, Any]:
        tool = "knowhow_list_middle_categories"
        target = runner.start(tool, site, major_category_id=major_category_id)
        return await runner.call(
            tool,
            target,
            FEATURE,
            "GET",
            f"/major-categories/{major_category_id}/middle-categories",
            messages=ErrorMessages(not_found="指定した大項目が見つかりません。"),
        )

    @server.tool(
        name="knowhow_search_knowhows",
        description=(
            "キーワードでノウハウを検索します。すべてのキーワードを含む（タイトル・キーワード・本文のいずれかに部分一致。"
            "大文字小文字は区別しない）ノウハウを返します。本文は含まないので、内容は knowhow_get_knowhow で取得します。"
        ),
        annotations=READ,
    )
    async def knowhow_search_knowhows(
        keywords: Annotated[
            list[Annotated[str, Field(min_length=1)]],
            Field(description="検索キーワード。1 つ以上", min_length=1),
        ],
        site: SiteArg = None,
    ) -> dict[str, Any]:
        tool = "knowhow_search_knowhows"
        target = runner.start(tool, site, keyword_count=len(keywords))
        return await runner.call(tool, target, FEATURE, "GET", "/knowhows/search", params={"keyword": keywords})

    @server.tool(
        name="knowhow_get_knowhow",
        description="ノウハウ 1 件の詳細（タイトル・キーワード・本文・所属する中項目）を返します。",
        annotations=READ,
    )
    async def knowhow_get_knowhow(
        knowhow_id: Annotated[int, id_field("ノウハウの ID")],
        site: SiteArg = None,
    ) -> dict[str, Any]:
        tool = "knowhow_get_knowhow"
        target = runner.start(tool, site, knowhow_id=knowhow_id)
        return await runner.call(tool, target, FEATURE, "GET", f"/knowhows/{knowhow_id}")

    @server.tool(
        name="knowhow_create_knowhow",
        description="ノウハウを 1 件登録します。中項目を指定しないと未分類になります。",
        annotations=WRITE,
    )
    async def knowhow_create_knowhow(
        title: Annotated[str, Field(description="タイトル。空不可", min_length=1)],
        content: Annotated[str, Field(description="本文。空不可", min_length=1)],
        keywords: Annotated[str | None, Field(description="キーワード（自由記述）")] = None,
        middle_category_id: Annotated[int | None, Field(description="所属する中項目の ID。省略・null で未分類", ge=1)] = None,
        site: SiteArg = None,
    ) -> dict[str, Any]:
        tool = "knowhow_create_knowhow"
        target = runner.start(tool, site, middle_category_id=middle_category_id)
        return await runner.call(
            tool,
            target,
            FEATURE,
            "POST",
            "/knowhows",
            json={"title": title, "keywords": keywords, "content": content, "middle_category_id": middle_category_id},
            messages=ErrorMessages(not_found="指定した中項目が見つかりません。"),
        )

    @server.tool(
        name="knowhow_update_knowhow",
        description=(
            "登録済みのノウハウを更新します。すべての項目を送る必要があります。"
            "先に knowhow_get_knowhow で現在の値を確かめ、変えない項目も現在の値のまま渡してください"
            "（keywords を null にすると空に、middle_category_id を null にすると未分類になります）。"
        ),
        annotations=WRITE,
    )
    async def knowhow_update_knowhow(
        knowhow_id: Annotated[int, id_field("更新するノウハウの ID")],
        title: Annotated[str, Field(description="タイトル。空不可", min_length=1)],
        content: Annotated[str, Field(description="本文。空不可", min_length=1)],
        keywords: Annotated[str | None, Field(description="キーワード。空にするときは null")],
        middle_category_id: Annotated[int | None, Field(description="所属する中項目の ID。null で未分類", ge=1)],
        site: SiteArg = None,
    ) -> dict[str, Any]:
        tool = "knowhow_update_knowhow"
        target = runner.start(tool, site, knowhow_id=knowhow_id, middle_category_id=middle_category_id)
        return await runner.call(
            tool,
            target,
            FEATURE,
            "PATCH",
            f"/knowhows/{knowhow_id}",
            json={"title": title, "keywords": keywords, "content": content, "middle_category_id": middle_category_id},
            messages=ErrorMessages(not_found="ノウハウまたは中項目が見つかりません。"),
        )

    @server.tool(
        name="knowhow_delete_knowhow",
        description="ノウハウを削除します。この操作は元に戻せません（MCP サーバからは復元できません）。",
        annotations=DELETE,
    )
    async def knowhow_delete_knowhow(
        knowhow_id: Annotated[int, id_field("削除するノウハウの ID")],
        site: SiteArg = None,
    ) -> dict[str, Any]:
        tool = "knowhow_delete_knowhow"
        target = runner.start(tool, site, knowhow_id=knowhow_id)
        await runner.call(tool, target, FEATURE, "DELETE", f"/knowhows/{knowhow_id}")
        return ToolRunner.deleted(knowhow_id)
