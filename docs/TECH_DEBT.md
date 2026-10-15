# 技术债

技术债是已经进入实现、当前有意保留且未来需要偿还的妥协。尚未实现或尚未验证的外部假设属于 [RISK_REGISTER.md](RISK_REGISTER.md)。

## 分级

- **P0**：数据安全、正确性或当前验收阻断。
- **P1**：明显影响可靠性、性能或维护性，应在近期迭代偿还。
- **P2**：长期结构优化。

## 活跃技术债

### TD-001：ARM 容器停止缺少访客侧关机代理

- **优先级 / 位置 / 来源 / 目标阶段：** P1；`src/platform/rtd1619b.sh` `platformGuestShutdown`；Phase 3 生命周期；F5 前后。
- **当前妥协与原因：** ARM 路径明确要求通过 DSM UI/API 关机；共享 `power.sh` 的 x86 qemu-host API 不适用；容器 `docker stop` 仍可能走超时回退。
- **影响与最坏结果：** 自动化验收依赖凭据齐全的 UI shutdown；凭据失效时无法完成干净 guest-poweroff。
- **偿还方案：** 在不降低安全边界的前提下，评估 QMP 协作关机或受控 API 客户端；任何方案需保留 `guest-shutdown` 收据语义。
- **验证方式：** 两次干净关机出现 `All filesystems unmounted.`、`guest-poweroff`、QEMU rc=0。

登记模板：

```text
TD-XXX：标题
优先级 / 位置 / 来源 / 目标阶段
当前妥协与原因
影响与最坏结果
偿还方案
验证方式
```

## 生命周期

1. 红绿灯审查中的跨任务 🟡 或明确延期的实现妥协进入本文件。
2. 修复必须有回归证据；完成后移入 `docs/archive/tech-debt/YYYY-MM.md`。
