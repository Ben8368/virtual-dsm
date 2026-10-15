# Validated QEMU 8.2.2 production patches

Apply in filename order to upstream v8.2.2, commit
`11aa0b1ff115b86160c4d37e7c37e6a6b13b77ea`.

- `0001-arm-virt-dsm-platform.patch`: migrated from research
  `0001-arm-virt-add-research-mmio-16550.patch` without code changes. Adds the
  DSM MMIO 16550, sysbus AHCI with Realtek DT binding and sysbus XHCI.
- `0002-arm-virt-syno-leds.patch`: migrated from research
  `0002-arm-virt-add-research-syno-leds.patch`. Adds the syscon/register-bit-led
  and internal_slot@1 contract required by stock ds124_synobios.
  The original file's SHA256 was
  `5516ed3d762e63365b7df5ea2b410663c34d06dee9ba3072b031481e037d4207`.
  Its malformed hunk counts/positions were corrected, and one existing comment
  from the validated research source was restored. Executable C content is
  unchanged. Applying the first two production patches reproduces the Phase 2 research virt.c
  and virt.h byte-for-byte.

- `0003-arm-virt-dsm-shutdown-uart.patch`: registers a second MMIO 16550 at
  0x0b010000, IRQ 13 and DT alias serial1. Stock DS124 writes ttyS1 in its
  poweroff syscall before kernel_power_off(); the unprobed placeholder port
  faults in io_serial_out. This supplies a valid port without emulating microP
  responses. The console stays serial0; the control serial backend is null.

- `0004-tcg-dczva-full-page-code-invalidate.patch`: graduated from research
  `dcz-full-page-invalidation-candidate.patch`. Generic AArch64 DC ZVA
  handling: after both normal write probes succeed for RAM that is still
  NOTDIRTY with DIRTY_MEMORY_CODE clean, conservatively invalidate translated
  code for the whole target physical page (preserving retaddr / precise-SMC
  unwind), then reacquire through the ordinary block probe. The architectural
  zero remains exactly one DC ZVA block. No DSM, DS124 or RTD1619B branding.
  Watchpoints, permission faults, I/O byte-store fallback and migration/VGA
  dirty tracking stay on the existing paths.

The old research patch implementations were removed; the research directory
keeps a pointer. Production and research use `scripts/apply-qemu-patches.sh`.
The helper checks the exact upstream commit, clean-applies the series in a
scratch tree, then either applies to pristine tracked files or verifies that
the whole series is already present byte-for-byte across virt and TCG sources.
It never discards source changes or accepts a function-name substring as patch
identity.

`tests/qemu-patches.sh` separately checks clean application without compilation.
The native Docker builder compiles only aarch64-softmmu. All four patches are
mandatory; do not omit LED compatibility because initial HTTP works, and do not
omit DC ZVA code invalidation when rebuilding production QEMU.
