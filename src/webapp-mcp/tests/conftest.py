from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

SERVER_DIR = Path(__file__).resolve().parent.parent / "server"
sys.path.insert(0, str(SERVER_DIR))

from app.auth.passphrase import hash_passphrase  # noqa: E402
from app.config import Config, load_config  # noqa: E402
from app.logger import LOG_FILE, close_logging, setup_logging  # noqa: E402
from app.sites import SiteRegistry, load_sites  # noqa: E402

TEST_PASSPHRASE = "correct horse battery staple"
TEST_API_KEY = "wak_testKEY0123456789abcdefghijklmnopqrstuvwxyzAB"
OTHER_API_KEY = "wak_otherKEY123456789abcdefghijklmnopqrstuvwxyzC"

SITES_TOML = """
default_site = "home"

[sites.home]
title = "自宅"
kind = "claude_webapp"

[sites.home.api]
schedule = "http://webapp.test/schedule"
goods-management = "http://webapp.test/goods"
knowhow-management = "http://webapp.test/knowhow"
expense-management = "http://webapp.test/expense"
room = "http://webapp.test/room"
contract-management = "http://webapp.test/contract"

[sites.office]
title = "事務所"
kind = "claude_webapp"

[sites.office.api]
schedule = "http://office.test/schedule/"
"""


def write_env(tmp_path: Path, **overrides: str) -> Path:
    values = {
        "MCP_PUBLIC_URL": "http://127.0.0.1:9001",
        "MCP_SIGNIN_PASSPHRASE_HASH": hash_passphrase(TEST_PASSPHRASE),
        "MCP_SIGNIN_MAX_FAILURES": "3",
        "MCP_SIGNIN_LOCK_MINUTES": "15",
        "MCP_ACCESS_TOKEN_TTL_MINUTES": "60",
        "MCP_REFRESH_TOKEN_TTL_DAYS": "90",
        "MCP_ALLOWED_REDIRECT_URIS": "https://claude.ai/api/mcp/auth_callback,http://localhost/callback,http://127.0.0.1/callback",
        "MCP_DATA_DIR": str(tmp_path / "data"),
        "MCP_SITES_FILE": str(tmp_path / "sites.toml"),
        "SITE_HOME_API_KEY": TEST_API_KEY,
        "SITE_OFFICE_API_KEY": OTHER_API_KEY,
        "WEBAPP_TIMEOUT_SECONDS": "2",
    }
    values.update(overrides)
    path = tmp_path / ".env"
    path.write_text("".join(f"{key}={value}\n" for key, value in values.items() if value is not None), encoding="utf-8")
    sites = tmp_path / "sites.toml"
    if not sites.exists():
        sites.write_text(SITES_TOML, encoding="utf-8")
    return path


@pytest.fixture()
def cfg(tmp_path: Path) -> Config:
    return load_config(write_env(tmp_path))


@pytest.fixture()
def registry(cfg: Config) -> SiteRegistry:
    return load_sites(cfg)


@pytest.fixture(autouse=True)
def log_dir(tmp_path: Path) -> Iterator[Path]:
    directory = tmp_path / "log"
    setup_logging(log_dir=directory)
    yield directory
    close_logging()


def log_text(directory: Path) -> str:
    path = directory / LOG_FILE
    return path.read_text(encoding="utf-8") if path.exists() else ""
