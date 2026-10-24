# 框架发布与业务依赖

框架仓库 `git@github.com:liangboceo/yuanboot-python.git`，默认分支 **master**。
采用 Git tag 分发；公开仓库的依赖使用 HTTPS，可直接用于 CI 和 Docker。
无需 PyPI 账号。业务项目不要复制框架源码。

## 安装与生成项目

```bash
python -m pip install 'yuanboot[all] @ git+https://github.com/liangboceo/yuanboot-python.git@v0.1.0'
yuanbootctl new mvc -n orders --framework-ref v0.1.0
cd orders
python -m pip install -e '.[dev,components]'
yuanbootctl run
```

模板生成的 `pyproject.toml` 已包含：

```toml
[project]
name = "orders"
version = "0.1.0"
dependencies = [
  "yuanboot @ git+https://github.com/liangboceo/yuanboot-python.git@v0.1.0",
]

[project.optional-dependencies]
components = [
  "yuanboot[all] @ git+https://github.com/liangboceo/yuanboot-python.git@v0.1.0",
]
```

实际项目可将 `all` 改为 `mysql,redis,nacos` 等所需 extras，减小运行依赖。
`grpc` 模板自动启用 `yuanboot[grpc]`。
`--framework-repo git@github.com:organisation/framework.git` 可以覆盖仓库。
私有仓库通过 SSH agent/部署密钥提供访问权限，不要把 token 写进 URL 或 pyproject。

## 版本规则

框架只有一个版本源：`src/yuanboot/_version.py`。Hatch 构建元数据、ctl 和 Nacos metadata 从这里取版本。
业务项目自己管理版本，与框架版本互不绑定。

- 补丁版本 `v0.1.1`：修复兼容问题。
- 次版本 `v0.2.0`：新增能力或 0.x 阶段的不兼容变化。
- `v1.0.0` 后按语义化版本管理兼容性。

已发布 tag 保持不可变；修复后新建 tag。业务升级时修改 Git tag、重新锁定依赖、运行测试，再部署。
如需固定到完全不可变的引用，也可在 `@` 后使用完整 Git commit SHA。

## 框架开发与业务联调

```bash
# 在框架目录使用一个虚拟环境，避免先解析业务项目的远程 Git 依赖。
python -m pip install -e '.[dev,all]'
python -m pip install --no-deps -e ./examples/taskboard

# 业务项目已有完整依赖时，可切回本地框架实现。
python -m pip install -e /absolute/path/to/yuanboot_python
```

`--no-deps` 只用于此处已先安装完整依赖的本地联调；正常安装业务项目应允许 pip 解析依赖。

## 发布流程

修改版本源、更新文档后执行：

```bash
python -m pytest -q
python -m pytest -q examples/taskboard/tests
ruff check .
ruff format --check .
python -m build
python scripts/check_distribution.py
python scripts/check_release.py v0.1.0
git add .
git commit -m "Release yuanboot Python 0.1.0"
git tag -a v0.1.0 -m "yuanboot Python 0.1.0"
git push origin master
git push origin v0.1.0
```

首次发布后在仓库设置中将默认分支设为 `master`。
`.github/workflows/ci.yml` 在 master、PR 和 tag 上测试 Python 3.11–3.14；构建 wheel/sdist 并保留 Actions 产物。
CI 校验 tag 与版本源一致，不上传 PyPI。框架 wheel 包含模板资源，sdist 明确排除本地环境、数据和凭据。

## 锁定完整依赖

Git tag 只锁定框架，不能自动锁定 FastAPI、SQLAlchemy 等传递依赖。
每个业务项目应提交自己的 lock 文件。例如使用 uv：

```bash
uv lock
uv sync --frozen --extra components
# 升级框架 tag 后：
uv lock --upgrade-package yuanboot
uv sync --frozen --extra components
```

也可在干净虚拟环境安装业务项目后通过 `pip freeze > requirements.lock` 记录完整版本，
在同一 Python/操作系统环境使用该文件复现。使用多平台部署时优先采用 uv lock。
不要从混有其他项目的开发环境导出生产锁文件；不要在仓库提交账号密码或本地 `.env.integration`。
