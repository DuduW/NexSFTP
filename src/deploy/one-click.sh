#!/usr/bin/env bash
# =============================================================================
# sftpserver 一键部署脚本（Rocky Linux 9 + MySQL 8 后端）
# 用法: sudo bash one-click.sh [选项]
#   --db-pass PWD      MySQL 应用账户密码（默认随机生成并打印）
#   --db-name NAME     库名（默认 sftpserver）
#   --db-user NAME     应用账户（默认 sftpserver）
#   --admin-port N     管理面端口（默认 80）
#   --sftp-port N      SFTP 传输面端口（默认 2022）
#   --file-root PATH   用户数据根目录（默认 /srv/sftp；生产建议独立数据卷）
#   --skip-mysql       跳过 MySQL 安装（已有自管 MySQL 时使用，仍会建库授权）
#   --mirror URL       pip 镜像（默认阿里云）
#
# 幂等：重复执行安全（库/账户/目录/服务均 IF-NOT-EXISTS 语义）
# 产出: /opt/sftpserver（代码+venv）、/var/lib/sftpserver（数据）、/srv/sftp（用户文件）、
#       /etc/sftpserver.env（DB 连接）、systemd sftpserver 服务
# 固化坑位: systemd Environment 不解析 %40 → 用 EnvironmentFile；
#           特权端口 80 → AmbientCapabilities=CAP_NET_BIND_SERVICE（非 root）；
#           pip 直连慢 → 阿里云镜像；MySQL utf8mb4 强制。
# =============================================================================
set -euo pipefail

# ---------- 参数 ----------
die(){  echo -e "  \033[0;31m✗ $*\033[0m"; exit 1; }
DB_PASS="" DB_NAME="sftpserver" DB_USER="sftpserver"
ADMIN_PORT="80" SFTP_PORT="2022" FILE_ROOT="/srv/sftp" SKIP_MYSQL=0
MIRROR="https://mirrors.aliyun.com/pypi/simple/"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --db-pass)   DB_PASS="$2"; shift 2 ;;
    --db-name)   DB_NAME="$2"; shift 2 ;;
    --db-user)   DB_USER="$2"; shift 2 ;;
    --admin-port) ADMIN_PORT="$2"; shift 2 ;;
    --sftp-port) SFTP_PORT="$2"; shift 2 ;;
    --file-root) FILE_ROOT="$2"; shift 2 ;;
    --skip-mysql) SKIP_MYSQL=1; shift ;;
    --mirror)    MIRROR="$2"; shift 2 ;;
    *) echo "未知参数: $1"; exit 1 ;;
  esac
done

APP_DIR=/opt/sftpserver
DATA_DIR=/var/lib/sftpserver
SVC_USER=sftpserver

# 自定义数据目录校验：绝对路径、不含 .. 与空格、不得为系统关键目录
case "$FILE_ROOT" in
  /*) ;;
  *) die "--file-root 须为绝对路径（如 /data/sftp）" ;;
esac
[[ "$FILE_ROOT" == *..* || "$FILE_ROOT" == *" "* ]] && die "--file-root 不允许包含 .. 或空格"
case "$FILE_ROOT" in
  /|/bin|/boot|/dev|/etc|/lib|/proc|/root|/run|/sbin|/sys|/usr|/var|/opt|/srv|/home) 
     die "--file-root 不能直接使用系统目录（$FILE_ROOT），请用其子目录（如 $FILE_ROOT/sftp）" ;;
esac
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # deploy/ 上一级 = 项目根
ENV_FILE=/etc/sftpserver.env

# ---------- 输出工具 ----------
STEP=0
step(){ STEP=$((STEP+1)); echo -e "\n\033[0;34m==> [$STEP] $*\033[0m"; }
ok(){   echo -e "  \033[0;32m✓\033[0m $*"; }
warn(){ echo -e "  \033[0;33m⚠\033[0m $*"; }
die(){  echo -e "  \033[0;31m✗ $*\033[0m"; exit 1; }

# ---------- 1. 前置检查 ----------
step "前置检查"
[ "$(id -u)" -eq 0 ] || die "请用 root/sudo 运行"
grep -q "Rocky Linux 9" /etc/os-release 2>/dev/null \
  || warn "非 Rocky Linux 9（检测到 $(grep PRETTY_NAME /etc/os-release | cut -d'"' -f2)），脚本按 EL9 设计，继续执行"
[ -f "$SRC_DIR/run.py" ] && [ -d "$SRC_DIR/app" ] || die "项目根定位失败: $SRC_DIR（需含 app/ 与 run.py）"
ok "root 权限 / 项目根 $SRC_DIR"

# ---------- 2. 系统依赖 ----------
step "安装系统依赖（python3.11 / firewalld / rsync）"
dnf install -y python3.11 python3.11-pip firewalld rsync >/dev/null 2>&1
ok "python3.11 $(python3.11 --version 2>&1 | awk '{print $2}')"

# ---------- 3. pip 镜像（直连 PyPI 慢的坑） ----------
step "配置 pip 镜像"
if ! grep -q "index-url" /etc/pip.conf 2>/dev/null; then
  printf "[global]\nindex-url=%s\ntrusted-host=%s\n" \
    "$MIRROR" "$(echo "$MIRROR" | sed -E 's|https?://([^/]+)/.*|\1|')" > /etc/pip.conf
  ok "已写入 /etc/pip.conf → $MIRROR"
else
  ok "已存在 /etc/pip.conf，跳过"
fi

# ---------- 4. MySQL 8 ----------
if [ "$SKIP_MYSQL" -eq 1 ]; then
  step "跳过 MySQL 安装（--skip-mysql）"
else
  step "安装并启动 MySQL 8"
  if ! rpm -q mysql-server >/dev/null 2>&1; then
    dnf install -y mysql-server >/dev/null 2>&1
    ok "mysql-server 已安装"
  else
    ok "mysql-server 已存在"
  fi
  systemctl enable --now mysqld >/dev/null 2>&1
  sleep 2
  systemctl is-active --quiet mysqld || die "mysqld 未运行"
  ok "mysqld $(mysql --version | awk '{print $5}') active"
fi

step "初始化数据库与账户（幂等）"
if [ -z "$DB_PASS" ]; then
  DB_PASS="$(head -c 18 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 20)"
  GENERATED_DB_PASS=1
fi
mysql <<SQL
CREATE DATABASE IF NOT EXISTS \`${DB_NAME}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE USER IF NOT EXISTS '${DB_USER}'@'127.0.0.1' IDENTIFIED BY '${DB_PASS}';
CREATE USER IF NOT EXISTS '${DB_USER}'@'localhost' IDENTIFIED BY '${DB_PASS}';
ALTER USER '${DB_USER}'@'127.0.0.1' IDENTIFIED BY '${DB_PASS}';
ALTER USER '${DB_USER}'@'localhost' IDENTIFIED BY '${DB_PASS}';
GRANT ALL PRIVILEGES ON \`${DB_NAME}\`.* TO '${DB_USER}'@'127.0.0.1';
GRANT ALL PRIVILEGES ON \`${DB_NAME}\`.* TO '${DB_USER}'@'localhost';
FLUSH PRIVILEGES;
SQL
ok "库 ${DB_NAME}（utf8mb4）+ 账户 ${DB_USER}@127.0.0.1 授权完成"

# ---------- 5. 环境文件（systemd %40 坑 → EnvironmentFile） ----------
step "写入 $ENV_FILE（数据库连接，600 权限）"
# URL 编码密码中的特殊字符（@ → %40 等）
DB_PASS_ENC=$(python3 - "$DB_PASS" <<'PY'
import sys, urllib.parse
print(urllib.parse.quote(sys.argv[1], safe=""))
PY
)
DB_URL="mysql+pymysql://${DB_USER}:${DB_PASS_ENC}@127.0.0.1:3306/${DB_NAME}?charset=utf8mb4"
umask 077
cat > "$ENV_FILE" <<EOF
SFTPSERVER_DB_URL=${DB_URL}
EOF
ok "DB_URL 已写入（密码已 URL 编码，规避 systemd specifier 问题）"

# ---------- 6. 系统账号与目录 ----------
step "创建专用账号与目录"
id -u "$SVC_USER" >/dev/null 2>&1 \
  || useradd --system --shell /sbin/nologin --home-dir "$APP_DIR" "$SVC_USER"
mkdir -p "$APP_DIR" "$DATA_DIR" "$FILE_ROOT"
chown -R "$SVC_USER:$SVC_USER" "$DATA_DIR" "$FILE_ROOT"
ok "账号 $SVC_USER + $DATA_DIR + $FILE_ROOT"

# ---------- 7. 部署代码 ----------
step "同步代码 → $APP_DIR"
rsync -a --delete --exclude 'data' --exclude 'venv' --exclude '__pycache__' \
      --exclude 'tests' --exclude '.git' --exclude '*.pyc' "$SRC_DIR/" "$APP_DIR/"
ok "代码已同步（rsync --delete 保持一致，排除 venv/data/tests）"

# ---------- 8. venv 与依赖 ----------
step "创建 venv 并安装依赖（走镜像）"
[ -d "$APP_DIR/venv" ] || python3.11 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --quiet --upgrade pip
"$APP_DIR/venv/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"
chown -R "$SVC_USER:$SVC_USER" "$APP_DIR"
ok "依赖就绪（fastapi/asyncssh/sqlalchemy/pymysql 等）"

# ---------- 9. systemd 单元 ----------
step "安装 systemd 服务（端口 ${ADMIN_PORT}/${SFTP_PORT}）"
cat > /etc/systemd/system/sftpserver.service <<EOF
[Unit]
Description=SFTP Server (asyncssh transfer plane + FastAPI admin plane)
After=network.target mysqld.service
Wants=mysqld.service

[Service]
Type=simple
User=${SVC_USER}
Group=${SVC_USER}
WorkingDirectory=${APP_DIR}
Environment="PYTHONUNBUFFERED=1"
Environment="SFTPSERVER_DATA=${DATA_DIR}"
Environment="SFTPSERVER_FILES=${FILE_ROOT}"
Environment="SFTPSERVER_HOST=0.0.0.0"
Environment="SFTPSERVER_PORT=${SFTP_PORT}"
Environment="SFTPSERVER_ADMIN_PORT=${ADMIN_PORT}"
EnvironmentFile=-${ENV_FILE}
ExecStart=${APP_DIR}/venv/bin/python run.py
Restart=always
RestartSec=3
# 绑定特权端口（<1024）所需最小能力，进程仍为非 root
AmbientCapabilities=CAP_NET_BIND_SERVICE
# 沙箱加固
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
ReadWritePaths=${DATA_DIR} ${FILE_ROOT}
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
RestrictRealtime=true
LockPersonality=true

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable sftpserver >/dev/null 2>&1
ok "单元已安装并 enable（含 mysqld 依赖顺序 + 沙箱加固）"

# ---------- 10. 防火墙 ----------
step "防火墙放行 ${SFTP_PORT}/${ADMIN_PORT}"
systemctl is-active --quiet firewalld || systemctl enable --now firewalld >/dev/null 2>&1 || true
firewall-cmd --permanent --add-port="${SFTP_PORT}/tcp" >/dev/null
firewall-cmd --permanent --add-port="${ADMIN_PORT}/tcp" >/dev/null
firewall-cmd --reload >/dev/null
ok "已放行"

# ---------- 11. 启动与验证 ----------
step "启动服务并验证"
systemctl restart sftpserver
sleep 4
systemctl is-active --quiet sftpserver || { journalctl -u sftpserver -n 20 --no-pager; die "服务未起来，见上方日志"; }
ok "服务 active"

ss -tln | grep -q ":${SFTP_PORT} " || die "SFTP 端口 ${SFTP_PORT} 未监听"
ss -tln | grep -q ":${ADMIN_PORT} " || die "管理端口 ${ADMIN_PORT} 未监听"
ok "端口监听 ${SFTP_PORT} + ${ADMIN_PORT}"

# MySQL 表自动创建验证（init_db 在首次启动时建表）
TABLES=$(mysql -N -e "SHOW TABLES FROM \`${DB_NAME}\`" 2>/dev/null | tr '\n' ' ')
echo "$TABLES" | grep -q "admins" || die "MySQL 建表失败（admins 缺失）"
echo "$TABLES" | grep -q "sftp_users" || die "MySQL 建表失败（sftp_users 缺失）"
ok "MySQL 表: ${TABLES}"

HTTP=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:${ADMIN_PORT}/admin" || true)
[ "$HTTP" = "200" ] || die "管理页面 HTTP $HTTP"
ok "管理页面 HTTP 200"

# ---------- 12. 摘要 ----------
IP=$(hostname -I | awk '{print $1}')
cat <<BANNER

============================================================
 ✅ sftpserver 部署完成
------------------------------------------------------------
   SFTP 传输面   : ${IP}:${SFTP_PORT}
   管理后台      : http://${IP}:${ADMIN_PORT}/admin
   Web 文件访问  : http://${IP}:${ADMIN_PORT}/web/login
   API 文档      : http://${IP}:${ADMIN_PORT}/api/docs
   后台初始账号  : admin / admin1234  ⚠️ 首登立即修改
   数据库        : MySQL ${DB_NAME}（utf8mb4）@127.0.0.1
   应用账户密码  : ${DB_PASS:-}$( [ "${GENERATED_DB_PASS:-0}" = 1 ] && echo '  （随机生成，已写入 /etc/sftpserver.env）' )
   数据目录      : ${DATA_DIR}   用户文件: ${FILE_ROOT}
   日志          : journalctl -u sftpserver -f
------------------------------------------------------------
 建议后续:
   1. 修改 admin 初始密码（后台账号管理页）
   2. 管理面套 HTTPS（Nginx + 内网 CA 反代）
   3. 用户文件迁移到独立 XFS 数据卷并启用 pquota（OS 级硬配额）
============================================================
BANNER
