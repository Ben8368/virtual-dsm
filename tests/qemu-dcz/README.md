# DC ZVA production-QEMU regression

These synthetic AArch64 fixtures test the QEMU 8.2.2 production patch series.
They contain no DSM payload, guest disk, account or credential. All guests use
`virt,gic-version=3`, two TCG vCPUs, 128 MiB RAM and no NIC. The selected binary
must already contain the production patches; the suite never applies research
instrumentation or changes the production image.

## Run

On Linux with Bash, Python 3, GNU coreutils, `aarch64-linux-gnu-gcc` and
`aarch64-linux-gnu-nm`:

```sh
bash tests/qemu-dcz/run.sh /path/to/patched/qemu-system-aarch64 /tmp/qemu-dcz
```

`AARCH64_CC` and `AARCH64_NM` may select equivalent compiler/binutils executables.
Use a fresh output directory for each run. The suite records the QEMU version,
binary SHA256, compiled fixtures, serial logs and watchpoint/migration results.
Failed compilation, QEMU exit, timeout or assertion fails the suite.

To test the exact binary inside a built production image:

```sh
bash tests/qemu-dcz/docker.sh virtual-dsm:local /tmp/qemu-dcz-image
```

The Docker wrapper mounts the checkout read-only and the output directory
read-write. It installs cross-GCC/binutils only inside a disposable container.
Package acquisition needs network access; the synthetic QEMU guests have no NIC.
Both native image CI jobs run this same wrapper after building the image.

## Coverage and limits

- Exact 64-byte zeroing at 64 alignments, preserving surrounding RAM.
- Stale-code prevention, unaffected code on the same page, self-zeroing code
  across ISB, and functions spanning two pages.
- 128 handoffs between two vCPUs while unaffected same-page code executes.
- Permission/translation faults under a guest MMU and read-only MMIO fallback.
- A GDB write watchpoint on the last byte of a block, stopping before RAM changes.
- Actual migration and restore: DC ZVA clears 16 MiB after at least 8 MiB has
  already transferred; every restored byte must be zero.

The fixtures assume the selected `-cpu max` exposes a 64-byte DC ZVA block.
They test TCG correctness, not KVM/HVF compatibility, DSM readiness, watchdog
acceptance or NAS performance. Historical counters and performance experiments
remain private local research material. No i386 precise-SMC execution is claimed.

The historical AArch32 Thumb cross-page fixture did not reproduce its expected
result, including ordinary-store controls. It remains private and outside this
suite; see RISK-004 in the [risk register](../../docs/RISK_REGISTER.md).
The AArch64 two-page-function test above spans separate TBs and does not establish
invalidation of a single TB spanning two physical pages.
