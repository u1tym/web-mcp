"""契約管理（契約と、解約の手順）のツール。

パスワードの値は、入力にも出力にも無い（requirements.md REQ-017、REQ-018）。
登録・更新のツールに、パスワードの引数は無い。Web アプリは、API キーで password を含む要求を拒否するので、
ツールは password を送らない。契約の削除、パスワードの値の取得、アカウント一覧、区分の管理、
解約順の保存のツールは、Web アプリが API キーでは拒否するため、作らない。
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from app.tools import DATE_PATTERN, READ, WRITE, SiteArg, ToolRunner, id_field
from app.webapp_client import ErrorMessages

FEATURE = "contract-management"

# 契約日は、精度に応じて YYYY-MM-DD、YYYY-MM、YYYY
CONTRACT_DATE_PATTERN = r"^\d{4}(-\d{2}(-\d{2})?)?$"

Status = Literal["active", "paused", "cancelled"]
FeeCycle = Literal["yearly", "monthly"]
DatePrecision = Literal["day", "month", "year", "unknown"]
LoginMethod = Literal["password", "passkey", "2fa_mail", "2fa_tel"]

_CONTRACT_ONLY = "契約を伴うときだけ指定できます。"

_NOT_FOUND = "契約が見つかりません。ID を contract_list_contracts で確かめてください（削除済みのものも見つかりません）。"
_UPDATE_CONFLICT = (
    "Web アプリが更新を受け付けませんでした。依存契約の関係が循環している、または、"
    "他の契約の支払方法になっている契約の区分を、金融機関でない区分に変えようとした可能性があります。"
    "（Web アプリ: {detail}）"
)

_PASSWORD_NOTE = (
    "パスワードの値は、指定できません（引数がありません）。人が Web アプリの画面でパスワードを入力・変更します。"
)

_FIELDS_NOTE = (
    "契約を伴わない契約（has_contract が false）は、維持費、更新日、契約日、無料期間の終了日、契約終了日、"
    "自動更新、契約者名義、会員番号・契約番号、解約の受付期限、解約手数料・違約金、最低契約期間、問い合わせ先、"
    "解約方法、依存契約、支払方法を指定できません。支払方法には、金融機関の区分（contract_list_categories の "
    "is_financial が true）の契約だけを指定できます。"
)


def _body(**fields: Any) -> dict[str, Any]:
    """渡された項目だけを、Web アプリの本文の項目名のまま返す（省略したものは送らない）。

    契約を伴うかどうかと、項目の組み合わせの整合は検査せず、Web アプリの 400 に任せる。
    """
    return {key: value for key, value in fields.items() if value is not None}


def register(server: MCPServer, runner: ToolRunner) -> None:
    @server.tool(
        name="contract_list_contracts",
        description=(
            "契約管理の契約の一覧を返します。契約（電気・動画配信・金融口座など）の情報が分かります。"
            "契約を伴わない、ユーザ名とパスワードだけを控えたアカウントも含みます。"
            "キーワード（名称・ホームページ・登録メールアドレス・ユーザ名・メモ）、区分、ステータス、"
            "契約を伴うか伴わないか、パスワードが未設定のものだけ、で絞り込めます"
            "（組み合わせると、すべてに合うものだけを返します）。"
            "パスワードの値は返りません（設定されているかと、未設定かどうかだけが分かります）。"
            "password_unset が true の契約は、人が Web アプリの画面でパスワードを入力するのを待っています。"
            "更新・詳細で使う ID も、ここで確かめます。"
        ),
        annotations=READ,
    )
    async def contract_list_contracts(
        keyword: Annotated[
            str | None,
            Field(description="名称・ホームページ・登録メールアドレス・ユーザ名・メモの部分一致（大文字小文字を区別しない）。パスワードは対象外"),
        ] = None,
        category_id: Annotated[int | None, id_field("区分で絞り込む（contract_list_categories の ID）")] = None,
        status: Annotated[Status | None, Field(description="ステータスで絞り込む。active（有効）、paused（休止中）、cancelled（解約）")] = None,
        has_contract: Annotated[bool | None, Field(description="true で契約を伴うもの、false で契約を伴わないもの")] = None,
        password_unset: Annotated[bool | None, Field(description="true のとき、パスワードが未設定のものだけ。false は絞り込まない")] = None,
        site: SiteArg = None,
    ) -> dict[str, Any]:
        tool = "contract_list_contracts"
        # キーワードの文字列はログに出さない。有無だけを残す
        target = runner.start(
            tool,
            site,
            keyword_given=bool(keyword and keyword.strip()),
            category_id=category_id,
            status=status,
            has_contract=has_contract,
            password_unset=password_unset,
        )
        params = {
            "keyword": keyword,
            "category_id": category_id,
            "status": status,
            "has_contract": has_contract,
            "password_unset": password_unset,
        }
        return await runner.call(tool, target, FEATURE, "GET", "/contracts", params=params)  # type: ignore[arg-type]

    @server.tool(
        name="contract_get_contract",
        description=(
            "契約管理の契約を 1 件、詳細に返します。維持費、更新日、契約日、ログイン方法、2 段階認証の送付先、"
            "ユーザ名、登録メールアドレス、依存契約、支払方法、解約方法、問い合わせ先などが分かります。"
            "この契約に依存している契約と、この契約を支払方法としている契約も分かります。"
            "パスワードの値は返りません。"
        ),
        annotations=READ,
    )
    async def contract_get_contract(
        contract_id: Annotated[int, id_field("取得する契約の ID")],
        site: SiteArg = None,
    ) -> dict[str, Any]:
        tool = "contract_get_contract"
        target = runner.start(tool, site, contract_id=contract_id)
        return await runner.call(
            tool, target, FEATURE, "GET", f"/contracts/{contract_id}", messages=ErrorMessages(not_found=_NOT_FOUND)
        )

    @server.tool(
        name="contract_list_categories",
        description=(
            "契約管理の区分の一覧を返します。区分は、契約の分類です（「その他」は最初から用意されています）。"
            "契約の登録・更新で、区分を指定するために使います。is_financial が true の区分（銀行・カードなど、金融機関）の"
            "契約だけが、他の契約の支払方法に選べます。"
        ),
        annotations=READ,
    )
    async def contract_list_categories(site: SiteArg = None) -> dict[str, Any]:
        tool = "contract_list_categories"
        target = runner.start(tool, site)
        return await runner.call(tool, target, FEATURE, "GET", "/categories")

    @server.tool(
        name="contract_get_cancellation_plan",
        description=(
            "契約管理の解約順（解約する契約を、解約する順に並べたもの）を返します。"
            "各契約の名称、解約方法、依存契約が分かります。ある契約が依存している契約が、その契約より先に"
            "解約される並びになっているときは、warnings に出ます（解約の順序を決めるときの注意に使います）。"
            "解約順の保存は、Web アプリの画面で行います（このツールは取得だけです）。"
            "パスワードなどは返りません。"
        ),
        annotations=READ,
    )
    async def contract_get_cancellation_plan(site: SiteArg = None) -> dict[str, Any]:
        tool = "contract_get_cancellation_plan"
        target = runner.start(tool, site)
        return await runner.call(tool, target, FEATURE, "GET", "/cancellation-plan")

    @server.tool(
        name="contract_create_contract",
        description=(
            "契約管理の契約を 1 件登録します。名称だけが必須です。契約（電気・動画配信など）を伴う場合は、維持費、"
            "更新日、契約日、解約方法などを指定できます。ユーザ名とパスワードだけを控えるアカウントは、"
            "has_contract を false にします。" + _FIELDS_NOTE
            + "区分を省略すると「その他」になります。ステータスの既定は有効（active）です。"
            + _PASSWORD_NOTE + "登録した契約は、パスワード未設定になります。"
        ),
        annotations=WRITE,
    )
    async def contract_create_contract(
        name: Annotated[str, Field(description="名称。前後の空白を除いて、空でなく、200 文字以内")],
        has_contract: Annotated[bool | None, Field(description="契約を伴うか。既定 true。false は契約を伴わない（アカウントの控えだけ）")] = None,
        category_id: Annotated[int | None, id_field("区分。省略すると「その他」（contract_list_categories の ID）")] = None,
        status: Annotated[Status | None, Field(description="ステータス。既定 active（有効）。paused = 休止中、cancelled = 解約")] = None,
        homepage: Annotated[str | None, Field(description="ホームページ")] = None,
        memo: Annotated[str | None, Field(description="メモ")] = None,
        login_methods: Annotated[
            list[LoginMethod] | None,
            Field(description="ログイン方法（重複なし）。password = ユーザ名とパスワード、passkey = パスキー、2fa_mail = 2 段階認証（メール）、2fa_tel = 2 段階認証（TEL）"),
        ] = None,
        twofa_mail_address: Annotated[str | None, Field(description="2 段階認証（メール）の送付先。login_methods に 2fa_mail があるときだけ指定できる")] = None,
        twofa_tel_number: Annotated[str | None, Field(description="2 段階認証（TEL）の送付先。login_methods に 2fa_tel があるときだけ指定できる")] = None,
        username: Annotated[str | None, Field(description="ユーザ名")] = None,
        registered_email: Annotated[str | None, Field(description="登録メールアドレス")] = None,
        fee_amount: Annotated[int | None, Field(ge=0, description="維持費の金額（0 以上）。fee_cycle と一緒に指定する。" + _CONTRACT_ONLY)] = None,
        fee_cycle: Annotated[FeeCycle | None, Field(description="維持費の周期。yearly = 年間、monthly = 月額。fee_amount と一緒に指定する。" + _CONTRACT_ONLY)] = None,
        renewal_date: Annotated[str | None, Field(description="更新日（YYYY-MM-DD）。" + _CONTRACT_ONLY, pattern=DATE_PATTERN)] = None,
        contract_date_precision: Annotated[
            DatePrecision | None,
            Field(description="契約日の精度。day = 年月日、month = 年月、year = 年、unknown = 不明。" + _CONTRACT_ONLY),
        ] = None,
        contract_date: Annotated[
            str | None,
            Field(
                description="契約日。精度が day なら YYYY-MM-DD、month なら YYYY-MM、year なら YYYY。精度が unknown または無いときは指定しない。" + _CONTRACT_ONLY,
                pattern=CONTRACT_DATE_PATTERN,
            ),
        ] = None,
        trial_end_date: Annotated[str | None, Field(description="無料期間の終了日（YYYY-MM-DD）。" + _CONTRACT_ONLY, pattern=DATE_PATTERN)] = None,
        end_date: Annotated[str | None, Field(description="契約終了日（YYYY-MM-DD）。ステータスが cancelled のときだけ。" + _CONTRACT_ONLY, pattern=DATE_PATTERN)] = None,
        auto_renewal: Annotated[bool | None, Field(description="自動更新。true = あり、false = なし。" + _CONTRACT_ONLY)] = None,
        holder_name: Annotated[str | None, Field(description="契約者名義。" + _CONTRACT_ONLY)] = None,
        member_number: Annotated[str | None, Field(description="会員番号・契約番号。" + _CONTRACT_ONLY)] = None,
        cancel_notice_days: Annotated[int | None, Field(ge=0, description="解約の受付期限（更新日の何日前まで。0 以上）。" + _CONTRACT_ONLY)] = None,
        cancellation_fee: Annotated[str | None, Field(description="解約手数料・違約金。" + _CONTRACT_ONLY)] = None,
        min_term_months: Annotated[int | None, Field(ge=0, description="最低契約期間（月数。0 以上）。" + _CONTRACT_ONLY)] = None,
        contact_phone: Annotated[str | None, Field(description="問い合わせ先の電話番号。" + _CONTRACT_ONLY)] = None,
        contact_email: Annotated[str | None, Field(description="問い合わせ先のメールアドレス。" + _CONTRACT_ONLY)] = None,
        contact_hours: Annotated[str | None, Field(description="問い合わせ先の受付時間。" + _CONTRACT_ONLY)] = None,
        cancellation_method: Annotated[str | None, Field(description="解約方法（複数行可）。" + _CONTRACT_ONLY)] = None,
        depends_on_ids: Annotated[
            list[Annotated[int, Field(ge=1)]] | None,
            Field(description="依存契約（その契約が成り立つ前提の契約）の ID（重複なし、自分以外）。" + _CONTRACT_ONLY),
        ] = None,
        payment_contract_id: Annotated[
            int | None,
            Field(ge=1, description="支払方法として選ぶ契約の ID。金融機関の区分の契約だけ。" + _CONTRACT_ONLY),
        ] = None,
        site: SiteArg = None,
    ) -> dict[str, Any]:
        tool = "contract_create_contract"
        # 名称・ユーザ名などの内容はログに出さない
        target = runner.start(tool, site, category_id=category_id, status=status, has_contract=has_contract)
        body = _body(
            name=name,
            has_contract=has_contract,
            category_id=category_id,
            status=status,
            homepage=homepage,
            memo=memo,
            login_methods=login_methods,
            twofa_mail_address=twofa_mail_address,
            twofa_tel_number=twofa_tel_number,
            username=username,
            registered_email=registered_email,
            fee_amount=fee_amount,
            fee_cycle=fee_cycle,
            renewal_date=renewal_date,
            contract_date=contract_date,
            contract_date_precision=contract_date_precision,
            trial_end_date=trial_end_date,
            end_date=end_date,
            auto_renewal=auto_renewal,
            holder_name=holder_name,
            member_number=member_number,
            cancel_notice_days=cancel_notice_days,
            cancellation_fee=cancellation_fee,
            min_term_months=min_term_months,
            contact_phone=contact_phone,
            contact_email=contact_email,
            contact_hours=contact_hours,
            cancellation_method=cancellation_method,
            depends_on_ids=depends_on_ids,
            payment_contract_id=payment_contract_id,
        )
        return await runner.call(tool, target, FEATURE, "POST", "/contracts", json=body)

    @server.tool(
        name="contract_update_contract",
        description=(
            "登録済みの契約管理の契約を更新します。名称以外の項目も、現在の値のまま渡してください。"
            "送らなかった任意の項目は、空に更新されます（null、依存契約は空）。"
            "先に contract_get_contract で現在の値を確かめ、変えない項目も、現在の値のまま渡します"
            "（応答の category.id を category_id に、depends_on の ID を depends_on_ids に、"
            "payment_contract.id を payment_contract_id に渡します）。"
            "契約を伴うか（has_contract）とステータスも、省略すると、has_contract は true、ステータスは active、"
            "区分は「その他」に戻ります。契約を伴うから伴わないに変えると、契約を伴う契約だけの項目は消え、"
            "解約順の対象からも外れます。" + _FIELDS_NOTE
            + _PASSWORD_NOTE + "更新しても、保存済みのパスワードは変わりません（消えも、書き換わりもしません）。"
        ),
        annotations=WRITE,
    )
    async def contract_update_contract(
        contract_id: Annotated[int, id_field("更新する契約の ID")],
        name: Annotated[str, Field(description="名称。前後の空白を除いて、空でなく、200 文字以内")],
        has_contract: Annotated[bool | None, Field(description="契約を伴うか。省略すると true（現在の値のままではない）")] = None,
        category_id: Annotated[int | None, id_field("区分。省略すると「その他」（現在の値のままではない）")] = None,
        status: Annotated[Status | None, Field(description="ステータス。省略すると active（現在の値のままではない）")] = None,
        homepage: Annotated[str | None, Field(description="ホームページ。省略すると空")] = None,
        memo: Annotated[str | None, Field(description="メモ。省略すると空")] = None,
        login_methods: Annotated[
            list[LoginMethod] | None,
            Field(description="ログイン方法（重複なし）。省略すると空。password = ユーザ名とパスワード、passkey = パスキー、2fa_mail = 2 段階認証（メール）、2fa_tel = 2 段階認証（TEL）"),
        ] = None,
        twofa_mail_address: Annotated[str | None, Field(description="2 段階認証（メール）の送付先。login_methods に 2fa_mail があるときだけ指定できる")] = None,
        twofa_tel_number: Annotated[str | None, Field(description="2 段階認証（TEL）の送付先。login_methods に 2fa_tel があるときだけ指定できる")] = None,
        username: Annotated[str | None, Field(description="ユーザ名。省略すると空")] = None,
        registered_email: Annotated[str | None, Field(description="登録メールアドレス。省略すると空")] = None,
        fee_amount: Annotated[int | None, Field(ge=0, description="維持費の金額（0 以上）。fee_cycle と一緒に指定する。" + _CONTRACT_ONLY)] = None,
        fee_cycle: Annotated[FeeCycle | None, Field(description="維持費の周期。yearly = 年間、monthly = 月額。fee_amount と一緒に指定する。" + _CONTRACT_ONLY)] = None,
        renewal_date: Annotated[str | None, Field(description="更新日（YYYY-MM-DD）。" + _CONTRACT_ONLY, pattern=DATE_PATTERN)] = None,
        contract_date_precision: Annotated[
            DatePrecision | None,
            Field(description="契約日の精度。day = 年月日、month = 年月、year = 年、unknown = 不明。" + _CONTRACT_ONLY),
        ] = None,
        contract_date: Annotated[
            str | None,
            Field(
                description="契約日。精度が day なら YYYY-MM-DD、month なら YYYY-MM、year なら YYYY。精度が unknown または無いときは指定しない。" + _CONTRACT_ONLY,
                pattern=CONTRACT_DATE_PATTERN,
            ),
        ] = None,
        trial_end_date: Annotated[str | None, Field(description="無料期間の終了日（YYYY-MM-DD）。" + _CONTRACT_ONLY, pattern=DATE_PATTERN)] = None,
        end_date: Annotated[str | None, Field(description="契約終了日（YYYY-MM-DD）。ステータスが cancelled のときだけ。" + _CONTRACT_ONLY, pattern=DATE_PATTERN)] = None,
        auto_renewal: Annotated[bool | None, Field(description="自動更新。true = あり、false = なし。" + _CONTRACT_ONLY)] = None,
        holder_name: Annotated[str | None, Field(description="契約者名義。" + _CONTRACT_ONLY)] = None,
        member_number: Annotated[str | None, Field(description="会員番号・契約番号。" + _CONTRACT_ONLY)] = None,
        cancel_notice_days: Annotated[int | None, Field(ge=0, description="解約の受付期限（更新日の何日前まで。0 以上）。" + _CONTRACT_ONLY)] = None,
        cancellation_fee: Annotated[str | None, Field(description="解約手数料・違約金。" + _CONTRACT_ONLY)] = None,
        min_term_months: Annotated[int | None, Field(ge=0, description="最低契約期間（月数。0 以上）。" + _CONTRACT_ONLY)] = None,
        contact_phone: Annotated[str | None, Field(description="問い合わせ先の電話番号。" + _CONTRACT_ONLY)] = None,
        contact_email: Annotated[str | None, Field(description="問い合わせ先のメールアドレス。" + _CONTRACT_ONLY)] = None,
        contact_hours: Annotated[str | None, Field(description="問い合わせ先の受付時間。" + _CONTRACT_ONLY)] = None,
        cancellation_method: Annotated[str | None, Field(description="解約方法（複数行可）。" + _CONTRACT_ONLY)] = None,
        depends_on_ids: Annotated[
            list[Annotated[int, Field(ge=1)]] | None,
            Field(description="依存契約（その契約が成り立つ前提の契約）の ID（重複なし、自分以外）。省略すると空。" + _CONTRACT_ONLY),
        ] = None,
        payment_contract_id: Annotated[
            int | None,
            Field(ge=1, description="支払方法として選ぶ契約の ID。金融機関の区分の契約だけ。省略すると空。" + _CONTRACT_ONLY),
        ] = None,
        site: SiteArg = None,
    ) -> dict[str, Any]:
        tool = "contract_update_contract"
        target = runner.start(tool, site, contract_id=contract_id, category_id=category_id, status=status, has_contract=has_contract)
        body = _body(
            name=name,
            has_contract=has_contract,
            category_id=category_id,
            status=status,
            homepage=homepage,
            memo=memo,
            login_methods=login_methods,
            twofa_mail_address=twofa_mail_address,
            twofa_tel_number=twofa_tel_number,
            username=username,
            registered_email=registered_email,
            fee_amount=fee_amount,
            fee_cycle=fee_cycle,
            renewal_date=renewal_date,
            contract_date=contract_date,
            contract_date_precision=contract_date_precision,
            trial_end_date=trial_end_date,
            end_date=end_date,
            auto_renewal=auto_renewal,
            holder_name=holder_name,
            member_number=member_number,
            cancel_notice_days=cancel_notice_days,
            cancellation_fee=cancellation_fee,
            min_term_months=min_term_months,
            contact_phone=contact_phone,
            contact_email=contact_email,
            contact_hours=contact_hours,
            cancellation_method=cancellation_method,
            depends_on_ids=depends_on_ids,
            payment_contract_id=payment_contract_id,
        )
        return await runner.call(
            tool,
            target,
            FEATURE,
            "PATCH",
            f"/contracts/{contract_id}",
            json=body,
            messages=ErrorMessages(not_found=_NOT_FOUND, conflict=_UPDATE_CONFLICT),
        )
