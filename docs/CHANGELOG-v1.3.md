# v1.3 变更记录（2026-10-12）

## 新增
- MySQL 8 后端支持：SFTPSERVER_DB_URL 环境变量（缺省回退 SQLite，pool_pre_ping/pool_recycle/utf8mb4）
- 用户组管理：admins 表 role/remark 列；后台账号 CRUD API（/admins，仅 super_admin）；管理后台「后台账号管理」页
- 一键部署脚本 deploy/one-click.sh（Rocky9+MySQL8，参数化+幂等，固化 systemd %40/特权端口/pip 镜像坑位）
- 审计导出：GET /api/v1/logs/export（服务端 CSV，10 万行上限，导出入审计）
- Web 文件页 UI 统一：规范设计语言（#f5f5f7/#0b3d62/16px 圆角），面包屑导航、上传/改名/删除按钮按权限显隐
- 审计 size_bytes 数值列（SFTP/Web 传输量精确入库，趋势优先数值聚合）

## 修复
- [重要] sftp_server.py _local()：asyncssh _to_local_path 在 Linux 返回 bytes，str() 包装致读文件/列目录 FileNotFoundError（Windows 不复现）
- Web 上传目标目录不存在自动级联创建（mkdir -p 语义，此前 404）
- Web 列表页 ?path= 子目录导航失效（此前写死根目录）
- PATCH /users 支持 enabled 字段（禁用账号，此前 400）
- 管理端口默认 80（systemd AmbientCapabilities=CAP_NET_BIND_SERVICE，非 root 绑特权端口）

## 变更
- 管理后台导航：账号管理→SFTP账号管理；用户组管理→后台账号管理（单标签，仅管理员）
- 删除账号保护锁：需 ?confirm=<用户名>，同管理员 60 秒窗口限删 1 个
- 管理员/SFTP 用户名大写显式 400（不再静默转小写）
- 管理会话升级 token→(username,expire)，操作者可审计追溯
