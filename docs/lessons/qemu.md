# Lesson：QEMU 补丁与 TCG

- 生产补丁系列与研究补丁必须分离；晋升走 `patches/qemu/8.2.2/`。
- DC ZVA 病理 NOTDIRTY 来自 CODE 保护残留 TB；缓解是保守整页 TB 失效，不是改写访客内存语义。
- 不要用扩展 `tb_invalidate_phys_range_fast` 长度绕过 API 契约。
- soft lockup 串口匹配要避开 `init_oops_id` 等假阳性。
