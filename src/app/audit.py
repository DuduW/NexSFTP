import os
from datetime import datetime

from .db import SessionLocal
from .models import AuditLog


def audit(src: str, username: str, action: str, detail: str = "",
          client_ip: str = "", result: str = "ok", size_bytes: int = 0):
    """写审计日志（与 SFTP/Web/管理面共用同表）；size_bytes 记录传输量"""
    try:
        with SessionLocal() as s:
            s.add(AuditLog(src=src, username=username or "-", action=action,
                           detail=detail[:1000], client_ip=client_ip or "-",
                           result=result, size_bytes=size_bytes or 0,
                           ts=datetime.now()))
            s.commit()
    except Exception:
        pass  # 审计失败不阻塞传输主流程；生产可加本地队列兜底


def recalc_usage(root: str) -> tuple[int, int]:
    """实扫目录，返回 (bytes, files) —— 用于配额对账复核"""
    total_b, total_f = 0, 0
    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in filenames:
            try:
                total_b += os.path.getsize(os.path.join(dirpath, fn))
                total_f += 1
            except OSError:
                pass
    return total_b, total_f
