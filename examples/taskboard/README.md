# Taskboard 任务管理服务

使用 **yuanbootctl 生成的 MVC 模板**开发的业务项目：FastAPI + yuanboot DI/MVC。
环境名统一为 `dev / fat / uat / pro`，默认 `dev`；默认存储为 SQLite。
通过 `TASKBOARD_INFRASTRUCTURE=remote` 独立启用 MySQL、Redis、Nacos 配置/注册和 JSON 日志，连接配置位于 `infrastructure.yml`。
环境名与连接方式相互独立，Nacos 的 `yuanboot_env` 始终使用实际环境名。
支持任务增删改查、状态流转、关键字搜索、分页、状态统计和重启后数据持久化。
交互入口为 Swagger API 文档，可直接在浏览器中创建和管理任务。

生成命令（已执行，当前目录为其开发结果）：

```bash
yuanbootctl new mvc -n taskboard -p examples
```

## 启动

从仓库根目录运行：

```bash
source .venv/bin/activate
python -m pip install -e '.[dev,all]'
python -m pip install --no-deps -e './examples/taskboard'
yuanbootctl run -p examples/taskboard --host 127.0.0.1 --port 8080
```

也可直接执行仓库中的 `./scripts/run_taskboard.sh`。
访问 [接口文档](http://127.0.0.1:8080/docs)，在接口下点击 **Try it out** 执行操作。
根地址会自动跳转到接口文档。Ctrl+C 停止，任务仍保存在数据库中。

项目目录独立运行：

```bash
cd examples/taskboard
../../.venv/bin/yuanbootctl run --host 127.0.0.1 --port 8080
../../.venv/bin/python -m pytest -q
../../.venv/bin/yuanbootctl build
```

## API

| 方法 | 地址 | 功能 |
| --- | --- | --- |
| POST | `/api/tasks` | 创建，返回 201 |
| GET | `/api/tasks?page=1&page_size=20&status=todo&q=关键词` | 分页、状态筛选、搜索 |
| GET | `/api/tasks/stats` | 各状态任务数量 |
| GET | `/api/tasks/{id}` | 详情 |
| PATCH | `/api/tasks/{id}` | 更新标题、描述、状态 |
| DELETE | `/api/tasks/{id}` | 删除，返回 204 |
| GET | `/actuator/health/readiness` | 就绪状态 |
| GET | `/actuator/prometheus` | 请求计数与耗时 |
| GET | `/api/runtime` | profile、配置版本及示例消息（不返回凭据） |

状态：`todo` → `in_progress` → `done`，也可以在这三种状态间调整。
返回统一使用 `{success, message, data}`；删除成功返回空响应。
不存在的任务返回 404，字段或查询参数不合法返回 422。
标题自动去除首尾空白，限制 1–200 字符；描述最多 5000 字符。
PATCH 至少提供一个字段，不接受 null，清空描述使用空字符串。

```bash
curl -X POST http://127.0.0.1:8080/api/tasks \
  -H 'Content-Type: application/json' \
  -d '{"title":"完成第一个 yuanboot 应用","description":"从模板到运行"}'

curl 'http://127.0.0.1:8080/api/tasks?status=todo&page=1&page_size=10'
curl http://127.0.0.1:8080/api/tasks/stats
```

## 结构与持久化

- `taskboard/main.py`：应用工厂、配置和 HostBuilder。
- `taskboard/startup.py`：注册服务、控制器、运维端点和 404 处理器。
- `taskboard/controllers.py`：MVC 动作、请求绑定与响应模型。
- `taskboard/services.py`：业务逻辑。
- `taskboard/repository.py`：参数化 SQL、分页与统计。
- `taskboard/database.py`：宿主启动时初始化表，按请求创建和关闭数据库连接。
- `taskboard/cloud.py`：MySQL 任务仓储和 Redis 统计缓存，写入后失效，缓存故障回退数据库。
- `taskboard/models.py`：Pydantic 请求/响应模型。
- `tests/`：15 项业务测试，使用临时数据库。

默认数据库 `./data/taskboard.db`，相对运行项目目录；首次启动自动建表并启用 WAL。
通过 `YUANBOOT_DATABASE__PATH=/path/to/tasks.db` 覆盖；生产配置也支持 `TASKBOARD_DATABASE`。
本项目作为本地单用户业务示例；网络部署需要接入业务自己的认证和权限控制。

## Nacos / MySQL / Redis 联调

框架默认使用 Git tag 依赖，单独安装项目时执行 `pip install -e '.[dev,cloud]'`。
本仓库本地开发按上文先安装框架再 `--no-deps` 安装业务，避免拉取远程框架覆盖正在调试的代码。
项目已提供 `uv.lock`，固定框架 `v0.1.2` 对应的 commit 和传递依赖；可在项目目录运行
`uv sync --frozen --extra dev --extra cloud` 复现依赖，再用
`TASKBOARD_INFRASTRUCTURE=remote uv run --frozen --extra cloud yuanbootctl run --profile fat` 启动。
这里 `cloud` 仅是安装组件的 extras 名称，环境由 `--profile` 指定。
当前锁文件使用清华 PyPI 镜像；重新生成时使用 `uv lock --default-index https://pypi.tuna.tsinghua.edu.cn/simple`，
也可选择其他镜像并重新生成、验证锁文件。

从仓库根目录执行：

```bash
# 根据 .env.example 创建本地 .env.integration，填入测试连接；该文件不提交。
set -a
. ./.env.integration
set +a
python scripts/setup_cloud_demo.py
./scripts/run_taskboard_cloud.sh
# 联调脚本默认使用 fat，可覆盖为 dev / uat / pro：
./scripts/run_taskboard_cloud.sh --profile uat
```

setup 脚本只创建专用数据库 `yuanboot_python_taskboard`，不改动其他库；Nacos 配置已存在时保留原文档。
`nacos-config.example.yml` 是发布到配置中心的示例文档，凭据保留为环境变量引用。
当前联调资源：Nacos group `YUANBOOT_PYTHON_DEMO`，data ID `yuanboot-python-taskboard.yml`，
服务名 `yuanboot-python-taskboard`，MySQL 表 `taskboard_tasks`，Redis key 前缀 `yuanboot-python-taskboard:`。
日志在 `examples/taskboard/data/logs/application.log`，默认 10MB 轮转，保留 5 份。

修改 Nacos 文档中的 `demo.message`，约 2 秒后 `/api/runtime` 可看到消息和配置版本更新。
更改 MySQL/Redis 连接信息、监听地址等基础设施配置需要重启。
Nacos 注册使用本机 LAN 地址和 8080 端口，metadata 与 Go 版八字段对齐，默认权重 10。
正常停止会注销实例，再次启动后业务数据保留。

## Docker

在仓库根目录构建，框架从本地源码安装：

```bash
docker compose -f examples/taskboard/docker-compose.yml up --build
```

使用命名卷保存数据库。Docker 配置已提供，本次验证范围为本机 Python 运行。

## 验证记录

框架与全部模板、业务项目 SQLite 模式和 MySQL/Redis 模式均有自动测试。
`verification.json` 记录本机 8080 端口的真实 HTTP 验证，包括创建、更新、查询、删除、404、422、就绪检查和文档访问。
仓库根目录 `reports/components-integration.json` 记录 MySQL/Redis/Nacos 实服测试与临时资源清理。

```bash
# SQLite 测试
python -m pytest -q examples/taskboard/tests
# 载入 .env.integration 后执行实际 MySQL/Redis 业务测试，每次使用独立临时 schema/key。
TASKBOARD_TEST_CLOUD=1 python -m pytest -q examples/taskboard/tests
python scripts/verify_components.py
```
