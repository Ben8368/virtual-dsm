# 治理文档维护规则

## 目标

治理文档要让执行者快速获得正确边界、当前事实和下一步，而不是把历史、计划、命令和复盘复制到每个入口。原则是：**单一事实源、按需加载、证据分级、预算可检查、历史可归档**。

## 单一事实源

| 事实 | 唯一权威位置 | 不应重复的位置 |
| --- | --- | --- |
| AI 入口、硬边界、读取路由 | `AGENTS.md` | 工具摘要、专题文档 |
| 当前阶段、决策、三项优先级、最近验证 | `CONTEXT.md` | Roadmap 展开、提交记录 |
| 可复发经验的索引与详情 | `LESSONS.md`、`docs/lessons/*` | Context、技术债 |
| 产品范围与非目标摘要 | `docs/PRODUCT.md` | README 长文展开的重复结论 |
| 平台契约与启动参数 | `docs/platforms.md` | 研究笔记中的副本 |
| ARM 开发与 Phase 证据 | `docs/arm64-development.md`、`research/arm64/production-phase3.md` | Context 细节 |
| 运行时磁盘策略 | `docs/arm64-runtime-state.md` | 安装脚本注释 |
| QEMU 生产补丁系列 | `patches/qemu/8.2.2/README.md` | 研究 README 的晋升声明之外 |
| CI / 发布 | `docs/ci.md` | workflow 注释 |
| 测试策略与完成定义 | `docs/QUALITY.md` | PR 模板副本 |
| 未验证假设与外部风险 | `docs/RISK_REGISTER.md` | 技术债、Context 详情 |
| 已产生的实现妥协 | `docs/TECH_DEBT.md` | 风险台账 |
| 长期决策及理由 | `docs/ADR/*` | 状态卡、提交信息 |
| 审查、验证、提交与 AI Git trailer | `docs/AI_RULES.md` | `AGENTS.md`、`CONTRIBUTING.md` 的副本 |
| 历史状态、已关闭风险、长复盘 | `docs/archive/` 与 Git 历史 | 强制加载文件 |

## 状态词

- **设计中**：存在方案，没有实现。
- **计划**：已进入路线，但尚未开始。
- **已实现未验证**：代码存在，目标环境证据不足。
- **已验证**：通过约定自动化或真实路径验收，并记录证据。
- **不支持**：明确拒绝或不在当前范围。

“构建通过”不等于“能力已验证”；“研究复现”不等于“生产门禁通过”。

## 强制加载预算

由 `python3 scripts/governance-docs-check.py` 同时检查行数和字符数：

| 文件 | 最大行数 | 最大字符数 | 允许内容 |
| --- | ---: | ---: | --- |
| `AGENTS.md` | 85 | 5,200 | 路由、硬边界、执行入口 |
| `CONTEXT.md` | 45 | 3,000 | 当前事实、三项优先级、最近验证 |
| `LESSONS.md` | 20 | 1,800 | 任务标签到经验详情的路由 |
| `CLAUDE.md` / `.cursorrules` | 12 | 800 | 指向 `AGENTS.md` 的摘要 |

超预算时先拆分或归档，不允许单纯提高预算。

## 更新触发器

1. 先判断事实属于哪个权威文档，只更新一处，其他位置只放链接或一句稳定摘要。
2. `CONTEXT.md` 仅在阶段、当前阻断、前三优先级或最近验证结论变化时更新；每条“最近验证”必须链接证据。
3. 尚未验证的外部不确定性进入 `RISK_REGISTER`；代码已经产生且未来需偿还的妥协进入 `TECH_DEBT`。
4. 影响长期边界、公开契约、补丁策略或发布的决定新增 ADR。
5. 关闭的风险、已偿债条目与长复盘按日期移入 `docs/archive/`。

## 变更验收

1. 运行 `python3 scripts/governance-docs-check.py`。
2. 人工确认链接指向权威文档，未把未测结论写成已验证。
3. 确认 Context 仍只有三项可执行优先级。
4. 若改变平台、QEMU 或安全边界，确认对应 ADR / PRODUCT / platforms 已同步。
