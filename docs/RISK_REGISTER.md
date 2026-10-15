# 风险与开放假设

本文件只登记尚未验证的外部不确定性；实现后有意保留的妥协进入 [TECH_DEBT.md](TECH_DEBT.md)。

## 分级

- **P0**：阻断指定验收门禁。
- **P1**：不阻断当前门禁，但会改变发布或体验边界。
- **P2**：后续增强风险。

## 活跃风险

### RISK-001（P0）：Phase 3 F5 依赖的 disposable 管理员会话失效

- **阻断 Gate：** Phase 3 严格 F5。
- **问题：** 配置态冷启动与 HTTP/HTTPS 已验证，但对 `phase3local` 的 DSM Auth 返回 499（失败次数/锁定或密码漂移），无法发起 stock `SYNO.Core.System` shutdown。
- **控制：** 不降低 F5 门禁；不把 host-directed stop 记为干净关机；不提交新密码到 Git。
- **关闭证据：** 可复现的 Auth 成功 + 两次 QMP `guest-shutdown` / `guest-poweroff` + 30/30 HTTP 观察。

### RISK-002（P1）：原生 ARM64-host KVM 未经验证

- **阻断 Gate：** Phase 4 / 发布级 ARM 性能声明。
- **问题：** 当前验收主要在 amd64 宿主 TCG multi；KVM 兼容探针后的真机路径未闭环。
- **关闭证据：** 目标 ARM64 宿主上的冷启动、管理面与稳定性记录。

### RISK-003（P2）：Surveillance Station 与包安装矩阵未完成

- **阻断 Gate：** 功能完整度声明。
- **问题：** 包安装与 Surveillance 仍依赖单独文档路径，不由默认 CI 证明。
- **关闭证据：** 见 [package-installation.md](package-installation.md) 约定的官方 PAT/硬件检查。
