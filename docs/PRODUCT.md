# 产品范围摘要

权威展开见根 [readme.md](../readme.md) 与 [platforms.md](platforms.md)。本文件只固定范围边界，避免在多处复制长文。

## 目标

- 在 Docker 中运行 Virtual DSM；默认平台 `virtualdsm`（x86）。
- 提供实验性 `rtd1619b` / DS124 ARM64 访客路径与官方 PAT 自动准备。
- 独立维护、独立发布 `ghcr.io/ben8368/virtual-dsm`。

## 非目标（当前）

- 不宣称物理 DS124 分区表完全兼容。
- 不默认同步上游 vdsm 变更。
- 不在未验证前宣称 ARM64 KVM、Surveillance Station 或商店级支持。
- 不把研究用诊断补丁当作未晋升的生产行为。
