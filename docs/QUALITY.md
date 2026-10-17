# 质量与验收

## 证据分层

| 层级 | 含义 | 示例 |
| --- | --- | --- |
| L0 静态 | 语法、策略、文档预算、QEMU 补丁干净应用 | ShellCheck、governance-docs-check、`tests/qemu-patches.sh` |
| L1 合成 | 无官方 PAT 的单元/合成与镜像构建检查 | ARM installer/runtime、image validation、accelerator/lifecycle policy |
| L2 产品运行时 | 官方 PAT 的产品冷启动、配置和持久化 | Phase 3 F5、Phase 4A K5 |
| L3 硬件加速 | 指定宿主和加速器上的运行证据 | M5 + Apple VZ nested KVM；裸机 ARM64 单独列项 |

上层通过不能代替下层未跑项。CI 不证明 DSM 启动或 KVM 兼容。

## CI 红绿灯（6/6）

PR 与 `master` 推送的 `CI` workflow 固定为六个可检查 job：

1. Docs governance
2. Lint
3. Synthetic regression tests（amd64 与 arm64 hosted runners）
4. QEMU patch apply
5. Research smoke
6. Production image build（原生 amd64 与 arm64 runners）

| Accepted baseline | Evidence |
| --- | --- |
| Phase 3 F5 + Watchdog L5 | [Strict F5 boot, watchdog scan, persistence and UI shutdown evidence](../research/arm64/production-phase3.md#strict-f5-completed-acceptance-evidence--2026-10-15) |
| Phase 4A K5 | [Official PAT fresh install, configured KVM boots, volume, marker and lifecycle evidence](../research/arm64/production-phase4a.md) |

六项全绿是仓库自动通行条件；人工 `🚦 Audit Report` 仍是源码合并前的独立门禁。

## 完成定义（摘要）

- Phase 3 F5：配置态、PostgreSQL、volume1、persistence SHA、30/30 HTTP、HTTPS 200、两次干净 guest-shutdown、≥30 分钟无 soft lockup/oops/panic。
- 不得用 host-directed `docker stop` / SIGINT 充当干净关机。
