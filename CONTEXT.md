# 当前状态

> **最后确认：** 2026-10-17
> **阶段：** Phase 4B: pre-R1；已接受基线仍为 Phase 4A / K5、Phase 3 F5、Watchdog L5
> **产品代码：** 生产 QEMU 8.2.2 补丁系列与 ARM `rtd1619b` 实验路径；严格 F5 已通过。

## 当前决策

- 仓库独立维护于 [Ben8368/virtual-dsm](https://github.com/Ben8368/virtual-dsm)；上游 vdsm 变更不自动同步。
- `DSM_PLATFORM=virtualdsm` 为稳定 x86 默认；`rtd1619b` 为实验性 DS124 ARM64 路径。
- 生产 QEMU 补丁只经 [patches/qemu/8.2.2](patches/qemu/8.2.2/README.md) 与共享 apply helper 进入镜像。
- 严格 Phase 3 F5 仍要求两次访客 UI 干净关机；不把 host-directed stop 记为干净关机。

## 近期优先级

1. 恢复 Docker Hub 构建前端可达性，验证干净 amd64 生产镜像；当前 M5 builder 只提供 amd64 仿真。
2. 完成多平台 OCI manifest 与 hosted CI 验证（默认 x86 命令回归已通过）。
3. 完成 Phase 4B 生命周期/运行时安全、CI 与发布边界检查；保持实验性 ARM 支持范围。

## 当前阻断与风险

- Phase 4A：K5。精确官方 PAT fresh install 后，boot3/4/5 三次配置态 KVM 冷启动均通过 K3；共享目录 marker、Basic/Btrfs、`configured=true`、升级完成、PostgreSQL active 与 HTTP/HTTPS 200 均复核。boot3 31 组稳定采样全部 200、跨度约 50 分钟；至少两次 DSM UI clean shutdown 有 guest-shutdown、exit 0、clean=true 收据。生产 QEMU 始终为 ARM64 `-accel kvm -cpu host`，无 TCG 回退。环境是 Apple VZ nested KVM，不代表裸机 ARM64；Phase 3 runtime 跨主机可移植性仍为 UNTESTED。见 [Phase 4A 证据](research/arm64/production-phase4a.md) 与 [RISK-002](docs/RISK_REGISTER.md)。
- ARM64 KVM 与 Surveillance Station 仍属未验证硬件/包路径。
- Phase 4B 为 pre-R1：arm64 镜像和 hermetic x86 命令回归通过，但没有原生 amd64 builder；先前 amd64 build 在 Docker Hub frontend TLS 超时。OCI manifest 与 GitHub CI 未验证。见 [Phase 4B 记录](research/arm64/production-phase4b.md)。

## 最近验证

- 2026-10-17：[Phase 4A K5 验收](research/arm64/production-phase4a.md) 记录官方 PAT fresh install、三次配置态 KVM 冷启动、稳定采样、卷与 marker 持久化及干净关机收据。
- 2026-10-17：Phase 4B 本地 arm64 镜像与合成测试结果、amd64 构建阻断和未完成门禁见 [Phase 4B 记录](research/arm64/production-phase4b.md)。
- 2026-10-13：Phase 3 配置态持久化与管理面验收记录见 [production-phase3.md](research/arm64/production-phase3.md)。
- 2026-10-15：三次冷启动、两次 UI 干净关机、两轮 30 guest minutes 与账号清理通过，见 [严格 F5 证据](research/arm64/production-phase3.md#strict-f5-completed-acceptance-evidence--2026-10-15)。

## 按需入口

- 平台与 Phase 3：[docs/platforms.md](docs/platforms.md)、[research/arm64/production-phase3.md](research/arm64/production-phase3.md)
- 治理与审查：[docs/GOVERNANCE.md](docs/GOVERNANCE.md)、[docs/AI_RULES.md](docs/AI_RULES.md)
- CI 与发布：[docs/ci.md](docs/ci.md)
