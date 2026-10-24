# 框架发布与业务依赖

框架仓库 `git@github.com:liangboceo/yuanboot-python.git`，默认分支 **master**。
采用 Git tag 分发；公开仓库的依赖使用 HTTPS，可直接用于 CI 和 Docker。
无需 PyPI 账号。业务项目通过依赖使用框架。

## 安装与生成项目

```bash
python -m pip install 'yuanboot[all] @ git+https://github.com/liangboceo/yuanboot-python.git@v0.1.4'
yuanbootctl-python new mvc -n orders --framework-ref v0.1.4
cd orders
python -m pip install -e '.[dev,components]'
yuanbootctl-python run
```

模板生成的 `pyproject.toml` 已包含：

```toml
[project]
name = "orders"
version = "0.1.0"
dependencies = [
  "yuanboot @ git+https://github.com/liangboceo/yuanboot-python.git@v0.1.4",
]

[project.optional-dependencies]
components = [
  "yuanboot[all] @ git+https://github.com/liangboceo/yuanboot-python.git@v0.1.4",
]
```

实际项目可将 `all` 改为 `mysql,redis,nacos` 等所需 extras，减小运行依赖。
`grpc` 模板自动启用 `yuanboot[grpc]`。
`--framework-repo git@github.com:organisation/framework.git` 可以覆盖仓库。
私有仓库通过 SSH agent/部署密钥提供访问权限，不要把 token 写进 URL 或 pyproject。

## 版本规则

框架只有一个版本源：`src/yuanboot/_version.py`。Hatch 构建元数据、ctl 和 Nacos metadata 从这里取版本。
业务项目自己管理版本，与框架版本互不绑定。

- 补丁版本 `v0.1.4`：修复兼容问题。
- 次版本 `v0.2.0`：新增能力或 0.x 阶段的不兼容变化。
- `v1.0.0` 后按语义化版本管理兼容性。

已发布 tag 保持不可变；修复后新建 tag。业务升级时修改 Git tag、重新锁定依赖、运行测试，再部署。
如需固定到完全不可变的引用，也可在 `@` 后使用完整 Git commit SHA。

## 发布流程

通过 GitHub Actions 手动发布：

1. 将待发布代码推送到 `master`。
2. 打开仓库 **Actions → Build Release → Run workflow**，选择 `master`。
3. 填写 `version`（例如 `0.1.4`，不带 `v`），选择 `prerelease` 和 `draft`，默认均为 `true`。
4. 工作流同步版本源，在 Python 3.11–3.14 上构建包，并为各平台编译独立命令行工具。
5. 全部通过后，提交版本变更到 `master`，创建 `v<version>` tag，生成 GitHub Release，上传可执行文件、wheel、sdist 和 SHA256SUMS。

也可使用 GitHub CLI 手动触发：

```bash
gh workflow run Release.yml --ref master \
  -f version=0.1.4 -f prerelease=false -f draft=false
```

已存在的 tag 会被拒绝，不会覆盖。构建期间如果 `master` 有更新，发布中止，需从最新 `master` 重新运行。
`draft=true` 只控制 GitHub Release 是否为草稿，Git tag 仍会创建并可供业务依赖。
工作流使用仓库自带的 `GITHUB_TOKEN`，不需要额外配置发布密钥，不上传 PyPI。
由该 token 推送的 tag 不会再次触发 CI，发布工作流本身完成构建。

本地开发时可先执行检查：

```bash
ruff check .
ruff format --check .
python -m build
```

首次发布后在仓库设置中将默认分支设为 `master`。
`.github/workflows/ci.yml` 在 master、PR 和 tag 上构建 Python 3.11–3.14 包；构建 wheel/sdist 并保留 Actions 产物。
框架 wheel 包含模板资源，sdist 明确排除本地环境、数据和凭据。
所有模板默认生成 `README.md` 和 `spec` 文档目录，包含 `yuanboot-python.md`、
`components.md` 和 `backend-module-development.md`；独立二进制内也包含这些资源。

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

## 独立命令行工具

命令名为 `yuanbootctl-python`，Windows 使用 `yuanbootctl-python.exe`。
可执行文件包含 Python 运行时、框架和标准组件。下载并解压后即可创建、运行模板项目，无需预装 Python。

发布包含五种构建：Linux amd64 / arm64、macOS Intel / Apple Silicon、Windows amd64。
文件名为 `yuanbootctl-python_<version>_<system>_<arch>.tar.gz`，Windows 使用 `.zip`。
所有产物的 SHA-256 在同一 Release 的 `SHA256SUMS` 中。

```bash
./yuanbootctl-python new mvc -n orders
cd orders
../yuanbootctl-python run --profile dev
```

项目增加其他 Python 依赖后，创建业务虚拟环境、安装依赖，再选择该解释器：

```bash
python -m venv .venv
.venv/bin/python -m pip install -e '.[dev,components]'
../yuanbootctl-python run --python .venv/bin/python
../yuanbootctl-python build --python .venv/bin/python --wheel
```

`--python` 建议使用绝对路径；相对路径以项目目录为准。Windows 对应 `.venv\Scripts\python.exe`。
二进制的 `build` 默认使用项目 `.venv` 内的 Python，需要该环境安装 `build`。
`run` 默认使用内置运行时，支持环境选择、TLS、reload 和多 worker。

## 本地编译命令行工具

```bash
python -m pip install -e '.[all,binary]'
python packaging/build_binary.py
```

输出可执行文件在 `dist/bin`，发布压缩包在 `dist`。每个平台在对应系统上原生构建。
