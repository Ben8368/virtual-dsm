# AI 开发与审查规则

> 协作入口见 [AGENTS.md](../AGENTS.md)，当前状态见 [CONTEXT.md](../CONTEXT.md)，文档治理见 [GOVERNANCE.md](GOVERNANCE.md)。

## 1. 工作顺序

```text
读取 Context / Lessons → 确认当前阶段与事实源 → 修改 → 红绿灯审查 → 客观验证 → 更新唯一权威文档 → 汇报
```

- 答疑或评审只做只读检查，除非用户同时要求修改。
- 默认不自动提交、推送、发布或创建外部资源。

## 2. 红绿灯审查

产品源码发生变化后、运行完整验证前，必须输出：

```markdown
## 🚦 Audit Report

**总体评价：** [ 🔴 阻断 / 🟡 可通行 / 🟢 通过 ]

**1. 🔴 阻断项：**
- 无 / 具体问题

**2. 🟡 跟进项：**
- 无 / 具体问题及权威登记位置

**3. 验证计划：**
- 命令、真实路径与未覆盖项
```

审查至少覆盖：真实性、范围、生产/研究边界、补丁与凭据安全、异常路径、可测试性。

分级：

- 🔴：安全越界、伪造就绪、生产/研究补丁混用、数据丢失、契约破坏或阶段越权。
- 🟡：不阻断当前目标，但存在已登记的兼容性、性能或验收缺口。
- 🟢：范围内目标完成，客观验证通过，没有未登记风险。

🔴 不得合并或宣称完成；🟡 必须进入 `RISK_REGISTER` 或 `TECH_DEBT`。

## 3. 验证层级

| 变化 | 最低验证 |
| --- | --- |
| 仅治理文档 | `python3 scripts/governance-docs-check.py` |
| Shell / 平台脚本 | 上述 + `shellcheck` + `bash research/arm64/tests/smoke.sh` |
| QEMU 补丁 | 上述 + `bash tests/qemu-patches.sh` |
| 生产镜像 / ARM 行为 | 上述 + 文档化冷启动或合成回归；不得用构建代替访客证据 |

未执行的项写“未运行”及原因。

## 4. 文档与 Git

- 只更新发生事实变化的权威文档，遵守 [GOVERNANCE.md](GOVERNANCE.md)。
- 默认不自动 `git commit` / `git push` / 发布；仅在用户明确要求时执行。
- 不修改或清理用户的无关改动，不使用破坏性 Git 命令；不得提交凭据、PAT 或磁盘镜像。

### 提交信息与 AI trailer

- 标题与正文使用中文；Conventional Commit 类型前缀与 Git trailer 键名保留英文，例如 `feat:`、`fix:`、`docs:`。
- 一次提交只表达一个可审查主题。
- AI 工具参与实质改动并执行提交时，在 message 末尾追加对应 `Co-authored-by` trailer，前方保留一个空行。主作者保持维护者身份。
- trailer 记录**工具来源**，不记录具体模型。

| 当前工具 | 必须追加的 trailer |
| --- | --- |
| Codex | `Co-authored-by: Codex <codex@openai.com>` |
| Claude Code | `Co-authored-by: Claude Code <noreply@anthropic.com>` |
| Cursor（含 Cursor Agent / Auto） | `Co-authored-by: Cursor <cursoragent@cursor.com>` |

Windows PowerShell 中不得在单个 `git commit -m` 字符串内嵌入 `\n`。正文与 trailer 使用独立 `-m` 参数：

```powershell
git commit -m "docs: 标题" -m "正文说明。" -m "Co-authored-by: Cursor <cursoragent@cursor.com>"
```

提交后必须执行：

```powershell
git show -s --format=%B HEAD | git interpret-trailers --parse
```

确认对应 `Co-authored-by` 出现在解析结果中。

### 仓库级署名校验

每个独立 clone 都应运行 `python3 scripts/install-git-hooks.py`，启用 [.githooks/commit-msg](../.githooks/commit-msg)。安装只设置该 clone 的 `core.hooksPath`。纯人工改动用 `Human-authored: true`；有 AI 参与不得混用该声明。CI 运行 hook 回归，不扫描或重写旧提交。
