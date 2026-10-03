from __future__ import annotations

from pathlib import Path

import pytest

from app.config import ConfigError, load_config
from app.sites import FeatureNotConfiguredError, SiteNotFoundError, load_sites
from conftest import OTHER_API_KEY, TEST_API_KEY, write_env


def test_loads_config_and_sites(tmp_path: Path) -> None:
    cfg = load_config(write_env(tmp_path))
    assert cfg.public_url == "http://127.0.0.1:9001"
    assert cfg.resource_url == "http://127.0.0.1:9001/mcp"
    assert cfg.allowed_origins == ["http://127.0.0.1:9001"]
    registry = load_sites(cfg)
    assert registry.default_id == "home"
    assert registry.resolve(None).api_key == TEST_API_KEY
    assert registry.resolve("office").api_key == OTHER_API_KEY
    assert registry.resolve("office").base_url("schedule") == "http://office.test/schedule"
    # ROOM の接続先。office には room が無い
    assert registry.resolve(None).base_url("room") == "http://webapp.test/room"
    with pytest.raises(FeatureNotConfiguredError):
        registry.resolve("office").base_url("room")
    # 契約管理の接続先。office には contract-management が無い
    assert registry.resolve(None).base_url("contract-management") == "http://webapp.test/contract"
    with pytest.raises(FeatureNotConfiguredError):
        registry.resolve("office").base_url("contract-management")


def test_unknown_site(tmp_path: Path) -> None:
    registry = load_sites(load_config(write_env(tmp_path)))
    with pytest.raises(SiteNotFoundError):
        registry.resolve("nowhere")


@pytest.mark.parametrize(
    ("overrides", "fragment"),
    [
        ({"MCP_PUBLIC_URL": ""}, "MCP_PUBLIC_URL"),
        ({"MCP_PUBLIC_URL": "http://mcp.example.com"}, "https"),
        ({"MCP_PUBLIC_URL": "https://example.com/mcp/webapp"}, "ルート"),
        ({"MCP_SIGNIN_PASSPHRASE_HASH": ""}, "MCP_SIGNIN_PASSPHRASE_HASH"),
        ({"MCP_ALLOWED_REDIRECT_URIS": ""}, "MCP_ALLOWED_REDIRECT_URIS"),
        ({"MCP_ALLOWED_ORIGINS": "*"}, "*"),
        ({"MCP_ACCESS_TOKEN_TTL_MINUTES": "x"}, "整数"),
    ],
)
def test_invalid_config(tmp_path: Path, overrides: dict[str, str], fragment: str) -> None:
    with pytest.raises(ConfigError) as exc:
        load_config(write_env(tmp_path, **overrides))
    assert fragment in str(exc.value)


def test_missing_api_key_stops_startup(tmp_path: Path) -> None:
    cfg = load_config(write_env(tmp_path, SITE_OFFICE_API_KEY=""))
    with pytest.raises(ConfigError) as exc:
        load_sites(cfg)
    assert "SITE_OFFICE_API_KEY" in str(exc.value)
    assert OTHER_API_KEY not in str(exc.value)


@pytest.mark.parametrize(
    ("sites_toml", "fragment"),
    [
        ('default_site = "none"\n[sites.home]\nkind = "claude_webapp"\n', "default_site"),
        ('default_site = "home"\n[sites.home]\nkind = "other"\n', "種別"),
        ('default_site = "Home"\n[sites.Home]\nkind = "claude_webapp"\n', "識別子"),
        ('default_site = "home"\n[sites.home]\nkind = "claude_webapp"\n[sites.home.api]\nnotes = "http://x"\n', "未知の機能"),
        # 契約管理に似た名前（contract、contracts）は、未知の機能として拒否される
        ('default_site = "home"\n[sites.home]\nkind = "claude_webapp"\n[sites.home.api]\ncontract = "http://x"\n', "未知の機能"),
        # room に似た名前は、未知の機能として拒否される
        ('default_site = "home"\n[sites.home]\nkind = "claude_webapp"\n[sites.home.api]\nrooms = "http://x"\n', "未知の機能"),
    ],
)
def test_invalid_sites(tmp_path: Path, sites_toml: str, fragment: str) -> None:
    (tmp_path / "sites.toml").write_text(sites_toml, encoding="utf-8")
    cfg = load_config(write_env(tmp_path))
    with pytest.raises(ConfigError) as exc:
        load_sites(cfg)
    assert fragment in str(exc.value)
