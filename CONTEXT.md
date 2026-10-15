# 当前状态

> **最后确认：** 2026-10-15
> **阶段：** Phase 3 / F4
> **产品代码：** 生产 QEMU 8.2.2 补丁系列与 ARM `rtd1619b` 实验路径；严格 F5 未完成。

## 当前决策

- 仓库独立维护于 [Ben8368/virtual-dsm](https://github.com/Ben8368/virtual-dsm)；上游 vdsm 变更不自动同步。
- `DSM_PLATFORM=virtualdsm` 为稳定 x86 默认；`rtd1619b` 为实验性 DS124 ARM64 路径。
- 生产 QEMU 补丁只经 [patches/qemu/8.2.2](patches/qemu/8.2.2/README.md) 与共享 apply helper 进入镜像。
- 严格 Phase 3 F5 仍要求两次访客 UI 干净关机；不把 host-directed stop 记为干净关机。

## 近期优先级

1. 恢复或轮换配置态 clone 的 disposable 管理员会话，完成严格 F5。
2. 完成 Phase 4 准备：原生 ARM64-host KVM 验证与生命周期硬化。
3. 保持治理文档与 CI 六项红绿灯一致，避免事实源漂移。

## 当前阻断与风险

- F5 阻断于 DSM Auth（API 499）；详见 [RISK-001](docs/RISK_REGISTER.md#risk-001)。
- ARM64 KVM 与 Surveillance Station 仍属未验证硬件/包路径。

## 最近验证

- 2026-10-13：Phase 3 配置态持久化与管理面验收记录见 [production-phase3.md](research/arm64/production-phase3.md)。
- 2026-10-15：文档治理与六项 CI 门禁落地；检查入口见 [GOVERNANCE.md](docs/GOVERNANCE.md)。

## 按需入口

- 平台与 Phase 3：[docs/platforms.md](docs/platforms.md)、[research/arm64/production-phase3.md](research/arm64/production-phase3.md)
- 治理与审查：[docs/GOVERNANCE.md](docs/GOVERNANCE.md)、[docs/AI_RULES.md](docs/AI_RULES.md)
- CI 与发布：[docs/ci.md](docs/ci.md)
