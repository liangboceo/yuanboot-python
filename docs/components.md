# 组件使用与 Go 实现对应

安装 `yuanboot[all]` 启用所有可选组件，或按需选择 `mysql,redis,nacos,jwt,http,apollo,scheduler,grpc,discovery,xxljob`。
Python 版采用 Python SDK 和标准库表达 Go 版的能力，不照搬 goroutine、GORM、Viper 的内部实现。

## 对应清单与验证范围

| Go 模块 | Python 实现 | 验证与边界 |
| --- | --- | --- |
| abstractions / console / dependencyinjection | HostBuilder、生命周期、DI、作用域、事件 | 自动测试，启动失败回滚与退出清理 |
| web / MVC / Swagger / JWT / actuator | FastAPI、控制器、签名绑定、JWT、健康、Prometheus | 自动测试和真实 HTTP；支持原生 WebSocket、CORS、静态文件与视图 |
| cli/yuanbootctl | 六类模板、new/run/build/version、Git tag 依赖 | 每个模板生成后实际执行测试 |
| configuration / OptionsSnapshot | 分层配置、bind、options().current_value、热更新 | 原子替换，错误保留旧快照 |
| configuration/nacos | Nacos HTTP OpenAPI、认证、重载 | 用户 Nacos 2.4.3 实服联调 |
| configuration/apollo | Apollo HTTP 配置、签名、轮询 | 协议测试，未做 Apollo 实服联调 |
| datasources/mysql / GORM | SQLAlchemy Core/ORM、池、事务、请求级 Session | MySQL 实服提交/回滚/业务测试 |
| cache/redis / datasources/redis | redis-py、JSON TTL、锁、原生 Redis API | Redis 实服缓存/TTL/锁；Cluster 配置未做集群实测 |
| xlog | 标准 logging、JSON/text、文件轮转、级别、request_id | 格式、脱敏、文件与请求测试 |
| servicediscovery/nacos | 注册、心跳、下线、查询、监听、选择 | 实服验证，metadata 与 Go 八字段一致 |
| servicediscovery/memory | MemoryDiscovery | 自动测试，限当前进程 |
| servicediscovery/consul、eureka、etcd | HTTP/JSON 协议适配 | 请求契约测试；尚未接入对应实服，etcd 需要 v3 JSON gateway |
| servicediscovery/strategy | round-robin、按实例权重 random | 已实现；Go weight-time 策略与发现缓存暂未移植 |
| httpclient | HttpClientFactory、池、JSON/form/multipart、lb:// 发现 | 协议测试；同步 API，async 路由用线程池调用 |
| task | Scheduler、间隔任务、带秒 Cron、时区 | 自动测试，异常隔离、停机等待 |
| scheduler / XXL-Job | WebHost 的 BEAN 执行器、认证、注册、回调、日志、kill | 协议测试；仅协作取消 async handler；无脚本 GLUE、持久化回调重试队列和高级阻塞策略 |
| email | SMTP、TLS、文本/HTML、附件 | 构造与连接流程测试；未实际发送邮件 |
| mq/observer | Observer 异步广播 | 自动测试；Go 此模块也只是进程内广播，不是消息代理 |
| grpc | grpc.aio、DI/宿主、TLS/interceptors、健康、通道工厂 | 本机真实 protobuf RPC；每次创建 lb 通道时发现实例 |
| captcha、utils、二进制序列化工具 | 暂未逐个移植 | 可按业务需要接入 Python 库 |
| IoT/Kafka、admin 业务示例 | 暂未移植 | 不包含在本框架组件交付范围内 |

## 统一启用组件

```python
builder = ConfigurationBuilder().add_yaml_file().add_environment()
bootstrap = builder.build()
configuration = builder.add_nacos().build()  # 从本地 bootstrap 读取 Nacos 连接信息
host = WebHostBuilder(configuration).use_components().use_startup(Startup()).build()
```

`use_components()` 根据已合并配置启用日志、MySQL、Redis、注册中心、HTTP 客户端和 SMTP；
也可明确调用 `.use_mysql().use_redis().use_nacos_discovery().use_logging()`。
远程配置必须在 build 前加入 ConfigurationBuilder，后台监视器随宿主启动。
调度任务需代码注册，XXL-Job 需 `use_xxl_job(builder, handlers)` 显式挂载。

```yaml
yuanboot:
  application:
    name: orders
    server:
      address: ":8080"
      path: ""
  logging:
    level: INFO
    json: true
    console: true
    file: ./logs/application.log
    max_bytes: 10485760
    backup_count: 5
    levels:
      sqlalchemy.engine: WARNING
  datasource:
    mysql:
      host: "${MYSQL_HOST}"
      port: 3306
      database: orders
      username: "${MYSQL_USERNAME}"
      password: "${MYSQL_PASSWORD}"
      pool_size: 5
      max_overflow: 10
      pool_recycle: 1800
    redis:
      url: "${REDIS_URL:redis://127.0.0.1:6379}"
      password: "${REDIS_PASSWORD:}"
      prefix: "orders:"
      db: 0
  cloud:
    nacos:
      server_addr: "${NACOS_SERVER_ADDR:http://127.0.0.1:8848}"
      username: "${NACOS_USERNAME:}"
      password: "${NACOS_PASSWORD:}"
      namespace: public
      group: DEFAULT_GROUP
      cluster: DEFAULT
      data_id: orders.yml
      poll_interval: 5
    discovery:
      type: nacos
      # ip: 10.0.0.10  # 默认根据到 Nacos 的路由探测本机地址
      heartbeat_interval: 5
      register-enable: true
      instance_metadata:
        region: cn
```

MySQL 数据库需要预先创建；业务表由应用管理。支持 Go 的 `datasource.db.type=mysql`、
`url: tcp(host:port)/database?charset=utf8mb4`、`max_open_conns`、`max_idle_conns`、`conn_max_lifetime`。
连接池使用 SQLAlchemy 的 `pool_size + max_overflow`；Go 的无限连接、空闲回收细节并非逐项等价。
Redis 支持 Go 的 `host:port` URL，Cluster 用 `cluster: true` 且 db=0。

## MySQL、Redis 与请求作用域

```python
from sqlalchemy import text
from sqlalchemy.orm import Session
from yuanboot.components.mysql import MySqlDataSource
from yuanboot.components.redis import RedisCache, RedisDataSource

# MySqlDataSource 是 singleton；Session 是 scoped。
with source.transaction() as connection:
    connection.execute(
        text("UPDATE orders SET status=:value WHERE id=:id"), {"value": "done", "id": 1}
    )

cache.set_json("summary", {"total": 10}, ttl=30)
value = cache.get_json("summary")
with cache.lock("summary-refresh", timeout=30, blocking_timeout=2):
    pass

# RedisDataSource.client 是完整 redis-py 客户端。
# hash/list/set/zset/geo/streams/pipeline/pubsub 使用原生 API；原始 key 需自行加 prefix。
```

同步数据库/Redis 调用放在 FastAPI 同步动作中，或从 async 动作使用线程池调用。
容器管理池的关闭；事务出错回滚；Session 随请求结束关闭。锁释放校验持有者 token。

## 配置中心与热更新

默认优先级为本地配置 < 远程源 < 环境 < flags。支持 YAML/JSON、多个来源和 `${ENV:default}`。
轮询更改后先完整解析，再原子替换；无效文档、网络错误保留上一次可用快照，健康检查反映错误。
`configuration.on_change(callback)` 注册同步回调；异步订阅生命周期 `configuration_changed` 事件。
`configuration.options(MySettings, "section").current_value` 每次重新绑定当前快照。

业务每次读取 configuration 时会看到新值；**已经创建的连接池、日志处理器、监听端口、注册中心连接配置需要重启**。
这不是基础设施的自动重连/迁移机制。bootstrap Nacos 地址应保存在本地配置/环境中。

Apollo 使用：

```python
from yuanboot.components.apollo import ApolloOptions

configuration = (
    ConfigurationBuilder()
    .add_yaml_file()
    .add_environment()
    .add_apollo(ApolloOptions(appid="orders", endpoint="http://apollo:8080"))
    .build()
)
```

## Nacos metadata 与注册

严格保留 Go registrar 的默认字段和值，所有 metadata 值为字符串：

| 字段 | 默认值来源 |
| --- | --- |
| yuanboot_version | 框架版本 |
| yuanboot_env | 部署环境 dev / fat / uat / pro |
| yuanboot_author | jackson |
| yuanboot_application_description | quickly,quickly,quickly,quickly,quickly!!!!! |
| yuanboot_application_context-path | discovery.metadata.path，回退 application.server.path |
| yuanboot_application_pid | PID 字符串 |
| yuanboot_application_create_time | 本地时间 YYYY-MM-DD HH:mm:ss |
| yuanboot_application_name | 应用名 |

权重 10，enabled/healthy/ephemeral 为 true；group/cluster 空值回退 DEFAULT_GROUP/DEFAULT。
自定义 `instance_metadata` 可覆盖字段。context-path 是注册描述，实际 HTTP 挂载路径需由路由配置。
兼容 Go 的 `cloud.discovery.metadata.url/port/namespace/group/cluster/auth/configserver.dataid` bootstrap 结构。
所有组件完成启动后注册；正常退出注销；心跳故障后重试，实例丢失重新注册。
多实例同名同 IP 必须使用不同端口；`register-enable: false` 可作为只发现不注册的客户端。
gRPC 服务注册需使用真实 RPC 监听端口；显式配置 discovery.port 可以覆盖。

其他注册中心改 `discovery.type` 为 `memory/consul/eureka/etcd`，连接地址使用
`discovery.metadata.server_addr`，兼容 `address`。支持单 endpoint；地址列表目前取首个。
etcd 凭据通过 `metadata.auth` 或 username/password；Consul token 用 `metadata.token`。

## HTTP、任务与消息

```python
from yuanboot.components.httpclient import HttpClientFactory
from yuanboot.components.observer import Observer

# builder.use_http_client()，从 DI 解析工厂；关闭宿主会关闭已创建客户端。
client = factory.create("lb://inventory")
response = client.get("/items", params={"page": 1})
response.raise_for_status()

host = (
    HostBuilder()
    .use_scheduler(lambda scheduler: scheduler.add("refresh", refresh, interval=30))
    .build()
)
# Cron 与 Go 相同：秒 分 时 日 月 [星期]，星期 0=周日。
# scheduler.add("daily", refresh, cron="0 0 2 * * *", timezone="Asia/Shanghai")

observer = Observer()
subscription = observer.subscribe(capacity=100)
observer.publish({"type": "changed"})
# async for event in subscription: ...
subscription.close()
observer.close()
```

定时任务同名不重叠执行，异常记录后继续；多个进程各自执行，唯一执行需 Redis 锁/外部调度。
广播仅限同一事件循环，满队列抛出 QueueFull，关闭唤醒消费者，结束时可能舍弃末尾缓存消息。
SMTP 通过 `SmtpClient.send` 或 `.use_email()` 使用；需要提供可用 SMTP 服务并显式调用发送。

## gRPC 与 XXL-Job

```python
from yuanboot.grpc import GrpcHostBuilder

host = (
    GrpcHostBuilder(configuration)
    .use_components()
    .configure_server(register_generated_servicers)
    .build()
)
# register_generated_servicers(server, services) 在事件循环中调用，可解析 DI 服务。
```

gRPC 地址配置 `yuanboot.grpc.address`。支持 `configure_server(..., interceptors=..., credentials=...)`；
业务生成的 protobuf servicer 可直接注册到 grpc.aio server。`yuanbootctl new grpc` 的示例无需 protoc 即可运行。

```python
from yuanboot.components.xxljob import use_xxl_job


async def sync_orders(context):
    context.report("started")
    return "done"


builder = use_xxl_job(WebHostBuilder(configuration), {"syncOrders": sync_orders})
```

XXL 配置在 `yuanboot.application.xxl`：`admin_url`、`access_token`、`registry_key`、
`executor_url`（例如 http://worker:8080/xxl-job/）、`log_dir`。
兼容 Go 的 serverAddr/accessToken/registryKey 名称；监听端口由当前 WebHost 管理。
支持 `/xxl-job/beat`、idleBeat、run、kill、log，支持 BEAN 分片参数、日志与结果回调。
正在执行同 jobId 时返回 busy；回调只在内存重试，进程退出/崩溃不保证补发；生产接入需按场景补持久化策略。
