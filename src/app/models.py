from datetime import datetime  # 时间戳统一本地时区（服务器 Asia/Shanghai）
from sqlalchemy import Column, Integer, String, BigInteger, Boolean, DateTime, ForeignKey, UniqueConstraint
from .db import Base


class Project(Base):
    """项目（多租户隔离单元）"""
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True)
    name = Column(String(64), unique=True, nullable=False)
    code = Column(String(32), unique=True, nullable=False)
    remark = Column(String(255), default="")
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)


class AdminProject(Base):
    """管理员-项目映射（多对多；project_admin 的管辖范围）"""
    __tablename__ = "admin_projects"
    id = Column(Integer, primary_key=True)
    admin_id = Column(Integer, ForeignKey("admins.id"), nullable=False, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    __table_args__ = (UniqueConstraint("admin_id", "project_id", name="uq_admin_project"),)


class SftpUser(Base):
    __tablename__ = "sftp_users"
    id = Column(Integer, primary_key=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    password_hash = Column(String(128), nullable=False)
    root_dir = Column(String(512), nullable=False)
    # 四权限：读(列表/下载) 写(上传/建目录) 删 改名
    perm_read = Column(Boolean, default=True)
    perm_write = Column(Boolean, default=True)
    perm_delete = Column(Boolean, default=False)
    perm_rename = Column(Boolean, default=False)
    # 配额
    quota_bytes = Column(BigInteger, default=10 * 1024 ** 3)
    quota_files = Column(BigInteger, default=0)          # 0 = 不限
    max_file_size = Column(BigInteger, default=0)        # 0 = 不限
    # M3 限速与并发（字节/秒；0 = 不限）
    rate_up = Column(BigInteger, default=0)
    rate_down = Column(BigInteger, default=0)
    max_sessions = Column(Integer, default=0)            # 0 = 不限
    # 状态
    enabled = Column(Boolean, default=True)
    expires_at = Column(DateTime, nullable=True)
    # Web 加密路径
    web_enabled = Column(Boolean, default=True)
    web_token = Column(String(32), unique=True, nullable=True, index=True)
    web_salt = Column(String(32), nullable=True)
    web_token_at = Column(DateTime, nullable=True)
    # 用量
    used_bytes = Column(BigInteger, default=0)
    used_files = Column(BigInteger, default=0)
    remark = Column(String(255), default="")
    # 项目归属（NULL=未分配，仅平台级管理员可见可改）
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    deleted_at = Column(DateTime, nullable=True)


class Admin(Base):
    __tablename__ = "admins"
    id = Column(Integer, primary_key=True)
    username = Column(String(64), unique=True, nullable=False)
    password_hash = Column(String(128), nullable=False)
    enabled = Column(Boolean, default=True)
    # 用户组：super_admin（可管理管理员）/ admin（仅后台管理）
    role = Column(String(16), default="admin")
    remark = Column(String(255), default="")
    created_at = Column(DateTime, default=datetime.now)
    last_login_at = Column(DateTime, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True)
    ts = Column(DateTime, default=datetime.now, index=True)
    src = Column(String(8), default="sftp")        # sftp / web / admin
    username = Column(String(64), index=True)
    action = Column(String(32))                    # login/upload/download/delete/mkdir/rename/quota_deny/deny/manage
    detail = Column(String(1024), default="")
    client_ip = Column(String(64), default="")
    result = Column(String(8), default="ok")       # ok / deny
    # P1：传输字节数独立列（upload/download），替代 trend 对 detail 正则解析
    size_bytes = Column(BigInteger, default=0)
