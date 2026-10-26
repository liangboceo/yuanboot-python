# Yuanboot Admin

基于 yuanboot-python、FastAPI、Vue 3 和 Element Plus 的管理后台，包含用户、角色、菜单、部门和系统配置。

## 创建项目

```bash
python -m pip install 'yuanbootctl-python[admin]==0.2.0'
yuanbootctl-python new admin -n my-admin
cd my-admin
```

生成 `my-admin-server`、`my-admin-web`、README 和 spec 文档。
后端自动依赖与工具同版本的 `yuanboot[admin]`，可通过 `--framework-version` 显式选择版本。

## 启动

后端（Python 3.11+）：

```bash
cd my-admin-server
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
yuanbootctl-python run
```

前端（Node.js 20.19+ 或 22.13+、pnpm 10）：

```bash
cd my-admin-web
pnpm install --frozen-lockfile
pnpm dev
```

- 后台：<http://127.0.0.1:8848/>
- API 文档：<http://127.0.0.1:8090/docs>
- 开发初始账号：`admin` / `admin123`，填写页面图形验证码后登录。

默认使用 SQLite（`my-admin-server/data/admin.db`）和进程内会话，无需外部服务。
初始化只插入缺失数据，重新启动保留用户、授权、菜单和配置。
登录密码经过 PBKDF2-SHA256 加盐处理；修改或重置密码后旧令牌失效。
刷新令牌单次使用，支持退出登录；验证码有效期 2 分钟。

## 目录

- `my-admin-server/`：Python API、模型、业务服务、配置和离线框架文档。
- `my-admin-web/`：管理前端，Vite 将 `/v1/` 代理到后端 8090 端口。
- `spec/`：框架文档与管理模块开发约定。

## MySQL、Redis 与配置中心

单机开发可直接使用默认配置。多进程、多实例部署配置 Redis，共享验证码、登录会话和刷新令牌。
将 `my-admin-server/infrastructure.example.yml` 中的配置合并到所需环境文件（例如 `config_fat.yml`），
通过环境变量提供连接信息。先创建专用 MySQL 数据库，应用启动时创建所需表。
配置中心和服务发现沿用框架的 Nacos 组件，参见后端 `spec/components.md`。

`YUANBOOT_PROFILE` 支持 `dev`、`fat`、`uat`、`pro`。
`pro` 必须提供 `ADMIN_JWT_SECRET`（至少 32 字符）和强密码 `ADMIN_PASSWORD`。
`ADMIN_PASSWORD` 只用于首次创建管理员，不会覆盖已有账号密码。
每个脚手架项目生成独立 JWT 密钥，也可始终使用环境变量覆盖。
本地 SQLite + 内存会话运行一个 worker；配置 MySQL、Redis 后可增加 worker 数量。

构建前端：`pnpm typecheck && pnpm build`。生产环境将前端 `dist/` 托管为静态站点，
将同源 `/v1/` 反向代理到 Python API。业务接口统一返回 `status`、`code`、`message`、`data`。

## 权限与扩展

超级管理员可访问全部模块；普通用户通过角色关联菜单，菜单的 `permission` / `perms` 字段配置后端权限。
例如 `sys:user:list`、`sys:user:query`、`sys:user:add`、`sys:user:edit`、`sys:user:delete`、`sys:user:resetPwd`。
角色、菜单、部门使用对应的 `sys:role:*`、`sys:menu:*`、`sys:dept:*`；系统配置使用 `sys:config:query/edit`。
可通过按钮类型菜单分配写权限，前端权限显示与后端校验同时生效。
角色的 `dataScope` 控制用户查询及修改范围：1 全部、2 本部门及下级、3 本部门、4 本人、5 自定义部门。
内置超级管理员账号和角色受到保护。

开发新模块请阅读 生成项目中的 `spec/admin.md`、`spec/yuanboot-python.md` 和后端 `spec/backend-module-development.md`。

## License

Copyright (c) 2026 jackson liang。项目采用 MIT License；第三方前端组件见 `THIRD_PARTY_NOTICES.md`。
