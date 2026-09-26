from __future__ import annotations

from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from app.logger import write
from app.sites import Site
from app.tools import (
    AMOUNT_PATTERN,
    DELETE,
    READ,
    WRITE,
    YEAR_MONTH_PATTERN,
    SiteArg,
    ToolRunner,
    date_field,
    id_field,
)
from app.webapp_client import ErrorMessages

FEATURE = "expense-management"

Amount = Annotated[str, Field(description="金額。0 以上、小数点以下 2 桁まで（例: \"980.00\"）", pattern=AMOUNT_PATTERN)]
_PERIOD_NOT_FOUND = ErrorMessages(not_found="指定した予算期間が見つかりません。")


def register(server: MCPServer, runner: ToolRunner) -> None:
    async def _resolve_payment_date(
        tool: str, target: Site, payment_method_id: int, usage_date: str, payment_date: str | None, action: str
    ) -> tuple[str, bool]:
        """支払日と「自動算出か」を決める。省略時は Web アプリの算出 API を呼ぶ。失敗したら登録・更新しない。"""
        if payment_date is not None:
            return payment_date, False
        method_not_found = f"指定した支出方法が見つかりません。expense_list_payment_methods で確かめてください。（{action}していません）"
        try:
            body = await runner.call(
                tool,
                target,
                FEATURE,
                "GET",
                f"/payment-methods/{payment_method_id}/estimated-payment-date",
                params={"usage_date": usage_date},
                messages=ErrorMessages(not_found=method_not_found),
            )
        except ToolError as exc:
            message = str(exc)
            if message == method_not_found:
                raise
            write("WRN", f"ツール失敗 tool={tool} site={target.id} 理由=支払日の算出に失敗")
            raise ToolError(f"支払日を算出できませんでした。（{action}していません）{message}") from None
        computed = body.get("payment_date") if isinstance(body, dict) else None
        if not isinstance(computed, str):
            write("ERR", f"ツール失敗 tool={tool} site={target.id} 理由=支払日の算出結果が不正")
            raise ToolError(f"支払日を算出できませんでした。（{action}していません）")
        return computed, True

    @server.tool(
        name="expense_list_budget_periods",
        description="予算期間の一覧（開始日の新しい順。予算項目の金額合計つき）を返します。",
        annotations=READ,
    )
    async def expense_list_budget_periods(site: SiteArg = None) -> dict[str, Any]:
        tool = "expense_list_budget_periods"
        target = runner.start(tool, site)
        return await runner.call(tool, target, FEATURE, "GET", "/budget-periods")

    @server.tool(
        name="expense_list_budget_items",
        description="指定した予算期間の予算項目の一覧を返します。支出記録を予算に割り当てるときの budget_item_id をここで確かめます。",
        annotations=READ,
    )
    async def expense_list_budget_items(
        budget_period_id: Annotated[int, id_field("予算期間の ID")],
        site: SiteArg = None,
    ) -> dict[str, Any]:
        tool = "expense_list_budget_items"
        target = runner.start(tool, site, budget_period_id=budget_period_id)
        return await runner.call(
            tool, target, FEATURE, "GET", "/budget-items", params={"budget_period_id": budget_period_id}, messages=_PERIOD_NOT_FOUND
        )

    @server.tool(
        name="expense_list_payment_methods",
        description="支出方法（現金・カードなど）の一覧を、締め日・支払日のルールとともに返します。支出記録の登録・更新で指定する payment_method_id をここで確かめます。",
        annotations=READ,
    )
    async def expense_list_payment_methods(site: SiteArg = None) -> dict[str, Any]:
        tool = "expense_list_payment_methods"
        target = runner.start(tool, site)
        return await runner.call(tool, target, FEATURE, "GET", "/payment-methods")

    @server.tool(
        name="expense_list_expenses",
        description=(
            "支出記録の一覧（利用日の新しい順）を返します。絞り込みは次のいずれか 1 つです: "
            "利用日の期間（start_date と end_date）、予算期間（budget_period_id）、予算なしの記録だけ（unassigned=true）。"
        ),
        annotations=READ,
    )
    async def expense_list_expenses(
        start_date: Annotated[str, date_field("利用日の期間の開始日。budget_period_id も unassigned も指定しないとき必須")] | None = None,
        end_date: Annotated[str, date_field("利用日の期間の終了日。同上")] | None = None,
        budget_period_id: Annotated[int | None, Field(description="この予算期間の記録だけを返す", ge=1)] = None,
        unassigned: Annotated[bool, Field(description="true で予算なしの記録だけを返す。budget_period_id と同時には指定できない")] = False,
        site: SiteArg = None,
    ) -> dict[str, Any]:
        tool = "expense_list_expenses"
        target = runner.start(
            tool, site, start_date=start_date, end_date=end_date, budget_period_id=budget_period_id, unassigned=unassigned
        )
        return await runner.call(
            tool,
            target,
            FEATURE,
            "GET",
            "/expenses",
            params={
                "start_date": start_date,
                "end_date": end_date,
                "budget_period_id": budget_period_id,
                "unassigned": True if unassigned else None,
            },
        )

    @server.tool(
        name="expense_get_usage_date_report",
        description="予算期間を指定して、予算項目ごとの予算と実績（利用日が期間内の支出の合計）と差額を返します。",
        annotations=READ,
    )
    async def expense_get_usage_date_report(
        budget_period_id: Annotated[int, id_field("予算期間の ID")],
        site: SiteArg = None,
    ) -> dict[str, Any]:
        tool = "expense_get_usage_date_report"
        target = runner.start(tool, site, budget_period_id=budget_period_id)
        return await runner.call(
            tool,
            target,
            FEATURE,
            "GET",
            "/reports/usage-date",
            params={"budget_period_id": budget_period_id},
            messages=_PERIOD_NOT_FOUND,
        )

    @server.tool(
        name="expense_get_payment_month_report",
        description="年月を指定して、支払日がその月の支出を予算項目ごとに合計して返します（支払発生月基準）。",
        annotations=READ,
    )
    async def expense_get_payment_month_report(
        year_month: Annotated[str, Field(description="年月（YYYY-MM）", pattern=YEAR_MONTH_PATTERN)],
        site: SiteArg = None,
    ) -> dict[str, Any]:
        tool = "expense_get_payment_month_report"
        target = runner.start(tool, site, year_month=year_month)
        return await runner.call(tool, target, FEATURE, "GET", "/reports/payment-month", params={"year_month": year_month})

    @server.tool(
        name="expense_create_expense",
        description=(
            "支出記録を 1 件登録します。payment_method_id は expense_list_payment_methods で確かめます。"
            "予算に割り当てるときは budget_period_id と budget_item_id の両方を指定します（expense_list_budget_items で確かめる）。"
            "どちらも省略すると「予算なし」になります。payment_date（支払日）を省略すると、支出方法と利用日から自動で算出します。"
        ),
        annotations=WRITE,
    )
    async def expense_create_expense(
        usage_date: Annotated[str, date_field("利用日")],
        purpose: Annotated[str, Field(description="用途。空不可", min_length=1)],
        amount: Amount,
        payment_method_id: Annotated[int, id_field("支出方法の ID")],
        budget_period_id: Annotated[int | None, Field(description="予算期間の ID。budget_item_id と組で指定", ge=1)] = None,
        budget_item_id: Annotated[int | None, Field(description="予算項目の ID。budget_period_id の予算項目", ge=1)] = None,
        memo: Annotated[str | None, Field(description="メモ")] = None,
        payment_date: Annotated[str, date_field("支払日。省略すると自動で算出する")] | None = None,
        site: SiteArg = None,
    ) -> dict[str, Any]:
        tool = "expense_create_expense"
        target = runner.start(
            tool,
            site,
            usage_date=usage_date,
            payment_method_id=payment_method_id,
            budget_period_id=budget_period_id,
            budget_item_id=budget_item_id,
            payment_date_given=payment_date is not None,
        )
        resolved_date, is_auto = await _resolve_payment_date(tool, target, payment_method_id, usage_date, payment_date, "登録")
        return await runner.call(
            tool,
            target,
            FEATURE,
            "POST",
            "/expenses",
            json={
                "usage_date": usage_date,
                "budget_period_id": budget_period_id,
                "budget_item_id": budget_item_id,
                "purpose": purpose,
                "amount": amount,
                "payment_method_id": payment_method_id,
                "memo": memo,
                "payment_date": resolved_date,
                "payment_date_is_auto": is_auto,
            },
        )

    @server.tool(
        name="expense_update_expense",
        description=(
            "登録済みの支出記録を更新します。支払日以外のすべての項目を送る必要があります。"
            "先に expense_list_expenses で現在の値を確かめ、変えない項目も現在の値のまま渡してください"
            "（budget_period_id・budget_item_id を null にすると予算なしに、memo を null にすると空になります）。"
            "payment_date を省略すると、支出方法と利用日から支払日を算出し直します。"
        ),
        annotations=WRITE,
    )
    async def expense_update_expense(
        expense_id: Annotated[int, id_field("更新する支出記録の ID")],
        usage_date: Annotated[str, date_field("利用日")],
        purpose: Annotated[str, Field(description="用途。空不可", min_length=1)],
        amount: Amount,
        payment_method_id: Annotated[int, id_field("支出方法の ID")],
        budget_period_id: Annotated[int | None, Field(description="予算期間の ID。予算なしは null", ge=1)],
        budget_item_id: Annotated[int | None, Field(description="予算項目の ID。予算なしは null", ge=1)],
        memo: Annotated[str | None, Field(description="メモ。空にするときは null")],
        payment_date: Annotated[str, date_field("支払日。省略すると算出し直す（自動算出として記録）")] | None = None,
        site: SiteArg = None,
    ) -> dict[str, Any]:
        tool = "expense_update_expense"
        target = runner.start(
            tool,
            site,
            expense_id=expense_id,
            usage_date=usage_date,
            payment_method_id=payment_method_id,
            budget_period_id=budget_period_id,
            budget_item_id=budget_item_id,
            payment_date_given=payment_date is not None,
        )
        resolved_date, is_auto = await _resolve_payment_date(tool, target, payment_method_id, usage_date, payment_date, "更新")
        return await runner.call(
            tool,
            target,
            FEATURE,
            "PATCH",
            f"/expenses/{expense_id}",
            json={
                "usage_date": usage_date,
                "budget_period_id": budget_period_id,
                "budget_item_id": budget_item_id,
                "purpose": purpose,
                "amount": amount,
                "payment_method_id": payment_method_id,
                "memo": memo,
                "payment_date": resolved_date,
                "payment_date_is_auto": is_auto,
            },
            messages=ErrorMessages(not_found="支出記録が見つかりません。ID を確かめてください。"),
        )

    @server.tool(
        name="expense_delete_expense",
        description="支出記録を削除します。この操作は元に戻せません（MCP サーバからは復元できません）。",
        annotations=DELETE,
    )
    async def expense_delete_expense(
        expense_id: Annotated[int, id_field("削除する支出記録の ID")],
        site: SiteArg = None,
    ) -> dict[str, Any]:
        tool = "expense_delete_expense"
        target = runner.start(tool, site, expense_id=expense_id)
        await runner.call(tool, target, FEATURE, "DELETE", f"/expenses/{expense_id}")
        return ToolRunner.deleted(expense_id)
