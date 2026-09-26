from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

# scrypt のパラメータ（ハッシュ文字列に含めて保存するので、後から変えても古いハッシュは照合できる）
_N = 2**15
_R = 8
_P = 1
_DKLEN = 32
_MAXMEM = 64 * 1024 * 1024
_PREFIX = "scrypt"


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def hash_passphrase(passphrase: str) -> str:
    """`scrypt$N$r$p$salt$hash` の形の文字列を返す。平文は含まない。"""
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(passphrase.encode("utf-8"), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN, maxmem=_MAXMEM)
    return f"{_PREFIX}${_N}${_R}${_P}${_b64(salt)}${_b64(digest)}"


def verify_passphrase(passphrase: str, stored: str) -> bool:
    """定数時間で比較する。形式が不正なハッシュは常に不一致。"""
    try:
        prefix, n, r, p, salt, expected = stored.split("$")
        if prefix != _PREFIX:
            return False
        expected_bytes = _unb64(expected)
        digest = hashlib.scrypt(
            passphrase.encode("utf-8"),
            salt=_unb64(salt),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected_bytes),
            maxmem=_MAXMEM,
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest, expected_bytes)
