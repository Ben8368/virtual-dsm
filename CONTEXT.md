# 当前状态

> **最后确认：** 2026-10-15
> **阶段：** Phase 4A / K0；Phase 3 F5 与 Watchdog L5 保持通过
> **产品代码：** 生产 QEMU 8.2.2 补丁系列与 ARM `rtd1619b` 实验路径；严格 F5 已通过。

## 当前决策

- 仓库独立维护于 [Ben8368/virtual-dsm](https://github.com/Ben8368/virtual-dsm)；上游 vdsm 变更不自动同步。
- `DSM_PLATFORM=virtualdsm` 为稳定 x86 默认；`rtd1619b` 为实验性 DS124 ARM64 路径。
- 生产 QEMU 补丁只经 [patches/qemu/8.2.2](patches/qemu/8.2.2/README.md) 与共享 apply helper 进入镜像。
- 严格 Phase 3 F5 仍要求两次访客 UI 干净关机；不把 host-directed stop 记为干净关机。

## 近期优先级

1. 获取真实 ARM64 Linux / KVM 主机，按 [Phase 4A 协议](research/arm64/production-phase4a.md) 开始配置态验证。
2. 完成生命周期硬化与原生 amd64/arm64 容器构建验证。
3. 完成 release-readiness 检查，保持实验性 ARM 发布边界。

## 当前阻断与风险

- Phase 4A 预检只有 x86_64 WSL；没有可用 ARM64 目标，分类 K0，见 [RISK-002](docs/RISK_REGISTER.md)。
- ARM64 KVM 与 Surveillance Station 仍属未验证硬件/包路径。

## 最近验证

- 2026-10-15：[Phase 4A 环境预检](research/arm64/production-phase4a.md) 确认 amd64 AArch64 QEMU 仅支持 TCG；显式 KVM 被拒绝。
- 2026-10-13：Phase 3 配置态持久化与管理面验收记录见 [production-phase3.md](research/arm64/production-phase3.md)。
- 2026-10-15：三次冷启动、两次 UI 干净关机、两轮 30 guest minutes 与账号清理通过，见 [严格 F5 证据](research/arm64/production-phase3.md#strict-f5-completed-acceptance-evidence--2026-10-15)。

## 按需入口

- 平台与 Phase 3：[docs/platforms.md](docs/platforms.md)、[research/arm64/production-phase3.md](research/arm64/production-phase3.md)
- 治理与审查：[docs/GOVERNANCE.md](docs/GOVERNANCE.md)、[docs/AI_RULES.md](docs/AI_RULES.md)
- CI 与发布：[docs/ci.md](docs/ci.md)
