import base64
import hashlib
import hmac
import secrets
import time
from datetime import datetime

import bcrypt

from . import config

_B62 = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except ValueError:
        return False


def _b62(data: bytes) -> str:
    n = int.from_bytes(data, "big")
    out = []
    while n:
        n, r = divmod(n, 62)
        out.append(_B62[r])
    s = "".join(reversed(out))
    return s or "0"


def gen_web_token(username: str, salt: str, secret: bytes) -> str:
    """固定加密目录路径：HMAC-SHA256(服务端密钥, username|salt) 截取 128bit -> Base62（约22位）"""
    mac = hmac.new(secret, f"{username}|{salt}".encode(), hashlib.sha256).digest()[:16]
    return _b62(mac)


def new_salt() -> str:
    return secrets.token_hex(8)


def make_admin_token() -> str:
    return secrets.token_hex(32)


# ---- 简单内存会话管理（M1；生产可换 Redis/DB） ----
_admin_sessions: dict[str, tuple[str, float]] = {}  # token -> (username, expire_ts)
_web_sessions: dict[str, tuple[str, float]] = {}    # token -> (username, expire_ts)
SESSION_TTL = 8 * 3600


def admin_session_create(token: str, username: str = ""):
    _admin_sessions[token] = (username, time.time() + SESSION_TTL)


def admin_login(token: str):
    """校验管理会话；有效则滑动续期并返回用户名，否则 None"""
    item = _admin_sessions.get(token)
    if item and item[1] > time.time():
        _admin_sessions[token] = (item[0], time.time() + SESSION_TTL)
        return item[0] or True
    _admin_sessions.pop(token, None)
    return None


def admin_username(token: str):
    """从管理会话 token 反查用户名（不续期；无效返回 None）"""
    item = _admin_sessions.get(token)
    if item and item[1] > time.time():
        return item[0] or None
    return None


def admin_logout(token: str):
    _admin_sessions.pop(token, None)


def web_login(token: str, username: str):
    _web_sessions[token] = (username, time.time() + SESSION_TTL)


def web_get(token: str):
    item = _web_sessions.get(token)
    if item and item[1] > time.time():
        _web_sessions[token] = (item[0], time.time() + SESSION_TTL)
        return item[0]
    _web_sessions.pop(token, None)
    return None


def web_logout(token: str):
    _web_sessions.pop(token, None)


def utcnow() -> datetime:
    return datetime.utcnow()
