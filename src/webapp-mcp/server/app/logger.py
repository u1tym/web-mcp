from __future__ import annotations

import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Literal

from app.config import SERVER_DIR

Level = Literal["INF", "WRN", "ERR", "DBG"]

LOG_NAME = "webapp-mcp"
LOG_FILE = "webapp-mcp.log"
API_KEY_PREFIX_LENGTH = 12

_logger = logging.getLogger(LOG_NAME)
_logger.setLevel(logging.INFO)
_logger.propagate = False


def safe_text(value: str) -> str:
    return value.replace("\r", " ").replace("\n", " ")


def key_prefix(api_key: str) -> str:
    """ログで API キーを識別するための先頭部分。キー全体は出さない。"""
    return api_key[:API_KEY_PREFIX_LENGTH]


def close_logging() -> None:
    for handler in list(_logger.handlers):
        handler.close()
        _logger.removeHandler(handler)


def setup_logging(log_dir: Path | None = None, max_bytes: int = 1048576, backup_count: int = 5) -> Path:
    directory = log_dir if log_dir is not None else SERVER_DIR / "log"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / LOG_FILE
    close_logging()
    handler = RotatingFileHandler(path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(message)s"))
    _logger.addHandler(handler)
    return path


def write(level: Level, message: str) -> None:
    if not _logger.handlers:
        setup_logging()
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _logger.info("%s %s %s", stamp, level, safe_text(message))
    for handler in _logger.handlers:
        handler.flush()
