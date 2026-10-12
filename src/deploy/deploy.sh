#!/usr/bin/env bash
# =============================================================================
# sftpserver 一键部署脚本（Rocky Linux 9）
# 用法: sudo bash deploy.sh
# 功能: 专用账号 / 目录 / venv / systemd / firewalld / SELinux / XFS pquota 检测
# =============================================================================
set -euo pipefail

APP_DIR=/opt/sftpserver
DATA_DIR=/var/lib/sftpserver
FILE_ROOT=/srv/sftp
SVC_USER=sftpserver
PY_VER=python3.11

echo "==> [1/8] 检查 root 权限"
[ "$(id -u)" -eq 0 ] || { echo "请用 sudo 运行"; exit 1; }

echo "==> [2/8] 安装系统依赖"
dnf install -y "${PY_VER}" "${PY_VER}-devel" "${PY_VER}-pip" firewalld >/dev/null

echo "==> [3/8] 创建专用账号与目录（非 root 运行）"
id -u "${SVC_USER}" >/dev/null 2>&1 || useradd --system --shell /sbin/nologin --home-dir "${APP_DIR}" "${SVC_USER}"
mkdir -p "${APP_DIR}" "${DATA_DIR}" "${FILE_ROOT}"
chown -R "${SVC_USER}:${SVC_USER}" "${DATA_DIR}" "${FILE_ROOT}"

echo "==> [4/8] 部署代码"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # deploy/ 的上一级 = 项目根
rsync -a --exclude 'data' --exclude 'venv' --exclude '__pycache__' \
      --exclude 'tests' --exclude '.git' "${SCRIPT_DIR}/" "${APP_DIR}/"
chown -R "${SVC_USER}:${SVC_USER}" "${APP_DIR}"

echo "==> [5/8] 创建 venv 并安装依赖"
[ -d "${APP_DIR}/venv" ] || "${PY_VER}" -m venv "${APP_DIR}/venv"
"${APP_DIR}/venv/bin/pip" install --quiet --upgrade pip
"${APP_DIR}/venv/bin/pip" install --quiet -r "${APP_DIR}/requirements.txt"

echo "==> [6/8] 检测文件系统（XFS project quota，PRD 7.2 L2 硬限制）"
FS_TYPE=$(findmnt -no FSTYPE -T "${FILE_ROOT}")
echo "    ${FILE_ROOT} 所在文件系统: ${FS_TYPE}"
if [ "${FS_TYPE}" = "xfs" ]; then
    if mount | grep "$(findmnt -no TARGET -T "${FILE_ROOT}")" | grep -q pquota; then
        echo "    ✅ XFS pquota 已启用，可运行 quota_sync.sh 同步每用户硬限制"
    else
        echo "    ⚠️  XFS 但未启用 pquota：需在 /etc/fstab 该分区加 defaults,pquota 后重启，"
        echo "       或当前仅使用应用层配额（后台会提示风险）"
    fi
else
    echo "    ⚠️  非 XFS（${FS_TYPE}）：无法启用 OS 级 project quota 硬限制，"
    echo "       仅应用层配额生效。建议迁移到 XFS 分区后再启用 L2 硬限制"
fi

echo "==> [7/8] 安装 systemd 服务"
cp "${APP_DIR}/deploy/sftpserver.service" /etc/systemd/system/sftpserver.service
systemctl daemon-reload
systemctl enable --now sftpserver
sleep 2
systemctl --no-pager --lines 5 status sftpserver || true

echo "==> [8/8] 防火墙放行"
systemctl enable --now firewalld >/dev/null 2>&1 || true
firewall-cmd --permanent --add-port=2022/tcp
firewall-cmd --permanent --add-port=80/tcp
firewall-cmd --reload

cat <<BANNER

============================================================
 ✅ 部署完成
   SFTP 传输面 : $(hostname -I | awk '{print $1}'):2022
   管理后台    : http://$(hostname -I | awk '{print $1}'):80/admin  (admin / admin1234，请立即修改)
   数据目录    : ${DATA_DIR}   用户文件: ${FILE_ROOT}
   日志        : journalctl -u sftpserver -f
 建议后续:
   1. 修改 admin 初始密码（后台或 API /users 无 → 直接改库，见 README）
   2. HTTPS 建议套 Nginx + 内网 CA 证书
   3. 如为 XFS+pquota，配置 quota_sync.sh 定时同步用户硬限制
============================================================
BANNER
