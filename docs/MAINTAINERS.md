# 维护者职责

当前以本文件定义责任域；在 `CODEOWNERS` 建立前，合并前重点按下表执行。

## 责任域

| 领域 | 规划范围 | 合并前重点 |
| --- | --- | --- |
| Product / Platforms | 产品范围、`virtualdsm` / `rtd1619b` | 不夸大 KVM/商店/验收状态 |
| QEMU / TCG | `patches/qemu/8.2.2`、apply helper | 补丁可干净应用、研究/生产边界 |
| ARM runtime | 安装、runtime schema、生命周期 | 失败封闭、不丢用户盘 |
| CI / Release | workflows、GHCR 发布 | 六项红绿灯、无秘密泄漏 |
| Governance / Quality | AGENTS、Context、Risk、测试 | 事实源、证据状态、署名 trailer |

## 必须升级评审

- 生产 QEMU 补丁系列增减或语义变化。
- ARM 运行时磁盘策略、重置/恢复语义变化。
- 对外发布镜像标签或默认平台行为变化。
- 安全、凭据处理或专有产物策略变化。

## 合并原则

- 🔴 不得合并；🟡 必须进入 Risk 或 Tech Debt。
- 客观验证和主观确认分开记录。
- 长期边界变化必须有 ADR。
