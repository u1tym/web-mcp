from __future__ import annotations

from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from app.tools import DELETE, READ, WRITE, SiteArg, ToolRunner, date_field, id_field
from app.webapp_client import ErrorMessages

FEATURE = "goods-management"


def _without_thumbnail_data(body: dict[str, Any]) -> dict[str, Any]:
    """画像のデータ（Base64）は大きく AI の役に立たないため出力から除く（tool-design.md）。"""
    items = [{key: value for key, value in item.items() if key != "thumbnail_image_data"} for item in body.get("items", [])]
    return {**body, "items": items}


def _without_image_data(body: dict[str, Any]) -> dict[str, Any]:
    images = [{key: value for key, value in image.items() if key != "image_data"} for image in body.get("images", [])]
    return {**body, "images": images}


def register(server: MCPServer, runner: ToolRunner) -> None:
    async def _simple_list(tool: str, site: str | None, path: str) -> dict[str, Any]:
        target = runner.start(tool, site)
        return await runner.call(tool, target, FEATURE, "GET", path)

    @server.tool(
        name="goods_list_persons",
        description="人物の一覧を返します。グッズの一覧（goods_list_goods）には人物の指定が必要なので、先にこれで person_id を確かめます。",
        annotations=READ,
    )
    async def goods_list_persons(site: SiteArg = None) -> dict[str, Any]:
        return await _simple_list("goods_list_persons", site, "/persons")

    @server.tool(
        name="goods_list_artists",
        description="アーティストの一覧を返します。グッズの登録・更新で指定する artist_id を確かめます。",
        annotations=READ,
    )
    async def goods_list_artists(site: SiteArg = None) -> dict[str, Any]:
        return await _simple_list("goods_list_artists", site, "/artists")

    @server.tool(
        name="goods_list_media",
        description="媒体の一覧を返します。グッズの登録・更新で指定する media_id を確かめます。",
        annotations=READ,
    )
    async def goods_list_media(site: SiteArg = None) -> dict[str, Any]:
        return await _simple_list("goods_list_media", site, "/media")

    @server.tool(
        name="goods_list_goods",
        description=(
            "人物を起点に、グッズの一覧を返します（発売日の新しい順）。アーティスト・媒体で絞り込めます。"
            "人物・アーティスト・媒体の ID は、それぞれの一覧のツールで確かめます。画像のデータは含みません。"
        ),
        annotations=READ,
    )
    async def goods_list_goods(
        person_id: Annotated[int, id_field("起点の人物の ID")],
        artist_id: Annotated[int | None, Field(description="絞り込むアーティストの ID（その人物に紐づくもの）", ge=1)] = None,
        media_id: Annotated[int | None, Field(description="絞り込む媒体の ID", ge=1)] = None,
        site: SiteArg = None,
    ) -> dict[str, Any]:
        tool = "goods_list_goods"
        target = runner.start(tool, site, person_id=person_id, artist_id=artist_id, media_id=media_id)
        body = await runner.call(
            tool,
            target,
            FEATURE,
            "GET",
            "/goods",
            params={"person_id": person_id, "artist_id": artist_id, "media_id": media_id},
            messages=ErrorMessages(
                not_found="人物・アーティスト・媒体のいずれかが見つからないか、アーティストがその人物に紐づいていません。"
            ),
        )
        return _without_thumbnail_data(body)

    @server.tool(
        name="goods_get_goods",
        description="グッズ 1 件の詳細（メモを含む）を返します。更新の前に現在の値を確かめるのにも使います。画像のデータは含みません。",
        annotations=READ,
    )
    async def goods_get_goods(
        goods_id: Annotated[int, id_field("対象のグッズの ID")],
        site: SiteArg = None,
    ) -> dict[str, Any]:
        tool = "goods_get_goods"
        target = runner.start(tool, site, goods_id=goods_id)
        body = await runner.call(tool, target, FEATURE, "GET", f"/goods/{goods_id}")
        return _without_image_data(body)

    @server.tool(
        name="goods_create_goods",
        description="グッズを 1 件登録します。artist_id・media_id はそれぞれの一覧のツールで確かめます。画像はこのツールでは登録できません。",
        annotations=WRITE,
    )
    async def goods_create_goods(
        media_id: Annotated[int, id_field("媒体の ID")],
        artist_id: Annotated[int, id_field("アーティストの ID")],
        title: Annotated[str, Field(description="タイトル。空不可", min_length=1)],
        release_date: Annotated[str, date_field("発売日。省略すると登録日になる")] | None = None,
        memo: Annotated[str | None, Field(description="メモ")] = None,
        is_owned: Annotated[bool, Field(description="所持済みか")] = False,
        code_number: Annotated[str | None, Field(description="品番")] = None,
        site: SiteArg = None,
    ) -> dict[str, Any]:
        tool = "goods_create_goods"
        target = runner.start(tool, site, media_id=media_id, artist_id=artist_id)
        body = await runner.call(
            tool,
            target,
            FEATURE,
            "POST",
            "/goods",
            json={
                "media_id": media_id,
                "artist_id": artist_id,
                "title": title,
                "release_date": release_date,
                "memo": memo,
                "is_owned": is_owned,
                "code_number": code_number,
            },
            messages=ErrorMessages(not_found="指定した媒体またはアーティストが見つかりません。"),
        )
        return _without_image_data(body)

    @server.tool(
        name="goods_update_goods",
        description=(
            "登録済みのグッズを更新します。すべての項目を送る必要があります。"
            "先に goods_get_goods で現在の値を確かめ、変えない項目も現在の値のまま渡してください"
            "（memo・code_number を null にすると空になります。release_date を null にすると現在の発売日のままになります）。"
            "画像は変わりません。"
        ),
        annotations=WRITE,
    )
    async def goods_update_goods(
        goods_id: Annotated[int, id_field("更新するグッズの ID")],
        media_id: Annotated[int, id_field("媒体の ID")],
        artist_id: Annotated[int, id_field("アーティストの ID")],
        title: Annotated[str, Field(description="タイトル。空不可", min_length=1)],
        release_date: Annotated[str, date_field("発売日。null で現在の値のまま")] | None,
        memo: Annotated[str | None, Field(description="メモ。空にするときは null")],
        is_owned: Annotated[bool, Field(description="所持済みか")],
        code_number: Annotated[str | None, Field(description="品番。空にするときは null")],
        site: SiteArg = None,
    ) -> dict[str, Any]:
        tool = "goods_update_goods"
        target = runner.start(tool, site, goods_id=goods_id, media_id=media_id, artist_id=artist_id)
        body = await runner.call(
            tool,
            target,
            FEATURE,
            "PATCH",
            f"/goods/{goods_id}",
            json={
                "media_id": media_id,
                "artist_id": artist_id,
                "title": title,
                "release_date": release_date,
                "memo": memo,
                "is_owned": is_owned,
                "code_number": code_number,
            },
            messages=ErrorMessages(not_found="グッズ・媒体・アーティストのいずれかが見つかりません。"),
        )
        return _without_image_data(body)

    @server.tool(
        name="goods_delete_goods",
        description="グッズを削除します。この操作は元に戻せません（MCP サーバからは復元できません）。",
        annotations=DELETE,
    )
    async def goods_delete_goods(
        goods_id: Annotated[int, id_field("削除するグッズの ID")],
        site: SiteArg = None,
    ) -> dict[str, Any]:
        tool = "goods_delete_goods"
        target = runner.start(tool, site, goods_id=goods_id)
        await runner.call(tool, target, FEATURE, "DELETE", f"/goods/{goods_id}")
        return ToolRunner.deleted(goods_id)
