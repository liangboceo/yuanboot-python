# yuanbootctl-python

作者：jackson liang。Copyright (c) 2026 jackson liang。

yuanboot-python 的项目工具，支持创建项目、运行应用和构建业务包。Python 3.11+。

## 安装

```bash
python -m pip install yuanbootctl-python
yuanbootctl-python --version
```

该包自动安装同版本的 `yuanboot`，命令入口与模板资源由框架提供。
需要 MySQL、Redis、Nacos 等全部标准组件时：

```bash
python -m pip install 'yuanbootctl-python[all]'
```

## 创建与运行项目

```bash
yuanbootctl-python new --list
yuanbootctl-python new webapi -n demo
cd demo
python -m pip install -e '.[dev,components]'
yuanbootctl-python run --profile dev
```

支持 `simpleweb`、`webapi`、`mvc`、`microservice`、`console` 和 `grpc` 六种模板。
每个项目包含 README、配置、部署文件和 `spec` 开发文档。
生成项目默认通过 Git tag 固定框架依赖，需安装 Git；也可在业务项目中改为同版本的 PyPI 依赖。

```bash
yuanbootctl-python run --reload
yuanbootctl-python run --workers 2
yuanbootctl-python build
```

环境支持 `dev / fat / uat / pro`。Web 模板默认在 http://127.0.0.1:8080/docs 提供 API 文档。

## 独立可执行文件

无需安装 Python 的版本可从 [GitHub Releases](https://github.com/liangboceo/yuanboot-python/releases) 下载。
支持 Linux、macOS 和 Windows。

- [框架文档](https://github.com/liangboceo/yuanboot-python/tree/master/docs)
- [源码与问题反馈](https://github.com/liangboceo/yuanboot-python)
