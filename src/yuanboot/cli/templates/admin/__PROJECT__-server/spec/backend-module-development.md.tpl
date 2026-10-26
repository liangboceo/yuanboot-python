# __PROJECT__ 后端模块开发规范

本文约定本项目的业务分层、服务注册、参数校验、数据访问和接口行为。
项目模板为 `webapi`，Python 包名为 `__PACKAGE__`；框架说明见 [yuanboot-python](yuanboot-python.md)，组件配置见 [核心组件](components.md)。

## 目录与分层

```text
__PROJECT__/
├── __PACKAGE__/          # 应用代码，入口 main.py
│   ├── main.py          # 配置、组件和宿主创建
│   └── ...              # 控制器、服务、后台任务等模块
├── config.yml           # 基础配置
├── config_dev.yml       # 开发环境
├── config_fat.yml       # 联调环境
├── config_uat.yml       # 验收环境
├── config_pro.yml       # 生产环境
├── spec/                # 框架说明和业务规范
├── pyproject.toml       # 项目信息、依赖和运行入口
└── README.md            # 项目说明
```

Web 项目可以沿用 `startup.py`、`controllers.py` / `endpoints.py`、`services.py`，
业务规模增长后再拆分 `modules/<module>/`。Console 和 gRPC 项目沿用各自的 Worker / RPC 入口，按相同原则组织业务服务。

| 层 | 职责 |
| --- | --- |
| Controller / Endpoint / RPC | 接收请求、校验参数、调用服务、转换响应 |
| DTO / Schema | 定义输入和输出结构、字段约束 |
| Service | 业务规则、事务边界、缓存与外部服务协调 |
| Repository | 数据查询、写入和模型转换 |
| Model | 数据库映射与持久化字段 |

入口层保持简洁；共享业务逻辑集中到 Service，数据库访问集中到 Repository。

## 命名与类型

- Python 模块、函数和字段采用 `snake_case`，类采用 `PascalCase`。
- 按业务命名，例如 `OrderController`、`OrderService`、`OrderRepository`。
- 请求、响应和公开服务方法提供类型标注。
- HTTP 请求体使用 Pydantic 模型，声明长度、范围及必填规则。
- 对外字段采用项目统一约定，Python 字段需要别名时通过 Pydantic `Field(alias=...)` 声明。

## 依赖注入

```python
class OrderService:
    def describe(self, order_id: int) -> dict:
        return {"id": order_id}


# 在 Startup.configure_services 中注册：
# services.add_scoped(OrderService)
```

无状态业务服务、请求级 Repository 和数据库 Session 使用 scoped。
连接池、Redis 客户端等由框架组件按 singleton 管理。
singleton 不能持有 scoped 服务；后台任务需要请求级资源时，单独创建并关闭作用域。
通过构造器注入依赖，避免将容器或全局客户端散落在业务代码中。

## HTTP 接口

MVC 模块可按以下方式注册控制器：

```python
from fastapi import Path
from yuanboot.web import ApiController, controller, route


@controller("/api/orders", tags=["订单"])
class OrderController(ApiController):
    def __init__(self, service: OrderService):
        self.service = service

    @route("/{order_id}", methods=["GET"])
    def detail(self, order_id: int = Path(gt=0)):
        return self.ok(self.service.describe(order_id))


# 在 Startup.configure 中注册：
# app.use_mvc(lambda mvc: mvc.add_controller(OrderController))
```

Web API 模板也可通过 `RouterBuilder` 和 `inject(Service)` 注册路由及依赖。
保持同一业务模块的 URL、标签、响应结构一致；参数校验交给 Pydantic / FastAPI。
使用 HTTP 状态表达错误：参数错误返回 422，资源不存在返回 404，状态冲突返回 409。
业务错误通过明确的异常或响应处理，服务端内部异常记录日志，不向客户端暴露连接串或堆栈。

分页接口建议统一使用 `page`、`page_size`，限制最大页大小，响应包含 `items` 和 `total`。
列表查询提供稳定排序，过滤条件使用绑定参数，避免拼接外部输入生成 SQL。

## 数据模型与事务

- MySQL 使用 SQLAlchemy Core / ORM，表结构及迁移由业务项目管理。
- 根据业务需要定义主键、创建时间、更新时间和审计字段。
- 如采用软删除，统一约定删除字段并在查询中明确过滤。
- 多表写入的事务由 Service 协调，失败时整体回滚。
- Repository 不擅自提交由上层拥有的事务，不跨请求复用 Session。
- 同步数据库操作使用同步动作或线程池，避免阻塞 async 路由的事件循环。

## Redis 与并发

缓存键使用应用和业务前缀，例如 `__PROJECT__:orders:summary`，根据数据性质设置 TTL。
缓存失效与数据库写入保持明确顺序；关键业务以数据库或业务约定的数据源为准。
分布式锁设置超时，使用框架锁的上下文管理器释放，避免错误释放其他持有者的锁。
幂等规则使用业务唯一键、数据库约束或专门的幂等记录实现。

## 配置、日志与部署

环境固定为 `dev / fat / uat / pro`，连接地址和敏感信息通过配置及环境变量提供。
Nacos 注册的 `yuanboot_env` 使用当前部署环境，应用名和服务端口与实际部署一致。
配置热更新用于可动态读取的业务参数；连接池、端口和注册中心连接变更需要重启。

日志使用标准 `logging.getLogger(__name__)`，保留框架的 Request ID 和结构化日志。
避免记录密码、令牌、完整连接串及其他敏感数据。
后台任务和调度器在每个 worker / 副本中分别运行，需要唯一执行的任务通过外部协调实现。

新增或修改业务模块时，同步更新接口说明、配置要求和本目录的业务文档。
