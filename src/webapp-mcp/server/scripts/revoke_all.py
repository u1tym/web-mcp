"""すべてのトークン・保留中の認可・クライアント登録を失効させる（端末の紛失時など）。

使い方: server ディレクトリで `venv/Scripts/python scripts/revoke_all.py --yes`
実行後は、各 MCP クライアントで再接続（サインイン）が必要になる。MCP サーバの再起動は不要。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.auth.store import AuthStore  # noqa: E402
from app.config import ConfigError, load_config  # noqa: E402
from app.logger import setup_logging, write  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="すべての接続を取り消す")
    parser.add_argument("--yes", action="store_true", help="確認なしで実行する")
    args = parser.parse_args()
    if not args.yes:
        answer = input("すべての MCP クライアントの接続を取り消します。よろしいですか？ [y/N]: ")
        if answer.strip().lower() != "y":
            print("中止しました。")
            return 1
    try:
        cfg = load_config()
    except ConfigError as exc:
        print(f"設定を読めません: {exc}", file=sys.stderr)
        return 1
    setup_logging(max_bytes=cfg.log_max_bytes, backup_count=cfg.log_backup_count)
    store = AuthStore(cfg.data_dir)
    counts = store.revoke_all()
    store.close()
    summary = " ".join(f"{table}={count}" for table, count in counts.items())
    write("INF", f"一括失効 {summary}")
    print(f"すべての接続を取り消しました（{summary}）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
