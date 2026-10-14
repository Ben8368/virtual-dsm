# Package installation and Surveillance Station

Record image ID, DSM_PLATFORM, DSM build, guest uname -m, package version and
complete failure text. Container CPU and guest CPU are separate. Do not replace
a runtime disk or change identity to investigate a generic installation failure.

## Local builds

compose.yml still uses the published upstream image. Deploy this branch with:

```sh
DSM_PLATFORM=rtd1619b docker compose -f compose.local.yml build
DSM_PLATFORM=rtd1619b docker compose -f compose.local.yml up -d
```

Use DSM_PLATFORM=virtualdsm for the x86 guest. The example defaults to TCG on
both hosts, requires no privileged devices and publishes only to loopback.
Configure KVM separately when host and guest CPUs match. Forwarding SSH does
not enable SSH inside DSM. User networking does not guarantee camera discovery;
initially enter camera IP addresses manually.

DSM_STORAGE defaults to ./storage-local. An existing installation must retain
its storage directory and DSM_PLATFORM. Updating the image never replaces its
existing root. Selecting empty storage creates a separate installation.

## ARM initialization

Only the exact official DS124 DSM 7.2.2-72806 PAT is supported. New roots retain
its bundled SPKs under /.SynoUpgradePackages, following the x86 installer;
ActiveInsight is excluded. This handoff does not guarantee every package installs.

A one-shot service installs the authenticated PAT's Storage Manager through
normal synopkg install, checking its SHA-256 and propagating failures. It skips
an already installed package. No signature/identity check is bypassed. It does
not create a volume, mark DSM configured or install Surveillance Station.

ARM virt currently has no stock-kernel-compatible RTC. The launcher passes its
UTC epoch to a sysinit service which seeds guest time using launch epoch plus
guest uptime, before network/package services. NTP remains authoritative after
startup. This compensates for the 1970 initial clock; it is not RTC emulation
or a guarantee of precise TCG timekeeping. Keep the host clock synchronized.

New-seed service activation uses vendor target.wants directories under
/usr/lib/systemd/system. DSM's first initialization reconstructs /etc and drops
preseeded /etc/systemd/system activation links; merely writing those links into
an offline seed is insufficient. Existing configured roots use normal systemctl
enable through the explicit migration script.

Old runtime disks are unchanged. For an existing DS124 root, first update its
container launcher. Copy clock.sh, virtual-dsm-clock.service and install-clock.sh
from src/guest into a private temporary directory inside DSM and run
sh install-clock.sh there as root. It enables the unit for the next boot,
without stepping the running clock. Restart/shut down through DSM. Remove the
temporary copies afterward. If Storage Manager is absent on an old root,
manually install the exact PAT's StorageManager-rtd1619b-1.0.0-00502.spk through
Package Center, then use the normal storage wizard. No disk/root reset is needed.

## Read-only diagnosis

src/guest/package-diagnostics.sh runs **inside DSM**, not the Docker Linux host.
--network adds bounded public HTTPS probes with certificate verification.
It exports state and log classifications, never raw logs, serials, MACs, request
bodies or license keys. From a host with existing SSH key access/known-host entry:

```sh
python3 scripts/package-readiness.py --guest admin@127.0.0.1 --port 5022 --sudo --network
```

--sudo uses sudo -n and requires cached/noninteractive permission. No password
is collected. The tool does not enable SSH, install packages, register accounts
or modify the guest. Alternatively run the collector in an existing DSM root
shell, save its TSV output privately, and analyze with --from-report report.tsv.
JSON goes to stdout. Exit codes: 0 prerequisites passed, 2 blocked/collection
failure, 3 incomplete. None certifies NVR authorization or camera licensing.

Investigate in this order:

1. Correct platform/CPU and UTC, Storage Manager, mounted writable /volume1,
   active PostgreSQL. An empty directory named volume1 is not a mounted volume.
2. Guest DNS/TCP/TLS. curl 28 means timeout, 6 DNS, 60 certificate validation.
   HTTP 403/404 at a public root URL proves transport only, not authorization.
3. Recent hwid/authorization/dependency errors. Historical warnings do not prove
   the current failure's cause. Capture the complete failure plus matching-time
   synopkg.log/synopkgmgr.log locally; do not publish credentials.
4. Install an ordinary package, then Surveillance Video Extension, then
   Surveillance Station. Verify startup, restart, licensed recording/playback.

SVE requires online installation; manually installing the main SPK does not
eliminate dependencies. x86 qemu-host and ARM DS124 identity interfaces differ.
HOST_MODEL/HOST_SERIAL/GUEST_SERIAL configure the x86 sidecar, not ARM hardware.
Arbitrary identifiers are not a repair. hwid/online authorization requires a
measured guest-side failure and appropriate supported identity.

Tests cover diagnosis, epoch validation, seed integration and runtime retention.
HTTP 200/transport success is never NVR acceptance. Real package installation on
both platforms and ARM64 KVM require separate runtime evidence.

## Local validation on 2026-10-14

The final disposable official DS124 PAT test on an amd64/TCG host observed the
clock service successfully setting UTC, the normal Storage Manager installer
returning success, and management HTTP 200. Twelve non-ActiveInsight PAT packages
were staged. The test guest was stopped afterward and its private disk/evidence
retained. The initial candidate's /etc activation links were lost during DSM
initialization; offline inspection confirmed missing links and intact /usr
service files. Vendor activation fixed that measured issue.

ShellCheck, Dockerfile lint/build, Compose validation, platform/PAT regressions,
synthetic ARM construction/runtime/metadata checks, integration path protection,
diagnostic classification and production x86 argv checks passed. This is
prerequisite acceptance only: SVE/Surveillance Station online installation,
hardware-identity authorization, camera licenses, recording and ARM-host KVM
were not accepted by this test. The broader stock hardware/TCG stability limits
documented in Phase 3 still apply.
