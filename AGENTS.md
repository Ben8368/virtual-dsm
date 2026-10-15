# AI 协作规范

`AGENTS.md` 是 AI 协作的唯一入口；`CLAUDE.md` 与 `.cursorrules` 只能保留摘要。规则细节只在权威文档维护，不在入口复制。

## 开局与按需读取

所有任务先读 [CONTEXT.md](CONTEXT.md) 和 [LESSONS.md](LESSONS.md)，再按本轮实际改动/审查对象加载命中项；文中提及某关键词不触发整条依赖链，不递归读取所有链接：

| 任务 | 必读文档 |
| --- | --- |
| 产品范围、平台能力、发布边界 | [docs/PRODUCT.md](docs/PRODUCT.md)、[docs/platforms.md](docs/platforms.md)、[readme.md](readme.md) |
| 任意产品源码改动 | [docs/AI_RULES.md](docs/AI_RULES.md)、[docs/QUALITY.md](docs/QUALITY.md) |
| ARM64 / DS124 / Phase 3 | [docs/arm64-development.md](docs/arm64-development.md)、[research/arm64/production-phase3.md](research/arm64/production-phase3.md)、[docs/arm64-runtime-state.md](docs/arm64-runtime-state.md) |
| QEMU 补丁或 TCG | [patches/qemu/8.2.2/README.md](patches/qemu/8.2.2/README.md)、[docs/platforms.md](docs/platforms.md) |
| CI、镜像发布、依赖更新 | [docs/ci.md](docs/ci.md) |
| 技术债、风险或阶段推进 | [docs/TECH_DEBT.md](docs/TECH_DEBT.md)、[docs/RISK_REGISTER.md](docs/RISK_REGISTER.md) |
| 治理文档改动 | [docs/GOVERNANCE.md](docs/GOVERNANCE.md) |
| 维护职责或长期决策 | [docs/MAINTAINERS.md](docs/MAINTAINERS.md)、[docs/ADR/README.md](docs/ADR/README.md) |

Windows PowerShell 读取或输出中文时使用 UTF-8；文件一律保存为 UTF-8、LF。

## 不可跨越的边界

- 本仓库维护独立的 Virtual DSM Docker 镜像；默认 x86 平台为 `virtualdsm`，ARM 实验平台为 `rtd1619b` / DS124。
- 不把研究脚本、临时凭据、PAT、磁盘镜像或串口长日志提交进 Git；专有证据留在忽略目录。
- 生产 QEMU 补丁只通过 `patches/qemu/8.2.2/` 与 `scripts/apply-qemu-patches.sh` 进入镜像；研究补丁不得静默混入生产系列。
- 不修改访客 DSM 看门狗设置来“过”稳定性门禁；不伪造 configured/volume/HTTP 就绪。
- 未经目标环境证据，不得宣称 KVM、Surveillance Station、商店兼容或 Phase 验收完成。
- 默认不自动提交、推送或发布；仅在用户明确要求时执行对应 Git/发布动作。

## 执行与汇报

- 改动前确认事实源，避免把同一状态复制到多份文档。
- 源码改动后按 [docs/AI_RULES.md](docs/AI_RULES.md) 输出 `🚦 Audit Report`，再运行约定验证；文档改动至少运行 `python3 scripts/governance-docs-check.py`。
- 客观验证必须给出命令和结果；真机/TCG 冷启动与管理面结论必须保留证据，不能由构建通过代替。
- 当前状态只写 [CONTEXT.md](CONTEXT.md)；风险与技术债分开登记；长期决策写 ADR。
- 提交信息与 AI `Co-authored-by` trailer 以 [docs/AI_RULES.md](docs/AI_RULES.md) 为准。
- 默认使用中文汇报；标识符、命令、路径、API 字段和专有名词保留原文。

## 治理文档自治理

- 遵守 [docs/GOVERNANCE.md](docs/GOVERNANCE.md) 的单一事实源、篇幅预算、状态词和归档规则。
- `AGENTS.md`、`CONTEXT.md`、`LESSONS.md` 是强制加载面，只保留路由、当前事实和经验索引。
- 治理改动后运行 `python3 scripts/governance-docs-check.py`；超预算时先拆分或归档，不提高预算逃避治理。
