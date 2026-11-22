# Python 版本支持

yuanboot-python 0.3.0 起支持 Python **3.6.2–3.14**；框架和 yuanbootctl-python 的最低安装版本为 3.6.2。
Python 3.6 分支使用 3.6.15 验证，Python 3.7 分支使用 3.7.17 验证。

## 安装

在目标 Python 环境中更新 pip，再安装框架和工具：

```bash
python -m pip install --upgrade pip
python -m pip install 'yuanbootctl-python[all]==0.3.1'
yuanbootctl-python --version
yuanbootctl-python new webapi -n demo
cd demo
python -m pip install -e '.[dev]'
yuanbootctl-python run
```

pip 会按当前解释器选择可用版本；Python 3.6 使用 pip 21.3.1，Python 3.7 使用 pip 24.0。
无需手动改包的 requires-python，也无需手动替换框架源码。

## 依赖选择

| Python | Web 与数据模型 | 组件与构建 |
| --- | --- | --- |
| 3.6 / 3.7 | FastAPI 0.83、Pydantic 1.9、Uvicorn 0.16 | SQLAlchemy 1.4、Redis 4.3、HTTPX 0.22、Pillow 8.4，使用兼容的构建后端 |
| 3.8–3.14 | FastAPI 0.115+、Pydantic 2.9+、Uvicorn 0.30+ | 按解释器自动解析可用版本，使用 Hatch 构建 |

框架通过环境标记分别声明依赖；新版本 Python 保留现代依赖，旧版本使用最后兼容的依赖范围。
MySQL、Redis、Nacos、配置热更新、日志、SMTP、任务调度、XXL-Job、gRPC 和管理后台沿用相同的组件入口。

Python 3.6 / 3.7 及其兼容依赖已结束上游维护；已有环境可继续运行，新部署建议使用仍在维护的 Python 版本。

## 项目模板

七种模板均支持生成、安装和运行：`webapi`、`simpleweb`、`mvc`、`microservice`、`console`、`grpc`、`admin`。
新项目默认依赖与工具相同版本的框架。

已有 0.2.x 脚手架项目迁移到 Python 3.6 / 3.7 时，需要同步：

- 项目 `pyproject.toml` 的 `requires-python` 改为 `>=3.6.2`，框架依赖升级为 `0.3.1`。
- 构建配置和 `_build_backend/`、`setup.py`、`MANIFEST.in` 使用新模板中的版本，以支持旧解释器安装。
- 业务代码使用目标 Python 支持的语法和依赖 API，注入写法见下文。

可用新版工具在独立目录生成同类项目，对照迁移业务代码和配置，保留原项目的数据和密钥。

```bash
yuanbootctl-python new admin -n my-admin
cd my-admin/my-admin-server
python -m pip install -e '.[dev]'
yuanbootctl-python run
```

Admin 前端仍使用 Node.js 和 pnpm，其版本要求与后端 Python 无关。

## 业务代码

运行在 Python 3.6 时，业务代码也需使用该版本支持的语法：

```python
from yuanboot.web import create_default_builder, inject


class GreetingService:
    def greet(self, name):
        return "Hello, " + name


def endpoints(router):
    @router.get("/hello")
    def hello(service: GreetingService = inject(GreetingService)):
        return {"message": service.greet("Python")}


host = (
    create_default_builder(endpoints)
    .configure_services(lambda services: services.add_singleton(GreetingService))
    .build()
)
app = host.app
if __name__ == "__main__":
    host.run()
```

类型容器使用 `List[str]`、`Optional[str]`，避免 `list[str]`、`str | None` 等较新语法。
FastAPI 注入使用 `service: Service = inject(Service)`，可同时兼容新旧运行时。
配置绑定可接受相应版本的 Pydantic 模型，框架统一处理模型解析、校验与导出。

## 独立工具

GitHub Release 的独立二进制内含 Python 运行时，可直接创建和运行项目。
需要使用业务环境中的 Python 3.6–3.14 时，通过 `run --python /path/to/python` 显式指定。
Git tag 源码安装、wheel 安装及生成项目的源码构建都支持旧版 Python。
发布工作流验证 3.6–3.14，五个平台的独立二进制继续在受支持的构建环境中原生编译。

`install`、`run`、`build` 在 Admin 根目录均可执行，依赖文件和构建工具会自动准备。
传统 `python -m pip install -r requirements.txt` 同样支持。
