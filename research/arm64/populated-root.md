# DS124 populated-p1 experiment

This experiment answers whether the stock DS124 DSM 7.2.2 kernel and initramfs
can continue normal boot after the system partition contains the official
hda1 root payload. It does not establish canonical Synology geometry or a
complete installed disk. All proprietary inputs, disk images and raw evidence
remain under the ignored research/arm64/work directory.

## Construction

Run from a Linux host with root access (WSL was used):

```sh
sudo bash research/arm64/prepare-populated-root.sh
sudo python3 research/arm64/boot-populated-root.py
```

The preparer recreates only work/test-sata-root-populated.img. It rejects a
symlink, an attached loop or a file in use. It checks the resolved file path
before partitioning and verifies the loop backing file, offset and size before
formatting. Cleanup unmounts the extraction directory and detaches that loop.
No physical disk or existing DSM image is a target.

Research geometry: a 2 GiB raw image, DOS/MBR, 512-byte sectors, only p1,
start 2048, length 4,190,917 sectors, end 4,192,964, type 0x83. There is no p2 or
p3. This repeats the previous temporary partition geometry.

The ext4 filesystem has 4096-byte blocks and 256-byte inodes. Its feature set
matches the observed Synology formatter: has_journal, ext_attr, resize_inode,
filetype, extent, 64bit, flex_bg, sparse_super, large_file, huge_file, uninit_bg,
dir_nlink, extra_isize, quota, project. metadata_csum is absent. This is a
research-compatible filesystem contract, not a claim about canonical DS124
formatting.

The full guest mount options remain prjquota,rootprjquota,barrier=1,noatime at
/tmpRoot. The host rejected that option set; removing rootprjquota allowed the
WSL extraction mount with prjquota,barrier=1,noatime. This does not change the
stock guest mount script.

Despite its .tgz suffix, hda1.tgz is XZ-compressed tar data. GNU tar 1.35
extracts as Linux root with numeric ownership, original modes, delayed directory
timestamp restoration, xattrs, ACLs and SELinux metadata support. The archive
contains 21,732 members: 16,633 regular files, 2,030 directories, 2,820 symlinks,
247 hardlinks and two character devices (console 5:1 and net/tun 10:200).
There are no block devices or FIFOs, and no PAX xattr/ACL metadata is encoded.
Archive inspection precedes formatting/extraction. Verification compares all
members' ownership, modes, mtime, type/size, link targets/inodes and device
numbers against the mounted filesystem: zero mismatches.

Stock inputs remain unchanged:

- Image SHA256: 4c6584070c2bfee8a7ab1b73ef74d1872a0469700e61fc806e6b72d23e576b14
- Decompressed rd.bin SHA256: 3177c1be9dbc40224c5ad193d7ad032e74c83ce54e5d436ebec209b26384a2bf
- hda1.tgz SHA256: 1bc3c52e83567fdac1ec2bc77239293273554bfa7951d5c3fd2102e142d78c2c

## Verified root tree and expectations

/etc, /etc.defaults, /usr, /usr/syno and /var.defaults exist. /bin -> usr/bin,
/sbin -> usr/sbin, /lib -> usr/lib, /sbin/init -> ../lib/systemd/systemd and
/bin/sh -> bash all retain their official links. etc.defaults/synoinfo.conf
identifies synology_rtd1619b_ds124; etc.defaults/VERSION has buildnumber 72806.

The preparation report records stat, file and readlink evidence. The separate
root-expectations-checklist.txt maps pre-boot paths to the exact operations in
linuxrc.syno.impl, check_root_junior_match.sh and dsmupdate scripts.

The payload's /etc contains passwd/group template symlinks, so the stock normal
boot replaces it from etc.defaults. /usr/syno/etc and /var are initially absent;
the stock script seeds them from usr/syno/etc.defaults and var.defaults. These
are stock boot operations, not host adjustments to satisfy validation.

/.syno/patch and /.syno/patch/VERSION are absent from the official root payload.
No substitute directory, VERSION file, install marker or bypass is added.

## Normal /init result

QEMU uses the existing research MMIO UART and sysbus AHCI, virt with GICv3,
max,lpa2=off, 2 CPUs, 2 GiB RAM, no network, normal kernel and rd.bin. The command
line has rdinit=/init, root=/dev/sata1p1 and pty.legacy_count=0. It has no shell
PID 1 override. The original /init resolves to the stock BusyBox init.

The main /dev/sata1p1 mount at /tmpRoot succeeds with the Synology project-quota
options. The previous missing-etc.defaults fatal failure is cleared. The normal
path finishes its no-upgrade lookup, skips smallupdate on a version-match
failure, successfully seeds /etc, /usr/syno/etc and /var, and reaches the
mandatory root/junior match check.

First new fatal blocker:

- Script: /usr/syno/sbin/check_root_junior_match.sh, AssertDirectory at line 45.
- Command: /usr/syno/sbin/check_root_junior_match.sh /tmpRoot, called by
  /linuxrc.syno.impl at line 913.
- Expected path: /tmpRoot/.syno/patch/; actual state: absent.
- Validator returns 1 via AssertDirectory. The earlier smallupdate invocation
  treats this condition as a skip; the later mandatory validation is fatal.
- /linuxrc.syno.impl calls Exit 7 "root not matched with junior".
- Serial evidence: Failed to AssertDirectory[/tmpRoot/.syno/patch/] followed by
  Exit on error [7] root not matched with junior...

The harness termination and QEMU exit status are recorded separately and do
not replace the guest's failure code. The harness stops after the first fatal
conclusion; a fallback junior-mode /etc/rc is not evidence of DSM root services.

## Root execution and transition

Classification: P2 — DSM begins executing files from the populated system root.

The first proven root-file-based process is
/tmpRoot/usr/syno/sbin/synoupgradepreserve. The unchanged datadevice.sh calls
this helper as --attach --root /tmpRoot during the upgrade-search fallback.
An external hardware-breakpoint trace of another normal /init boot records
its kernel execve filename, successful execve return code 0, new user PC
0x7fb6c129c0, and execution at that user entry point. The command arguments
come from the unchanged script: user argv could not be read while stopped
in the kernel. Successful execve and first user instruction are direct runtime
evidence, rather than an inference from the shell source.

To reproduce the trace, recreate the image first and run:

TRACE_EXEC=1 sudo -E python3 research/arm64/boot-populated-root.py

The tracer attaches immediately before the main /tmpRoot mount and uses
hardware breakpoints. A stock-Image SHA256 guard protects the recovered
DS124 72806 addresses. The helper runs with the initramfs as its process root;
executing this file does not complete the PID 1 root transition.

The conditional chroot into /tmpRoot for synoautonano is skipped because the
root/junior match check fails. The later conditional synoselfcheck-min chroot
is not reached. No successful PID 1 root handoff, pivot_root, switch_root or
mount move is established by this experiment. Upgrade-script comments referring
to switch_root are not runtime evidence.

Static file/readelf inspection records AArch64 systemd, bash and synoautonano
and their /lib/ld-linux-aarch64.so.1 interpreter. Resolving the official /lib
and loader symlinks finds /usr/lib/ld.so.1 with executable mode 0555. The early
synoupgradepreserve helper is an AArch64 static PIE without a PT_INTERP; its
execution does not establish that every dynamically linked DSM service loads.

## p2 and p3

p2 requirement: unknown beyond the reached stage. decide_system_partition.sh
selects /dev/sata1p2 for this DS124, but no required swap operation is observed
before the fatal root match gate. mkswap belongs to installer scripts; swap
control surrounds actual upgrade extraction and junior fallback startup.
Neither partition is added.

p3 requirement: unknown beyond the reached stage. Its observed use is an
upgrade search: datadevice.sh tries /dev/sata1p3 at /tmpData, then searches p1
and a preserved-upgrade loop for SynoUpgrade.tar.gz. The missing p3 mount is
nonfatal; "No upgrade file found" returns to the main boot script. This proves
p3 is unnecessary through this stage, not that later DSM runtime never needs a
data partition. The raw reference inventory is root-populated-partition-references.txt.

## Evidence and validation

Ignored evidence:

- root-population-report.txt and root-expectations-checklist.txt
- root-populated-normal-init.log and root-populated-boot-result.json
- root-populated-normal-init-traced.log and root-populated-boot-result-traced.json
- root-populated-exec-trace.txt, root-transition.txt and root-elf-report.txt
- root-populated-partition-references.txt

Validation commands: bash research/arm64/tests/smoke.sh;
shellcheck -x research/arm64/*.sh research/arm64/tests/*.sh; git diff --check.
The Python sources and embedded GDB Python are also syntax checked. Actual
normal /init boot is the behavior test; smoke checks alone do not establish DSM
boot success.

Next task: determine the official provenance and deployment procedure for
/.syno/patch/VERSION, then test only that required installed-state metadata in
a new disposable root image. Do not bypass the match check or invent values.
