# Yuanboot Admin Web

Vue 3 + TypeScript + Element Plus 管理后台，连接同项目的 yuanboot-python API。

```bash
pnpm install --frozen-lockfile
pnpm dev
pnpm typecheck
pnpm build
```

开发地址 `http://127.0.0.1:8848/`；Vite 将 `/v1/` 代理到 `http://127.0.0.1:8090/`。
修改后端端口时同步修改 `vite.config.ts` 中的 proxy target。
生产构建使用同源 `/v1/`，部署时通过反向代理连接后端，不包含模拟登录和模拟业务接口。

完整启动说明、初始账号和组件配置见项目根 README。
Copyright (c) 2026 jackson liang。第三方依赖声明见项目根 THIRD_PARTY_NOTICES.md。
