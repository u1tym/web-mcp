from __future__ import annotations

import hmac
import secrets
from html import escape
from urllib.parse import urlsplit

from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

from app.auth.passphrase import verify_passphrase
from app.auth.provider import WebappOAuthProvider
from app.auth.store import AuthStore, now, token_hash
from app.config import Config
from app.logger import write

MSG_WRONG = "パスフレーズが違います。"
MSG_LOCKED = "しばらく時間をおいてから、もう一度お試しください。"
MSG_EXPIRED = "この要求は期限切れです。もう一度接続し直してください。"
MSG_INVALID = "要求が正しくありません。もう一度接続し直してください。"

_HEADERS = {
    "X-Frame-Options": "DENY",
    "Cache-Control": "no-store",
    "Pragma": "no-cache",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
}

_STYLE = """
:root { --bg:#faf7f2; --surface:#fff; --text:#3a3244; --muted:#8b8496; --border:#e6e0ed; --primary:#6c9bff; --danger:#d1477a; }
* { box-sizing: border-box; }
body { margin:0; min-height:100vh; display:flex; align-items:center; justify-content:center; padding:16px;
       background:var(--bg); color:var(--text); font-family:system-ui,-apple-system,"Segoe UI","Hiragino Sans",sans-serif; font-size:16px; }
main { width:100%; max-width:420px; background:var(--surface); border:1px solid var(--border); border-radius:8px; padding:24px; }
h1 { font-size:20px; margin:0 0 16px; }
dl { margin:0 0 16px; display:grid; grid-template-columns:auto 1fr; gap:8px 16px; }
dt { color:var(--muted); }
dd { margin:0; overflow-wrap:anywhere; font-weight:600; }
label { display:block; margin-bottom:8px; }
input[type=password] { width:100%; height:44px; padding:0 8px; font-size:16px; border:1px solid var(--border); border-radius:8px; }
input[type=password]:focus, button:focus { outline:2px solid var(--primary); outline-offset:2px; }
.actions { display:flex; gap:8px; margin-top:16px; }
button { flex:1; height:44px; font-size:16px; border-radius:8px; cursor:pointer; }
.allow { background:var(--primary); border:1px solid var(--primary); color:var(--text); }
.deny { background:var(--surface); border:1px solid var(--border); color:var(--text); }
.error { color:var(--danger); margin:0 0 16px; }
.note { color:var(--muted); font-size:14px; margin:16px 0 0; }
"""


def _csp(form_target: str | None) -> dict[str, str]:
    """フォーム送信後のリダイレクト先（MCP クライアントの戻り先）も form-action で許可する。"""
    targets = "'self'" + (f" {form_target}" if form_target else "")
    return {
        **_HEADERS,
        "Content-Security-Policy": f"default-src 'none'; style-src 'unsafe-inline'; form-action {targets}; frame-ancestors 'none'",
    }


def _page(body: str, status: int = 200, form_target: str | None = None) -> HTMLResponse:
    html = (
        '<!doctype html><html lang="ja"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>webapp-mcp へのアクセスの許可</title><style>{_STYLE}</style></head>"
        f"<body><main>{body}</main></body></html>"
    )
    return HTMLResponse(html, status_code=status, headers=_csp(form_target))


def _message_page(message: str, status: int) -> HTMLResponse:
    return _page(f'<h1>webapp-mcp へのアクセスの許可</h1><p class="error" role="alert">{escape(message)}</p>', status)


def _form_page(
    request_id: str, csrf: str, client_name: str, redirect_host: str, redirect_origin: str, error: str | None = None
) -> HTMLResponse:
    error_html = f'<p class="error" role="alert">{escape(error)}</p>' if error else ""
    body = f"""
<h1>webapp-mcp へのアクセスの許可</h1>
{error_html}
<dl>
  <dt>クライアント</dt><dd>{escape(client_name)}</dd>
  <dt>戻り先</dt><dd>{escape(redirect_host)}</dd>
</dl>
<form method="post" action="/signin">
  <input type="hidden" name="request" value="{escape(request_id)}">
  <input type="hidden" name="csrf" value="{escape(csrf)}">
  <label for="passphrase">パスフレーズ</label>
  <input id="passphrase" name="passphrase" type="password" autocomplete="current-password" autofocus>
  <div class="actions">
    <button class="deny" type="submit" name="action" value="deny">拒否</button>
    <button class="allow" type="submit" name="action" value="allow">許可</button>
  </div>
</form>
<p class="note">許可すると、このクライアントから Web アプリのデータを参照・登録・更新・削除できるようになります。</p>
"""
    return _page(body, 400 if error else 200, form_target=redirect_origin)


class SigninPage:
    """OAuth のサインイン画面。パスフレーズで利用者を確かめ、認可コードを発行する。"""

    def __init__(self, cfg: Config, store: AuthStore, provider: WebappOAuthProvider):
        self.cfg = cfg
        self.store = store
        self.provider = provider

    def _render_form(self, request_id: str, pending: dict[str, object], error: str | None = None) -> HTMLResponse:
        csrf = secrets.token_urlsafe(32)
        self.store.set_pending_csrf(request_id, csrf)
        client_name = str(pending.get("client_name") or "（名前なし）")
        parts = urlsplit(str(pending["redirect_uri"]))
        return _form_page(request_id, csrf, client_name, parts.netloc, f"{parts.scheme}://{parts.netloc}", error)

    async def get(self, request: Request) -> Response:
        request_id = request.query_params.get("request") or ""
        found = self.store.get_pending(request_id) if request_id else None
        if found is None:
            write("WRN", "サインイン画面 理由=期限切れまたは不明な要求")
            return _message_page(MSG_EXPIRED, 400)
        _client_id, pending, _csrf = found
        return self._render_form(request_id, pending)

    async def post(self, request: Request) -> Response:
        form = await request.form()
        request_id = str(form.get("request") or "")
        csrf = str(form.get("csrf") or "")
        action = str(form.get("action") or "")
        passphrase = str(form.get("passphrase") or "")

        found = self.store.get_pending(request_id) if request_id else None
        if found is None:
            write("WRN", "サインイン失敗 理由=期限切れまたは不明な要求")
            return _message_page(MSG_EXPIRED, 400)
        client_id, pending, csrf_hash = found
        client = str(pending.get("client_name") or "-")
        if not csrf or not csrf_hash or not hmac.compare_digest(token_hash(csrf), csrf_hash):
            write("WRN", f"サインイン失敗 client={client} 理由=CSRF の値が不一致")
            return _message_page(MSG_INVALID, 400)

        if action == "deny":
            self.store.delete_pending(request_id)
            write("INF", f"サインイン拒否 client={client} 理由=利用者が拒否")
            return RedirectResponse(WebappOAuthProvider.denied_redirect(pending), status_code=302, headers=_HEADERS)
        if action != "allow":
            return _message_page(MSG_INVALID, 400)

        state = self.store.get_signin_state()
        if state.locked_until > now():
            write("WRN", f"サインイン失敗 client={client} 理由=ロック中")
            return self._render_form(request_id, pending, MSG_LOCKED)

        if not verify_passphrase(passphrase, self.cfg.passphrase_hash):
            failures = state.failures + 1
            if failures >= self.cfg.signin_max_failures:
                self.store.set_signin_state(0, now() + self.cfg.signin_lock_minutes * 60)
                write("WRN", f"サインイン失敗 client={client} 理由=パスフレーズ不一致 連続失敗={failures} ロック開始")
                return self._render_form(request_id, pending, MSG_LOCKED)
            self.store.set_signin_state(failures, 0)
            write("WRN", f"サインイン失敗 client={client} 理由=パスフレーズ不一致 連続失敗={failures}")
            return self._render_form(request_id, pending, MSG_WRONG)

        self.store.set_signin_state(0, 0)
        self.store.delete_pending(request_id)
        write("INF", f"サインイン成功 client={client} client_id={client_id}")
        return RedirectResponse(self.provider.complete_authorization(client_id, pending), status_code=302, headers=_HEADERS)
