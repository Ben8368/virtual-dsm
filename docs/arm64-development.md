# ARM64 DSM development notes

Status: the research PoC reached B5 and its validated hardware contract has
graduated into Production Integration Phase 1. Experimental DS124 / rtd1619b
automatically prepares the exact DSM 7.2.2-72806 PAT (Production Integration
Phase 2); stable x86 VirtualDSM remains the default. See
[automatic preparation](arm64-auto-install.md). See
[the production platform interface](platforms.md).

The historical research evidence below is retained. Architecture audit statements
describe the pre-integration code unless explicitly marked as production.

## Startup and architecture audit

`Dockerfile` copies the qemux/qemu 7.50 runtime into this image and overlays
this repository's `/run` scripts. `src/entry.sh` is the startup orchestrator:
it sources the base image's `start.sh`, `utils.sh`, `init.sh`, `memory.sh`,
`server.sh`, `download.sh`, `disk.sh`, `display.sh`, `network.sh`, `boot.sh`,
`proc.sh`, `balloon.sh`, and helper scripts. Those inherited files are not in
this repository, so their behavior comes from qemux/qemu. The current upstream
base `init.sh` defaults `MACHINE=q35`; the ARM reference replaces architecture
hooks rather than duplicating the base layer. The inherited files are absent
from this checkout, so verify exact runtime behavior against the built image
when it is available; source links below point to qemux/qemu upstream.

The repo-specific parts are:

| Area | Current behavior | Classification |
|---|---|---|
| Guest selection | `src/entry.sh` defaults `PLATFORM=x64` and unconditionally runs `qemu-system-x86_64`. | x86 guest specific |
| PAT install | `src/install.sh` reuses `/run/extract.py` (patology), supports tar PATs, expects `*.bin.zip`, `hda1.tgz`, and x86 VirtualDSM partition layout. | VirtualDSM/PAT-layout specific |
| Boot disks | `src/prepare.sh` creates boot and system disks using the configured disk device and Synology boot order. | VirtualDSM-specific; device choice needs ARM validation |
| Machine | `src/config.sh` adds `q35`, SMM, VMPort, HPET, and PCIe bus/address assumptions. | x86/q35-specific |
| Processor | `src/config.sh` sets an x86-style CPU topology; `src/install.sh` checks SSE4.2 for x64 when KVM is enabled. | x86-specific |
| Serial | `src/serial.sh` attaches a qemu-host VirtIO serial port on a PCI bus. | PCI/VirtIO and DSM-agent specific |
| Disk/network lifecycle | Primarily inherited from qemux/qemu and configured here through shared variables. | Mostly architecture-independent orchestration; emulated devices/drivers are guest-specific |
| Image build | `.github/workflows/build.yml` targets amd64 and arm64. The qemux/qemu base installs `qemu-system-x86`; it does not establish that `qemu-system-aarch64` is present. | Container multi-arch only |

The inherited qemux `init.sh` defaults `KVM=Y`, `MACHINE=q35`, and
`BOOT_MODE` unset. It sets `ARCH` from `dpkg --print-architecture` (the image
architecture), derives a KVM target from the guest `PLATFORM`, and disables
KVM when those do not match. Thus the existing `PLATFORM=x64` guest on an
ARM64 image uses TCG; that is x86 emulation, not ARM KVM. CPU and acceleration
options are then assembled in `proc.sh`. Its generic disk helper accepts IDE/SATA/NVMe/USB,
SCSI, `virtio-blk`, and `virtio-scsi` device types; network setup defaults to
`virtio-net-pci`. These are QEMU-side choices only: the DSM kernel must have
the matching drivers and a bootable machine description. The ARM reference
changes the machine to `virt`, supplies ARM GIC settings, and chooses ARM CPU
models and firmware. Its source install explicitly includes `qemu-system-arm`
and AAVMF; the base x86 image's `qemu-system-x86` package is insufficient for
the native ARM guest.

The key variables are distinct: `HOST_ARCH` describes the container host,
`GUEST_ARCH` describes the emulated processor, and a DSM platform selects the
guest image/model. Today the repo has no explicit platform-selection layer:
`PLATFORM=x64` and the hardcoded emulator implement VirtualDSM. The base KVM
logic may disable acceleration for an architecture mismatch; an ARM host with
an x86 guest is not ARM KVM acceleration. `qemus/qemu-arm` uses separate ARM
hooks (`entry.sh`, `boot.sh`, `config.sh`, `proc.sh`, `display.sh`) and
`qemu-system-aarch64`, `MACHINE=virt`, ARM CPU/GIC settings, and ARM firmware.
Its Debian install adds `qemu-system-arm`; these are useful references, not
proof that a Synology kernel boots there.

FnNAS and the ophub kernel/u-boot/Armbian projects organize real boards around
platform, SoC, kernel/modules, DTB, bootloader, and board configuration. That
separation is relevant if a DSM image is ever bootable, but their board-specific
behavior is not applicable to DSM.

References inspected: [qemus/qemu-arm entry](https://github.com/qemus/qemu-arm/blob/master/src/entry.sh),
[ARM QEMU config](https://github.com/qemus/qemu-arm/blob/master/src/config.sh),
[ARM QEMU boot](https://github.com/qemus/qemu-arm/blob/master/src/boot.sh),
[ARM QEMU processor setup](https://github.com/qemus/qemu-arm/blob/master/src/proc.sh),
[qemux base init](https://github.com/qemus/qemu/blob/master/src/init.sh),
[qemux base processor setup](https://github.com/qemus/qemu/blob/master/src/proc.sh),
[qemux base disk helper](https://github.com/qemus/qemu/blob/master/src/disk.sh),
[qemux base network helper](https://github.com/qemus/qemu/blob/master/src/network.sh),
and [ophub/fnnas](https://github.com/ophub/fnnas).

## DS124 7.2.2 PAT inventory

The official [Synology Archive release listing](https://archive.synology.com/download/Os/DSM/7.2.2-72806)
provides `DSM_DS124_72806.pat` (the DS124 ARMv8 / `rtd1619b` build). It was
downloaded only to the ignored `research/arm64/work/` directory for this
investigation and must not be redistributed.

| Property | Finding |
|---|---|
| Filename | `DSM_DS124_72806.pat` |
| Size | 319,317,444 bytes (304.52 MB as listed by Synology) |
| SHA256 | `17f48a9a4572c9b3b994921d3fb410d8186e9c4bf02cf9334e37897e5752e1dd` |
| DSM version | 7.2.2-72806 |
| Platform / model | `rtd1619b` / DS124 |

The file is a Synology PAT archive, not a tar file (`tar -tf` reports “This
does not look like a tar archive”). The normal Docker extractor initially
could not contact the WSL Docker daemon (`permission denied` on
`/var/run/docker.sock`). `extract-pat.sh` was improved to use the same upstream
`patology.py` extractor and its Python dependencies from an ignored local
workspace when Docker is unavailable. PAT signature validation succeeded and
47 entries were extracted. No production installer code was changed.

The generated inventory is `research/arm64/work/pat-report.txt`. Important
top-level artifacts include `zImage` (4,942,880 bytes), `rd.bin` (7,360,512),
`model.dtb` (40,837), `uboot_DS124.bin` (1,576,960),
`uboot_do_upd.sh`, `hda1.tgz` (205,899,560), `synohdpack_img.txz`,
`indexdb.txz`, `VERSION`, and ARMv8 / `rtd1619b` packages. There are no
`*.dtbo`, `*.bin.zip`, FIT image, or GRUB boot configuration artifacts in the
PAT listing. `hda1.tgz` is actually XZ-compressed tar data. The bootloader
update script checks the running hardware version for `DS124`; it is not
needed for the direct QEMU kernel experiment.

### Kernel and initrd formats

`file` identifies PAT `zImage` as an LZMA-alone stream. Decompressing one
stream with `xz --single-stream --format=lzma -dc` produces a 17,129,480-byte
Linux ARM64 boot `Image` (little-endian, 4K pages). It is not ELF (`readelf`
appropriately rejects it); its ARM64 Image header magic `ARMd` is at offset
`0x38`. There is no FDT magic in the decompressed image, so the DTB is
separate, not appended. The ARM64 Image is directly usable by QEMU `-kernel`
after decompression; the QEMU instruction trace reaches the image loaded at
`0x40200000`. The banner identifies Linux `5.10.55+`, built for AArch64.

`rd.bin` is also LZMA-alone compressed. Decompressing its first stream gives
an SVR4 no-CRC cpio archive. `research/arm64/work/initrd-file-list.txt`
contains the extracted regular-file list (320 files). Unprivileged cpio
extraction could not create `/dev/console` and `/dev/net/tun`, but the original
decompressed archive, including its device entries, is what the QEMU PoC
passes. The extracted tree includes `/etc/model.dtb`, matching the standalone
model DTB.

The extractor's full artifact inventory, decompressed test files, DTB
decompilations, module listing, QEMU packages, and logs are all below ignored
`research/arm64/work/`. They include proprietary data and must stay out of Git.

### Device tree and hardware coupling

The standalone `model.dtb` is DTB v17. `dtc` decompiles it to ignored
`work/model.dts` (with duplicate-unit-address warnings). Its root says
`compatible = "Synology"` and `model = "synology_rtd1619b_ds124"`. It describes
four Cortex-A55 CPUs, an ARM GICv3, and three `snps,dw-apb-uart` UARTs; the
chosen serial output is `serial0:460800n8`. It also describes Realtek-specific
clock, pinctrl, USB, eMMC (`realtek,rtd13xx-emmc`), AHCI/SATA
(`realtek,ahci-sata`), Ethernet (`realtek,rtd16xxb-r8169soc`), and two Realtek
PCIe controllers. The initrd includes this DTB as `/etc/model.dtb`.

`uboot_DS124.bin` is an ASCII-readable Realtek U-Boot 2015.07 image (not a
Linux kernel or FIT container). Its environment strings name a Realtek QA
board, SPI offsets, and DS124 update version. The embedded `kernelargs` specify
`earlycon=uart8250,mmio32,0x98007800 console=ttyS0,115200` and
`root=/dev/sata1p1`. This confirms the physical boot path expects a DesignWare
UART at the RTD1619B address and a SATA root device. QEMU `virt` instead puts
its PL011 UART at `0x09000000` and does not expose Realtek eMMC/SATA wiring.

For comparison, QEMU 8.2.2's generated `virt` DTB is captured at
`work/qemu-virt.dtb` and decompiled at `work/qemu-virt.dts`. It presents a
PL011 UART, generic PCI ECAM host, virtio-mmio transports, an ARM GIC (GICv2 by
default; QEMU can be asked for GICv3), and a generic timer. These are not the
devices named by the DS124 tree. The kernel contains GICv3 and generic PCI core
strings, but no PL011 driver strings or module, while both DTBs' UART
compatibles differ. No direct `/proc/device-tree` or
`/sys/firmware/devicetree` path checks were found in the examined initrd
startup scripts; this does not rule out checks in other binaries/userspace.

`/etc/synoinfo.conf` sets `platform_name="rtd1619b"`, `synobios="ds124"`, and
`unique="synology_rtd1619b_ds124"`. `/etc/rc` loads the Synology `synobios`
module and creates `/dev/synobios`. `/etc/rc.network` has an early interface
rule for `r8169@rtd1619@6`. `/linuxrc.syno.impl` mentions VirtIO module loads,
but only inside a guard for x86 KVM `UniqueRD` values (`kvmx64`, etc.); the
DS124 platform does not enter that branch.

### Driver inventory (stock PAT)

The PAT does not include a kernel config. “Absent” below means no matching
driver/module evidence in the decompressed kernel strings and all 228 modules
listed from `hda1.tgz` plus the initrd modules; this is strong static evidence,
not a Kconfig dump.

| Feature | Finding | Evidence |
|---|---|---|
| PL011 | Absent | No PL011/`ttyAMA` driver strings or module; QEMU `virt` UART is PL011. DS124 DTB uses DesignWare APB UART instead. |
| GIC | Present | Kernel has GICv3 init/error strings; DS124 DTB declares `arm,gic-v3`. |
| Generic timer | Present | `drivers/clocksource/arm_arch_timer.c` and `arch_timer` implementation strings are in the kernel. |
| PCI | Present, generic host uncertain | PCI core/PCIe strings and vendor PCIe nodes exist. |
| PCIe ECAM host | Unknown | QEMU `virt` DTB says `pci-host-ecam-generic`; that compatible string was not found in kernel strings or module inventory. |
| VirtIO PCI | Absent | No kernel markers or `.ko`; initrd's VirtIO load branch is x86-KVM-only. |
| VirtIO MMIO | Absent | No kernel markers or `.ko`; QEMU `virt` advertises virtio-mmio. |
| VirtIO block | Absent | No `virtio_blk.ko` in either module inventory or built-in driver markers. Stock QEMU virt disk visibility is therefore not supported by evidence. |
| VirtIO SCSI | Absent | No `virtio_scsi.ko` or built-in driver markers. |
| VirtIO net | Absent | No `virtio_net.ko` or built-in driver markers. |
| AHCI | Present (generic driver); board path coupled | AHCI core strings exist; DS124 DTB points to Realtek AHCI/SATA and SoC PHY. |
| Candidate NIC | Realtek only | `r8168.ko` is shipped and a Realtek `r8169` SoC driver is in the kernel; no e1000/e1000e/rtl8139 driver evidence. Neither maps directly to QEMU's default NICs. |

Conclusion for stock virtual devices: a QEMU virtio disk or network adapter is
not evidenced as usable by the stock DS124 kernel/initrd. A SATA/AHCI device
could match the generic AHCI support, but QEMU `virt` PCI discovery is
unverified and the DS124 controller path is tied to the Realtek DTB; actual
controller discovery needs a boot test. e1000/e1000e are not evidenced; the
Realtek NIC drivers do not emulate a QEMU NIC.

### QEMU boot PoC

`qemu-system-aarch64` was not initially installed. To avoid changing host
packages/configuration, Ubuntu QEMU 8.2.2 and its missing runtime libraries
were downloaded and unpacked under ignored `work/tools/`; the emulator then
ran directly under WSL2 on x86_64 with TCG. For that unpacked binary, the run
set `LD_LIBRARY_PATH` to `work/tools/qemu-root/usr/lib/x86_64-linux-gnu` and
its `rdma` subdirectory, and set `QEMU` to the unpacked
`usr/bin/qemu-system-aarch64`; a normally installed QEMU does not need this
workaround. An ARM physical host is not needed for this experiment. KVM is
not applicable to this x86_64 host; ARM-to-ARM KVM is a later performance
test.

`research/arm64/boot-qemu.sh` now recognizes and decompresses the actual LZMA
kernel/initrd streams, selects `-cpu max` for TCG, disables a default NIC (the
unpacked QEMU otherwise requested an absent `efi-virtio.rom`), and captures
QEMU serial output to ignored `work/boot.log`. The 35-second run used:

```sh
QEMU=/path/to/work/tools/qemu-root/usr/bin/qemu-system-aarch64 \
ACCEL=tcg SMP=2 RAM=2048 \
timeout 35s research/arm64/boot-qemu.sh research/arm64/work/extracted
```

The resolved QEMU command was:

```sh
qemu-system-aarch64 -machine virt,accel=tcg,gic-version=3 -cpu max -smp 2 -m 2048 \
  -nic none -kernel work/boot/zImage.Image -initrd work/boot/rd.bin.cpio \
  -append 'console=ttyAMA0 earlycon=pl011,0x09000000 loglevel=8' \
  -nographic -no-reboot
```

There were no serial lines: `work/boot.log` is empty and QEMU kept running
until the 20-second timeout. The script uses GICv3 because the DS124 DTB
declares it. Earlier 35-second run with QEMU's default GICv2 was silent; an
additional 10-second GICv3 run was also silent. A separate 8-second attempt
with the DS124 `model.dtb` explicitly passed was silent. A QEMU `-d in_asm` trace (ignored at
`work/qemu-instructions.log`) confirms translated execution at the boot stub,
then the kernel Image at `0x40200000`, and continued execution in kernel text
around `0x40a97000`; this is more than a QEMU loader/format rejection, but no
normal init or Synology userspace was observed. The serial mismatch is the
strongest demonstrated blocker: `console=ttyAMA0` targets QEMU's PL011, for
which the stock kernel has no driver evidence, while the official DTB uses
Realtek DesignWare UARTs at SoC addresses absent from `virt`. Passing the
board DTB to `virt` does not create those Realtek devices.

One further serial attempt used QEMU's `pci-serial` (16550) device and
`console=ttyS0,115200`, justified by the stock kernel's `serial8250` and
`8250_pci` markers. It also produced no guest output during 30 seconds of
TCG. This leaves generic PCI host discovery and console registration unproven;
the timeout line in `work/boot-pci-serial.log` is QEMU's termination notice,
not a guest kernel message.

This older silent-console result was superseded by the MMIO 16550 experiment
below. The initial `-cpu max` test also exposed a QEMU LPA2 feature mismatch,
which is documented with the successful console run below.

The research PoC remains isolated: it never uses or converts `/storage`, and
the default x86 VirtualDSM platform, entry command, disk format, and README
support claims remain unchanged.

## 2026-10-12: observability and symbol recovery

This remains a research-only experiment. The stock Image and initrd are passed
unchanged to QEMU; no files under `src/`, the Docker build, or production
platform selection are involved.

### QEMU 8.2.2 MMIO 16550

The exact QEMU source tag is `v8.2.2` (commit
`11aa0b1ff115b86160c4d37e7c37e6a6b13b77ea`). The existing binary reports
`QEMU emulator version 8.2.2 (Debian 1:8.2.2+ds-0ubuntu1.18)`; the upstream tag
matches its upstream version, although the distro build can carry packaging
patches. In this version there is no
`hw/char/serial-mm.c` or `serial-mm.h`: the implementation is in
`hw/char/serial.c` and `include/hw/char/serial.h`. It emulates the 16550A
register set. `serial_mm_init()` creates a byte-register MMIO region and
supports a `regshift`; its operations accept wider bus transactions but
consume/return the low register byte. Existing ARM boards instantiate it with
`regshift=2` (Allwinner A10/H3 and others). Little-endian is explicit here,
matching DS124 `reg-io-width = <4>` on a little-endian ARM64 system. This
matches `earlycon=uart8250,mmio32,<addr>` and four-byte-spaced DesignWare
registers. Linux v5.10's `earlycon.c` parser explicitly sets `UPIO_MEM32` and
`regshift = 2` for `mmio32`; `8250_early.c` then applies the shift and uses
32-bit reads/writes. That confirms the mapping rather than relying on the
`reg-io-width` property alone ([upstream v5.10 earlycon parser](https://github.com/torvalds/linux/blob/v5.10/drivers/tty/serial/earlycon.c),
[8250 early console](https://github.com/torvalds/linux/blob/v5.10/drivers/tty/serial/8250/8250_early.c)).

`serial-mm` is not user-creatable through `-device` in this version. Its
`TYPE_SYS_BUS_DEVICE` parent defaults `user_creatable` to false, and the
`serial-mm` class does not override that setting. Its IRQ is also a SysBus
output without a command-line wire to ARM `virt`'s GIC. The research patch
therefore instantiates it from `virt.c`, attaches a real GIC input, adds a DT
node and routes it to the second serial chardev. This avoids relying on an
unconnected IRQ. The added line is GIC input 10 (SPI ID 42), distinct from QEMU
`virt`'s allocated lines. The PL011 remains on serial backend 0; the custom UART
uses backend 1, so the test routes `-serial null -serial stdio`.

The QEMU 8.2.2 `virt.c` map places GIC at `0x08000000`, standard devices from
`0x09000000`, the 32 virtio-mmio windows from `0x0a000000` (each `0x200`), and
the platform bus at `0x0c000000`. `0x0b000000` is a 64 KiB aligned gap between
the virtio windows and platform bus; it does not intersect any listed
peripherals, PCIe windows (`0x10000000` and above), or 2 GiB RAM (which begins
at `0x40000000`). The virtual clock is 1.8432 MHz, the standard UART clock
that pairs with QEMU's 115200 baud base and divisor 1; copying the DS124
432 MHz clock would make the guest's divisor disagree with QEMU's serial
timing model.

The reproducible patch is
`patches/qemu/8.2.2/0001-arm-virt-dsm-platform.patch` and the
build helper is `research/arm64/build-qemu-research.sh`. QEMU source, build
output, and downloaded development packages remain under ignored
`research/arm64/work/`. Use `research/arm64/boot-qemu-mmio16550.sh` to run the
custom image with the stock kernel and initrd. Its default CPU is
`max,lpa2=off`: QEMU 8.2.2 TCG `-cpu max` defaults LPA2 on, setting
`ID_AA64MMFR0_EL1.TGran4` to 1. The stock 5.10.55+ kernel requires this field
to be zero for 4KB translation granules and branches into the permanent
`__no_granule_support` wait loop when it is one. A short `-d cpu` capture
confirmed x2=1 after the field extraction in that path. Disabling QEMU's LPA2
property made the field zero and allowed normal early boot. `CPU=max` remains
available to reproduce the failing baseline.

The successful run used QEMU's generated `virt` DTB, the unchanged DS124 Image
and initrd, `-m 2048`, `-smp 2`, GICv3, and:

```text
earlycon=uart8250,mmio32,0x0b000000 console=ttyS0,115200 loglevel=8 ignore_loglevel
```

Early console works. The first lines identify the stock 5.10.55+ kernel and
`linux,dummy-virt`; later lines show GICv3, the generic timer, both CPUs, and
`Trying to unpack rootfs image as initramfs...` followed by `Freeing initrd
memory`. Thus the generic DTB path reached initramfs extraction (C3). The
captured 60-second TCG run reached a Realtek-specific `rtk_bootstatus_init`
warning at guest time 7.04 seconds. It did not show a kernel panic or init
process start before the capture ended. The first 50 lines, last 50 lines, and
first warning are preserved in ignored `work/boot-mmio16550-first50.txt`,
`work/boot-mmio16550-last50.txt`, and `work/boot-mmio16550-first-warning.txt`;
the full log is `work/boot-mmio16550-virt.log`.

For comparison, passing the stock `model.dtb` reaches Linux startup and prints
the model `synology_rtd1619b_ds124`, then synchronously aborts in
`gic_of_init+0x58/0x230` while accessing `0xff110000` and panics. That address
is a Realtek GIC mapping not implemented by QEMU `virt`. The generic QEMU DTB
progresses farther. A minimal custom DTB was not needed for this iteration.

Focused QEMU tracing with `-d in_asm,cpu_reset,int,guest_errors` shows forward
execution through early init and kernel virtual addresses such as
`of_parse_thermal_zones` and `of_find_node_by_name`, with timer IRQ exceptions
and normal exception returns. It did not show a stable loop or unmapped-MMIO
cycle in the successful run. The initial `CPU=max` baseline did show the
stable `__no_granule_support` loop at physical PCs `0x40a972f8–0x40a97300`,
with no exception or MMIO access. Full selected PC mappings, including those
post-MMU PCs, are in ignored `work/pc-map.txt`.

### Kallsyms and PC mapping

`vmlinux-to-elf` 1.3.6 successfully found 35,266 embedded symbols in the
decompressed ARM64 Image. It found kallsyms names at file offset `0x0097e6a8`,
offsets at `0x0095bf90`, and token tables at `0x009e79a0`/`0x009e7d00`. It
reconstructed `research/arm64/work/recovered.elf`, an AArch64 ELF accepted by
`readelf` and `nm`. The tool's fallback base is `0xffffffc010000000`, corroborated
by the first kallsyms addresses and image-relative ARM64 boot functions. No
symbol shifting was applied to force a match.

The ARM64 Image header has `text_offset = 0x80000`, `image_size = 0x018e0000`,
and magic `ARMd` at `+0x38`. QEMU's existing trace shows the first Image word at
`0x40200000`. That word is an AArch64 branch whose encoded target is
`0x40ff0000`, where kallsyms places `primary_entry`. Thus the physical load
address is evidenced as `0x40200000`, and the mapping used is
`kernel VA = 0xffffffc010000000 + (QEMU PC - 0x40200000)`. The Image header's
`text_offset` is the ARM64 boot protocol offset from the aligned RAM base; it
does not mean that the raw first byte in this QEMU trace is at `0x40080000`.

The mapper is `research/arm64/map-pcs.py`; the current full mapping of unique
PCs from the earlier instruction trace is in ignored
`research/arm64/work/pc-map.txt`. Key entries:

| QEMU PC | Image offset | Recovered symbol | Interpretation |
|---|---:|---|---|
| `0x40200000` | `+0x0` | Image header; branch target `primary_entry` at `+0xdf0000` | Exact header/branch evidence, not a kallsyms function address |
| `0x40a97000` | `+0x897000` | `el2_setup` | Exact symbol address |
| `0x40a9717c` | `+0x89717c` | `set_cpu_boot_mode_flag` | Exact symbol address |
| `0x40a975d4` | `+0x8975d4` | `__cpu_setup` | Exact symbol address; MMU/cache setup path |
| `0x40a97284` | `+0x897284` | `__enable_mmu` | Exact symbol address |
| `0x40a972e0` | `+0x8972e0` | `__no_granule_support` | Exact symbol; LPA2-on baseline failure path |
| `0x40a972f8` | `+0x8972f8` | `__no_granule_support+0x18` | Stable WFE/WFI branch loop |
| `0x40a97304` | `+0x897304` | `__primary_switch` | Exact symbol address |
| `0x40ff0000` | `+0xdf0000` | `primary_entry` | Exact symbol address |
| `0x40ff0020` | `+0xdf0020` | `preserve_boot_args` | Exact symbol address |
| `0x40ff0040` | `+0xdf0040` | `__create_page_tables` | Exact symbol address |
| `0x40226d44` | `+0x26d44` | `__dma_inv_area` | Exact symbol address; trace enters cache maintenance code |
| `0xffffffc010e1d7c8` | `+0xe1d7c8` | `of_parse_thermal_zones` | Exact post-MMU symbol address |
| `0xffffffc0107306e0` | `+0x7306e0` | `of_find_node_by_name` | Exact post-MMU symbol address |

The captured instruction trace progresses through `primary_entry`, boot-argument
preservation, page-table setup, EL2 setup, and CPU setup. At `0x40a97284`,
`__enable_mmu` reads `ID_AA64MMFR0_EL1.TGran4` and branches to
`__no_granule_support` when the field is nonzero. The trace reaches that failure
path at `0x40a972e0`; its final loop is `0x40a972f8–0x40a97300` (`wfe; wfi; b`).
This is a stable early boot loop before the primary MMU switch. No exception or
MMIO access appears in the captured loop. The branch condition points to the
CPU's reported 4KB granule feature as the immediate failure; focused tracing of
the research QEMU boot should verify the actual register value and whether the
custom UART changes observability.

### DesignWare 8250 driver evidence

The recovered built-in symbol table contains `dw8250_probe`,
`dw8250_platform_driver_init`, `dw8250_serial_in32`, `dw8250_serial_out32`,
`dw8250_set_termios`, and other `dw8250_*` functions. The Image strings contain
`snps,dw-apb-uart`, `dw-apb-uart`, `serial8250`, `early_serial8250_setup`,
`ttyS0`, and `ttyS1`. Literal `8250_dw` and `UART_16550` strings were not found.
No `8250_dw.ko` or matching 8250 UART module is present in the initrd module
directory or the 228-module rootfs inventory. Together this is strong evidence
that the DesignWare 8250 driver and serial8250 console are built into the stock
kernel, not modular. The `.ko` absence alone would not prove that; the
recovered function symbols provide the built-in evidence.

### Current experiment status

The earlier C3 result above is superseded by the I3 result below. The stock
kernel and original initramfs execute Synology startup on QEMU `virt` using
the research UART. This is not production ARM support.

## 2026-10-12: initramfs control flow and PID 1 (I3)

The unchanged DS124 7.2.2-72806 Image and decompressed original cpio now boot
to an interactive BusyBox shell as PID 1. The real Synology initramfs wrapper
also runs, loads modules, and stops explicitly at `DISK NOT INSTALLED` before
system RAID assembly or root mounting. No proprietary initramfs copy was
modified, no Synology kernel patch was used, and no disk image was created.

### Entrypoint contract

`inspect-initramfs.py` inspects the original newc archive's modes as well as
`ls -l`, `stat`, `file`, and recursive `readelf` results. DrvFS extraction can
display mode 0777 for regular files, so the archive's 0755 mode is authoritative.
The script resolves symlinks inside the guest root, including `/bin -> usr/bin`
and `/lib -> usr/lib`, without executing guest programs on the host.

| Path | Type / target | Executable | Interpreter | Shared-library closure |
|---|---|---|---|---|
| `/init` | symlink to `bin/busybox` | yes, target 0755 | `/lib/ld-linux-aarch64.so.1` | present |
| `/linuxrc` | symlink to `bin/busybox` | yes | same ELF interpreter | present |
| `/linuxrc.syno` | regular shell script, 0755 | yes | `/bin/sh` | present through BusyBox |
| `/linuxrc.syno.impl` | regular shell script, 0755 | yes | `/bin/sh` | present through BusyBox |
| `/sbin/init` | symlink to `../bin/busybox` | yes | same ELF interpreter | present |
| `/bin/init` | absent | no | n/a | n/a |
| `/bin/sh` | symlink to `busybox` | yes | same ELF interpreter | present |
| `/etc/rc` | regular shell script, 0755 | yes | `/bin/sh` | present through BusyBox |

BusyBox is a dynamically linked AArch64 ELF, not a static executable. Its
`DT_NEEDED` entries are `libcrypt.so.1`, `libtirpc.so.3`, `libc.so.6`, and
`ld-linux-aarch64.so.1`. All are in the initramfs, including their recursive
dependencies. This proves the ELF loading contract; it does not imply that
every optional module or hardware dependency of the scripts is available.

Reproduce the read-only audit with:

```sh
python3 research/arm64/inspect-initramfs.py \
  research/arm64/work/boot/rd.bin.cpio \
  research/arm64/work/initrd \
  research/arm64/work/initramfs-entrypoints.txt
```

### The apparent post-extraction stall

The initial 55-second `initcall_debug` log last completed `n_null_init` and
entered `pty_init`. This was a capture boundary, not evidence of a hang.
Longer runs show `pty_init` returning 0 after about 85-89 guest seconds. Its
stock legacy PTY count is 256. Focused GDB hardware breakpoints observed many
`kernel_execve("/sbin/hotplug", ...)` calls, and CPU snapshots captured actual
user-space PCs during this interval. Those pre-PID1 helpers must not be confused
with PID 1 execution. `pty.legacy_count=0` is an optional research boot argument
that shortens this interval; the final default boot also succeeded with the
stock count and no `rdinit` override.

`rtk_bootstatus_init` warns about the absent Realtek node, then returns 0
(`22687 usecs` in the initial debug capture). Subsequent initcalls run. It is
non-blocking and has not been bypassed or modified.

The last completed built-in initcall is `of_platform_sync_state_init`, returning
0. The recovered binary inlines `do_basic_setup` into `kernel_init_freeable`;
there is no independent symbol to pretend to trace. Disassembly identifies the
inlined setup at `kernel_init_freeable+0x184` and its completion at `+0x28c`,
just before `console_on_rootfs`. Hardware breakpoints confirm this completion,
a successful `filp_open("/dev/console")`, a zero `init_eaccess` return, and a
zero `kernel_execve` return from `run_init_process`.

Both `/bin/sh` and the default `/init` have those successful access/exec
results. The disassembled zero-return branch skips `prepare_namespace`; its
breakpoint was armed throughout. The normal-root fallback is therefore ruled
out for these boots, consistently with the
[Linux v5.10 init control flow](https://github.com/torvalds/linux/blob/v5.10/init/main.c).
There is no ENOENT, EACCES, missing interpreter, missing shared library, or
exec-format failure on either entrypoint.

### A normal serial console

The stock kernel contains `dw8250_probe`, `dw8250_platform_driver_init`,
`dw8250_setup_port`, and `serial8250_register_8250_port`, plus the literal
`snps,dw-apb-uart` and `snps,uart-16550-compatible` properties. No
`of_platform_serial_probe` symbol or separate 8250 OF module was found.
`ns16550`/`ns16550a` strings alone do not establish a generic OF platform driver;
the research DT now advertises only the evidenced DesignWare compatible.

The exact register accesses were checked in the recovered stock binary. Even
with `snps,uart-16550-compatible`, `dw8250_setup_port+0x20` reads UCV at
`membase+0xf8`. The original QEMU `serial-mm` region covers only 8 registers
with shift 2, i.e. 32 bytes. A diagnostic boot progressed past `pty_init` and
faulted on this read, with a synchronous external abort and PID 1 kernel panic.
This is the demonstrated DT/device mismatch, not an `rtk_bootstatus` fault.

The research patch adds two zero-valued 32-bit identification registers at
`+0xf4` (CPR) and `+0xf8` (UCV). Zero UCV causes the driver to stop extension
probing; the boolean binding selects the generic 16550 interrupt handler and
avoids unimplemented DesignWare busy/USR behavior. This is a minimal 16550
compatibility view, not a Realtek hardware model. The driver's property handling
is also described by the
[v5.10 DesignWare driver](https://github.com/torvalds/linux/blob/v5.10/drivers/tty/serial/8250/8250_dw.c).

The QEMU-generated node has address `0x0b000000`, reg-shift 2, reg-io-width 4,
clock-frequency 1843200, interrupts `<0 10 4>`, status `okay`, and
`snps,uart-16550-compatible`. `/aliases/serial0` points to it and
`/chosen/stdout-path` is `/serial@b000000:115200n8`. GIC input 10 is hardware
SPI ID 42; the driver's reported Linux virtual IRQ 47 is a different numbering
space. The full DT dump is `work/qemu-mmio16550-current.dts`.

The successful log contains:

```text
printk: bootconsole [uart8250] enabled
b000000.serial: ttyS0 at MMIO 0xb000000 (irq = 47, base_baud = 115200) is a 16550A
printk: console [ttyS0] enabled
```

With `keep_bootcon`, both consoles remain active on the same UART, so printk
lines may duplicate or interleave. The shell prints `SHELL_PID=1`, accepts
commands, and successfully writes `CONSOLE_USABLE` directly to `/dev/console`.
There is no initial-console-open warning. BusyBox warns that job control is
disabled because PID 1's shell has no controlling tty; serial input/output still
works. The complete required diagnostics, including both CPUs and the guest DT,
are in `work/boot-sh-console.log`.

### Synology startup and the first terminating failure

The default boot logs `Run /init as init process`, then `START /linuxrc.syno`
and `START /linuxrc.syno.impl`. This confirms BusyBox's Synology dispatch, which
also has those path/command strings in the binary. `/linuxrc.syno` is the
confirmed wrapper; `/linuxrc` is another BusyBox applet alias, and the `.impl`
script is the wrapper's child, not a guessed kernel init path.

The direct test uses `rdinit=/linuxrc.syno`, `pty.legacy_count=0`, and the original
physical `root=/dev/sata1p1`. It mounts proc, sysfs and devtmpfs, runs the
implementation, and loads USB modules. The absent `etxhci-hcd.ko` is the first
reported missing file, but the script continues. Synobios reports missing LED
information and an I2C/RTC adapter, but its init returns 0. `synocfgen` returns
0 and synobios unloads normally. These errors are not the demonstrated stop.

`linuxrc.syno.impl` then calls `synodiskport -installable_disk_list`. With no
disk returned and nonzero `MaxDisks`, lines 468-472 create `/.nodisk` and call
`Exit 1 "DISK NOT INSTALLED"`. This occurs before system RAID assembly at line
483, filesystem checking, and mounting `/tmpRoot`. The direct wrapper exits as
PID 1 and produces the expected `Attempted to kill init` panic, exit code
`0x00000100`; this is a userspace exit, not a hardware abort. The default
BusyBox PID 1 instead reports the script failure and starts `/etc/rc` in the
initramfs. Neither path proves root-device handoff, so the result is **I3**.

After proving userspace, root-related static inspection shows that
`rootdevice.sh` reads `root=` from `/proc/cmdline`, normally queries `blkid` for
the filesystem, and has ext4 fallback and btrfs handling. The legacy fstab says
ext3; an installed disk's actual filesystem cannot be established here. The
system path includes `/dev/md0`, a first system partition evidenced by
`/dev/sata1p1`, and swap on partition 2 for md1. Exact offsets and sizes remain
unproved. `hda1.tgz` is a root-file tar archive (XZ compressed), not a partition
image; the autoinstall scripts rename it to `SynoUpgrade.tar.gz`. The initramfs
contains transition and diskless junior-mode startup, whereas this archive
provides installed DSM root files. No production partition layout was designed.

### Reproduction, evidence and validation

Use the rebuilt research QEMU with the existing `LD_LIBRARY_PATH` workaround
if needed. All boots retain `-cpu max,lpa2=off`, GICv3, two CPUs, 2 GiB RAM,
and `-serial null -serial stdio`:

```sh
# Default /init, including the stock legacy PTYs (allow several minutes on TCG):
timeout 240s bash research/arm64/boot-qemu-mmio16550.sh

# Interactive diagnostic PID 1 with the original initramfs:
APPEND='earlycon=uart8250,mmio32,0x0b000000 console=ttyS0,115200 initcall_debug keep_bootcon ignore_loglevel loglevel=8 printk.time=1 pty.legacy_count=0 rdinit=/bin/sh' \
  bash research/arm64/boot-qemu-mmio16550.sh

# Real Synology wrapper, preserving the original physical root argument:
APPEND='earlycon=uart8250,mmio32,0x0b000000 console=ttyS0,115200 initcall_debug keep_bootcon ignore_loglevel loglevel=8 printk.time=1 pty.legacy_count=0 root=/dev/sata1p1 rdinit=/linuxrc.syno' \
  bash research/arm64/boot-qemu-mmio16550.sh
```

`TRACE=1` now selects bounded address ranges around the recovered init path and
uses `in_asm,guest_errors`, without an unrestricted interrupt/CPU dump.
`TRACE_FILTER` can override the ranges for another research kernel. Execution
and return values in this investigation came from QEMU GDB hardware
breakpoints, not from assuming that translated blocks necessarily executed.

Ignored evidence files include `initramfs-entrypoints.txt`, `init-sequence.txt`,
`init-pc-map.txt`, `init-disassembly.txt`, `boot-initcall-default.log`,
`boot-sh-original.log`, `boot-sh-no-legacy.log` (the UART fault),
`boot-sh-console.log`, `boot-default-final.log`, `boot-synology-direct.log`,
`trace-default-long.txt`, `trace-shell-focused.txt`, and
`trace-default-focused.txt`. The Image SHA256 is
`4c6584070c2bfee8a7ab1b73ef74d1872a0469700e61fc806e6b72d23e576b14`; the
original decompressed initramfs SHA256 is
`3177c1be9dbc40224c5ad193d7ad032e74c83ce54e5d436ebec209b26384a2bf`.

The patch builds against QEMU v8.2.2 and applies cleanly to pristine files from
that tag. Research smoke checks, `shellcheck -x`, Python compilation, and
Windows Git `diff --check` pass. WSL Git initially treated the Windows checkout's
CRLF files as whole-file changes; the repository's Windows Git was used for
the actual whitespace check without changing unrelated files or Git settings.

The next research task is to prove whether a QEMU SATA/AHCI controller can be
discovered by the stock DS124 kernel and yield an installable disk in
`synodiskport`, using the proven initramfs shell before designing root disks.

## Non-PCI networking research

The current objective is a usable DSM network interface after the demonstrated
J5 systemd handoff. Stock DS124 modules match QEMU v8.2.2 USB CDC Ethernet,
and the research-only patch now adds sysbus XHCI. Normal `/init` reaches
**N5**: `cdc_ether` creates `eth0`, DSM DHCP assigns `10.0.2.15/24`, gateway
communication succeeds, and nginx listens on 80, 443, 5000 and 5001. The
experiment explicitly activates the shipped CDC module on a disposable
root copy; the subsequent loopback-only host access experiment is recorded below. See
[the USB network experiment](../research/arm64/usb-network.md) for driver
evidence, memory/IRQ allocation, normal-init reproduction, and observed results.

## Host management access research

The stock ARM64 DSM instance now demonstrates **W5** for bounded host access:
Windows and WSL curl receive the DSM LOGIN page on loopback-forwarded HTTP
15000 -> 5000 and HTTPS 15001 -> 5001. QEMU listener ownership and the Windows
WSL relay were checked; no wildcard host bind or forwarding for 80/443 was
added. HTTP / returns 200; /webman/ redirects to /. TLS 1.3 succeeds with
research certificate verification disabled. Both page-referenced read-only
bootstrap APIs respond through synoscgi.

All 20 spaced Windows GETs and 10 additional keepalive GETs returned 200.
RX/frame errors stayed 6 -> 6 and TX errors 0 -> 0 during that request window;
RX/frame errors reached 8 by the end of the longer observation.
This does not establish complete application/kernel health: PostgreSQL upgrade
status is failed, configured is false. The MTD timeout does not block the
checked page/bootstrap. No account, wizard, installation or disk configuration
was attempted. See [host management evidence and reproduction](../research/arm64/host-management.md).

## scemd / synobios soft-lockup diagnosis (B5)

Persistent `scemd` soft lockups on `queued_write_lock_slowpath` were traced to
`SYNOIO_SET_DISK_LED` (`0xc0184b0a`) under `LedSetLock` in `ds124_synobios`.
`SetupLedTrigDiskMap` left NULL `led_classdev` entries because virt `gpio-leds`
on PL061 cannot probe: the stock DS124 kernel has no `pl061` driver. The first
writer (`syno_led_mask_o`) oopsed in `ledtrig_syno_disk_led_on` without
unlocking; later `scemd` writers busy-spun.

The research QEMU patch
`patches/qemu/8.2.2/0002-arm-virt-syno-leds.patch` now exposes
`register-bit-led` children under a tiny `syscon`/`simple-mfd` MMIO page at
`0x0b120000` plus `/internal_slot@1` phandles. After that fix, guest uptime
past the previous 700 s failure window showed no LED NULL oops, no
`can't get class`, no `scemd` soft lockup, and a clean **30/30** loopback
management GET / series on port 15000. Synology kernel/userspace binaries were
not modified. Production `src/**` integration remains deferred.

## Production Integration Phase 1 (2026-10-13)

The validated research hardware contract graduated to `src/platform/` and the
shared production entrypoint. The default `virtualdsm` platform remains x86;
`rtd1619b` is the experimental DS124 contract with prepared artifacts only.
The [platform API and configuration](platforms.md) describe the current code.

Graduated contracts:

| Research evidence | Production owner |
|---|---|
| ARM64 guest on virt/GICv3 | `src/platform/rtd1619b.sh` machine and CPU policy |
| TCG `max,lpa2=off` | ARM acceleration policy; matching ARM KVM requires a successful probe |
| Stock direct Image/initramfs `/init` boot | Persistent `/storage/DSM_DS124_72806.kernel` and `.initrd` |
| MMIO 16550 plus ttyS0 | First production QEMU patch and `-serial null -serial stdio` |
| sysbus AHCI / stock rtk_ahci / sata1 | First patch plus raw `if=ide,index=0` system backend |
| sysbus XHCI / CDC ECM / eth0 | First patch plus USB NIC; user-mode backend remains separate |
| Explicit stock cdc_ether activation | Read-only prepared-image validator and documented preparation step |
| synobios LED / scemd stability | Mandatory second production patch: syscon, register-bit-led, internal_slot@1 |
| HTTP/HTTPS management | Validated port forwards using container WEB_PORT and DSM_HTTPS_PORT |

Production source never references ignored research artifacts. The regression
alone copied the known-good kernel, initramfs and system disk into a disposable
prepared storage directory, and started the Docker image through its actual
`/usr/bin/tini -s /run/entry.sh`. No research boot launcher ran this guest.
Existing observer files in the disposable root supplied read-only guest evidence;
logs were cleared in the disposable copy before boot, not in the source image.

Demonstrated locally on an amd64 WSL2 host:

- Full production Docker runtime built successfully. ARM QEMU is v8.2.2;
  inherited x86 QEMU reports 11.1.0. Both binaries execute and ARM dependencies
  resolve. Both patches clean-apply to exact upstream v8.2.2 and reproduce the
  validated research hardware sources byte-for-byte.
- Actual ARM process uses qemu-system-aarch64, virt/GICv3, TCG multi-thread,
  max,lpa2=off, the persistent direct-boot files, raw first IDE backend and
  usb-net. No q35, x86 PCI device or VirtIO serial/storage/network policy leaks.
- systemd PID 1, sata1p1, ttyS0, XHCI, CDC eth0, DHCP 10.0.2.15 and nginx listeners
  on 5000/5001 are observed. Host requests return HTTP 200 for 30/30 requests;
  HTTPS also returns 200 (self-signed certificate verification disabled only
  in the test).
- Guest observation reaches 997.95 seconds and serial output reaches about
  1,016 seconds. scemd is active/running in repeated management snapshots,
  with later samples at PID 7244 in Ssl state. No soft lockup, LED oops or
  queued_write_lock_slowpath is present in the fresh boot evidence. This is a
  bounded regression result, not a claim of indefinite stability.
- Unset DSM_PLATFORM selects the original VirtualDSM path. A synthetic-image
  production-entry test captures the same complete argv byte-for-byte as the
  pre-integration entrypoint, including q35 chipset flags, fixed PCI addresses,
  VirtIO devices, synoboot/synosys and legacy boot. No full x86 DSM install was
  needed. Installer/config/serial scripts remain byte-identical after LF
  normalization.
- Platform snapshots, invalid-input rejection, prepared-image validation with
  synthetic MBR/GPT ext4 disks, research smoke checks and shellcheck pass.
  Native ARM64 Docker/KVM runtime has not been tested locally; a separate
  manually dispatched CI build uses native amd64 and ARM64 runners.

The highest demonstrated level is G5. The next task is Production Integration
Phase 2: automatic official PAT -> boot artifacts + DSM system disk. Canonical
DS124 geometry, p2/p3, the fresh installer and official patch reconstruction
remain outside Phase 1. The retained historical research sections above do not
imply those installer steps have graduated.
