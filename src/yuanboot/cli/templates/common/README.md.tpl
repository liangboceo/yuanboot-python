# __PROJECT__

基于 **yuanboot-python** 的 __TEMPLATE__ 项目，Python 3.11+。

## 项目文档

| 文档 | 内容 |
| --- | --- |
| [yuanboot-python](spec/yuanboot-python.md) | 框架使用说明、配置、依赖注入、MVC 和生命周期 |
| [核心组件](spec/components.md) | MySQL、Redis、Nacos、日志、服务发现与任务配置 |
| [后端模块开发规范](spec/backend-module-development.md) | 业务分层、DTO、路由、事务和接口约定 |

生成工具版本：`__YUANBOOT_VERSION__`；框架依赖引用：`__FRAMEWORK_REF__`。
文档随项目生成，可离线查阅；后续业务规范可在 `spec` 中补充。

## 快速启动

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
yuanbootctl-python run
```

框架通过 `pyproject.toml` 中的 Git tag 依赖安装，无需 PyPI。
项目的版本和框架版本各自维护。升级框架时修改 Git tag 并更新依赖 lock。
也可将框架依赖改为公开 PyPI 的 `yuanboot==<version>`，组件依赖使用 `yuanboot[all]==<version>`；
gRPC 项目的基础依赖使用 `yuanboot[grpc]==<version>`，版本应与需要的框架版本一致。
私有仓库需要配置 Git SSH/HTTPS 访问权限；默认 Dockerfile 适用于公开 HTTPS 仓库。
本地联调先安装完整框架 `pip install -e '/path/to/yuanboot_python[all]'`，
再用 `pip install --no-deps -e .` 安装业务代码。

也可用独立二进制直接运行默认模板：`/path/to/yuanbootctl-python run`。
项目引入额外依赖后，使用 `run --python /path/to/.venv/bin/python` 指定业务环境。

## 组件与构建

启用全部基础组件：`python -m pip install -e '.[dev,components]'`。
`main.py` 的 `use_components()` 自动读取 MySQL、Redis、Nacos 注册、日志等配置。
配置 `yuanboot.cloud.nacos.data_id` 后，Web/Console 模板会加载 Nacos 配置并监视更新。

```bash
yuanbootctl-python build
yuanbootctl-python run --profile pro
```

Web 模板：`http://127.0.0.1:8080/docs` 查看 API 文档，
`/actuator/health/readiness` 查看就绪状态。
Console 模板：运行后台任务，Ctrl+C 或 SIGTERM 优雅停止。
gRPC 模板：监听 `yuanboot.grpc.address`，默认 127.0.0.1:9090。

## 环境与配置

配置按 config.yml → config_<profile>.yml → YUANBOOT_ 环境变量覆盖。
环境固定为 dev / fat / uat / pro；模板包含对应的四份配置，默认 dev。
例如 `YUANBOOT_PORT=9000`、`YUANBOOT_GREETING__MESSAGE=hello`。
`yuanbootctl-python run --port 9000 --reload` 适用于 Web 开发；
`yuanbootctl-python run --workers 2` 适用于 Web 多进程部署。
每个 worker 都会运行自己的后台服务，需要任务唯一性时请使用外部协调机制。
