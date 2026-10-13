# NexSFTP

轻量级 SFTP 文件传输服务器：**标准 SFTP 协议（TCP 2022）+ HTTPS 风格 Web 文件访问 + 管理后台**，单进程双端口，虚拟账号体系，MySQL 8 / SQLite 双后端。

![version](https://img.shields.io/badge/version-v1.7-blue) ![python](https://img.shields.io/badge/Python-3.11+-3776ab) ![os](https://img.shields.io/badge/OS-Rocky%20Linux%209-red) ![db](https://img.shields.io/badge/DB-MySQL%208%20%7C%20SQLite-orange)

## 功能一览

| 模块 | 能力 |
|------|------|
| **SFTP 传输面** (:2022) | 标准 SFTP 协议（FileZilla / WinSCP / `sftp` 命令直连）；虚拟账号（不落 /etc/passwd）；应用层 chroot 目录隔离；读/写/删/改名四权限；空间/文件数/单文件三级配额；上传下载限速；并发会话数限制 |
| **Web 文件访问** (/web/login) | 浏览器访问本人目录：列表/下载/上传/删除/改名；每用户固定 HMAC-SHA256 加密路径（真实路径零暴露）；权限与 SFTP 共享 |
| **项目管理** | 多租户隔离：项目 CRUD / project_admin 三级角色 / 服务端 scope 强制过滤 / 停用即冻结+强断 |
| **管理后台** (/admin) | 仪表盘（7 日趋势）/ SFTP 账号管理 / 后台账号管理（super_admin·admin 两级）/ 会话监控（强制断开）/ 审计日志（筛选+CSV 导出）/ 用户 Web 访问总览 |
| **安全** | 登录防爆破（10 次锁 15 分钟）；三重加密路径校验；全部操作审计入库；systemd 沙箱加固（非 root 运行）；删除保护锁 |
| **数据库** | MySQL 8（生产，utf8mb4，连接池自愈）/ SQLite（开发，零配置）环境变量一键切换 |

## 快速部署（Rocky Linux 9 一键安装）

```bash
# 1. 下载部署包（releases/ 目录）
unzip sftpserver-v1.7-deploy-20261013.zip -d sftpserver
cd sftpserver/deploy

# 2. 一键部署（自动装 MySQL 8 + 建库授权 + systemd + 防火墙）
sudo bash one-click.sh

# 常用选项
sudo bash one-click.sh --db-pass YourPass --admin-port 80 --sftp-port 2022 --skip-mysql
```

部署完成自动输出访问入口。详见 [docs/安装使用说明.md](docs/安装使用说明.md)。

## 访问入口（默认）

| 入口 | 地址 | 说明 |
|------|------|------|
| 管理后台 | `http://<IP>/admin` | 初始 admin / admin1234，**首登立即修改** |
| Web 文件访问 | `http://<IP>/web/login` | SFTP 用户同一账号 |
| SFTP 传输 | `sftp -P 2022 <user>@<IP>` | 任意 SFTP 客户端 |
| API 文档 | `http://<IP>/api/docs` | Swagger |

## 目录结构

```
├── releases/                          版本部署包
│   ├── sftpserver-v1.7-deploy-20261013.zip   ← 最新（含 CHANGELOG）
│   ├── sftpserver-v1.6-deploy-20261013.zip
│   ├── sftpserver-v1.4-deploy-20261012.zip
│   └── sftpserver-v1.2-deploy-20261011.zip   历史版本
├── docs/
│   ├── 安装使用说明.md                 部署 + 使用 + 运维手册
│   └── CHANGELOG-v1.3.md              版本变更记录
└── src/                               源码（v1.3 同步版）
    ├── app/                           应用代码
    ├── deploy/                        one-click.sh 等部署脚本
    └── requirements.txt
```

## 技术栈

Python 3.11 + FastAPI + asyncssh 2.24 + SQLAlchemy + MySQL 8 / SQLite + 原生 JS（零前端依赖，纯内置 UI）

## 版本历史

- **v1.7**（2026-10-13）：--file-root 自定义数据目录、审计日志对项目管理员三层禁用、全套弹窗 UI 统一、角色徽标三分支修复
- **v1.6**（2026-10-13）：项目管理与项目管理员（多租户隔离/三级角色/停用联动）、单文件上限硬拦、审计关联到人、时区统一东八区
- **v1.4**（2026-10-12）：NexSFTP 品牌统一、GitHub 开源仓库与安装使用说明成文、发版流程固化
- **v1.3**（2026-10-12）：MySQL 8 后端、用户组管理（super_admin/admin）、一键部署脚本、Web 文件页 UI 统一、审计 CSV 导出 + size_bytes 列、Linux SFTP 读 bug 修复、管理端口 80
- **v1.2**（2026-10-11）：M1~M4 全量交付，三套测试 74 项通过

## License

Internal use.
