# yuanboot-python 使用说明

yuanboot-python 作者：jackson liang。Copyright (c) 2026 jackson liang。

本文为 `__PROJECT__` 随项目附带的框架开发文档。生成工具版本 `__YUANBOOT_VERSION__`，框架依赖 `__FRAMEWORK_REF__`。
项目依赖以 `pyproject.toml` 为准；升级依赖后应同步检查项目中的文档。

## 框架概述

yuanboot-python 是基于 FastAPI、Uvicorn 和依赖注入的 Python 微服务框架，支持 Web API、MVC、gRPC 和后台服务。
框架统一管理配置、依赖作用域、组件资源和宿主生命周期。

## 文档导航

- [核心组件](components.md)：MySQL、Redis、Nacos、日志、服务发现、任务与通信。
- [后端模块开发规范](backend-module-development.md)：业务分层、DTO、接口和持久化约定。
- [项目说明](../README.md)：安装、启动和环境选择。

## 项目命令

```bash
yuanbootctl-python run --profile dev
yuanbootctl-python build
```

项目运行入口由 `pyproject.toml` 的 `[tool.yuanboot]` 决定。
Web 项目支持 `--host`、`--port`、`--reload` 和 `--workers`。
Console / gRPC 项目使用各自的 module 入口，Console 不使用 Web 启动参数。
独立二进制直接运行默认模板；增加其他 Python 依赖后，可通过 `--python /path/to/python` 指定业务环境。
`build` 生成业务 wheel / sdist，需要安装 `build` 的 Python 环境。

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

`use_actuator(router)` 提供以下运维端点：

| 路径 | 行为 |
| --- | --- |
| `/actuator/health/detail` | 健康检查，失败 HTTP 503 |
| `/actuator/health/readiness` | hosted services 完成启动后返回 up，异常/停机 HTTP 503 |
| `/actuator/health/liveness` | 进程存活 |
| `/actuator/prometheus` | 请求计数和耗时分布，按路由模板聚合 |
| `/docs`、`/openapi.json` | FastAPI 原生接口文档 |

独立 `use_health(router, {"database": check_db})` 支持自定义同步/异步检查和超时。
默认请求中间件生成/透传 `X-Request-ID`、记录访问耗时、回收请求作用域，并把未处理异常转换为不含异常堆栈的 JSON 500。日志使用统一的 zap / logrus 文本或 JSON 格式，并关联 Request ID。
宿主启动与 Swagger 文档显示框架版本、版权和 MIT 许可，详细配置见核心组件文档。
可选 `pip install -e ".[jwt]"` 后使用 `yuanboot.web.security.JwtBearer` 作为 FastAPI Security 依赖验证 JWT。


## PyCharm 调试与直接运行

模板提供项目根目录 `main.py` 和 `.run/yuanboot.run.xml`。
使用项目虚拟环境安装 `pip install -e '.[dev]'` 后，直接运行或 Debug 根目录 `main.py`，
也可从项目根目录执行 `python -m __PACKAGE__.main`（将 `__PACKAGE__` 替换为业务包名）。
PyCharm 手动配置使用 Module name `__PACKAGE__.main`，Working directory 选择项目根目录。
包内入口使用绝对导入，业务项目安装后也支持直接运行 `__PACKAGE__/main.py`。
配置优先读取当前目录的 `config.yml`，当前目录没有配置时回退到项目根目录。
