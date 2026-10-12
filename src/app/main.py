import asyncio
import sys

from .config import ADMIN_PORT, HOST, SFTP_PORT
from .db import init_db
from .apiapp import build_app


async def usage_reconciler():
    """M3：每 5 分钟磁盘实扫对账，修正应用层用量统计漂移（PRD 7.2 L1）"""
    import asyncio
    from .audit import recalc_usage
    from .db import SessionLocal
    from .models import SftpUser
    while True:
        await asyncio.sleep(300)
        try:
            with SessionLocal() as s:
                for u in s.query(SftpUser).filter_by(deleted_at=None).all():
                    used_bytes, used_files = recalc_usage(u.root_dir)
                    if (u.used_bytes or 0) != used_bytes or (u.used_files or 0) != used_files:
                        s.query(SftpUser).filter_by(id=u.id).update(
                            {"used_bytes": used_bytes, "used_files": used_files})
                s.commit()
            print("[sftpserver] usage reconciled", flush=True)
        except Exception as e:
            print("[sftpserver] reconcile error:", e, flush=True)


async def main():
    init_db()
    from .sftp_server import start_sftp
    await start_sftp()          # SFTP 传输面 :2022
    import uvicorn
    cfg = uvicorn.Config(build_app(), host=HOST, port=ADMIN_PORT, log_level="warning")
    server = uvicorn.Server(cfg)   # 管理面 + Web 文件访问（默认 :80）
    import asyncio
    recon = asyncio.ensure_future(usage_reconciler())
    try:
        await server.serve()
    finally:
        recon.cancel()


def run():
    import logging
    import os
    if os.environ.get("SFTP_DEBUG"):
        logging.basicConfig(level=logging.DEBUG)
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())


if __name__ == "__main__":
    run()
