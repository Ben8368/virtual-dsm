# 质量与验收

## 证据分层

| 层级 | 含义 | 示例 |
| --- | --- | --- |
| L0 静态 | 语法/策略/文档预算 | shellcheck、governance-docs-check、qemu patch apply |
| L1 合成 | 无官方 PAT 的本地回归 | `tests/arm-runtime.py`、`image-validation.py` |
| L2 生产路径 | 官方 PAT / 配置态冷启动 | Phase 3 HTTP、persistence、guest-poweroff |
| L3 硬件 | 目标宿主加速或外设 | ARM64 KVM |

上层通过不能代替下层未跑项。

## CI 红绿灯（6/6）

PR 与 `master` 推送的 `CI` workflow 固定为六个可检查 job：

1. Docs governance
2. Lint
3. Synthetic regression tests
4. QEMU patch apply
5. Research smoke
6. Production image build（amd64；arm64 由同系列原生 runner 工作流覆盖）

六项全绿是仓库自动通行条件；人工 `🚦 Audit Report` 仍是源码合并前的独立门禁。

## 完成定义（摘要）

- Phase 3 F5：配置态、PostgreSQL、volume1、persistence SHA、30/30 HTTP、HTTPS 200、两次干净 guest-shutdown、≥30 分钟无 soft lockup/oops/panic。
- 不得用 host-directed `docker stop` / SIGINT 充当干净关机。
