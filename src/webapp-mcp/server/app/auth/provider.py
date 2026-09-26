from __future__ import annotations

import secrets
import time
from typing import Any
from urllib.parse import urlsplit

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    AuthorizeError,
    RefreshToken,
    RegistrationError,
    TokenError,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

from app.auth.store import AuthStore, now
from app.config import Config
from app.logger import write

SCOPE = "webapp"
SUBJECT = "owner"  # 利用者は 1 人
PENDING_TTL_SECONDS = 10 * 60
CODE_TTL_SECONDS = 5 * 60
PURGE_INTERVAL_SECONDS = 10 * 60
_LOOPBACK_HOSTS = ("localhost", "127.0.0.1")


def _new_secret() -> str:
    return secrets.token_urlsafe(32)


def redirect_uri_allowed(uri: str, allowlist: list[str]) -> bool:
    """許可リストと完全一致で照合する。ループバック（http の localhost・127.0.0.1）だけポート番号を問わない。"""
    if uri in allowlist:
        return True
    parts = urlsplit(uri)
    if parts.scheme != "http" or parts.hostname not in _LOOPBACK_HOSTS:
        return False
    portless = parts._replace(netloc=parts.hostname).geturl()
    return portless in allowlist


def _normalize_resource(value: str) -> str:
    return value.rstrip("/")


class WebappOAuthProvider:
    """SDK の OAuthAuthorizationServerProvider の実装。利用者 1 人向けの最小限の認可サーバ。"""

    def __init__(self, cfg: Config, store: AuthStore):
        self.cfg = cfg
        self.store = store
        self._last_purge = 0.0

    # ---- 片付け ----

    def purge_if_due(self) -> None:
        current = time.monotonic()
        if current - self._last_purge < PURGE_INTERVAL_SECONDS:
            return
        self._last_purge = current
        removed = self.store.purge_expired()
        if removed:
            write("INF", f"期限切れの認証情報を削除 件数={removed}")

    # ---- クライアント登録 ----

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        info = self.store.get_client(client_id)
        return OAuthClientInformationFull.model_validate_json(info) if info else None

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        self.purge_if_due()
        uris = [str(uri) for uri in (client_info.redirect_uris or [])]
        name = client_info.client_name or "-"
        rejected = [uri for uri in uris if not redirect_uri_allowed(uri, self.cfg.allowed_redirect_uris)]
        if not uris or rejected:
            write("WRN", f"クライアント登録拒否 client={name} redirect_uris={uris} 理由=許可リストに無いリダイレクト URI")
            raise RegistrationError(
                error="invalid_redirect_uri",
                error_description="このリダイレクト URI は許可されていません",
            )
        self.store.save_client(client_info.client_id or "", client_info.client_name, uris, client_info.model_dump_json())
        write("INF", f"クライアント登録 client={name} client_id={client_info.client_id} redirect_uris={uris}")

    # ---- 認可 ----

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        """保留中の認可を保存し、サインイン画面へ誘導する。"""
        self.purge_if_due()
        if params.resource and _normalize_resource(params.resource) != _normalize_resource(self.cfg.resource_url):
            write("WRN", f"認可要求拒否 client_id={client.client_id} 理由=対象違い")
            raise AuthorizeError(error="invalid_target", error_description="このリソースには発行できません")
        scopes = params.scopes or [SCOPE]
        if any(scope != SCOPE for scope in scopes):
            raise AuthorizeError(error="invalid_scope", error_description="要求されたスコープは使えません")
        request_id = _new_secret()
        self.store.save_pending(
            request_id,
            client.client_id or "",
            {
                "state": params.state,
                "scopes": scopes,
                "code_challenge": params.code_challenge,
                "redirect_uri": str(params.redirect_uri),
                "redirect_uri_provided_explicitly": params.redirect_uri_provided_explicitly,
                "client_name": client.client_name,
            },
            now() + PENDING_TTL_SECONDS,
        )
        write("INF", f"認可要求受付 client={client.client_name or '-'} client_id={client.client_id}")
        return f"{self.cfg.public_url}/signin?request={request_id}"

    def complete_authorization(self, client_id: str, pending: dict[str, Any]) -> str:
        """サインインで許可されたとき、認可コードを発行してリダイレクト先の URL を返す。"""
        code = _new_secret()
        expires_at = now() + CODE_TTL_SECONDS
        self.store.save_code(
            code,
            client_id,
            {
                "scopes": pending["scopes"],
                "expires_at": expires_at,
                "client_id": client_id,
                "code_challenge": pending["code_challenge"],
                "redirect_uri": pending["redirect_uri"],
                "redirect_uri_provided_explicitly": pending["redirect_uri_provided_explicitly"],
                "resource": self.cfg.resource_url,
                "subject": SUBJECT,
            },
            expires_at,
        )
        write("INF", f"認可コード発行 client_id={client_id}")
        return construct_redirect_uri(pending["redirect_uri"], code=code, state=pending.get("state"))

    @staticmethod
    def denied_redirect(pending: dict[str, Any]) -> str:
        return construct_redirect_uri(
            pending["redirect_uri"], error="access_denied", error_description="利用者が拒否しました", state=pending.get("state")
        )

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        stored = self.store.get_code(authorization_code)
        if stored is None or stored.client_id != client.client_id:
            return None
        return AuthorizationCode(code=authorization_code, **stored.data)

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        if not self.store.consume_code(authorization_code.code):
            write("WRN", f"認可コード交換失敗 client_id={client.client_id} 理由=使用済み")
            raise TokenError(error="invalid_grant", error_description="認可コードは使用済みです")
        token = self._issue(client.client_id or "", authorization_code.scopes)
        write("INF", f"トークン発行 client_id={client.client_id} 種類=認可コード")
        return token

    # ---- トークン ----

    def _issue(self, client_id: str, scopes: list[str]) -> OAuthToken:
        access = _new_secret()
        refresh = _new_secret()
        access_ttl = self.cfg.access_token_ttl_minutes * 60
        access_expires = now() + access_ttl
        refresh_expires = now() + self.cfg.refresh_token_ttl_days * 86400 if self.cfg.refresh_token_ttl_days else None
        common = {"client_id": client_id, "scopes": scopes, "resource": self.cfg.resource_url, "subject": SUBJECT}
        self.store.save_tokens(
            access,
            {**common, "expires_at": access_expires},
            access_expires,
            refresh,
            {**common, "expires_at": refresh_expires},
            refresh_expires,
            client_id,
        )
        return OAuthToken(
            access_token=access,
            token_type="Bearer",
            expires_in=access_ttl,
            refresh_token=refresh,
            scope=" ".join(scopes),
        )

    async def load_refresh_token(self, client: OAuthClientInformationFull, refresh_token: str) -> RefreshToken | None:
        stored = self.store.get_refresh(refresh_token)
        if stored is None or stored.revoked or stored.client_id != client.client_id:
            write("WRN", f"リフレッシュ失敗 client_id={client.client_id} 理由=無効または失効済み")
            return None
        if stored.expires_at is not None and stored.expires_at <= now():
            write("WRN", f"リフレッシュ失敗 client_id={client.client_id} 理由=期限切れ")
            return None
        return RefreshToken(token=refresh_token, **stored.data)

    async def exchange_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: RefreshToken, scopes: list[str]
    ) -> OAuthToken:
        requested = scopes or refresh_token.scopes
        if any(scope not in refresh_token.scopes for scope in requested):
            raise TokenError(error="invalid_scope", error_description="要求されたスコープは使えません")
        # ローテーション: 古いリフレッシュトークンと、それから発行したアクセストークンを失効させる
        self.store.revoke_refresh(refresh_token.token)
        token = self._issue(client.client_id or "", requested)
        write("INF", f"トークン発行 client_id={client.client_id} 種類=リフレッシュ")
        return token

    async def load_access_token(self, token: str) -> AccessToken | None:
        self.purge_if_due()
        stored = self.store.get_access(token)
        if stored is None:
            write("WRN", "MCP クライアント認証失敗 理由=無効")
            return None
        if stored.revoked:
            write("WRN", f"MCP クライアント認証失敗 client_id={stored.client_id} 理由=失効済み")
            return None
        if stored.expires_at is not None and stored.expires_at <= now():
            write("WRN", f"MCP クライアント認証失敗 client_id={stored.client_id} 理由=期限切れ")
            return None
        return AccessToken(token=token, **stored.data)

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        if isinstance(token, AccessToken):
            self.store.revoke_access(token.token)
        else:
            self.store.revoke_refresh(token.token)
        write("INF", f"トークン失効 client_id={token.client_id} 種類={type(token).__name__}")
