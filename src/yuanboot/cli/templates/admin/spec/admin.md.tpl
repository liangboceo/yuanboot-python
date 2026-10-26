# Admin 开发约定

后端按控制器、服务、数据库模型分层，使用 yuanboot-python 的配置、依赖注入、宿主生命周期、日志与组件。
新增模型继承 `Audit`、`Base`；涉及关联写入时使用 `SystemService.session()` 事务。
不要把会话、SQLAlchemy Session 或请求对象保存到全局单例；每个 API 操作创建独立事务。

接口基础路径 `/v1/`，返回 `{status, code, message, data}`。
用户、角色列表的 data 为 `{list, total, page}`；树形列表的节点包含 `children`。
保留现有 camelCase 请求字段。控制器为界面调用路径保留别名，OpenAPI 展示主要接口。

新增受保护操作必须通过 `actor` 验证当前账号、令牌类型、过期时间、会话与 token_version，
然后通过 `SystemService.authorize` 校验模块权限。前端隐藏按钮不能代替后端授权。
普通用户的用户数据访问使用 `require_user_scope`；可扩展该模式处理业务数据。
菜单父节点不自动授予权限，路由树会补齐父目录，按钮节点只提供权限而不生成页面路由。
禁止创建菜单/部门的父子循环，删除父节点前处理子节点与关联数据。

密码只存加盐哈希，不从接口返回。验证码一次性消费，刷新令牌轮换；修改密码增加 token_version。
部署多个 worker/实例时必须配置 Redis，共享这些状态。JWT 密钥、数据库口令通过环境提供。

初始化在托管服务内执行，仅补齐缺失种子数据；不覆盖用户已修改的菜单或系统配置。
数据库结构变更使用显式迁移，验证与测试放在项目自己的开发目录中，业务运行数据不提交。

前端新增页面放在 `src/views/`，接口放在 `src/api/`，通过菜单 component 指向页面相对路径。
构建前执行 `pnpm typecheck` 与 `pnpm build`。Python 代码检查使用 Ruff。
