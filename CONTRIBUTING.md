# 贡献指南

## 分支与 PR

- 从当前默认分支开题分支；一个 PR 一个可审查主题。
- PR 描述使用仓库模板；客观验证与主观确认分开写。
- CI 六个 job 全绿是自动通行条件；源码改动另需 `🚦 Audit Report`（见 [docs/AI_RULES.md](docs/AI_RULES.md)）。

## 提交

- Conventional Commit 类型前缀用英文，标题/正文用中文。
- AI 工具参与的提交必须附加工具级 `Co-authored-by` trailer；纯人工使用 `Human-authored: true`。
- 本地启用钩子：`python3 scripts/install-git-hooks.py`。

## 验证

```bash
python3 scripts/governance-docs-check.py
python3 scripts/git-hooks-test.py
shellcheck -x src/*.sh src/platform/*.sh research/arm64/*.sh research/arm64/tests/*.sh
bash research/arm64/tests/smoke.sh
bash tests/qemu-patches.sh
```

完整合成回归见 [docs/ci.md](docs/ci.md) 与 `.github/workflows/test.yml`。
