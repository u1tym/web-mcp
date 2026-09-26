from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values

SERVER_DIR = Path(__file__).resolve().parent.parent

# テストなどで別の設定ファイルを使うときに指定する
ENV_FILE_VARIABLE = "WEBAPP_MCP_ENV_FILE"


class ConfigError(Exception):
    """設定の不備。メッセージに秘密の値を含めない。"""


@dataclass(frozen=True)
class Config:
    host: str
    port: int
    public_url: str
    allowed_origins: list[str]
    passphrase_hash: str
    signin_max_failures: int
    signin_lock_minutes: int
    access_token_ttl_minutes: int
    refresh_token_ttl_days: int
    allowed_redirect_uris: list[str]
    data_dir: Path
    sites_file: Path
    webapp_timeout_seconds: float
    log_max_bytes: int
    log_backup_count: int
    env: dict[str, str]

    @property
    def resource_url(self) -> str:
        """MCP のエンドポイント。OAuth のトークンの対象（リソース）でもある。"""
        return f"{self.public_url}/mcp"

    @property
    def public_host(self) -> str:
        return urlsplit(self.public_url).netloc

    @property
    def public_origin(self) -> str:
        parts = urlsplit(self.public_url)
        return f"{parts.scheme}://{parts.netloc}"


def _split(raw: str | None) -> list[str]:
    return [part.strip() for part in (raw or "").split(",") if part.strip()]


def _int(values: dict[str, str], key: str, default: int, minimum: int) -> int:
    raw = values.get(key) or str(default)
    try:
        value = int(raw)
    except ValueError:
        raise ConfigError(f"{key} は整数で指定してください") from None
    if value < minimum:
        raise ConfigError(f"{key} は {minimum} 以上で指定してください")
    return value


def _resolve(path: str) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else SERVER_DIR / candidate


def env_file_path() -> Path:
    override = os.environ.get(ENV_FILE_VARIABLE)
    return Path(override) if override else SERVER_DIR / ".env"


def load_config(env_file: Path | None = None) -> Config:
    path = env_file or env_file_path()
    if not path.exists():
        raise ConfigError(f"設定ファイルがありません: {path.name}")
    values = {key: value for key, value in dotenv_values(path).items() if value is not None}

    public_url = (values.get("MCP_PUBLIC_URL") or "").strip().rstrip("/")
    if not public_url:
        raise ConfigError("MCP_PUBLIC_URL を指定してください")
    parts = urlsplit(public_url)
    if parts.scheme not in ("http", "https") or not parts.netloc or parts.path not in ("", "/"):
        raise ConfigError("MCP_PUBLIC_URL はホストのルートの URL（例: https://mcp.example.com）で指定してください")
    if parts.scheme == "http" and parts.hostname not in ("localhost", "127.0.0.1", "::1"):
        raise ConfigError("MCP_PUBLIC_URL は https で指定してください（http は localhost だけ）")

    passphrase_hash = (values.get("MCP_SIGNIN_PASSPHRASE_HASH") or "").strip()
    if not passphrase_hash:
        raise ConfigError("MCP_SIGNIN_PASSPHRASE_HASH を指定してください（scripts/hash_passphrase.py で作成）")

    redirect_uris = _split(values.get("MCP_ALLOWED_REDIRECT_URIS"))
    if not redirect_uris:
        raise ConfigError("MCP_ALLOWED_REDIRECT_URIS を指定してください")

    try:
        timeout = float(values.get("WEBAPP_TIMEOUT_SECONDS") or "10")
    except ValueError:
        raise ConfigError("WEBAPP_TIMEOUT_SECONDS は数値で指定してください") from None
    if timeout <= 0:
        raise ConfigError("WEBAPP_TIMEOUT_SECONDS は 0 より大きい値で指定してください")

    public_origin = f"{parts.scheme}://{parts.netloc}"
    allowed_origins = _split(values.get("MCP_ALLOWED_ORIGINS")) or [public_origin]
    if "*" in allowed_origins:
        raise ConfigError("MCP_ALLOWED_ORIGINS に * は使えません")

    return Config(
        host=values.get("MCP_HOST") or "127.0.0.1",
        port=_int(values, "MCP_PORT", 9001, 1),
        public_url=public_url,
        allowed_origins=allowed_origins,
        passphrase_hash=passphrase_hash,
        signin_max_failures=_int(values, "MCP_SIGNIN_MAX_FAILURES", 5, 1),
        signin_lock_minutes=_int(values, "MCP_SIGNIN_LOCK_MINUTES", 15, 1),
        access_token_ttl_minutes=_int(values, "MCP_ACCESS_TOKEN_TTL_MINUTES", 60, 1),
        refresh_token_ttl_days=_int(values, "MCP_REFRESH_TOKEN_TTL_DAYS", 90, 0),
        allowed_redirect_uris=redirect_uris,
        data_dir=_resolve(values.get("MCP_DATA_DIR") or "data"),
        sites_file=_resolve(values.get("MCP_SITES_FILE") or "sites.toml"),
        webapp_timeout_seconds=timeout,
        log_max_bytes=_int(values, "LOG_MAX_BYTES", 1048576, 1024),
        log_backup_count=_int(values, "LOG_BACKUP_COUNT", 5, 1),
        env=values,
    )
