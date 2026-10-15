# 风险与开放假设

本文件只登记尚未验证的外部不确定性；实现后有意保留的妥协进入 [TECH_DEBT.md](TECH_DEBT.md)。

## 分级

- **P0**：阻断指定验收门禁。
- **P1**：不阻断当前门禁，但会改变发布或体验边界。
- **P2**：后续增强风险。

## 活跃风险

### RISK-002（P1）：原生 ARM64-host KVM 未经验证

- **阻断 Gate：** Phase 4 / 发布级 ARM 性能声明。
- **问题：** 当前验收主要在 amd64 宿主 TCG multi；KVM 兼容探针后的真机路径未闭环；stock DSM 对目标 KVM 的 LPA2 暴露兼容性未知。
- **环境证据与协议：** [Phase 4A](../research/arm64/production-phase4a.md)；需真实 ARM64 主机及独立 KVM 初始化、guest-visible CPU features 证据。
- **关闭证据：** 目标 ARM64 宿主上的冷启动、管理面与稳定性记录。

### RISK-003（P2）：Surveillance Station 与包安装矩阵未完成

- **阻断 Gate：** 功能完整度声明。
- **问题：** 包安装与 Surveillance 仍依赖单独文档路径，不由默认 CI 证明。
- **关闭证据：** 见 [package-installation.md](package-installation.md) 约定的官方 PAT/硬件检查。

### RISK-004（P2）：历史 Thumb 跨页实验结果未澄清

- **阻断 Gate：** 单个 TB 跨两物理页的动态覆盖声明；不改写既有 AArch64 DSM F5 证据。
- **问题：** 整理历史夹具时，修正汇编 `.endr` 后，生产 QEMU 8.2.2 的 Thumb 实验返回 0x1234，预期为 0x1000；目标半字实际为零。普通半字 store 和显式 cache-maintenance 对照同样失败，尚不能归因为 DC ZVA 补丁或确定为夹具错误。
- **证据与边界：** 忽略目录 `research/arm64/work/local-file-cleanup/thumb-investigation/` 保存三组日志；`local-archive-2026-10-15/diagnostics/thumb-investigation/` 保存修复后的实验源码。二进制 SHA256 与 [Phase 4A 预检](../research/arm64/production-phase4a.md) 相同。该实验未进入正式 [DC ZVA 测试](../tests/qemu-dcz/README.md)，正式套件仅声明已核查的 AArch64 覆盖。
- **关闭证据：** 独立核对 Thumb 解码、异常返回、访客内存和实际 TB 覆盖，获得可重复且能解释 store 对照结果的最小实验，再决定修正夹具或调查 QEMU。

## 已关闭风险

- [RISK-001：Phase 3 严格 F5](archive/risks/2026-10.md#risk-001)。
