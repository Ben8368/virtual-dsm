# Production Integration Phase 2 validation

Validated on October 13, 2026 (Asia/Shanghai), on
`feat/rtd1619b-auto-install`. Existing Phase 1 work was retained without rewriting
history. Tests used an amd64 WSL2 Docker host and the production patched QEMU
8.2.2 with TCG; ARM64 KVM remains outside this phase.

## Result: A5

The normal production entrypoint prepared artifacts from the official DS124
DSM 7.2.2-72806 PAT and empty relevant storage, booted DSM management, then
reused the same generation on restart. Both boots completed **30/30 HTTP 200**
and **HTTPS 200** management checks. Stock guest logs, read after stopping,
confirmed DHCP `10.0.2.15`, scemd activity, systemd PID 1, sata1p1, XHCI and
cdc_ether eth0. Neither boot showed a kernel NULL oops, scemd soft lockup or
queued_write_lock_slowpath.

The original PAT remained unchanged, SHA-256:

```text
17f48a9a4572c9b3b994921d3fb410d8186e9c4bf02cf9334e37897e5752e1dd
```

The cache receipt matched the stopped first-boot generation, all three artifact
hashes and modification timestamps before QEMU resumed. Restart logs contained
an explicit cache hit and no PAT extraction or filesystem rebuild. Guest writes
subsequently change the system-image hash; orderly container teardown records
its validated stopped hash. Kernel/initrd stay immutable.

The existing Phase 1 shutdown limitation remains: the container fallback
terminates QEMU and does not demonstrate a graceful DSM guest shutdown. The
restart accepted that stopped image, passed offline validation and reached
management again. DSM UI shutdown should be used when available.

## Construction checks

The builder audited all **21,732** hda1 archive entries offline for ownership,
modes, modification times, hardlinks, symlinks and device numbers. The original
research oracle and the production /.syno/patch matched in selected names,
file bytes, VERSION, checksum subset, ownership and modes.

Two independent unbooted official builds using the final timestamp normalization
produced identical artifacts:

| Artifact | SHA-256 |
|---|---|
| kernel | `4c6584070c2bfee8a7ab1b73ef74d1872a0469700e61fc806e6b72d23e576b14` |
| initrd | `3177c1be9dbc40224c5ad193d7ad032e74c83ce54e5d436ebec209b26384a2bf` |
| initial system.img | `6347a3ea89773964973b72a6178b00dca15644153acc04e1ec24ee3f0a43e538` |

Official PAT headers use zero timestamps, which e2fsprogs treats specially.
The builder fixes filesystem creation/access/change times to a nonzero epoch,
sets the superblock write time explicitly, and retains original root archive
modification times. This is filesystem metadata normalization, not a DSM binary
change. Boot acceptance and deterministic-build checks were separate local runs.

Failed-build recovery was exercised before successful production startup;
synthetic tests also checked abandoned partial work, failure before publication,
corruption, missing/empty artifacts, public-link repair and legacy adoption.
Extracted official root trees and temporary duplicate filesystems were deleted.
Generated bootable images remain only in test storage.

## Regression and tooling

Passed:

- Required production/research shellcheck command and research smoke tests.
- Platform command/artifact snapshots and original x86 installer byte hash,
  reconstructed after moving unchanged PAT/mirror helpers to common code.
- Common PAT mirror precedence/detection, file source preservation and retry arguments.
- Actual default x86 production entrypoint command using `virtual-dsm:phase2`.
- Synthetic image validator tests and the automatic ARM builder suite.
- Synthetic ARM suite under UID 1000, all capabilities dropped and no-new-privileges;
  device nodes, hardlinks, symlinks, numeric ownership, modes and xattrs survived.
- Root/junior mismatch rejection, exact identity rejection, deterministic builds,
  manifest/generation publication, cache reuse and recovery tests.
- Both production patches applied cleanly to pristine QEMU v8.2.2.
- Final Docker image build, runtime dependency checks and Dockerfile lint.
- Tracked proprietary-artifact policy and `git diff --check`.

CI uses only synthetic DSM equivalents and never downloads DSM. Local official
acceptance helpers are `tests/production-arm-install.py`,
`tests/production-arm-management.py`, `tests/production-arm-install-evidence.py`
and `tests/official-arm-patch-state.py`. Raw local evidence is ignored under
`research/arm64/work/production-phase2/`; it is not a runtime dependency.

## Next task

Production Integration Phase 3: persistent DSM configuration/data-disk behavior
and fresh-user setup semantics. Canonical DS124 layout, p2/p3 and fresh installer
behavior remain deliberately unimplemented.
