from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from . import config


def _build_engine():
    url = config.DB_URL
    if url.startswith("sqlite"):
        return create_engine(url, connect_args={"check_same_thread": False})
    # MySQL 8（PyMySQL 驱动）：增加连接健康检查与会话参数
    return create_engine(
        url,
        pool_pre_ping=True,          # 取连接前探活，避免 MySQL wait_timeout 掐断
        pool_recycle=1800,           # 30 分钟回收，低于 wait_timeout 默认 28800
        pool_size=10,
        max_overflow=20,
    )


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def init_db():
    from . import models  # noqa: F401
    config.ensure_dirs()
    Base.metadata.create_all(engine)
    # 轻量迁移：为旧库补齐新增列
    import sqlalchemy
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    if insp.has_table("sftp_users"):
        cols = {c["name"] for c in insp.get_columns("sftp_users")}
        migrations = [
            ("rate_up", "BIGINT DEFAULT 0"),
            ("rate_down", "BIGINT DEFAULT 0"),
            ("max_sessions", "INT DEFAULT 0"),
            ("project_id", "INT NULL"),
        ]
        with engine.begin() as conn:
            for name, ddl in migrations:
                if name not in cols:
                    conn.execute(text(f"ALTER TABLE sftp_users ADD COLUMN {name} {ddl}"))
    # 用户组管理：admins 表补 role/remark 列；首个账号升级 super_admin
    if insp.has_table("admins"):
        acols = {c["name"] for c in insp.get_columns("admins")}
        with engine.begin() as conn:
            if "role" not in acols:
                conn.execute(text("ALTER TABLE admins ADD COLUMN role VARCHAR(16) DEFAULT 'admin'"))
            if "remark" not in acols:
                conn.execute(text("ALTER TABLE admins ADD COLUMN remark VARCHAR(255) DEFAULT ''"))
        with engine.begin() as conn:
            conn.execute(text(
                "UPDATE admins SET role='super_admin' WHERE role='admin' "
                "AND (SELECT COUNT(*) FROM (SELECT 1 FROM admins WHERE role='super_admin') t)=0"))
    # P1：审计表补 size_bytes 数值列（趋势统计改读数值）
    if insp.has_table("audit_logs"):
        lcols = {c["name"] for c in insp.get_columns("audit_logs")}
        if "size_bytes" not in lcols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE audit_logs ADD COLUMN size_bytes BIGINT DEFAULT 0"))
    from .security import hash_password
    with SessionLocal() as s:
        if not s.query(models.Admin).filter_by(username=config.DEFAULT_ADMIN_USER).first():
            s.add(models.Admin(username=config.DEFAULT_ADMIN_USER,
                                password_hash=hash_password(config.DEFAULT_ADMIN_PASS)))
            s.commit()
