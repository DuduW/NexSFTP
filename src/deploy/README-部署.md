# README-部署

# SFTP 服务器 Rocky9 部署手册（M4）

> 对应 PRD《docs/PRD-SFTP服务器.md》里程碑 M4。架构：单进程双端口 —— asyncssh SFTP（TCP 2022）+ FastAPI 管理面/Web 文件访问（TCP 80）。

## 1. 文件清单

| 文件 | 用途 |
|---|---|
| `deploy.sh` | 一键部署：账号/目录/venv/systemd/firewalld/XFS 检测 |
| `sftpserver.service` | systemd 单元（非 root + 沙箱加固） |
| `quota_sync.sh` | XFS project quota 每用户硬限制同步（PRD 7.2 L2） |
| `../requirements.txt` | Python 依赖 |

## 2. 一键部署

```bash
# 上传整个 sftpserver 目录到服务器，例如 /root/sftpserver
cd /root/sftpserver/deploy
sudo bash deploy.sh
```

脚本自动完成：

1. 安装 python3.11 / firewalld
2. 创建系统账号 `sftpserver`（`/sbin/nologin`，非 root 运行）
3. 目录规划：代码 `/opt/sftpserver`、数据 `/var/lib/sftpserver`、用户文件 `/srv/sftp//`
4. venv + pip 依赖安装
5. systemd 启动并开机自启（`ProtectSystem=strict` 沙箱加固）
6. firewalld 放行 2022/tcp、80/tcp

## 3. 部署后验证

```bash
systemctl status sftpserver
journalctl -u sftpserver -f          # 日志
ss -tlnp | grep -E '2022|80'       # 端口监听
curl -s http://127.0.0.1:80/       # 管理面
# SFTP 登录测试（任意已建账号）
sftp -P 2022 alice@127.0.0.1
```

浏览器打开 `http://:80/admin`，初始账号 `admin / admin1234` —— **生产必须立即修改**：

```bash
sudo -u sftpserver /opt/sftpserver/venv/bin/python - <<'PY'
import sys; sys.path.insert(0, "/opt/sftpserver")
from app.security import hash_password
from app.db import SessionLocal
from app.models import Admin
with SessionLocal() as s:
    a = s.query(Admin).filter_by(username="admin").first()
    a.password_hash = hash_password("<新强密码>")
    s.commit()
print("admin password updated")
PY
```

## 4. XFS project quota（OS 级硬限制，PRD 7.2 L2）

前提：`/srv/sftp` 所在分区为 XFS 且挂载参数含 `pquota`。`deploy.sh` 会自动检测并提示。

```bash
# /etc/fstab 示例（加 pquota 后需重启或 remount）
# /dev/mapper/rl-root  /srv  xfs  defaults,pquota  0 0

# 同步每用户 bhard 硬限制（幂等，可重复执行；建议 cron 定时）
sudo bash /opt/sftpserver/deploy/quota_sync.sh
echo '*/10 * * * * root bash /opt/sftpserver/deploy/quota_sync.sh' > /etc/cron.d/sftpserver-quota

# 查看报告
xfs_quota -x -c 'report -h' /srv/sftp
```

- 硬限制生效后，即使应用层被绕过，内核直接拒绝写入
- 文件数配额无每目录 inode 限额，由应用层强制（open 预检 + Web 上传预检）

## 5. SELinux 说明（PRD 7.3 #8）

Rocky9 默认 enforcing。systemd 沙箱 + 非 root 专用账号已提供主要隔离；SELinux 对 `/srv/sftp` 需打上下文：

```bash
semanage fcontext -a -t var_t "/srv/sftp(/.*)?"     # 或自定义 policy
restorecon -Rv /srv/sftp
# 若遇 SELinux 拒绝，先排查再放行：
ausearch -m avc -ts recent
# 临时验证用（生产勿常开）：
# setsebool -P daemons_dump_core 0; semanage permissive -a sftpserver_t（需自建模块）
```

如需完全自定义 policy（`sepolicy generate`），按最小权限原则单独评审后启用；**不建议**为此把整机设为 permissive。

## 6. 建议配套

| 项 | 建议 |
|---|---|
| HTTPS 80 | 前置 Nginx 反代 + 内网 CA 证书（管理面含登录凭据，不宜裸 HTTP） |
| 管理面访问控制 | firewalld 可用 `rich rule` 限制 80 仅运维网段访问 |
| 数据库 | SQLite 起步；多实例/高并发换 MySQL（SQLAlchemy 已预留） |
| 备份 | `/var/lib/sftpserver/sftpserver.db` + 用户文件定期备份 |
| 限速 | 后台每账号可设上传/下载 KB/s 与并发会话数（M3，热生效于下次连接） |

## 7. 升级 / 回滚

```bash
# 升级：替换代码后重启
rsync -a --exclude data --exclude venv /root/sftpserver-new/ /opt/sftpserver/
systemctl restart sftpserver

# 回滚
systemctl stop sftpserver && cp -a /opt/sftpserver /opt/sftpserver.bak.日期   # 部署前建议先备份
```

数据（DB / 用户文件 / host key / secret.key）均在 `/var/lib/sftpserver` 与 `/srv/sftp`，升级代码不影响。
