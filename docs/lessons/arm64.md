# Lesson：ARM64 / Phase 3

- 生产 hostfwd 绑在容器内 `:5000/:5001`；主机暴露靠 Docker `-p`，不是研究用的裸 `15000` hostfwd。
- 配置态冷启动管理 HTTP 在 amd64 TCG multi 下常需 ~7–8 分钟；短观察窗会制造假失败。
- host-directed stop 不是 F5 干净关机；需要 DSM UI/API 的 `guest-shutdown` 收据。
- 不改访客 watchdog 设置来“通过”稳定性门禁。
