# DS124 ARM64: official patch backup and root handoff

On October 12, 2026, the stock DS124 DSM 7.2.2-72806 kernel and rd.bin,
QEMU virt with the existing research UART/sysbus AHCI implementation, and a
new populated p1 image reached **J5: DSM systemd begins normal service startup**.

The previous P2 image remains untouched. No kernel, initramfs, consistency
check, networking, partition geometry, or installer changes were made.
No p2/p3 partition was created. All proprietary inputs, extracted files,
disassembly, disk images, and full serial logs remain ignored under work/.

## Exact consistency contract

The running junior environment is identified by Synology's own
synogetstate.sh predicate: /linuxrc.syno exists. In this experiment it is the
boot/recovery/installer environment from rd.bin. Root means the installed
system filesystem mounted at /tmpRoot. These meanings come from the stock
scripts, rather than from treating every initramfs as junior.

check_root_junior_match.sh runs in junior and applies these tests in order:

| Step | Input pair/predicate | Compared field | Failure exit |
| --- | --- | --- | --- |
| 1 | argument root directory exists | directory | 1 |
| 2 | root/etc.defaults directory exists | directory | 1 |
| 3 | /etc.defaults/synoinfo.conf vs root/etc.defaults/synoinfo.conf | unique | 2 |
| 4 | /etc.defaults/VERSION vs root/etc.defaults/VERSION | buildnumber | 2 |
| 5 | non-virtual platforms: root/.syno/patch exists | directory | 1 |
| 6 | /etc.defaults/VERSION vs root/.syno/patch/VERSION | buildnumber | 2 |
| 7 | same pair | smallfixnumber | 2 |
| 8 | same pair, unless root/.SkipCheckPackingMatch is a regular file | packing | 2 |
| 9 | same pair, under the same condition | packing_id | 2 |

Every equality is a shell string comparison of get_key_value results.
The platform is unique split on underscore, field 2; exemptions are kvmx64,
nextkvmx64, kvmcloud, kvmx64sofs and kvmx64v2. DS124 uses rtd1619b, so it is
not exempt. Comparing full synoinfo unique also checks the model/platform.

productversion, buildphase, major/minor, nano and base are not compared.
Missing keys can compare as two empty strings; no explicit VERSION-file
existence test or helper-return check is made. Both DS124 VERSION files omit
packing and packing_id. No keys or skip markers were fabricated.

The caller maps any nonzero status to linuxrc Exit 7; the checker itself
returns 1 for absent directories and 2 for unequal values. In hda1.tgz the
checker itself is absent; the active checker is the one supplied by rd.bin.

## Official source and actual write operation

The source of the regular DS124 patch VERSION is **PAT top-level VERSION**,
620 bytes, not hda1.tgz's 222-byte etc.defaults/VERSION.

The official top-level updater SHA256 is
9d207ec7156abc1f70ab5970e2a53606cbc31a1b3e02ea30bbc3bf55c7c49c32.
Analysis of its sectionless AArch64 ELF established these operations:

| Updater virtual address | Proven operation |
| --- | --- |
| 0xe210c | logs the start of backup flash image |
| 0xe2178–0xe218c; selector 0x109f44 | selects regular files from the extracted PAT current directory |
| 0xe28640, stride 0x100 | eleven-entry exclusion table in the updater data segment |
| 0xe21a4–0xe2224 | constructs /tmpRoot/.syno/patch, patch_ and patch_swap paths |
| 0xe22f8–0xe2318 | executes mkdir -p -m 0755 for patch_ staging |
| 0xe3570–0xe3584 | executes cp -rf for every selected source filename into staging |
| 0xe3590–0xe35bc | collects matching original checksum.syno records |
| 0xe3614–0xe3634 | copies the resulting checksum file into staging |
| 0xe3648; helper 0xe80f0 | swaps staging into the final persistent patch directory |
| 0xe8160; wrapper 0x9707a0 | renameat syscall, number 38, confirms actual rename operation |

VERSION is a selected regular file and is absent from the exclusion table.
This establishes the actual source/destination copy logic, independently of
similar-looking metadata. There is no VERSION generation in that operation.

The selected DS124 files are DiskCompatibilityDB.tar, VERSION, model.dtb,
rd.bin, uboot_DS124.bin, uboot_do_upd.sh, updater, zImage, plus a generated
checksum subset. The directory preserves boot artifacts for system migration
and recovery; it is persistent, not a patch overlay unpacked into the root.

This backup precedes reboot-time extraction of hda1 via upgrade.sh and
extract_upgrade_tarballs.sh. The updater maps hda1.tgz to SynoUpgrade.tar.gz
(at 0xf523c–0xf5254); its -x mode instead decompresses to SynoUpgrade.tar.
The extraction script's RootMnt/* cleanup does not remove dot-prefixed .syno.
It extracts the root payload and separately deploys defaults/live configs.

There is also an explicit alternative mkdir/copy in rd.bin's autoinstall.sh,
which copies junior /etc.defaults/VERSION for models not backing up flash.
It requires support_auto_install=yes. That condition is absent for DS124,
so the experiment reproduced its complete regular backup set instead.

synoupgradepreserve handles upgrade space/backing-file management;
libsynoinstallcpp.so's SpacePreserve::EnsureBackingFile consumes patch/updater.
Its small-update unpacker has separate patch references. No standalone
synoupdate or executable literally named smallupdate exists in the inspected
artifacts; synoautonano and synoupgrade do exist and were inspected.

## VERSION inventory

| Source | Path | productversion | buildnumber | smallfixnumber | Other actual fields |
| --- | --- | --- | --- | --- | --- |
| PAT | VERSION | 7.2.2 | 72806 | 0 | majorversion=7, minorversion=2, GM, nano=0, base=72806; unique and payload sizes |
| rd.bin | etc/VERSION, reached via /etc.defaults | 7.2.2 | 72806 | 0 | majorversion=7, minorversion=2, GM, nano=0, base=72806; unique |
| hda1.tgz | etc.defaults/VERSION | 7.2.2 | 72806 | 0 | majorversion=7, minorversion=2, GM, nano=0, base=72806 |
| reconstructed root | .syno/patch/VERSION | 7.2.2 | 72806 | 0 | exact original top-level PAT VERSION bytes |
| nested synokey.tgz | VERSION | absent | absent | absent | text is only 3; codesign format metadata |

All three DSM sources have major/minor/micro=7/2/2, os_name=DSM,
builddate=2024/09/05, buildtime=14:33:04. Neither packing key is present.
The checker compares junior against the base root, then junior against the
persistent updater backup; it does not directly compare the two root files.

## Reconstruction and verification

The new work/test-sata-patch-state.img uses the previous disposable p1-only
geometry, ext4 feature set and hda1.tgz extraction procedure. The builder
reproduces the final state of the proven backup algorithm; it does not run
the whole installer or updater against any devices.

Directories .syno and .syno/patch are root:root 0755. Original PAT header
modes are 0755 for VERSION, updater and uboot_do_upd.sh; 0644 for the other
five original files. The checksum subset is root:root 0644. File contents
were compared to their official sources with cmp and SHA256, before boot.
PAT VERSION's SHA256 is
929b0c5b6aff3d4799fe3cfeed3506be1a4f032d29c164c875f4f5b94fed850e.

The existing PAT decoder interprets octal mode text as decimal; this research
corrects that one decoding operation when recovering metadata. It preserves
original PAT signature verification and authenticated decryption. Windows
DrvFS permissions are not used as the source of guest file modes.

Recursive analysis inspected all top-level payloads, nested tar/tgz/txz/xz/gz,
zip/cpio containers, all fourteen SPKs and their manifests/scripts/payloads.
Two encrypted SPKs use the package key class from the official codesign
library. Signature and MAC verification stay enabled. No key bytes are
stored in tracked files. Nested scanned bytes: 1,291,078,231.

The isolated guest boot mounted /dev/sata1p1 at /tmpRoot with Synology's
ext4 options. The unchanged command
/usr/syno/sbin/check_root_junior_match.sh /tmpRoot returned **0**, with empty
stdout and stderr. Only after that result did the normal /init boot run.

Normal boot reported linuxrc.syno executed successfully and Post init.
The external kernel breakpoints captured /sbin/init execve returning 0,
new user entry PC 0x7f8d76da80, and entry into the new program. The path is
/sbin/init after root handoff, corresponding to the former /tmpRoot/sbin/init
symlink to ../lib/systemd/systemd. Serial evidence identifies its PID as 1.
Two chroot syscalls were observed, although their user pointers were
unreadable in that breakpoint context. No pivot_root or switch_root was
observed; mount --move was not directly instrumented.

First systemd records include systemd 219 running in system mode and
Detected architecture arm64. It starts Synology swap, Synology Plugin Daemon,
D-Bus, udev, and reaches Sockets and Local File Systems targets.

The first new **failed unit** is syno-mount-usbfs.service, status=1/FAILURE.
Its official script tries to bind /dev/bus/usb at /proc/bus/usb and link the
USB devices debugfs file. The captured service log says /dev/bus/usb does not
exist, followed by a missing /proc/bus/usb/devices destination. This is not
a demonstrated global boot-fatal failure: other systemd services continued.
Later hardware-dependent failures/timeouts were observed without being fixed.
The observer terminated the exact scoped QEMU process after 432.12 seconds.
The harness now stops automatically on the first failed unit in future runs.

p2 is **not yet required**: it stays absent and Synology swap starts.
p3 is **upgrade-only** for this demonstrated boot: the upgrade search probes
absent sata1p3, falls back and finishes with No upgrade file found.

## Reproduction and local evidence

Run in Linux/WSL in this checkout. Reuse the existing authenticated PAT
extraction venv. The new-image preparation refuses an existing target.

~~~bash
research/arm64/work/venv/bin/python research/arm64/analyze-patch-state.py
research/arm64/work/venv/bin/python research/arm64/build-official-patch-state.py
sudo bash research/arm64/prepare-patch-state.sh
sudo python3 research/arm64/boot-patch-state.py isolated
sudo python3 research/arm64/boot-patch-state.py normal
~~~

The following local files remain ignored in research/arm64/work/:

- junior-match-contract.txt: ordered predicates, paths, fields and exit codes.
- patch-reference-map.txt: all matching ASCII/text references and resolved roles.
- pat-update-inventory.txt: recursive members, original ownership/modes, saved evidence paths.
- official-patch-source.txt: exact copy, checksum, file-selection and rename trace.
- version-metadata.txt: every discovered VERSION's small text payload.
- patch-state-report.txt: preboot ownership, permissions, contents, file source and checksums.
- patch-isolated-check.txt, patch-isolated.log and result JSON: isolated exit 0 evidence.
- patch-normal-init.log, patch-normal-exec-trace.txt and result JSON: normal boot and exec evidence.
- patch-root-handoff.txt: handoff/result/classification and partition conclusions.
- patch-first-blocker-report.txt: read-only postboot service script/unit/log evidence.

Next task: determine the official USB device-node/mount prerequisites for
syno-mount-usbfs.service on QEMU virt, starting with missing /dev/bus/usb.
