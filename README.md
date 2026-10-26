# yuanboot-python

作者：jackson liang。Copyright (c) 2026 jackson liang。

简单、轻量、快速的 Python 微服务框架，基于 FastAPI、Uvicorn 和依赖注入构建，支持 Web API、MVC、gRPC 与后台服务。Python 3.11+。

[![Build](https://github.com/liangboceo/yuanboot-python/actions/workflows/ci.yml/badge.svg)](https://github.com/liangboceo/yuanboot-python/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/tag/liangboceo/yuanboot-python?label=release&sort=semver)](https://github.com/liangboceo/yuanboot-python/releases)
[![PyPI](https://img.shields.io/pypi/v/yuanboot?label=yuanboot)](https://pypi.org/project/yuanboot/)
[![CLI](https://img.shields.io/pypi/v/yuanbootctl-python?label=yuanbootctl-python)](https://pypi.org/project/yuanbootctl-python/)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/github/license/liangboceo/yuanboot-python)](LICENSE)

## 框架特色

- 路由分组、MVC 控制器、请求校验、OpenAPI 和 WebSocket。
- Singleton、Scoped、Transient 依赖注入与资源自动释放。
- 统一宿主、应用生命周期、后台服务和优雅退出。
- YAML / JSON、多环境配置、环境变量和远程配置热更新。
- MySQL、Redis、Nacos 配置中心、服务注册与发现。
- 统一启动版权信息、zap / logrus 文本与 JSON 日志、请求追踪、健康检查、Prometheus 和 JWT。
- Swagger 展示框架版本、版权、联系信息与 MIT 许可，并保留业务文档配置。
- HTTP 客户端、定时任务、SMTP、gRPC 和 XXL-Job BEAN 执行器。
- `yuanbootctl-python` 提供六类项目模板、运行和构建命令。

## 下载命令行工具

从 [GitHub Releases](https://github.com/liangboceo/yuanboot-python/releases) 下载对应系统和架构的压缩包，解压后即可执行，无需预装 Python。

| 系统 | 架构 | 文件后缀 |
| --- | --- | --- |
| Linux | amd64 / arm64 | `_linux_amd64.tar.gz` / `_linux_arm64.tar.gz` |
| macOS | Intel / Apple Silicon | `_darwin_amd64.tar.gz` / `_darwin_arm64.tar.gz` |
| Windows | amd64 | `_windows_amd64.zip` |

例如 Linux amd64：

```bash
VERSION=0.1.9
curl -fLO "https://github.com/liangboceo/yuanboot-python/releases/download/v${VERSION}/yuanbootctl-python_${VERSION}_linux_amd64.tar.gz"
tar -xzf "yuanbootctl-python_${VERSION}_linux_amd64.tar.gz"
chmod +x yuanbootctl-python
./yuanbootctl-python --version
./yuanbootctl-python new webapi -n demo
cd demo
../yuanbootctl-python run --profile dev
```

访问 [API 文档](http://127.0.0.1:8080/docs)。Windows 使用 `yuanbootctl-python.exe`。
Release 同时提供 `SHA256SUMS`、wheel 和源码包。

独立可执行文件包含 Python 运行时、框架和标准组件，可以直接创建、运行模板项目。
业务增加其他 Python 依赖后，可使用 `run --python /path/to/.venv/bin/python` 选择业务环境。
`build` 打包 Python 项目，需要业务环境安装 `build`，详见 [命令行与发布说明](docs/releases.md)。

## 安装框架

从公开 PyPI 安装框架或项目工具：

```bash
python -m pip install 'yuanboot[all]==0.1.9'
# 也可通过工具包安装同版本框架和命令：
python -m pip install yuanbootctl-python==0.1.9
yuanbootctl-python --version
```

`yuanbootctl-python` 自动依赖同版本的 `yuanboot`，命令入口和模板资源统一由框架提供。
`yuanbootctl-python[all]` 会安装全部标准组件。PyPI 安装方式需要 Python 3.11+。

创建业务项目并安装依赖：

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install 'yuanbootctl-python[all]==0.1.9'
yuanbootctl-python new mvc -n orders
cd orders
python -m pip install -e '.[dev,components]'
yuanbootctl-python run --reload
```

按需选择 `mysql`、`redis`、`nacos`、`grpc` 等 extras；`all` 安装全部标准组件。
框架和业务项目分别管理版本，业务项目提交自己的依赖锁文件。
生成项目默认从 PyPI 安装，基础依赖固定 `yuanboot==0.1.9`，
组件固定 `yuanboot[all]==0.1.9`，gRPC 固定 `yuanboot[grpc]==0.1.9`。
版本自动读取生成工具内置的框架版本；升级工具后新生成项目使用新版本，已有项目保留原固定版本。
可用 `--framework-version` 选择其他 PyPI 版本，或显式用 `--framework-ref v0.1.9` 切换为 Git tag 依赖。

框架版本通过 GitHub **Actions → Build Release** 填写 version 发布。
公开的 Release/tag 创建成功后会自动启动 **Publish PyPI**，将两个同版本包上传到公开 PyPI。
草稿 Release 在公开发布时触发同步；上传失败可手动重跑 **Publish PyPI**。详见[发布说明](docs/releases.md)。


## PyCharm 调试与直接运行

模板提供项目根目录 `main.py` 和 `.run/yuanboot.run.xml`。
使用项目虚拟环境安装 `pip install -e '.[dev]'` 后，直接运行或 Debug 根目录 `main.py`，
也可从项目根目录执行 `python -m demo.main`（将 `demo` 替换为业务包名）。
PyCharm 手动配置使用 Module name `demo.main`，Working directory 选择项目根目录。
包内入口使用绝对导入，业务项目安装后也支持直接运行 `demo/main.py`。
配置优先读取当前目录的 `config.yml`，当前目录没有配置时回退到项目根目录。

## 项目模板

| 模板 | 内容 |
| --- | --- |
| `simpleweb` | 最小 HTTP 应用与运维端点 |
| `webapi` | API 路由、服务注入和请求校验 |
| `mvc` | 控制器、服务层和 Jinja2 页面 |
| `microservice` | Web API、监控和后台服务 |
| `console` | 命令行宿主与后台任务 |
| `grpc` | gRPC 服务与健康检查 |

模板包含项目元数据、配置、Dockerfile、Compose、README 和 `spec` 开发文档。
每个新项目默认提供以下文档，可离线查阅：

```text
README.md
spec/
├── yuanboot-python.md             # 框架使用说明
├── components.md                 # 核心组件配置与使用
└── backend-module-development.md  # 后端模块开发规范
```

```bash
yuanbootctl-python new --list
yuanbootctl-python new mvc -n my-app
yuanbootctl-python new grpc -n rpc-demo
yuanbootctl-python run --profile fat --port 9000
yuanbootctl-python run --workers 2
yuanbootctl-python build
yuanbootctl-python version
```

## 简单示例

```python
from yuanboot.web import create_default_builder
from yuanboot.web.endpoints import use_actuator


def endpoints(router):
    use_actuator(router)

    @router.get("/info")
    def info():
        return {"info": "ok"}


host = create_default_builder(endpoints).build()
app = host.app

if __name__ == "__main__":
    host.run()
```

默认监听 `0.0.0.0:8080`。可通过宿主构建器配置服务注册、中间件、路由和生命周期。

## 环境与配置

支持 `dev / fat / uat / pro`，默认 `dev`。通过 `--profile` 或 `YUANBOOT_PROFILE` 选择环境。

```text
config.yml
config_dev.yml
config_fat.yml
config_uat.yml
config_pro.yml
```

配置优先级：默认值 < 基础配置 < 环境配置 < 远程配置 < 环境变量 < 命令行。
MySQL、Redis 和 Nacos 等组件按配置启用；Nacos 注册 metadata 的 `yuanboot_env` 使用当前环境名。

```yaml
yuanboot:
  application:
    name: orders
    server:
      address: ":8080"
```

支持 `${ENV:default}` 插值和 Pydantic 模型绑定，敏感信息通过环境变量提供。

## 核心组件

| 能力 | 组件 |
| --- | --- |
| 数据与缓存 | MySQL / SQLAlchemy、Redis |
| 配置中心 | Nacos、Apollo |
| 注册与发现 | Nacos、Consul、Eureka、etcd、内存注册表 |
| 日志与监控 | 标准 logging、JSON 日志、Request ID、健康检查、Prometheus |
| 服务通信 | HTTP 客户端、gRPC |
| 后台任务 | HostedService、Scheduler、XXL-Job BEAN |
| 通知与事件 | SMTP、进程内 Observer |

组件配置和使用方法见 [组件文档](docs/components.md)。

## 发布

在 [Actions → Build Release](https://github.com/liangboceo/yuanboot-python/actions/workflows/Release.yml) 手动填写 `version`，选择 `prerelease`、`draft`。
构建通过后，自动同步版本、创建 Git tag 和 GitHub Release，上传各平台可执行文件、wheel、源码包和校验文件。
默认分支为 `master`，已发布 tag 保持不变。

## 文档

- [框架开发指南](docs/framework.md)
- [组件配置与使用](docs/components.md)
- [命令行、发布与依赖管理](docs/releases.md)

启动控制台显示 yuanboot logo 与彩色启动信息，保留版本及版权标识。日志支持 `color: auto / always / never`、`banner: false`；文件和 JSON 日志不含框架颜色码。详见[日志配置](docs/components.md#统一日志与启动信息)。

## License

[MIT](LICENSE)
