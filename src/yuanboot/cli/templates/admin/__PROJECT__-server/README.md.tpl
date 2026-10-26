# Yuanboot Admin Server

基于 yuanboot-python 的管理后台 API，提供验证码登录、JWT 会话、用户、角色、菜单、部门和系统配置。

```bash
python -m pip install -e '.[dev]'
yuanbootctl-python run
```

API 文档：`http://127.0.0.1:8090/docs`。初始开发账号为 `admin` / `admin123`。
默认 SQLite 数据保存在 `data/admin.db`，不应提交到 Git。
MySQL 与 Redis 配置见 `infrastructure.example.yml`，完整运行说明见项目根 README。
框架版本与依赖固定在 `pyproject.toml`，从公开 PyPI 安装。

- `__PACKAGE__/controllers.py`：HTTP 接口和授权。
- `__PACKAGE__/services.py`：事务、CRUD、树形结构和数据范围。
- `__PACKAGE__/models.py`：持久化模型。
- `__PACKAGE__/security.py`：验证码、密码、令牌。
- `spec/yuanboot-python.md`：框架使用说明。
- `spec/admin.md`：管理后台扩展约定。

接入已有数据表时先备份并在数据库迁移中为 `sys_user` 增加
`token_version INT NOT NULL DEFAULT 0`；`create_all` 只创建缺失表，不修改现有表结构。
登录会兼容原有 `SHA256(password + "sendex-salt")` 密码，成功后升级为 PBKDF2。

Copyright (c) 2026 jackson liang。MIT License。
