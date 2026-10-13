# v1.6 变更记录（2026-10-13）

## 新增：项目管理与项目管理员（多租户隔离）
- projects 项目表 + admin_projects 映射（一人可管多项目）+ 账号 project_id 归属
- 三级角色：super_admin / admin / project_admin（项目管理员仅管本项目）
- scope_projects() 服务端单点收口：列表/增删改/会话/审计/导出/仪表盘全部接口强制项目过滤，越权 404
- 项目停用三联动：账号登录即时冻结（SFTP+Web）+ 在线会话强断 + 审计留痕
- 管理后台新增「项目管理」页（新建/编辑/停启用/分配管理员）；账号页项目列与弹窗归属选择
- 项目管理员视角：导航自动隐藏平台管理入口，顶栏角色徽标
- PRD：docs/PRD-项目管理与项目管理员.md；交互演示：docs/demo-project-admin.html

## 修复
- [安全] 单文件大小上限可绕过：原预检依赖客户端上报 attrs.size，不传即绕过；改为写入进度硬拦（quota_deny 审计含精确字节数）
- [审计] 管理操作 username 记为 64 位会话哈希：require_admin 改返回用户名，存量已回填 admin
- [审计] SFTP logout 无来源 IP：登录时缓存会话 IP，断开审计带出
- [审计] 时间显示 UTC 差 8 小时：全链路改本地时区（Asia/Shanghai）+ MySQL time_zone=+08:00 永久化 + 存量回填

## 变更
- 管理员删除级联清理项目映射（外键健壮）
- project_admin 改账号归属显式 403；建号强校验管辖项目
