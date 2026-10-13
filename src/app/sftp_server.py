"""SFTP 传输面（基于 asyncssh 2.24.1 SFTPServer API）

安全分层：
- L-chroot：asyncssh 原生 chroot（map_path 词法规范化 + 拒绝创建指向外部的软链）
- L-perm：R/W/D/M 四权限，在每一类操作入口校验
- L-quota：open 写入预检 + QuotaFile 写入实时拦截 + close 更新用量
- L-audit：全部动作与拒绝事件写审计库

注意：基类方法为 MaybeAwait 语义（同步或协程），统一经 _ma() 适配调用。
"""
import asyncio
import inspect
import os
import secrets
import time

import asyncssh
from asyncssh.constants import FXF_WRITE, FXF_CREAT, FXF_TRUNC, FXF_APPEND
from asyncssh.sftp import _to_local_path, SFTPName

from . import state
from .audit import audit
from .config import HOST, HOST_KEY_PATH, SFTP_PORT, ensure_dirs
from .db import SessionLocal
from .models import SftpUser
from .security import verify_password


async def _ma(v):
    """MaybeAwait 适配：基类方法可能返回同步结果或协程"""
    if inspect.isawaitable(v):
        return await v
    return v


def project_disabled(project_id):
    """项目停用 → 账号登录即时冻结（PRD §6.2）"""
    if not project_id:
        return False
    from .models import Project
    from .db import SessionLocal
    with SessionLocal() as s:
        p = s.get(Project, project_id)
        return bool(p and not p.enabled)


def get_user(username: str):
    with SessionLocal() as s:
        u = s.query(SftpUser).filter_by(username=username, deleted_at=None).first()
        if not u:
            return None
        s.expunge(u)
        return u


class ThrottleFile:
    """限速包装句柄：按 字节/秒 节流读写（rate=0 不限）；未定义属性委托 inner"""

    def __init__(self, inner, rate: int, username: str, rel: str, direction: str):
        self.inner = inner
        self.rate = rate or 0
        self.username = username
        self.rel = rel
        self.direction = direction
        self._sent = 0
        self._t0 = time.monotonic()

    def __getattr__(self, name):
        return getattr(self.inner, name)

    async def pace(self, n: int):
        if self.rate <= 0:
            return
        self._sent += n
        expect = self._t0 + self._sent / self.rate
        now = time.monotonic()
        if now < expect:
            await asyncio.sleep(min(expect - now, 5.0))


class QuotaFile(ThrottleFile):
    """写句柄：限速 + 实时拦截超出剩余配额的写入"""

    def __init__(self, inner, limit_end: int, username: str, rel: str,
                 is_new: bool, rate: int = 0, file_size_limit: int = 0):
        super().__init__(inner, rate, username, rel, "upload")
        self.limit_end = limit_end
        self.is_new = is_new
        self.max_end = 0
        self.file_size_limit = file_size_limit or 0   # 单文件上限（0=不限），写入硬拦

    def close(self):
        self.inner.close()


class ReadThrottle(ThrottleFile):
    """读句柄：下载限速"""
    pass


class SftpFS(asyncssh.SFTPServer):
    def __init__(self, chan):
        username = chan.get_extra_info("username")
        self.user: SftpUser = get_user(username) or SftpUser(username=username)
        self.username = username
        self.root_real = os.path.realpath(self.user.root_dir)
        super().__init__(chan, chroot=self.root_real)

    # ---------- 工具 ----------
    def _local(self, path: bytes) -> str:
        # map_path 返回 SFTP 表示；_to_local_path 在 win32 返回 str、
        # 在 POSIX 返回 bytes（os.fsencode），统一 fsdecode 为本地 str
        return os.fsdecode(_to_local_path(self.map_path(path)))

    def _rel(self, path: bytes) -> str:
        # 硬校验：任何含 ".." 分量的路径一律拒绝（asyncssh chroot 会把 .. 词法归一化，
        # 如 ".." 映射回根目录、"/../../x" 归一为 "/x"，必须在其之前显式拦截）
        parts = path.replace(b"\\", b"/").split(b"/")
        if b".." in parts:
            audit("sftp", self.username, "deny",
                  f"拒绝越界路径 {path.decode('utf-8', 'replace')!r}", result="deny")
            raise asyncssh.SFTPPermissionDenied("permission denied")
        try:
            return self.reverse_map_path(path).decode("utf-8", "replace")
        except Exception:
            return path.decode("utf-8", "replace")

    def _need(self, perm: bool, action: str, rel: str = ""):
        if not perm:
            audit("sftp", self.username, "deny", f"无{action}权限 {rel}", result="deny")
            raise asyncssh.SFTPPermissionDenied("permission denied")

    # ---------- 列目录 / 元数据 ----------
    async def scandir(self, path: bytes):
        """自带实现：直接枚举本地目录。
        不用基类版本 —— 它会 yield "./.." 条目并内部 lstat("..")，
        与 `..` 硬校验（防逃逸）冲突；且客户端 listdir 本就会过滤 ./.."""
        rel = self._rel(path)
        self._need(self.user.perm_read, "读取", rel)
        local = self._local(path)
        if not os.path.isdir(local):
            raise asyncssh.SFTPNoSuchFile("no such directory")
        with os.scandir(local) as entries:
            for entry in entries:
                filename = os.fsencode(entry.name)
                attrs = asyncssh.sftp.SFTPAttrs.from_local(
                    entry.stat(follow_symlinks=False))
                yield SFTPName(filename, attrs=attrs)

    async def stat(self, path: bytes):
        self._need(self.user.perm_read, "读取", self._rel(path))
        return await _ma(super().stat(path))

    async def lstat(self, path: bytes):
        self._need(self.user.perm_read, "读取", self._rel(path))
        return await _ma(super().lstat(path))

    async def setstat(self, path: bytes, attrs):
        self._need(self.user.perm_write, "写入", self._rel(path))
        return await _ma(super().setstat(path, attrs))

    async def lsetstat(self, path: bytes, attrs):
        self._need(self.user.perm_write, "写入", self._rel(path))
        return await _ma(super().lsetstat(path, attrs))

    async def mkdir(self, path: bytes, attrs):
        rel = self._rel(path)
        self._need(self.user.perm_write, "写入", rel)
        if rel in ("/", ""):
            self._need(False, "写入", rel)
        await _ma(super().mkdir(path, attrs))
        audit("sftp", self.username, "mkdir", rel)

    async def rmdir(self, path: bytes):
        rel = self._rel(path)
        self._need(self.user.perm_delete, "删除", rel)
        if rel in ("/", ""):
            self._need(False, "删除", rel)
        await _ma(super().rmdir(path))
        audit("sftp", self.username, "delete", f"rmdir {rel}")

    async def remove(self, path: bytes):
        rel = self._rel(path)
        self._need(self.user.perm_delete, "删除", rel)
        await _ma(super().remove(path))
        audit("sftp", self.username, "delete", rel)

    async def rename(self, oldpath: bytes, newpath: bytes):
        self._need(self.user.perm_rename, "改名", self._rel(oldpath))
        await _ma(super().rename(oldpath, newpath))
        audit("sftp", self.username, "rename",
              f"{self._rel(oldpath)} -> {self._rel(newpath)}")

    async def posix_rename(self, oldpath: bytes, newpath: bytes):
        self._need(self.user.perm_rename, "改名", self._rel(oldpath))
        await _ma(super().posix_rename(oldpath, newpath))
        audit("sftp", self.username, "rename",
              f"{self._rel(oldpath)} -> {self._rel(newpath)} (posix)")

    async def readlink(self, path: bytes):
        self._need(self.user.perm_read, "读取", self._rel(path))
        return await _ma(super().readlink(path))

    async def symlink(self, oldpath: bytes, newpath: bytes):
        """链接目标含 ".." 分量一律拒绝（防逃逸，PRD 7.1 I3）"""
        tparts = oldpath.replace(b"\\", b"/").split(b"/")
        if b".." in tparts:
            audit("sftp", self.username, "deny",
                  f"拒绝软链 {self._rel(newpath)} -> {oldpath.decode('utf-8', 'replace')!r}"
                  "（目标含 ..，防逃逸）", result="deny")
            raise asyncssh.SFTPPermissionDenied("permission denied")
        rel = self._rel(newpath)
        self._need(self.user.perm_write, "写入", rel)
        try:
            await _ma(super().symlink(oldpath, newpath))
        except asyncssh.SFTPError:
            audit("sftp", self.username, "deny",
                  f"拒绝软链 {self._rel(oldpath)} -> {rel}（越出根目录）", result="deny")
            raise
        audit("sftp", self.username, "symlink", f"{rel} -> {self._rel(oldpath)}")

    async def link(self, oldpath: bytes, newpath: bytes):
        self._need(self.user.perm_write, "写入", self._rel(newpath))
        return await _ma(super().link(oldpath, newpath))

    async def statvfs(self, path: bytes):
        self._need(self.user.perm_read, "读取", self._rel(path))
        return await _ma(super().statvfs(path))

    async def fsync(self, file_obj):
        return await _ma(super().fsync(file_obj))

    # ---------- 文件读写 ----------
    async def open(self, path: bytes, pflags: int, attrs):
        rel = self._rel(path)
        write_mode = bool(pflags & (FXF_WRITE | FXF_CREAT | FXF_TRUNC | FXF_APPEND))
        local = self._local(path)
        if write_mode:
            self._need(self.user.perm_write, "写入", rel)
            exists = os.path.isfile(local)
            base = 0 if (pflags & FXF_TRUNC or not exists) else os.path.getsize(local)
            is_new = not exists or bool(pflags & FXF_TRUNC)
            new_size = getattr(attrs, "size", None)
            # 实时读取最新用量（self.user 是连接级快照，同连接多次上传会漂移）
            with SessionLocal() as s:
                fresh = (s.query(SftpUser.used_bytes, SftpUser.used_files)
                         .filter_by(username=self.username).first())
            used_bytes, used_files = fresh if fresh else (0, 0)
            if self.user.max_file_size and new_size and base + new_size > self.user.max_file_size:
                audit("sftp", self.username, "quota_deny",
                      f"{rel} 超过单文件大小限制", result="deny")
                raise asyncssh.SFTPQuotaExceeded("file size limit exceeded")
            if is_new and self.user.quota_files and used_files >= self.user.quota_files:
                audit("sftp", self.username, "quota_deny",
                      f"{rel} 超过文件数配额（{self.user.quota_files} 个）", result="deny")
                raise asyncssh.SFTPQuotaExceeded("file count quota exceeded")
            if self.user.quota_bytes:
                free = self.user.quota_bytes - (used_bytes or 0)
                limit_end = base + max(free, 0)
                if new_size and base + new_size > limit_end:
                    audit("sftp", self.username, "quota_deny",
                          f"{rel} 预检超配额（需 {new_size} B，剩余 {free} B）", result="deny")
                    raise asyncssh.SFTPQuotaExceeded("quota exceeded")
            else:
                limit_end = base + (new_size or 0) + (1 << 40)
            inner = await _ma(super().open(path, pflags, attrs))
            return QuotaFile(inner, limit_end, self.username, rel, is_new,
                             rate=getattr(self.user, "rate_up", 0) or 0,
                             file_size_limit=getattr(self.user, "max_file_size", 0) or 0)
        else:
            self._need(self.user.perm_read, "读取", rel)
            if not os.path.exists(local):
                raise asyncssh.SFTPNoSuchFile("no such file")
            if os.path.isdir(local):
                raise asyncssh.SFTPFailure("is a directory")
            audit("sftp", self.username, "download",
                  f"{rel} ({os.path.getsize(local):,} B)",
                  size_bytes=os.path.getsize(local))
            inner = await _ma(super().open(path, pflags, attrs))
            rate = getattr(self.user, "rate_down", 0) or 0
            return ReadThrottle(inner, rate, self.username, rel, "download") if rate else inner

    async def write(self, file_obj, offset: int, data: bytes) -> int:
        if isinstance(file_obj, QuotaFile):
            end = offset + len(data)
            # 单文件大小硬限制：基于实际写入进度（max_end 取历史+本次），防客户端不上报 size 绕过预检
            if file_obj.file_size_limit and max(end, file_obj.max_end) > file_obj.file_size_limit:
                audit("sftp", file_obj.username, "quota_deny",
                      f"传输中断：{file_obj.rel} 写至 {max(end, file_obj.max_end):,} B "
                      f"超单文件上限 {file_obj.file_size_limit:,} B", result="deny")
                raise asyncssh.SFTPQuotaExceeded("file size limit exceeded")
            if end > file_obj.limit_end:
                audit("sftp", file_obj.username, "quota_deny",
                      f"传输中断：{file_obj.rel} 写至 {end} 超出剩余配额", result="deny")
                raise asyncssh.SFTPQuotaExceeded("quota exceeded")
            file_obj.max_end = max(file_obj.max_end, end)
            file_obj.inner.seek(offset)
            file_obj.inner.write(data)
            await file_obj.pace(len(data))
            return len(data)
        return await _ma(super().write(file_obj, offset, data))

    async def read(self, file_obj, offset: int, size: int) -> bytes:
        if isinstance(file_obj, ThrottleFile):
            file_obj.inner.seek(offset)
            data = file_obj.inner.read(size)
            await file_obj.pace(len(data))
            return data
        return await _ma(super().read(file_obj, offset, size))

    async def close(self, file_obj):
        if isinstance(file_obj, QuotaFile):
            file_obj.close()
            if file_obj.max_end:
                with SessionLocal() as s:
                    u = get_user(file_obj.username)
                    if u:
                        delta_files = 1 if (file_obj.is_new and file_obj.max_end) else 0
                        s.query(SftpUser).filter_by(id=u.id).update({
                            "used_bytes": (u.used_bytes or 0) + file_obj.max_end,
                            "used_files": (u.used_files or 0) + delta_files,
                        })
                        s.commit()
                audit("sftp", file_obj.username, "upload",
                      f"{file_obj.rel} ({file_obj.max_end:,} B)",
                      size_bytes=file_obj.max_end)
            return None
        if isinstance(file_obj, ReadThrottle):
            file_obj.inner.close()
            return None
        return await _ma(super().close(file_obj))


class SftpSSHServer(asyncssh.SSHServer):
    def __init__(self):
        self.user: SftpUser | None = None
        self.username = ""
        self.conn = None
        self._sid = ""

    def connection_made(self, conn):
        self.conn = conn

    def connection_lost(self, exc):
        if self.conn:
            state.drop_session(self.conn)
        if self.username:
            # 连接关闭审计：用登录时缓存的来源 IP（此时 peername 已不可得）
            audit("sftp", self.username, "logout", "连接断开", getattr(self, "_ip", "-"))

    def begin_auth(self, username: str) -> bool:
        self.username = username
        return True

    def password_auth_supported(self) -> bool:
        # asyncssh 默认 False，必须显式开启密码认证
        return True

    async def validate_password(self, username: str, password: str) -> bool:
        ip = "-"
        try:
            ip = self.conn.get_extra_info("peername")[0]
        except Exception:
            pass
        if state.is_locked(username):
            audit("sftp", username, "login", "账号锁定中（连续失败≥10次）", ip, result="deny")
            return False
        u = get_user(username)
        expired = bool(u and u.expires_at and str(u.expires_at) <= security_utcnow())
        proj_disabled = project_disabled(u.project_id) if u else False
        if not u or not u.enabled or expired or proj_disabled or not verify_password(password, u.password_hash):
            locked = state.record_fail(username)
            audit("sftp", username, "login",
                  "认证失败" + ("（项目已停用）" if proj_disabled else
                               ("（已触发锁定）" if locked else "")), ip, result="deny")
            return False
        # M3：并发会话数限制（0 = 不限）
        max_sess = getattr(u, "max_sessions", 0) or 0
        if max_sess and state.count_sessions(username) >= max_sess:
            audit("sftp", username, "login",
                  f"并发会话数已达上限（{max_sess}）", ip, result="deny")
            return False
        state.clear_fails(username)
        self.user = u
        self._ip = ip   # 缓存会话来源 IP（断开时 peername 已不可得）
        self._sid = secrets.token_hex(8)
        state.add_session(self._sid, username, ip, self.conn)
        audit("sftp", username, "login", "SFTP 登录成功", ip)
        return True


def security_utcnow() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


async def start_sftp():
    ensure_dirs()
    if not os.path.exists(HOST_KEY_PATH):
        key = asyncssh.generate_private_key("ssh-ed25519")
        with open(HOST_KEY_PATH, "wb") as f:
            f.write(key.export_private_key())
    await asyncssh.create_server(
        SftpSSHServer, HOST, SFTP_PORT,
        sftp_factory=SftpFS,
        server_host_keys=[asyncssh.read_private_key(HOST_KEY_PATH)],
    )
    print(f"[sftpserver] SFTP listening on {HOST}:{SFTP_PORT}", flush=True)
