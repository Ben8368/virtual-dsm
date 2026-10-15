# ADR 0002：生产 QEMU 补丁单一目录

- 状态：已接受
- 日期：2026-10-15

## 背景

ARM 平台依赖精确的 QEMU v8.2.2 补丁。若研究补丁与生产补丁混用，镜像层缓存或本地 bind-mount 容易让“已验证二进制”与仓库事实源漂移。

## 决策

- 生产补丁只存在于 `patches/qemu/8.2.2/`，由 `scripts/apply-qemu-patches.sh` 应用到精确上游提交。
- 研究补丁保留在 `research/arm64/qemu/`，晋升前不得被 `Dockerfile` 消费。
- `tests/qemu-patches.sh` 与 CI “QEMU patch apply” job 验证干净应用。

## 后果

生产行为可审计；研究实验可并行。晋升需要显式移动/新增编号补丁并更新 README。

## 替代方案

- 在构建脚本中 curl 外部补丁：拒绝，不可复现。
- 允许研究目录被生产 Dockerfile 直接 COPY：拒绝，边界模糊。

## 关联文档

- [patches/qemu/8.2.2/README.md](../../patches/qemu/8.2.2/README.md)
- [docs/platforms.md](../platforms.md)
