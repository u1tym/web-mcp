from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from app.config import Config, ConfigError

SUPPORTED_KINDS = ("claude_webapp",)
FEATURES = ("schedule", "goods-management", "knowhow-management", "expense-management", "room")

_SITE_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class SiteNotFoundError(Exception):
    def __init__(self, site_id: str) -> None:
        super().__init__(site_id)
        self.site_id = site_id


class FeatureNotConfiguredError(Exception):
    def __init__(self, site_id: str, feature: str) -> None:
        super().__init__(f"{site_id}:{feature}")
        self.site_id = site_id
        self.feature = feature


@dataclass(frozen=True)
class Site:
    id: str
    title: str
    kind: str
    api: dict[str, str]
    api_key: str

    def base_url(self, feature: str) -> str:
        url = self.api.get(feature)
        if not url:
            raise FeatureNotConfiguredError(self.id, feature)
        return url.rstrip("/")


@dataclass(frozen=True)
class SiteRegistry:
    default_id: str
    sites: dict[str, Site]

    def resolve(self, site_id: str | None) -> Site:
        key = site_id if site_id else self.default_id
        site = self.sites.get(key)
        if site is None:
            raise SiteNotFoundError(key)
        return site


def api_key_variable(site_id: str) -> str:
    return f"SITE_{site_id.upper().replace('-', '_')}_API_KEY"


def load_sites(cfg: Config, sites_file: Path | None = None) -> SiteRegistry:
    path = sites_file or cfg.sites_file
    if not path.exists():
        raise ConfigError(f"サイトの構成ファイルがありません: {path.name}")
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"サイトの構成ファイルを読めません: {exc}") from None

    raw_sites = data.get("sites")
    if not isinstance(raw_sites, dict) or not raw_sites:
        raise ConfigError("sites.toml にサイトが 1 つもありません")

    sites: dict[str, Site] = {}
    for site_id, body in raw_sites.items():
        if not _SITE_ID.match(site_id):
            raise ConfigError(f"サイトの識別子が不正です: {site_id}（英小文字・数字・ハイフン）")
        if not isinstance(body, dict):
            raise ConfigError(f"サイト {site_id} の設定が不正です")
        kind = body.get("kind")
        if kind not in SUPPORTED_KINDS:
            raise ConfigError(f"サイト {site_id} の種別が不正です: {kind}")
        api = body.get("api") or {}
        if not isinstance(api, dict) or not all(isinstance(v, str) for v in api.values()):
            raise ConfigError(f"サイト {site_id} の api が不正です")
        unknown = set(api) - set(FEATURES)
        if unknown:
            raise ConfigError(f"サイト {site_id} に未知の機能があります: {', '.join(sorted(unknown))}")
        variable = api_key_variable(site_id)
        api_key = (cfg.env.get(variable) or "").strip()
        if not api_key:
            raise ConfigError(f"サイト {site_id} の API キー（{variable}）が .env にありません")
        sites[site_id] = Site(
            id=site_id,
            title=str(body.get("title") or site_id),
            kind=kind,
            api={feature: url for feature, url in api.items() if url.strip()},
            api_key=api_key,
        )

    default_id = data.get("default_site")
    if not isinstance(default_id, str) or default_id not in sites:
        raise ConfigError("sites.toml の default_site が、登録されたサイトを指していません")
    return SiteRegistry(default_id=default_id, sites=sites)
