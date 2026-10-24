# 框架发布与业务依赖

框架仓库 `git@github.com:liangboceo/yuanboot-python.git`，默认分支 **master**。
支持公开 PyPI 和 Git tag 分发；业务项目通过依赖使用框架。
安装公开包无需 PyPI 账号，上传包需要 Trusted Publisher 或 PyPI API Token。

## PyPI 安装

```bash
python -m pip install 'yuanboot[all]==0.1.8'
python -m pip install yuanbootctl-python==0.1.8
yuanbootctl-python --version
```

两个发行包共用 `src/yuanboot/_version.py` 版本源：

- `yuanboot`：框架、组件、CLI 实现、命令入口和模板资源。
- `yuanbootctl-python`：工具安装包，依赖精确版本的 `yuanboot`；`[all]` 可启用全部标准组件。

生成项目默认从 PyPI 安装。业务 `pyproject.toml` 中的框架依赖为
`yuanboot==0.1.8`，组件依赖改为 `yuanboot[all]==0.1.8`；gRPC 基础依赖使用 `yuanboot[grpc]==0.1.8`。

## 安装与生成项目

```bash
python -m pip install 'yuanbootctl-python[all]==0.1.8'
yuanbootctl-python new mvc -n orders --framework-version 0.1.8
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
  "yuanboot==0.1.8",
]

[project.optional-dependencies]
components = [
  "yuanboot[all]==0.1.8",
]
```

实际项目可将 `all` 改为 `mysql,redis,nacos` 等所需 extras，减小运行依赖。
`grpc` 模板自动启用 `yuanboot[grpc]`。
默认版本从 `src/yuanboot/_version.py` 自动读取，与生成工具和框架保持一致。
升级工具后新项目自动使用新版本；已有业务项目保留原固定版本。
`--framework-version 0.1.8` 可指定 PyPI 版本。
如需 Git，显式指定 `--framework-ref v0.1.8`，或用 `--framework-repo git@github.com:organisation/framework.git` 覆盖仓库。
Git 选项与 `--framework-version` 不能混用；使用 Git 依赖时需安装 Git。
私有仓库通过 SSH agent/部署密钥提供访问权限，不要把 token 写进 URL 或 pyproject。

## 版本规则

框架只有一个版本源：`src/yuanboot/_version.py`。Hatch 构建元数据、ctl 和 Nacos metadata 从这里取版本。
业务项目自己管理版本，与框架版本互不绑定。

- 补丁版本 `v0.1.8`：修复兼容问题。
- 次版本 `v0.2.0`：新增能力或 0.x 阶段的不兼容变化。
- `v1.0.0` 后按语义化版本管理兼容性。

已发布 tag 保持不可变；修复后新建 tag。业务升级时统一修改 PyPI 版本或 Git tag、重新锁定依赖、运行测试，再部署。
如需固定到完全不可变的引用，也可在 `@` 后使用完整 Git commit SHA。

## 发布流程

通过 GitHub Actions 手动发布：

1. 将待发布代码推送到 `master`。
2. 打开仓库 **Actions → Build Release → Run workflow**，选择 `master`。
3. 填写 `version`（例如 `0.1.8`，不带 `v`），选择 `prerelease` 和 `draft`，默认均为 `true`。
4. 工作流同步版本源，在 Python 3.11–3.14 上构建包，并为各平台编译独立命令行工具。
5. 全部通过后，提交版本变更到 `master`，创建 `v<version>` tag，生成 GitHub Release，上传可执行文件、两个 PyPI 包各自的 wheel / sdist 和 SHA256SUMS。
6. `draft=false` 的公开发布会自动启动 **Publish PyPI**，将同版本的框架包和工具包上传到正式 PyPI。

也可使用 GitHub CLI 手动触发：

```bash
gh workflow run Release.yml --ref master \
  -f version=0.1.8 -f prerelease=false -f draft=false
```

已存在的 tag 会被拒绝，不会覆盖。构建期间如果 `master` 有更新，发布中止，需从最新 `master` 重新运行。
`draft=true` 只控制 GitHub Release 是否为草稿，Git tag 仍会创建并可供业务依赖。
GitHub Release 工作流使用仓库自带的 `GITHUB_TOKEN`，PyPI 上传由独立的 **Publish PyPI** 工作流执行。
公开发布草稿 Release 时也会自动触发 PyPI 上传。
由该 token 推送的 tag 不会再次触发 CI，发布工作流本身完成构建。

本地开发时可先执行检查：

```bash
ruff check .
ruff format --check .
python packaging/build_packages.py
python -m twine check dist/*
```

`python -m build` 只构建框架；`packaging/build_packages.py` 构建两个同版本发行包。

## 发布到公开 PyPI

推荐使用 GitHub Trusted Publishing。首次发布前，在
[PyPI Publishing](https://pypi.org/manage/account/publishing/) 为两个项目分别添加 Pending Publisher：

| 配置项 | 框架包 | 工具安装包 |
| --- | --- | --- |
| PyPI Project Name | `yuanboot` | `yuanbootctl-python` |
| GitHub repository owner | `liangboceo` | `liangboceo` |
| GitHub repository name | `yuanboot-python` | `yuanboot-python` |
| Workflow filename | `PublishPyPI.yml` | `PublishPyPI.yml` |
| Environment name | `pypi` | `pypi-cli` |

首次创建两个项目时必须使用不同的发布者身份，PyPI 不允许相同的 Pending Publisher
同时对应不同的新项目。工作流通过独立的 GitHub Environment 区分两个发行包。

如果项目已经存在，在该项目的 Publishing 设置中添加同样的 Trusted Publisher。
也可使用有权发布两个项目的 PyPI API Token，在仓库 Actions Secrets 中设置 `PYPI_API_TOKEN`。
Token 只保存在 Secret 中，不写入代码、配置或命令参数。

正常发布只需运行 **Build Release**，公开 Release 创建后会自动分发两个 PyPI 包。
也可以在 GitHub 手动公开一个包含完整安装包和校验文件的 Release，触发同样的同步。
仅推送裸 Git tag 不包含安装包，不会直接上传 PyPI。

如果需要重试已发布的版本，手动运行 **Publish PyPI** 并填写相同版本：

```bash
gh workflow run PublishPyPI.yml --ref master -f version=0.1.8
```

该工作流下载指定 Release 的四个 Python 包，核对 `SHA256SUMS`、检查包元数据后，
分别在 `pypi`、`pypi-cli` 环境中上传到正式 PyPI。可为这些 GitHub Environment 配置审批规则。
Release 工作流显式分发 PyPI 任务，因此通过 `GITHUB_TOKEN` 创建的 tag / Release 也能继续上传。
已存在的文件会跳过，以便首次部分上传失败后重试；修复发布内容必须使用新版本。
两个包全部上传成功后，再通过 PyPI 安装验证。

首次发布后在仓库设置中将默认分支设为 `master`。
`.github/workflows/ci.yml` 在 master、PR 和 tag 上构建 Python 3.11–3.14 包；构建 wheel/sdist 并保留 Actions 产物。
框架 wheel 包含模板资源，sdist 明确排除本地环境、数据和凭据。
所有模板默认生成 `README.md` 和 `spec` 文档目录，包含 `yuanboot-python.md`、
`components.md` 和 `backend-module-development.md`；独立二进制内也包含这些资源。

## 锁定完整依赖

固定框架版本只锁定框架，不能自动锁定 FastAPI、SQLAlchemy 等传递依赖。
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
