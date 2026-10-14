# ARM64 DSM non-PCI USB networking research

This experiment uses the stock DS124 DSM 7.2.2-72806 kernel and initramfs,
QEMU **v8.2.2**, and a disposable copy of the already populated/patch-state
root disk. Its objective is a usable DSM network interface. A failed
`syno-mount-usbfs.service` is useful diagnostic evidence, not a boot fatal or
the primary goal. No installer, disk geometry, PCI ECAM, or production work
is included.

## Stock-driver compatibility gate

Run `python3 research/arm64/inventory-network-stock.py` after recovering the
kernel and extracting the official PAT. It reads the recovered ELF, its
kallsyms, Image strings, every root archive module entry, initramfs module
names, and the official `modules.alias`/`modules.dep`. It produces the ignored
`work/usb-host-driver-map.txt`, `work/usb-net-driver-map.txt`,
`work/network-stock/inventory.json`, extracted relevant modules, and
`work/network-policy-stock.txt`. Proprietary modules stay under ignored work.

The supplied `usb-common`, `usbcore`, `xhci-hcd`, and `xhci-plat-hcd` are
modules, present in both initramfs and root. The platform module exports
`of:N*T*Cgeneric-xhci` and `of:N*T*Cxhci-platform`, including their `C*`
variants. `dwc3`, `dwc3_rtk`, the Realtek USB manager and PHY modules also
exist; generic EHCI-platform, OHCI-platform and DWC2 were not found. The
EHCI core and PCI glue do not establish a usable non-PCI alternative.

The official root includes `usbnet.ko` and `cdc_ether.ko`. CDC exports the
generic alias `usb:v*p*d*dc*dsc*dp*ic02isc06ip00in*`, which matches QEMU's
CDC interface. The root's alias database includes this entry, and its
dependency database supplies the complete chain through `usbnet`, `usbcore`,
and `usb-common`. No supplied `rndis_host`, CDC NCM/MBIM, ASIX, RTL815x,
SMSC USB NIC, Pegasus, Net1080, CDC subset or Zaurus driver was found.

## QEMU USB device contract

The local v8.2.2 `hw/usb/dev-network.c` defines VID/PID **0525:a4a2**,
a USB 2.0 full-speed device with two configurations. Descriptor index zero
is **RNDIS, configuration value 2**, with control interface `02/02/ff`.
Descriptor index one is **CDC ECM, configuration value 1**, with control
interface `02/06/00`, CDC Ethernet/union descriptors, and data interface
`0a/00/00`. The CDC data interface uses altsetting zero with no endpoints
and altsetting one with bulk IN/OUT endpoints. The product string mentions
RNDIS but does not imply RNDIS is the only protocol.

`-device usb-net,help` exposes no protocol selection property. Stock
`usbcore.ko`'s `usb_choose_configuration.part.0` disassembly checks the first
RNDIS interface and skips it when an alternative configuration exists.
The runtime experiment must verify the selected configuration; matching
an alias alone is not an enumeration result.

The detailed source/descriptor analysis is recorded in ignored
`work/qemu-usb-net-contract.txt`. No Realtek Ethernet emulation or USB
identity/descriptor changes are required for the selected CDC path.

## Research controller and DT

The existing research patch now follows v8.2.2 `sbsa-ref.c:create_xhci()`
to instantiate `TYPE_XHCI_SYSBUS` on `virt`:

| Resource | Value |
|---|---|
| MMIO | `0x0b200000`, size `0x4000` |
| Interrupt | GIC SPI 12, architectural INTID 44, level high |
| Slots / interrupters | 8 / 1 |
| USB ports | 2 USB2, 2 USB3 |
| Compatible | `generic-xhci`, verified in the stock module |

This allocation avoids the complete low virt memory map, all 32 virtio
MMIO windows, UART `0x0b000000`, AHCI `0x0b100000`, shared AHCI syscon/reset
`0x0b110000`, GIC ranges, platform bus, PCI windows, and RAM starting at
`0x40000000`. SPI 12 is unused by the existing map. High GIC and PCI
windows are allocated beyond the low-memory region. The full comparison
is in ignored `work/xhci-memory-map.txt`.

The DT node contains only `compatible`, `reg`, `interrupts`, and `status`.
Disassembly of the actual Synology `xhci_plat_probe` establishes IRQ/MMIO
requirements and optional clocks. Missing PHY errors are tolerated except
probe deferral. No mandatory reset call or Realtek PHY/clock shim was found.

`build-qemu-research.sh` enables libslirp and reconfigures an existing build
that lacks it. The previous research build disabled slirp. Install the
libslirp development prerequisite alongside the existing QEMU build tools;
then run the build script. The source remains pinned to v8.2.2.

## Normal-init experiment and observation

The observer runs as an ordinary systemd service and only reads guest state
or performs connectivity probes. `prepare-network-observer.sh` requires an
unused output image path, clones `test-sata-patch-state.img`, and installs
that observer onto the copy. It leaves the proven source image unchanged.
It does not supply a replacement PID 1, edit the stock initramfs/kernel, or
change network configuration.

From Linux/WSL, using root only for loop mounting:

```sh
python3 research/arm64/inventory-network-stock.py
bash research/arm64/build-qemu-research.sh
bash research/arm64/prepare-network-observer.sh
python3 research/arm64/boot-usb-network.py host
python3 research/arm64/boot-usb-network.py network --mac 00:16:3e:12:34:56
bash research/arm64/enable-research-usb-cdc.sh
python3 research/arm64/boot-usb-network.py network --mac 00:16:3e:12:34:56 --label usb-network-cdc
```

The host run attaches no USB NIC. The network run refuses to attach the
NIC without prior normal-init host evidence. It uses precisely:

```text
-netdev user,id=net0 -device usb-net,netdev=net0,mac=00:16:3e:12:34:56
```

The harness verifies the exact stock kernel/initramfs SHA256 and records
full command lines, bounded serial logs, stop reasons and JSON results.
It continues past ordinary systemd unit failures. The observer captures
USB descriptors and driver links, interface naming/MAC/carrier, IP/routes,
DHCP processes, actual gateway probes, DNS/HTTP where possible, TCP/TCP6
listeners and failed/running units. It reports the guest's actual gateway
instead of assuming an address.

The actual stock `cdc_ether` driver-info flags are `0x1020`. Its shipped
`usbnet_probe` checks bit 1 of the MAC when both relevant flags are set:
a locally administered MAC keeps `usb%d`, while a globally administered
MAC selects `eth%d`. QEMU v8.2.2 `usb_net_realize()` **hardcodes the first
byte of the CDC Ethernet MAC string to `0x40`**, preserving only bytes 1–5
from the `mac=` property. Thus the default CDC MAC already selects the
Ethernet naming path; a special globally administered `mac=` value is not
necessary. The recorded command supplies `00:16:3e:12:34:56`, while the
actual guest MAC is **`40:16:3e:12:34:56`**. Runtime confirms `eth0`.
The module and QEMU offsets are saved in `work/usb-net-naming-contract.txt`.

The stock `/etc.defaults/sysconfig/network-scripts/ifcfg-eth0` requests
DHCP with `ONBOOT=yes`. `SynoInitEth.service` runs `syno_net_seq` because
`netif_seq_by_dts=yes`; `rc-network.service` runs the normal network script.
`rc.network` selects interfaces with readable `ifcfg-*` files. These are
potential policy interactions, not proof of USB filtering. Change policy
only after the observed device/name/configuration demonstrates a problem.

## Stock module activation

The first normal-init NIC run selected CDC configuration 1 and exposed the
correct control/data interfaces, but the official `usbnet` and `cdc_ether`
modules remained unloaded. The control interface had no driver link, no
physical network interface existed, and the supplied udev rules contained
no general USB alias module-autoload rule. This is an activation gap, not
incompatibility between the shipped driver and QEMU.

`enable-research-usb-cdc.sh` validates that observed baseline before adding
`70-network-0007-research-usb-cdc.conf` containing only `cdc_ether` to the
disposable root's `/usr/lib/modules-load.d`. The shipped dependency database
loads the USB framework. The new entry is processed before `SynoInitEth`,
allowing DSM's normal startup to initialize an interface without manual
IP assignment. No interface filters, `synoinfo.conf`, or `ifcfg-*` policy
are edited. The service/module activation is research instrumentation,
recorded in ignored `work/usb-cdc-activation.txt`.

## Root I/O diagnostic

The CDC module boot proved N2, but later root filesystem reads repeatedly
failed with `READ FPDMA QUEUED` / `ABRT` and the observer/normal network
initialization stalled. A separate repeat uses the stock kernel option
`libata.force=noncq`. The supplied Image contains `libata.force`, its force
parser diagnostics, and `noncq`; runtime confirms `FORCE: horkage modified
(noncq)` and `NCQ (not used)`. This is a boot argument on the same installed
root, not a disk-layout or AHCI-emulation change.

```sh
python3 research/arm64/boot-usb-network.py network --disable-ncq \
  --mac 00:16:3e:12:34:56 --label usb-network-noncq --snapshots 8
```

The earlier evidence remains separate in `usb-network-cdc.log`. The
`usb-network-noncq` run preserves the root I/O diagnostic independently.
The successful file-observer run used:

```sh
python3 research/arm64/boot-usb-network.py network --disable-ncq \
  --mac 00:16:3e:12:34:56 --seconds 1500 --snapshots 6 \
  --label usb-network-filelog
```

## Demonstrated result

The host-only ordinary `/init` run registered both root hubs and created
`/dev/bus/usb/001/001` and `/002/001`. `syno-mount-usbfs.service` finished
successfully. Controller platform driver is `xhci-hcd` from the shipped
`xhci_plat_hcd` module; Linux allocated IRQ 47 for GIC INTID 44 (SPI 12).

The supplied CDC module binds USB `1-1:1.0` in configuration 1 and creates
`eth0`, MAC `40:16:3e:12:34:56`. DSM's normal `rc.network` and
`dhclient@eth0.service` bring it up and assign **10.0.2.15/24**, with carrier
1 and default gateway **10.0.2.2**. Gateway ping returns 2/2 replies with
zero loss. An outbound HTTP HEAD request to `example.com` resolves the
hostname and returns **HTTP/1.1 200 OK**; the standalone `getent` probe is
unavailable in the guest. DNS is configured at **10.0.2.3**. nginx listens on
IPv4 and IPv6 wildcard addresses on **80, 443, 5000 and 5001** (PID 5212).
No listener on 22 was observed. This demonstrates **N5** under the
management-service listening criterion, without manual IP assignment or
network-policy modifications. Host forwarding and browser access remain
unverified.

`syno_net_seq` cannot find the real-board metadata for this generic USB
interface and skips it. It still returns success; DSM's interface catcher
adds `eth0 (dhcp)`, and `rc-network.service` reaches active/exited. Thus the
missing DT Ethernet metadata is **not** a demonstrated policy block and
must not be patched merely because a warning exists.

Verbose console observation stopped making progress in earlier runs.
The observer now saves full state in `/var/log/arm64-network-observer.log`
and emits only serial progress markers. After QEMU exits, the harness
reads that log from a read-only loop device with `ro,noload`, and saves
network unit logs independently. Live debugfs reads of the already synced
log were provisional; the final post-stop copy is authoritative.

The non-NCQ run no longer reports READ FPDMA QUEUED aborts; it did not
alone solve the console-observation stall. It remains a documented root
I/O diagnostic, not a generic networking requirement.

Authoritative ignored evidence is `usb-network-filelog-guest-observer.log`,
`usb-network-filelog-network-unit-logs.txt`, its command/result JSON, and
the distinct host/baseline/CDC/NCQ serial logs. The final run completed all
six snapshots in **580.79 seconds**, with QEMU return code 0 after the
harness requested termination and no guest-log capture error. Snapshot 5
confirms the address, carrier, route, gateway replies and management
listeners. The final interface counters include **5 RX/frame errors**
(82 RX packets and 113 TX packets); sustained network reliability has not
been established by this bounded experiment.

No network-relevant unit is failed in the final snapshot.
`syno-mount-usbfs`, `SynoInitEth` and `rc-network` are active/exited with
status 0. The remaining failed services are `SynoSwInitLed`,
`selfcheck_bootHealth`, `synoindex-checkpackage`, and `pgsql-adapter`.
The LED initialization produced a kernel NULL-pointer oops in
`ledtrig_syno_disk_led_on`, but systemd and networking continued; no global
panic was observed. The missing `dev-mtd0.device` timed out with dependent
MTD/burn-in jobs. Package/index and PostgreSQL adapter failures are
application/startup limitations, not evidence of a network failure. A
listening management socket does not establish successful application
responses or a healthy complete DSM boot.

The required research smoke suite, ShellCheck across all research/test
shell scripts, Python syntax checks, and Windows Git `diff --check` pass.
The patch applies to pristine QEMU v8.2.2 and reproduces the exact build
source. Both historical serial evidence and file-based baseline evidence
pass the stock-module activation gate; an already loaded CDC driver is
correctly rejected by that gate. After capture, no QEMU process or loop
device remains attached.

The subsequent [host management experiment](host-management.md) demonstrates
loopback-only HTTP/HTTPS access and records the remaining application and
kernel health limitations separately.
