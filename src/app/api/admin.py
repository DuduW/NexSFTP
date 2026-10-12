from fastapi import APIRouter, HTTPException, Request

from .. import security, state
from ..audit import audit, recalc_usage
from ..config import FILE_ROOT, load_secret
from ..db import SessionLocal
from ..models import Admin, AuditLog, SftpUser

router = APIRouter(prefix="/api/v1")


def require_admin(request: Request):
    auth = request.headers.get("Authorization", "")
    token = auth[7:] if auth.startswith("Bearer ") else ""
    if not security.admin_login(token):
        raise HTTPException(401, "未登录或会话过期")
    return token


def _user_dict(u: SftpUser, mask: bool = True) -> dict:
    d = {
        "id": u.id, "username": u.username, "root_dir": u.root_dir,
        "perm_read": u.perm_read, "perm_write": u.perm_write,
        "perm_delete": u.perm_delete, "perm_rename": u.perm_rename,
        "quota_bytes": u.quota_bytes, "quota_files": u.quota_files,
        "max_file_size": u.max_file_size,
        "enabled": u.enabled, "expires_at": u.expires_at.isoformat() if u.expires_at else None,
        "web_enabled": u.web_enabled, "web_token": u.web_token,
        "used_bytes": u.used_bytes, "used_files": u.used_files,
        "remark": u.remark,
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }
    return d


def get_valid_user(s, username: str) -> SftpUser:
    u = s.query(SftpUser).filter_by(username=username, deleted_at=None).first()
    return u


@router.post("/auth/login")
def admin_login(body: dict, request: Request):
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    with SessionLocal() as s:
        a = s.query(Admin).filter_by(username=username, enabled=True).first()
        if a and security.verify_password(password, a.password_hash):
            token = security.make_admin_token()
            security.admin_session_create(token, username)
            a.last_login_at = security.utcnow()
            s.commit()
            audit("admin", username, "login", "管理员登录成功",
                  request.client.host if request.client else "")
            return {"token": token}
    audit("admin", username, "login", "管理员登录失败",
          request.client.host if request.client else "", result="deny")
    raise HTTPException(401, "认证失败")


@router.post("/auth/logout")
def admin_logout(request: Request):
    security.admin_logout(require_admin(request))
    return {"ok": True}


@router.get("/dashboard/summary")
def dashboard(request: Request):
    require_admin(request)
    with SessionLocal() as s:
        users = s.query(SftpUser).filter_by(deleted_at=None).all()
        logs_today = s.query(AuditLog).filter(
            AuditLog.ts >= security.utcnow().replace(hour=0, minute=0, second=0)).count()
        top = sorted(users, key=lambda u: -(u.used_bytes or 0))[:5]
        return {
            "accounts_total": len(users),
            "accounts_enabled": sum(1 for u in users if u.enabled),
            "sessions_online": len(state.sftp_sessions),
            "audit_today": logs_today,
            "disk_top": [{"username": u.username, "used_bytes": u.used_bytes,
                          "quota_bytes": u.quota_bytes} for u in top],
        }


@router.get("/dashboard/trend")
def dashboard_trend(request: Request):
    """近 7 日上传/下载字节量趋势：优先 SUM(size_bytes)（P1），
    历史无数值的记录回退解析 detail 中的 '(N B)'。"""
    require_admin(request)
    from datetime import datetime, timedelta
    from sqlalchemy import func
    now = security.utcnow()
    days = [(now - timedelta(days=i)).date() for i in range(6, -1, -1)]
    start = datetime.combine(days[0], datetime.min.time())
    up = {d: 0 for d in days}
    down = {d: 0 for d in days}
    with SessionLocal() as s:
        rows = s.query(AuditLog).filter(
            AuditLog.ts >= start,
            AuditLog.action.in_(["upload", "download"]),
            AuditLog.result != "deny").all()
        # 数值列聚合（新数据）
        agg = (s.query(AuditLog.ts, AuditLog.action, func.sum(AuditLog.size_bytes))
               .filter(AuditLog.ts >= start,
                       AuditLog.action.in_(["upload", "download"]),
                       AuditLog.result != "deny",
                       AuditLog.size_bytes > 0)
               .group_by(AuditLog.ts, AuditLog.action).all())
        num_map = {}
        import re
        pat = re.compile(r"\(([\d,]+) B\)")
        legacy_rows = []
        for r_ in rows:
            d = r_.ts.date()
            if r_.size_bytes:
                num_map.setdefault((d, r_.action), 0)
                num_map[(d, r_.action)] += r_.size_bytes
            else:
                legacy_rows.append(r_)
        for (d, act), v in num_map.items():
            if d in up:
                (up if act == "upload" else down)[d] += v
        for r_ in legacy_rows:
            m = pat.search(r_.detail or "")
            if not m:
                continue
            size = int(m.group(1).replace(",", ""))
            d = r_.ts.date()
            if d in up:
                (up if r_.action == "upload" else down)[d] += size
    return {"items": [{"date": d.isoformat(), "up": up[d], "down": down[d]} for d in days]}


@router.get("/users")
def list_users(request: Request, q: str = ""):
    require_admin(request)
    with SessionLocal() as s:
        query = s.query(SftpUser).filter_by(deleted_at=None)
        if q:
            query = query.filter(SftpUser.username.contains(q))
        return [_user_dict(u) for u in query.order_by(SftpUser.id).all()]


@router.post("/users", status_code=201)
def create_user(body: dict, request: Request):
    admin = require_admin(request)
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    import re
    if not re.fullmatch(r"[a-z0-9_]{2,32}", username):
        raise HTTPException(400, "用户名仅限小写字母/数字/下划线，2-32 位（不支持大写）")
    if len(password) < 8 or not (any(c.isdigit() for c in password) and any(c.isalpha() for c in password)):
        raise HTTPException(400, "密码须≥8位且含字母和数字")
    with SessionLocal() as s:
        if s.query(SftpUser).filter_by(username=username).first():
            raise HTTPException(400, "用户名已存在")
        root = FILE_ROOT
        import os
        user_dir = os.path.join(FILE_ROOT, username)
        os.makedirs(user_dir, exist_ok=True)
        salt = security.new_salt()
        u = SftpUser(
            username=username,
            password_hash=security.hash_password(password),
            root_dir=user_dir,
            perm_read=body.get("perm_read", True),
            perm_write=body.get("perm_write", True),
            perm_delete=body.get("perm_delete", False),
            perm_rename=body.get("perm_rename", False),
            quota_bytes=int(body.get("quota_bytes", 10 * 1024 ** 3)),
            quota_files=int(body.get("quota_files", 0)),
            max_file_size=int(body.get("max_file_size", 0)),
            web_enabled=body.get("web_enabled", True),
            rate_up=int(body.get("rate_up", 0)),
            rate_down=int(body.get("rate_down", 0)),
            max_sessions=int(body.get("max_sessions", 0)),
            web_salt=salt,
            web_token=security.gen_web_token(username, salt, load_secret()),
            web_token_at=security.utcnow(),
            remark=body.get("remark", ""),
        )
        s.add(u)
        s.commit()
        audit("admin", admin, "manage", f"创建账号 {username}",
              request.client.host if request.client else "")
        return _user_dict(u)


@router.patch("/users/{user_id}")
def update_user(user_id: int, body: dict, request: Request):
    """编辑账号：权限四开关 / 配额 / 单文件上限 / 有效期 / Web 开关 / 备注"""
    admin = require_admin(request)
    fields = {
        "perm_read": bool, "perm_write": bool, "perm_delete": bool,
        "perm_rename": bool, "web_enabled": bool, "enabled": bool,
        "quota_bytes": int, "quota_files": int, "max_file_size": int,
        "rate_up": int, "rate_down": int, "max_sessions": int,
    }
    updates = {}
    for k, typ in fields.items():
        if k in body:
            updates[k] = typ(body[k])
    if "expires_at" in body:
        updates["expires_at"] = body["expires_at"] or None  # ""/null 清除有效期
    if "remark" in body:
        updates["remark"] = str(body["remark"])[:200]
    if not updates:
        raise HTTPException(400, "无可更新字段")
    with SessionLocal() as s:
        u = s.get(SftpUser, user_id)
        if not u or u.deleted_at:
            raise HTTPException(404, "用户不存在")
        for k, v in updates.items():
            setattr(u, k, v)
        s.commit()
        audit("admin", admin, "manage", f"编辑账号 {u.username}: {', '.join(updates)}",
              request.client.host if request.client else "")
        return _user_dict(u)


@router.post("/users/{user_id}/reset-password")
def reset_password(user_id: int, body: dict, request: Request):
    admin = require_admin(request)
    password = body.get("password") or ""
    if len(password) < 8:
        raise HTTPException(400, "密码须≥8位")
    with SessionLocal() as s:
        u = s.get(SftpUser, user_id)
        if not u or u.deleted_at:
            raise HTTPException(404, "用户不存在")
        u.password_hash = security.hash_password(password)
        s.commit()
        audit("admin", admin, "manage", f"重置 {u.username} 密码",
              request.client.host if request.client else "")
        return {"ok": True}


@router.post("/users/{user_id}/toggle")
def toggle_user(user_id: int, body: dict, request: Request):
    admin = require_admin(request)
    with SessionLocal() as s:
        u = s.get(SftpUser, user_id)
        if not u or u.deleted_at:
            raise HTTPException(404, "用户不存在")
        u.enabled = bool(body.get("enabled"))
        s.commit()
        audit("admin", admin, "manage",
              f"{'启用' if u.enabled else '禁用'}账号 {u.username}",
              request.client.host if request.client else "")
        return {"ok": True, "enabled": u.enabled}


@router.delete("/users/{user_id}")
def delete_user(user_id: int, request: Request, confirm: str = ""):
    """删除账号（软删）。P1 保护锁：须传 confirm=<用户名>，防止误删；
    60 秒内不允许连续删除多个账号（防手滑批量误删）。"""
    admin = require_admin(request)
    with SessionLocal() as s:
        u = s.get(SftpUser, user_id)
        if not u or u.deleted_at:
            raise HTTPException(404, "用户不存在")
        if confirm != u.username:
            raise HTTPException(400, f"请传 confirm={u.username} 二次确认，防止误删")
        # 时间窗保护：同一管理员 60 秒内仅允许删 1 个账号
        import time as _t
        now = _t.time()
        last = state._last_delete.get(admin)
        if last and now - last < 60:
            raise HTTPException(429, f"删除保护：60 秒内仅允许删除一个账号，请 {int(60-(now-last))} 秒后再试")
        state._last_delete[admin] = now
        u.deleted_at = security.utcnow()
        u.enabled = False
        u.web_enabled = False
        s.commit()
        audit("admin", admin, "manage", f"删除账号 {u.username}",
              request.client.host if request.client else "")
        return {"ok": True}


@router.post("/users/{user_id}/usage")
def refresh_usage(user_id: int, request: Request):
    require_admin(request)
    with SessionLocal() as s:
        u = s.get(SftpUser, user_id)
        if not u or u.deleted_at:
            raise HTTPException(404, "用户不存在")
        used_bytes, used_files = recalc_usage(u.root_dir)
        u.used_bytes, u.used_files = used_bytes, used_files
        s.commit()
        return {"used_bytes": used_bytes, "used_files": used_files}


@router.post("/users/{user_id}/regen-web-token")
def regen_web_token(user_id: int, request: Request):
    admin = require_admin(request)
    from ..config import load_secret
    with SessionLocal() as s:
        u = s.get(SftpUser, user_id)
        if not u or u.deleted_at:
            raise HTTPException(404, "用户不存在")
        u.web_salt = security.new_salt()
        u.web_token = security.gen_web_token(u.username, u.web_salt, load_secret())
        u.web_token_at = security.utcnow()
        s.commit()
        audit("admin", admin, "manage", f"轮换 {u.username} 加密路径（旧路径失效）",
              request.client.host if request.client else "")
        return {"web_token": u.web_token}


@router.get("/sessions")
def list_sessions(request: Request):
    require_admin(request)
    with state._lock:
        return [{"sid": sid, "username": v["username"], "ip": v["ip"],
                 "login_at": v["login_at"]}
                for sid, v in state.sftp_sessions.items()]


@router.delete("/sessions/{sid}")
def kick_session(sid: str, request: Request):
    admin = require_admin(request)
    with state._lock:
        sess = state.sftp_sessions.get(sid)
    if not sess:
        raise HTTPException(404, "会话不存在或已断开")
    try:
        sess["conn"].close()
    except Exception:
        pass
    audit("admin", admin, "manage", f"强制断开会话 {sess['username']}", "")
    return {"ok": True}


@router.get("/logs")
def list_logs(request: Request, username: str = "", action: str = "",
              page: int = 1, size: int = 50):
    require_admin(request)
    with SessionLocal() as s:
        query = s.query(AuditLog)
        if username:
            query = query.filter(AuditLog.username == username)
        if action:
            query = query.filter(AuditLog.action == action)
        total = query.count()
        rows = query.order_by(AuditLog.id.desc()).offset((page - 1) * size).limit(size).all()
        return {"total": total, "items": [{
            "id": r.id, "ts": r.ts.isoformat(), "src": r.src, "username": r.username,
            "action": r.action, "detail": r.detail, "client_ip": r.client_ip,
            "result": r.result} for r in rows]}


# ==================== 用户组管理：后台管理员（仅 super_admin） ====================

def _require_super_admin(request: Request) -> str:
    """管理员管理接口仅 super_admin 可用；返回操作者用户名"""
    token = require_admin(request)
    name = security.admin_username(token)
    if not name:
        raise HTTPException(403, "会话无效")
    with SessionLocal() as s:
        a = s.query(Admin).filter_by(username=name).first()
        if not a or a.role != "super_admin" or not a.enabled:
            raise HTTPException(403, "仅超级管理员可管理用户组")
    return name


def _admin_dict(a: Admin) -> dict:
    return {
        "id": a.id, "username": a.username, "role": a.role or "admin",
        "enabled": a.enabled, "remark": a.remark or "",
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "last_login_at": a.last_login_at.isoformat() if a.last_login_at else None,
    }


def _active_super_count(s) -> int:
    return s.query(Admin).filter_by(role="super_admin", enabled=True).count()


@router.get("/admins")
def list_admins(request: Request):
    _require_super_admin(request)
    with SessionLocal() as s:
        return [_admin_dict(a) for a in s.query(Admin).order_by(Admin.id).all()]


@router.post("/admins", status_code=201)
def create_admin(body: dict, request: Request):
    op = _require_super_admin(request)
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    role = body.get("role", "admin")
    import re
    if not re.fullmatch(r"[a-z0-9_]{2,32}", username):
        raise HTTPException(400, "用户名仅限小写字母/数字/下划线，2-32 位（不支持大写）")
    if username in ("admin", "root", "system"):
        raise HTTPException(400, "保留用户名不可使用")
    if len(password) < 8 or not (any(c.isdigit() for c in password) and any(c.isalpha() for c in password)):
        raise HTTPException(400, "密码须≥8位且含字母和数字")
    if role not in ("admin", "super_admin"):
        raise HTTPException(400, "role 仅支持 admin / super_admin")
    with SessionLocal() as s:
        if s.query(Admin).filter_by(username=username).first():
            raise HTTPException(400, "用户名已存在")
        a = Admin(username=username, password_hash=security.hash_password(password),
                  role=role, remark=body.get("remark", ""))
        s.add(a)
        s.commit()
        audit("admin", op, "manage", f"创建管理员 {username}（{role}）",
              request.client.host if request.client else "")
        return _admin_dict(a)


@router.patch("/admins/{admin_id}")
def update_admin(admin_id: int, body: dict, request: Request):
    op = _require_super_admin(request)
    with SessionLocal() as s:
        a = s.get(Admin, admin_id)
        if not a:
            raise HTTPException(404, "管理员不存在")
        new_role = body.get("role", a.role)
        new_enabled = bool(body.get("enabled", a.enabled))
        if new_role not in ("admin", "super_admin"):
            raise HTTPException(400, "role 仅支持 admin / super_admin")
        # 保护：不能降级/禁用/删除最后一个启用的 super_admin
        if a.role == "super_admin" and a.enabled and (new_role != "super_admin" or not new_enabled):
            others = s.query(Admin).filter(
                Admin.id != a.id, Admin.role == "super_admin", Admin.enabled.is_(True)).count()
            if others == 0:
                raise HTTPException(400, "系统至少保留一个启用的超级管理员")
        if a.username == op and new_enabled is False:
            raise HTTPException(400, "不能禁用自己")
        if "remark" in body:
            a.remark = str(body["remark"])[:255]
        a.role = new_role
        a.enabled = new_enabled
        s.commit()
        audit("admin", op, "manage",
              f"编辑管理员 {a.username}: role={a.role}, enabled={a.enabled}",
              request.client.host if request.client else "")
        return _admin_dict(a)


@router.post("/admins/{admin_id}/reset-pass")
def reset_admin_pass(admin_id: int, body: dict, request: Request):
    op = _require_super_admin(request)
    password = body.get("password") or ""
    if len(password) < 8 or not (any(c.isdigit() for c in password) and any(c.isalpha() for c in password)):
        raise HTTPException(400, "密码须≥8位且含字母和数字")
    with SessionLocal() as s:
        a = s.get(Admin, admin_id)
        if not a:
            raise HTTPException(404, "管理员不存在")
        a.password_hash = security.hash_password(password)
        s.commit()
        audit("admin", op, "manage", f"重置管理员 {a.username} 密码",
              request.client.host if request.client else "")
        return {"ok": True}


@router.delete("/admins/{admin_id}")
def delete_admin(admin_id: int, request: Request):
    op = _require_super_admin(request)
    with SessionLocal() as s:
        a = s.get(Admin, admin_id)
        if not a:
            raise HTTPException(404, "管理员不存在")
        if a.username == op:
            raise HTTPException(400, "不能删除自己")
        if a.role == "super_admin" and a.enabled and _active_super_count(s) <= 1:
            raise HTTPException(400, "系统至少保留一个启用的超级管理员")
        name = a.username
        s.delete(a)
        s.commit()
        audit("admin", op, "manage", f"删除管理员 {name}",
              request.client.host if request.client else "")
        return {"ok": True}


# ==================== P1：审计日志导出 CSV ====================

@router.get("/logs/export")
def export_logs(request: Request, username: str = "", action: str = "",
                result: str = "", days: int = 7):
    """导出审计日志 CSV（默认近 7 天，可按用户/动作/结果过滤，上限 10 万行）"""
    from datetime import timedelta as _td
    from fastapi.responses import StreamingResponse
    import csv, io
    admin = require_admin(request)
    with SessionLocal() as s:
        q = s.query(AuditLog).filter(AuditLog.ts >= security.utcnow() - _td(days=int(days)))
        if username:
            q = q.filter(AuditLog.username == username)
        if action:
            q = q.filter(AuditLog.action == action)
        if result:
            q = q.filter(AuditLog.result == result)
        rows = q.order_by(AuditLog.id.desc()).limit(100000).all()
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["id", "ts", "src", "username", "action", "detail",
                    "client_ip", "result", "size_bytes"])
        for r in rows:
            w.writerow([r.id, r.ts, r.src, r.username, r.action, r.detail,
                        r.client_ip, r.result, r.size_bytes or 0])
        buf.seek(0)
        audit("admin", admin, "manage", f"导出审计 CSV（{len(rows)} 行，近{days}天）",
              request.client.host if request.client else "")
        return StreamingResponse(
            iter([buf.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition":
                     f"attachment; filename=audit_logs_{security.utcnow():%Y%m%d_%H%M%S}.csv"})
