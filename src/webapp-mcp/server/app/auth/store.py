from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DB_FILE = "webapp-mcp.sqlite3"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS oauth_clients (
    client_id TEXT PRIMARY KEY,
    client_name TEXT,
    redirect_uris TEXT NOT NULL,
    registered_at INTEGER NOT NULL,
    info_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pending_authorizations (
    id_hash TEXT PRIMARY KEY,
    client_id TEXT NOT NULL,
    params_json TEXT NOT NULL,
    csrf_hash TEXT,
    expires_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS authorization_codes (
    code_hash TEXT PRIMARY KEY,
    client_id TEXT NOT NULL,
    data_json TEXT NOT NULL,
    expires_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS access_tokens (
    token_hash TEXT PRIMARY KEY,
    client_id TEXT NOT NULL,
    refresh_hash TEXT,
    data_json TEXT NOT NULL,
    expires_at INTEGER NOT NULL,
    revoked INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS refresh_tokens (
    token_hash TEXT PRIMARY KEY,
    client_id TEXT NOT NULL,
    data_json TEXT NOT NULL,
    expires_at INTEGER,
    revoked INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS signin_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    failures INTEGER NOT NULL DEFAULT 0,
    locked_until INTEGER NOT NULL DEFAULT 0
);
INSERT OR IGNORE INTO signin_state (id, failures, locked_until) VALUES (1, 0, 0);
"""


def token_hash(value: str) -> str:
    """トークン類は SHA-256 のハッシュだけを保存・照合する。"""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def now() -> int:
    return int(time.time())


@dataclass(frozen=True)
class SigninState:
    failures: int
    locked_until: int


@dataclass(frozen=True)
class StoredToken:
    client_id: str
    data: dict[str, Any]
    expires_at: int | None
    revoked: bool
    refresh_hash: str | None = None


class AuthStore:
    """認証の状態（SQLite）。利用者は 1 人なので、1 つの接続をロックで守って使う。"""

    def __init__(self, data_dir: Path):
        data_dir.mkdir(parents=True, exist_ok=True)
        self.path = data_dir / DB_FILE
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _execute(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.execute(sql, params)

    def _one(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(sql, params).fetchone()

    # ---- クライアント ----

    def save_client(self, client_id: str, client_name: str | None, redirect_uris: list[str], info_json: str) -> None:
        self._execute(
            "INSERT OR REPLACE INTO oauth_clients (client_id, client_name, redirect_uris, registered_at, info_json) "
            "VALUES (?, ?, ?, ?, ?)",
            (client_id, client_name, json.dumps(redirect_uris), now(), info_json),
        )

    def get_client(self, client_id: str) -> str | None:
        row = self._one("SELECT info_json FROM oauth_clients WHERE client_id = ?", (client_id,))
        return str(row["info_json"]) if row else None

    # ---- 保留中の認可 ----

    def save_pending(self, request_id: str, client_id: str, params: dict[str, Any], expires_at: int) -> None:
        self._execute(
            "INSERT INTO pending_authorizations (id_hash, client_id, params_json, expires_at) VALUES (?, ?, ?, ?)",
            (token_hash(request_id), client_id, json.dumps(params), expires_at),
        )

    def get_pending(self, request_id: str) -> tuple[str, dict[str, Any], str | None] | None:
        """期限内の保留中の認可（クライアント ID、要求の内容、CSRF の値のハッシュ）。"""
        row = self._one(
            "SELECT client_id, params_json, csrf_hash FROM pending_authorizations WHERE id_hash = ? AND expires_at > ?",
            (token_hash(request_id), now()),
        )
        if row is None:
            return None
        return str(row["client_id"]), json.loads(row["params_json"]), row["csrf_hash"]

    def set_pending_csrf(self, request_id: str, csrf: str) -> None:
        self._execute(
            "UPDATE pending_authorizations SET csrf_hash = ? WHERE id_hash = ?",
            (token_hash(csrf), token_hash(request_id)),
        )

    def delete_pending(self, request_id: str) -> None:
        self._execute("DELETE FROM pending_authorizations WHERE id_hash = ?", (token_hash(request_id),))

    # ---- 認可コード ----

    def save_code(self, code: str, client_id: str, data: dict[str, Any], expires_at: int) -> None:
        self._execute(
            "INSERT INTO authorization_codes (code_hash, client_id, data_json, expires_at) VALUES (?, ?, ?, ?)",
            (token_hash(code), client_id, json.dumps(data), expires_at),
        )

    def get_code(self, code: str) -> StoredToken | None:
        row = self._one(
            "SELECT client_id, data_json, expires_at FROM authorization_codes WHERE code_hash = ?", (token_hash(code),)
        )
        if row is None:
            return None
        return StoredToken(str(row["client_id"]), json.loads(row["data_json"]), int(row["expires_at"]), False)

    def consume_code(self, code: str) -> bool:
        """認可コードを削除する（1 回限り）。既に無ければ False。"""
        return self._execute("DELETE FROM authorization_codes WHERE code_hash = ?", (token_hash(code),)).rowcount == 1

    # ---- アクセストークン・リフレッシュトークン ----

    def save_tokens(
        self,
        access_token: str,
        access_data: dict[str, Any],
        access_expires_at: int,
        refresh_token: str,
        refresh_data: dict[str, Any],
        refresh_expires_at: int | None,
        client_id: str,
    ) -> None:
        with self._lock:
            self._conn.execute("BEGIN")
            try:
                self._conn.execute(
                    "INSERT INTO refresh_tokens (token_hash, client_id, data_json, expires_at) VALUES (?, ?, ?, ?)",
                    (token_hash(refresh_token), client_id, json.dumps(refresh_data), refresh_expires_at),
                )
                self._conn.execute(
                    "INSERT INTO access_tokens (token_hash, client_id, refresh_hash, data_json, expires_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (token_hash(access_token), client_id, token_hash(refresh_token), json.dumps(access_data), access_expires_at),
                )
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

    def get_access(self, access_token: str) -> StoredToken | None:
        row = self._one(
            "SELECT client_id, data_json, expires_at, revoked, refresh_hash FROM access_tokens WHERE token_hash = ?",
            (token_hash(access_token),),
        )
        if row is None:
            return None
        return StoredToken(
            str(row["client_id"]), json.loads(row["data_json"]), int(row["expires_at"]), bool(row["revoked"]), row["refresh_hash"]
        )

    def get_refresh(self, refresh_token: str) -> StoredToken | None:
        row = self._one(
            "SELECT client_id, data_json, expires_at, revoked FROM refresh_tokens WHERE token_hash = ?",
            (token_hash(refresh_token),),
        )
        if row is None:
            return None
        expires = row["expires_at"]
        return StoredToken(str(row["client_id"]), json.loads(row["data_json"]), int(expires) if expires is not None else None, bool(row["revoked"]))

    def revoke_by_refresh_hash(self, refresh_hash: str) -> None:
        """リフレッシュトークンと、それから発行したアクセストークンを失効させる。"""
        with self._lock:
            self._conn.execute("UPDATE refresh_tokens SET revoked = 1 WHERE token_hash = ?", (refresh_hash,))
            self._conn.execute("UPDATE access_tokens SET revoked = 1 WHERE refresh_hash = ?", (refresh_hash,))

    def revoke_refresh(self, refresh_token: str) -> None:
        self.revoke_by_refresh_hash(token_hash(refresh_token))

    def revoke_access(self, access_token: str) -> None:
        stored = self.get_access(access_token)
        self._execute("UPDATE access_tokens SET revoked = 1 WHERE token_hash = ?", (token_hash(access_token),))
        if stored and stored.refresh_hash:
            self.revoke_by_refresh_hash(stored.refresh_hash)

    # ---- サインインの失敗回数 ----

    def get_signin_state(self) -> SigninState:
        row = self._one("SELECT failures, locked_until FROM signin_state WHERE id = 1")
        assert row is not None
        return SigninState(int(row["failures"]), int(row["locked_until"]))

    def set_signin_state(self, failures: int, locked_until: int) -> None:
        self._execute("UPDATE signin_state SET failures = ?, locked_until = ? WHERE id = 1", (failures, locked_until))

    # ---- 片付け・一括失効 ----

    def purge_expired(self) -> int:
        current = now()
        with self._lock:
            total = 0
            total += self._conn.execute("DELETE FROM pending_authorizations WHERE expires_at <= ?", (current,)).rowcount
            total += self._conn.execute("DELETE FROM authorization_codes WHERE expires_at <= ?", (current,)).rowcount
            total += self._conn.execute(
                "DELETE FROM access_tokens WHERE expires_at <= ? OR revoked = 1", (current,)
            ).rowcount
            total += self._conn.execute(
                "DELETE FROM refresh_tokens WHERE (expires_at IS NOT NULL AND expires_at <= ?) OR revoked = 1", (current,)
            ).rowcount
            return total

    def revoke_all(self) -> dict[str, int]:
        with self._lock:
            counts = {}
            for table in ("access_tokens", "refresh_tokens", "authorization_codes", "pending_authorizations", "oauth_clients"):
                counts[table] = self._conn.execute(f"DELETE FROM {table}").rowcount
            self._conn.execute("UPDATE signin_state SET failures = 0, locked_until = 0 WHERE id = 1")
            return counts
