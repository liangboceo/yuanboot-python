# Yuanboot Admin

基于 yuanboot-python、FastAPI、Vue 3 和 Element Plus 的管理后台，包含用户、角色、菜单、部门和系统配置。

## 创建项目

```bash
python -m pip install 'yuanbootctl-python[admin]==0.3.3'
yuanbootctl-python new admin -n my-admin
cd my-admin
```

生成 `my-admin-server`、`my-admin-web`、README 和 spec 文档。
后端自动依赖与工具同版本的 `yuanboot[admin]`，可通过 `--framework-version` 显式选择版本。

## 启动

后端（Python 3.6.2+）：

```bash
cd my-admin-server
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
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

## 安装依赖与运行

0.3.3 起，在管理后台项目根目录执行以下命令即可管理后端：

```bash
cd my-admin
yuanbootctl-python install
yuanbootctl-python run
yuanbootctl-python build
```

CLI 自动定位 `my-admin-server/pyproject.toml`。`install` 在后端创建或复用 `.venv`，
仅安装运行依赖；Python 3.6 / 3.7 自动选择兼容的 pip 和组件版本。
`run` 会检查声明的依赖及组件 extras，缺失或版本不匹配时先安装再启动。
`run` 只运行，不构建业务项目；`install` 和 `run` 不安装业务包，不生成业务 `egg-info`、`build/` 或 `dist/`。
仅执行 `build` 时安装构建工具并生成 wheel / sdist。已有依赖完整的环境会直接复用。

新建时可一次完成后端依赖安装：

```bash
yuanbootctl-python new admin -n my-admin --install
```

`install --python /path/to/python3.7` 可选择创建虚拟环境所用的解释器；
`run --python` / `build --python` 可选择指定的运行环境，依赖缺失时安装到该环境。
`--index-url` 可指定包索引，也会沿用已有 pip 配置和 `PIP_INDEX_URL` 环境变量。
更改依赖后可执行 `install` 或 `run --install` 重新安装。

前端在 `my-admin-web` 执行 `pnpm install --frozen-lockfile && pnpm dev`。

## requirements.txt 与依赖维护

仍可直接使用标准 pip 命令：

```bash
python -m pip install -r requirements.txt
```

普通项目在项目根目录执行；Admin 在管理后台根目录或后端目录执行均可。
生成的 requirements.txt 直接声明运行依赖，Admin 根目录通过 `-r` 引用后端文件。
CLI 将后端文件的标记区与 pyproject.toml 的运行依赖同步；标记区外保留业务追加内容。
业务依赖可写在项目 pyproject.toml，也可追加到 requirements.txt；嵌套的 `-r` / `-c` 文件由 pip 解析。
业务 wheel 的运行依赖以 pyproject.toml 为准；requirements.txt 可补充部署和开发环境依赖。
CLI 会同时检查和安装 Admin 根目录、后端目录中的 requirements.txt，保留已有内容。
旧模板缺少依赖文件时自动补齐；旧模板中的项目自身 `-e .[dev]` 引用自动迁移为运行依赖，保留其他条目。

框架组件及兼容版本统一在框架仓库的 pyproject.toml 维护。
构建工具版本集中在 `yuanboot[build]`，生成项目的 `[dev]` 引用同版本的这一依赖组。
脚手架只写入框架版本引用，安装流程共用 CLI 的 environment.py 实现。

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
