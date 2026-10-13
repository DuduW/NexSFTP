# PRD：项目管理与项目管理员（v0.1 草案）

> 版本：v0.1（待评审） ｜ 日期：2026-10-13 ｜ 模块：NexSFTP 多项目权限体系
> 目标读者：吴大宝（评审）、开发实施

## 1. 背景与目标

当前 NexSFTP 为单租户扁平结构：`admin` 角色可管理**全部** SFTP 账号，无项目维度。随着接入项目增多（司法调证、大数据、运维等），需要：

1. **项目隔离**：每个 SFTP 账号归属一个项目；项目管理员只能管理**本项目**的账号/会话/审计，对其他项目零可见、零操作。
2. **分级治理**：超级管理员管平台与项目；项目管理员管自己项目内的账号生命周期。

**不做的事**：不做项目间共享账号、不做账号多项目归属（一人多项目=多账号）、不改 SFTP 传输协议层。

## 2. 角色与权限矩阵

三级角色（复用现有 admins 表，新增 `project_admin`）：

| 功能 | super_admin | admin（平台管理员） | project_admin（项目管理员） |
|------|:---:|:---:|:---:|
| 项目管理（建/编/停用） | ✅ | 👁 只读 | ❌ |
| 后台账号管理（管理员CRUD） | ✅ | ❌ | ❌ |
| 项目管理员分配 | ✅ | ❌ | ❌ |
| SFTP 账号列表 | 全部 | 全部 | **仅本项目** |
| SFTP 账号 创建/编辑/删除/重置密码/轮换路径 | ✅ | ✅ | **仅本项目** |
| 会话监控（查看/强断） | 全部 | 全部 | **仅本项目账号** |
| 审计日志（查询/导出） | 全部 | 全部 | **仅本项目账号** |
| 仪表盘 | 全局 | 全局 | **本项目统计** |
| 用户 Web 访问总览 | 全部 | 全部 | **仅本项目** |
| 系统设置 | ✅ | 👁 | ❌ |

**关键规则**：
- 数据范围（scope）在 **API 层强制注入**（服务端过滤），前端仅做展示配合——防止改包绕过。
- project_admin 登录后台后：侧边栏隐藏「项目管理」「后台账号管理」「系统设置」；数据自动过滤；直接请求他人项目资源一律 404（不泄露存在性）。
- 一个 project_admin 可被分配**多个项目**（如运维管理员管 2 个项目）；一个项目可有多名项目管理员。

## 3. 数据模型

### 3.1 新增表

```
projects（项目表）
  id            INT PK
  name          VARCHAR(64) UNIQUE   项目名（如：司法调证）
  code          VARCHAR(32) UNIQUE   项目标识（如：evidence）
  remark        VARCHAR(255)
  enabled       BOOL DEFAULT 1       停用=该项目账号全部冻结登录
  created_at    DATETIME

admin_projects（管理员-项目映射，多对多）
  admin_id      INT  → admins.id
  project_id    INT  → projects.id
  UNIQUE(admin_id, project_id)
```

### 3.2 存量表变更（幂等迁移）

```
sftp_users  + project_id INT NULL  （NULL=未分配，仅 super_admin/admin 可见可改）
admins.role 扩展枚举：super_admin / admin / project_admin
```

### 3.3 兼容策略

- 现有 8 个账号默认 `project_id=NULL`（未分配），由 super_admin 上线后逐个归入项目；
- 可选一键迁移：预建「默认项目」，把存量账号全部挂入（评审时定）。
- 现有 admin（double/double 之外的管理员）角色不变。

## 4. API 改造清单

| 接口 | 变更 |
|------|------|
| `GET/POST/PATCH/DELETE /api/v1/projects` | **新增**：项目 CRUD（仅 super_admin；admin 只读 GET） |
| `POST /api/v1/projects/{id}/admins` | **新增**：绑定/解绑项目管理员（仅 super_admin） |
| `GET /api/v1/users` | project_admin 请求时自动 `WHERE project_id IN (我的项目)`；新增 `project_id` 查询参数（管理员筛选） |
| `POST /users` `PATCH/DELETE /users/{id}` 等 | project_admin：仅当目标账号 ∈ 我的项目，否则 404；创建时 project_id 强制 ∈ 我的项目（多项目者需指定，单项目者默认） |
| `GET /sessions` `DELETE /sessions/{sid}` | 会话按 username → project 过滤/鉴权 |
| `GET /logs` `GET /logs/export` | 审计按 username ∈ 项目账号集过滤 |
| `GET /dashboard/*` | project_admin 返回项目内统计 |

**实现机制**：新增依赖注入函数 `scope_projects(request) -> list[project_id] | None`（None=不限）。None 走现有逻辑；有值则全部查询自动加过滤——单点收口，避免逐接口遗漏。

## 5. 前端改造

| 页面 | 变更 |
|------|------|
| 🆕 项目管理（super_admin） | 项目列表（名称/标识/账号数/管理员/状态）+ 新建/编辑 + 分配项目管理员弹窗 |
| SFTP账号管理 | 表格加「项目」列；顶部加项目筛选下拉（admin/super_admin 可见）；创建弹窗加项目必选项 |
| 仪表盘 | project_admin 显示「本项目」徽标，统计为项目内 |
| 侧边栏 | project_admin 隐藏：项目管理/后台账号管理/系统设置 |
| 登录后 | 顶栏显示当前身份角色徽标（超级/平台/项目管理员·项目名） |

## 6. 安全设计

1. **服务端强制 scope**：所有数据接口经 `scope_projects()` 收口；越权请求统一 404（与加密路径同策略，不泄露存在性）。
2. **项目停用**：`projects.enabled=0` → 该项目全部账号 SFTP/Web 登录即时拒绝（登录链路加判断），已有在线会话可选择性强断。
3. **审计**：项目维度操作照常入审计（username=操作管理员）；新增 action=`manage` detail 带项目名。
4. **项目管理员不能自我提权**：角色变更仅 super_admin；project_admin 无法触碰 /admins、/projects 写接口。

## 7. 测试方案（实施后回归）

- 权限矩阵逐格测试（3 角色 × 10 功能点）
- 越权样本：project_admin-A 用 B 项目账号 id 调 PATCH/DELETE → 404；创建时伪造 project_id=B → 400
- 数据隔离：列表/会话/审计/导出四接口均无跨项目泄漏
- 项目停用 → 账号登录即时冻结
- 现有 52 项回归全绿（不破坏既有能力）

## 8. 里程碑（评审通过后）

| 阶段 | 内容 | 预估 |
|------|------|------|
| M1 | 数据模型+迁移+项目 CRUD API | 0.5d |
| M2 | scope 收口 + 账号/会话/审计接口改造 | 1d |
| M3 | 前端三页（项目管理/账号页项目列/视角适配） | 1d |
| M4 | 全量回归 + v1.6 发版 | 0.5d |

## 9. 待评审决策点

1. 存量账号处理：保持 NULL 未分配 vs 一键挂「默认项目」？
2. project_admin 是否允许查看本项目账号的加密路径/轮换？（当前方案：允许，便于项目自治）
3. 项目停用时是否自动强断在线会话？
