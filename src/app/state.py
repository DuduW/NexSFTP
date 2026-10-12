"""跨模块共享的运行时状态（M1 用进程内存，生产可换 Redis）"""
import threading
import time

_lock = threading.Lock()

# sid -> {username, ip, login_at, conn}
sftp_sessions: dict[str, dict] = {}
# username -> [fail_count, lock_until_ts]
login_fails: dict[str, list] = {}
# conn -> sid 映射，连接关闭时清理
_conn_index: dict[int, str] = {}
# 删除保护锁：admin username -> last_delete_ts（60 秒窗口，防连续误删）
_last_delete: dict[str, float] = {}


def add_session(sid: str, username: str, ip: str, conn):
    with _lock:
        sftp_sessions[sid] = {"username": username, "ip": ip,
                              "login_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                              "conn": conn}
        _conn_index[id(conn)] = sid


def drop_session(conn):
    with _lock:
        sid = _conn_index.pop(id(conn), None)
        if sid:
            sftp_sessions.pop(sid, None)


def count_sessions(username: str) -> int:
    with _lock:
        return sum(1 for v in sftp_sessions.values() if v["username"] == username)


def record_fail(username: str) -> bool:
    """记录登录失败；返回是否已触发锁定"""
    with _lock:
        item = login_fails.setdefault(username, [0, 0.0])
        item[0] += 1
        if item[0] >= 10:
            item[1] = time.time() + 900   # 锁 15 分钟
            item[0] = 0
            return True
        return False


def is_locked(username: str) -> bool:
    with _lock:
        item = login_fails.get(username)
        return bool(item and item[1] > time.time())


def clear_fails(username: str):
    with _lock:
        login_fails.pop(username, None)
