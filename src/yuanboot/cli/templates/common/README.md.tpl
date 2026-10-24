# __PROJECT__

Python 3.11+ · yuanboot · __KIND__

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
yuanbootctl run
```

框架通过 `pyproject.toml` 中的 Git tag 依赖安装，无需 PyPI。
项目的版本和框架版本各自维护。升级框架时修改 Git tag、更新依赖 lock 并运行测试。
私有仓库需要配置 Git SSH/HTTPS 访问权限；默认 Dockerfile 适用于公开 HTTPS 仓库。
本地联调先安装完整框架 `pip install -e '/path/to/yuanboot_python[all]'`，
再用 `pip install --no-deps -e .` 安装业务代码。

启用全部基础组件：`python -m pip install -e '.[dev,components]'`。
`main.py` 的 `use_components()` 自动读取 MySQL、Redis、Nacos 注册、日志等配置。
配置 `yuanboot.cloud.nacos.data_id` 后，Web/Console 模板会加载 Nacos 配置并监视更新。

```bash
python -m pytest
yuanbootctl build
yuanbootctl run --profile prod
```

Web 模板：`http://127.0.0.1:8080/docs` 查看 API 文档，
`/actuator/health/readiness` 查看就绪状态。
Console 模板：运行后台任务，Ctrl+C 或 SIGTERM 优雅停止。
gRPC 模板：监听 `yuanboot.grpc.address`，默认 127.0.0.1:9090，运行测试可验证 protobuf RPC。

配置按 config.yml → config_<profile>.yml → YUANBOOT_ 环境变量覆盖。
例如 `YUANBOOT_PORT=9000`、`YUANBOOT_GREETING__MESSAGE=hello`。
`yuanbootctl run --port 9000 --reload` 适用于 Web 开发；
`yuanbootctl run --workers 2` 适用于 Web 多进程部署。
每个 worker 都会运行自己的后台服务，需要任务唯一性时请使用外部协调机制。
