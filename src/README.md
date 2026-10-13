# README

# sftpserver — SFTP 文件传输服务器

Python3 + FastAPI + asyncssh + HTML5。单进程双端口：SFTP 传输面（TCP 2022）+ 管理面/用户 Web 访问（80）。

对应 PRD：`docs/PRD-SFTP服务器.md`。GitHub：https://github.com/DuduW/NexSFTP

## 功能一览

- **SFTP 传输**：虚拟账号（不落 /etc/passwd）、应用层 chroot 用户隔离（P0）、读/写/删/改名四权限、容量/文件数配额、上传/下载限速、并发会话数、有效期
- **管理后台** `/admin`：仪表盘（7 日趋势）、账号管理（权限/配额/限速/加密路径）、会话监控（强制断开）、审计日志（筛选/导出 CSV）、Web 访问总览、系统设置
- **用户 Web 文件访问** `/web/login` → `/f//`：每用户固定 HMAC-SHA256 加密路径，列表/下载/上传/删除/改名，与 SFTP 共用权限配额审计

## 快速开始

### Windows（自测）

```bat
:: 1. 安装 Python 3.11+ 后：
cd sftpserver
python -m venv venv && venv\Scripts\pip install -r requirements.txt
:: 2. 双击 start.bat（或）
venv\Scripts\python run.py
```

### Rocky Linux 9（生产）

```bash
unzip sftpserver-v1.8-deploy-20261013.zip && cd sftpserver
sudo bash deploy/deploy.sh        # 一键：专用账号 + venv + systemd + firewalld + XFS 检测
sudo systemctl status sftpserver
```

详见 `deploy/README-部署.md`（含 SELinux、XFS project quota、升级回滚）。

## 访问入口

| 入口 | 地址 | 说明 |
|---|---|---|
| 管理后台 | `http://:80/admin` | 初始 admin/admin1234，**首登即改密** |
| 用户文件访问 | `http://:80/web/login` | SFTP 用户同一账号 |
| API 文档 | `http://:80/api/docs` | Swagger |
| SFTP | `:2022` | WinSCP/FileZilla/sftp 命令 |

## 目录与数据

- 数据目录可用环境变量覆盖：`SFTPSERVER_DATA_DIR`、`SFTPSERVER_HOST`、`SFTPSERVER_SFTP_PORT`、`SFTPSERVER_ADMIN_PORT`
- 默认 `/data/`：`sftpserver.db`（账号+审计）、`files//`（用户数据）、`host_ed25519`、`secret.key`（**务必随库备份，丢失则所有加密路径失效**）
- 生产布局：数据 `/var/lib/sftpserver`、用户文件 `/srv/sftp//`

## 测试

```bash
python tests/test_e2e.py        # 32 项：SFTP/隔离/配额/权限/Web/审计
python tests/test_m3.py         # 3 项：限速/并发/文件数配额
python tests/web_files_v2.py    # 31 项：Web 加密路径全链路（自愈式，可重复跑）
```
