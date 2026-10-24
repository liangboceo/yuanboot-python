# yuanboot Python

参照本地 Go 版 `yuanboot` 的实现逻辑，以 **FastAPI + Uvicorn** 为 HTTP 底座的轻量微服务框架。Python 3.11+。

已使用 `yuanbootctl new mvc -n taskboard -p examples` 生成模板并开发完成
[Taskboard 任务管理项目](examples/taskboard/README.md)，支持 MySQL/SQLite 持久化、Redis 缓存、Nacos 配置热更新与注册、CRUD、筛选分页和业务测试。
安装后可用 `./scripts/run_taskboard.sh` 启动，访问 `http://127.0.0.1:8080/docs` 操作。

保留 Go 版的 `HostBuilder → ConfigureServices → Configure → Build → Run` 流程，采用 Python 的 snake_case API。FastAPI 原生的 `Depends`、Pydantic 参数校验、OpenAPI、WebSocket 和 ASGI 中间件可以直接使用。

## 安装与创建项目

```bash
cd /Users/liangbo/Documents/develop/yuanboot_python
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev,all]"

yuanbootctl new --list
yuanbootctl new webapi -n demo -p /tmp
cd /tmp/demo
python -m pip install -e ".[dev]"
yuanbootctl run --reload
```

访问 `http://127.0.0.1:8080/docs`；调用示例：

```bash
curl http://127.0.0.1:8080/info
curl -X POST http://127.0.0.1:8080/api/greet \
  -H 'Content-Type: application/json' -d '{"name":"yuanboot"}'
```

框架仓库：[liangboceo/yuanboot-python](https://github.com/liangboceo/yuanboot-python)，默认分支 `master`。
业务项目默认以 Git tag 固定框架版本，无需发布 PyPI：

```bash
python -m pip install 'yuanboot[all] @ git+https://github.com/liangboceo/yuanboot-python.git@v0.1.2'
yuanbootctl new mvc -n orders --framework-ref v0.1.2
```

框架版本只维护在 `src/yuanboot/_version.py`；业务版本独立维护。
详见 [组件使用与移植范围](docs/components.md)、[Git 发布和依赖管理](docs/releases.md)。

| 模板 | 内容 |
| --- | --- |
| `simpleweb` | 最小 HTTP 应用、运维端点 |
| `webapi` | 路由分组、服务注入、Pydantic 请求校验 |
| `mvc` | 控制器自动注册、构造器注入、Jinja2 页面 |
| `microservice` | Web API、Prometheus、受宿主管理的后台服务 |
| `console` | 无 HTTP 的宿主、后台任务与信号退出 |
| `grpc` | protobuf RPC、健康检查、共享 DI 和宿主生命周期 |

每个模板包括 pyproject、配置、测试、Dockerfile、docker-compose 和使用说明。

```bash
yuanbootctl new mvc -n my-app -p /tmp
yuanbootctl new console -n worker -p /tmp
yuanbootctl new grpc -n rpc-demo -p /tmp
yuanbootctl new webapi -n orders --framework-ref v0.1.2
yuanbootctl run --profile pro --port 9000
yuanbootctl run --workers 2
yuanbootctl build                 # python -m build，输出 wheel/sdist
yuanbootctl version
python -m yuanboot new --list     # 等价入口
```

`run` 在项目目录读取 `[tool.yuanboot]`，通过当前 Python 解释器启动 Uvicorn 或 console module；支持 reload、多 worker、TLS 配置。console 使用 Ctrl+C / SIGTERM 停止。已有目录不会被模板生成器覆盖。

## 最小应用

```python
from yuanboot.web import RouterBuilder, create_default_builder
from yuanboot.web.endpoints import use_actuator


def endpoints(router: RouterBuilder):
    use_actuator(router)

    @router.get("/info")
    def info():
        return {"info": "ok"}


host = create_default_builder(endpoints).build()
app = host.app  # uvicorn main:app

if __name__ == "__main__":
    host.run()  # 默认 0.0.0.0:8080
```

`WebApplication` 本身也实现 ASGI，可直接传给 TestClient。每个应用实例只运行一个生命周期；测试时通过工厂创建新的应用。

## 配置

```python
from yuanboot import ConfigurationBuilder

config = (
    ConfigurationBuilder(".")
    .add_defaults({"greeting": {"message": "hello"}})
    .add_yaml_file("config")
    .add_environment()
    .add_flag_args()  # 显式启用，避免干扰宿主/测试的参数
    .build()
)
```

优先级：默认值 < `config.yml` < `config_<profile>.yml` < 远程配置（Nacos/Apollo/自定义源）< 环境变量 < CLI。
profile 默认 `dev`，通过 `build(profile="pro")`、`YUANBOOT_PROFILE` 或 `--profile` 选择；profile 文件与基础文件递归合并。
环境名统一为 `dev / fat / uat / pro`，其他值会在启动前报错。模板包含这四个环境的配置文件。
MySQL、Redis、Nacos 等基础设施由配置决定，不能使用 `cloud` 作为环境名。
支持 JSON、可选文件、`${ENV:default}` 插值、点路径查询和 Pydantic 模型绑定。

```yaml
yuanboot:
  application:
    name: demo
    server:
      address: ":8080"
      # 也可使用 host/port（不要同时设置 address）
      # tls:
      #   cert: ./cert.pem
      #   key: ./key.pem
database:
  url: "${DATABASE_URL:sqlite:///demo.db}"
```

`YUANBOOT_DATABASE__URL` 对应 `database.url`；双下划线表示层级。
完整框架键以 `YUANBOOT_YUANBOOT__APPLICATION__NAME` 覆盖，常用名称和端口有短写 `YUANBOOT_APP`、`YUANBOOT_PORT`。
配置值可通过 `get_string/get_int/get_bool/get_section` 读取；`config.bind(MySettings, "database")` 校验为 Pydantic 模型。
缺失必需文件、未提供默认值的环境插值及错误配置会立即报错。
显式启用 flag 解析时支持 `--app --port --profile --conf -f`，忽略其他工具的参数。
模板默认从**当前项目目录**读取配置，运行已打包项目时也应提供外部配置文件。

## 依赖注入

```python
from typing import Annotated
from yuanboot import Configuration, ServiceCollection
from yuanboot.web import WebHostBuilder, inject


class GreetingService:
    def __init__(self, config: Configuration):
        self.config = config


def services(collection: ServiceCollection):
    collection.add_scoped(GreetingService)


def endpoints(router):
    @router.get("/hello")
    def hello(service: Annotated[GreetingService, inject(GreetingService)]):
        return {"message": service.config.get_string("greeting.message", "hello")}


host = (
    WebHostBuilder()
    .configure_services(services)
    .configure(lambda app: app.use_endpoints(endpoints))
    .build()
)
```

- `add_singleton(Service[, Implementation])`：整个宿主共享。
- `add_scoped(Service[, Implementation])`：同一请求共享；WebSocket 以整个连接为作用域。
- `add_transient(Service[, Implementation])`：每次解析创建。
- `add_singleton(Service, instance=value)`：注册外部对象，其资源由调用方管理。
- 工厂函数通过参数类型标注注入；注册相同类型时以最后一次注册为准。

检测循环依赖，禁止在根容器或 singleton 依赖链中解析 scoped 服务。同步工厂构建实例，异步初始化放入 hosted service 的 `start`。容器创建的资源按创建逆序调用 `aclose` / `close`，请求作用域覆盖流式响应和 FastAPI 后台响应任务。独立任务应自行使用 `async with host.services.create_scope() as scope`，避免持有已经结束的请求作用域。

`HttpContext` 可通过 `Depends(get_context)` 注入，提供 query、param、bind、json、request_id、services。WebSocket 服务注入使用 `inject_websocket`。

## MVC 和扩展

```python
from pydantic import BaseModel
from yuanboot.web import ApiController, ApiResult, controller, route


class GreetingRequest(BaseModel):
    name: str


@controller("/api", tags=["Greeting"])
class GreetingController(ApiController):
    def __init__(self, service: GreetingService):
        self.service = service

    @route("/greet", methods=["POST"])
    def greet(self, body: GreetingRequest) -> ApiResult[str]:
        return self.ok(body.name)


# app.use_mvc(lambda mvc: mvc.add_controller(GreetingController))
```

动作方法保留类型签名，由 FastAPI 处理 path/query/body 校验与 OpenAPI。默认控制器为 scoped，支持同步/异步动作及 FastAPI `Depends`（可实现鉴权或过滤器）。`route` 的额外参数传给 FastAPI `add_api_route`。

`ApplicationBuilder` 提供 `use_middleware`、`use_cors`、`use_static`、`use_views`；原生 FastAPI 通过 `builder.app` 扩展。`WebHostBuilder(..., docs_url=None)` 等参数直接传入 FastAPI。生命周期由框架管理，使用 hosted services 或生命周期事件扩展。

## 生命周期和后台服务

`HostBuilder` 与 `WebHostBuilder` 共享配置、DI 和生命周期实现。`use_startup` 接收带 `configure_services` / `configure` 方法的对象或无参类。

```python
import asyncio
from yuanboot import BackgroundService, HostBuilder


class Worker(BackgroundService):
    async def execute(self):
        try:
            while True:
                await asyncio.sleep(5)
        finally:
            pass  # 释放任务内部资源


host = (
    HostBuilder()
    .configure_services(lambda services: services.add_hosted_service(Worker))
    .on_application_life_event(
        lambda life: life.subscribe("started", lambda event: print(event.topic))
    )
    .build()
)
# host.run()
```

事件按 `starting → started → stopping → stopped` 顺序触发，支持同步/异步处理器。HostedService 依次启动、逆序停止；启动失败回滚，单个清理失败仍继续清理其余服务。后台任务异常会记录日志并令 readiness 失败；正常停止取消并等待任务。
多 worker / 多副本会各自运行后台服务；跨实例的唯一执行、调度和分布式锁应由业务协调。

## 运维与安全

`use_actuator(router)` 添加与 Go 版路径一致的端点：

| 路径 | 行为 |
| --- | --- |
| `/actuator/health/detail` | 健康检查，失败 HTTP 503 |
| `/actuator/health/readiness` | hosted services 完成启动后返回 up，异常/停机 HTTP 503 |
| `/actuator/health/liveness` | 进程存活 |
| `/actuator/prometheus` | 请求计数和耗时分布，按路由模板聚合 |
| `/docs`、`/openapi.json` | FastAPI 原生接口文档 |

独立 `use_health(router, {"database": check_db})` 支持自定义同步/异步检查和超时。
默认请求中间件生成/透传 `X-Request-ID`、记录访问耗时、回收请求作用域，并把未处理异常转换为不含异常堆栈的 JSON 500。日志使用标准 Python logging。
可选 `pip install -e ".[jwt]"` 后使用 `yuanboot.web.security.JwtBearer` 作为 FastAPI Security 依赖验证 JWT。

## 与 Go 实现的对应与范围

| Go | Python |
| --- | --- |
| `abstractions.HostBuilder` / `console` | `yuanboot.hosting` / `yuanboot.console` |
| `ConfigurationBuilder` / Viper | `ConfigurationBuilder` / YAML、JSON、环境和 flags |
| `dependencyinjection.ServiceCollection` | `yuanboot.dependency_injection.ServiceCollection` |
| `web.ApplicationBuilder` / router | `yuanboot.web.ApplicationBuilder` / `RouterBuilder` |
| MVC、自动模型绑定、Swagger | `@controller` / `@route`、Pydantic、FastAPI OpenAPI |
| `ApplicationLife` / `IHostService` | `ApplicationLife` / `HostedService` / `BackgroundService` |
| `cli/yuanbootctl` 模板注册与生成 | 包内模板资源、`yuanbootctl new/run/build/version` |

已提供六类模板，以及 MySQL、Redis、日志、Nacos 配置/注册、Apollo 配置、memory/Consul/Eureka/etcd 注册发现、HTTP 客户端、定时任务、SMTP、进程内广播、gRPC 和 XXL-Job BEAN 执行器。
MySQL、Redis、Nacos 使用实服验证；gRPC 使用本机真实 RPC 验证；其他远程适配器使用协议测试，尚未做对应服务的实服联调。
Go 的 IoT/Kafka 示例、完整 admin 前端、验证码和通用工具/二进制序列化封装未逐项复刻；XXL-Job 脚本 GLUE 和高级队列策略也未实现。
具体对应关系和边界见 [组件清单](docs/components.md)，不能据此声称与 Go 版所有模块完全等价。

```bash
python -m pytest
ruff check .
python -m build
python scripts/check_distribution.py
```
