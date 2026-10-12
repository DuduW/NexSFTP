#!/usr/bin/env bash
# =============================================================================
# XFS project quota 每用户硬限制同步（PRD 7.2 L2）
# 原理: 为每个用户目录绑定 project id，设置 bhard（inode 无每目录限额，文件数由应用层强制）
# 前提: /srv/sftp 所在分区为 XFS 且挂载含 pquota
# 用法: sudo bash quota_sync.sh          # 读取 DB 中每用户 quota_bytes 逐个设置
#       sudo xfs_quota -x -c 'report -h' /srv/sftp   # 查看报告
# =============================================================================
set -euo pipefail

FILE_ROOT=/srv/sftp
DB=/var/lib/sftpserver/sftpserver.db
PRJ_BASE=10000

# 确认 pquota
mount | grep -E "$(findmnt -no TARGET -T ${FILE_ROOT}).*pquota" >/dev/null \
  || { echo "错误: ${FILE_ROOT} 未启用 pquota"; exit 1; }

# 依赖 sqlite3 读库（或用 python）
read_rows() {
  if command -v sqlite3 >/dev/null; then
    sqlite3 "${DB}" "select id,username,quota_bytes from sftp_users where deleted_at is null;"
  else
    python3 - <<'PY'
import sqlite3
c = sqlite3.connect("/var/lib/sftpserver/sftpserver.db")
for r in c.execute("select id,username,quota_bytes from sftp_users where deleted_at is null"):
    print(*r)
PY
  fi
}

while read -r uid uname qb; do
  [ -d "${FILE_ROOT}/${uname}" ] || mkdir -p "${FILE_ROOT}/${uname}"
  prj="sftp_${uname}"
  # project id 数字必须唯一，用用户行 id 映射
  prjid=$((PRJ_BASE + uid))
  # 写 /etc/projects 与 /etc/projid（幂等）
  grep -q "^${prjid}:" /etc/projects 2>/dev/null || echo "${prjid}:${FILE_ROOT}/${uname}" >> /etc/projects
  grep -q "^${prj}:" /etc/projid 2>/dev/null || echo "${prj}:${prjid}" >> /etc/projid
  # 递归建立项目标记并设置硬限制
  xfs_quota -x -c "project -s ${prj} ${FILE_ROOT}/${uname}" "${FILE_ROOT}" >/dev/null
  if [ "${qb}" -gt 0 ]; then
    xfs_quota -x -c "limit -p bhard=${qb} ${prj}" "${FILE_ROOT}"
    echo "✅ ${uname}: bhard=${qb} ($((qb/1024/1024)) MB)"
  else
    xfs_quota -x -c "limit -p bhard=0 ${prj}" "${FILE_ROOT}"
    echo "✅ ${uname}: 不限"
  fi
done < <(read_rows)

echo "完成。查看报告: xfs_quota -x -c 'report -h' ${FILE_ROOT}"
