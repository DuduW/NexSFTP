import os

# 生产部署可用环境变量覆盖（Rocky9 systemd 单元中注入）：
#   SFTPSERVER_DATA   数据目录（默认项目 data/，生产建议 /var/lib/sftpserver）
#   SFTPSERVER_FILES  用户文件根（生产建议 /srv/sftp）
#   SFTPSERVER_HOST   监听地址（生产 0.0.0.0）
#   SFTPSERVER_PORT / SFTPSERVER_ADMIN_PORT
DATA_DIR = os.environ.get("SFTPSERVER_DATA",
                          os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data'))
FILE_ROOT = os.environ.get("SFTPSERVER_FILES", os.path.join(DATA_DIR, 'files'))  # 等价于生产 /srv/sftp/
DB_PATH = os.path.join(DATA_DIR, 'sftpserver.db')
HOST_KEY_PATH = os.path.join(DATA_DIR, 'host_ed25519')
SECRET_PATH = os.path.join(DATA_DIR, 'secret.key')

# --- 数据库：默认 SQLite，设置 SFTPSERVER_DB_URL 即切换 MySQL 8 ---
# 例: mysql+pymysql://sftpserver:pass@127.0.0.1:3306/sftpserver?charset=utf8mb4
DB_URL = os.environ.get("SFTPSERVER_DB_URL", f"sqlite:///{DB_PATH}")

HOST = os.environ.get("SFTPSERVER_HOST", '127.0.0.1')
SFTP_PORT = int(os.environ.get("SFTPSERVER_PORT", '2022'))
ADMIN_PORT = int(os.environ.get("SFTPSERVER_ADMIN_PORT", '80'))

DEFAULT_QUOTA = 10 * 1024 * 1024 * 1024   # 10GB
DEFAULT_ADMIN_USER = 'admin'
DEFAULT_ADMIN_PASS = 'admin1234'

# 登录防爆破
MAX_FAILS = 10
LOCK_SECONDS = 900


def ensure_dirs():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(FILE_ROOT, exist_ok=True)


def load_secret() -> bytes:
    """服务端密钥：用于 HMAC 生成用户加密路径，泄露则所有加密路径可逆推"""
    ensure_dirs()
    if not os.path.exists(SECRET_PATH):
        with open(SECRET_PATH, 'wb') as f:
            f.write(os.urandom(32))
    with open(SECRET_PATH, 'rb') as f:
        return f.read()
