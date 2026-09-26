"""サインインのパスフレーズのハッシュを作る（.env の MCP_SIGNIN_PASSPHRASE_HASH に書く値）。

使い方: server ディレクトリで `venv/Scripts/python scripts/hash_passphrase.py`
入力したパスフレーズは画面に表示しない。平文はどこにも保存しない。
"""

from __future__ import annotations

import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.auth.passphrase import hash_passphrase  # noqa: E402

MIN_LENGTH = 12


def main() -> int:
    first = getpass.getpass("パスフレーズ: ")
    if len(first) < MIN_LENGTH:
        print(f"パスフレーズは {MIN_LENGTH} 文字以上にしてください。", file=sys.stderr)
        return 1
    second = getpass.getpass("もう一度: ")
    if first != second:
        print("入力が一致しません。", file=sys.stderr)
        return 1
    print(f"MCP_SIGNIN_PASSPHRASE_HASH={hash_passphrase(first)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
