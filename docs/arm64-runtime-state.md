# Experimental DS124 writable runtime policy

Phase 3 separates reproducible installation artifacts from user-owned runtime
state. This policy applies only to rtd1619b / DS124 DSM 7.2.2-72806. It does not
claim physical DS124 disk-layout compatibility or stable ARM support.

## Artifact ownership

| Artifact | Ownership and validation |
|---|---|
| *.kernel | Immutable official boot payload; replaceable only by explicit installation/reset; exact stock SHA-256 |
| *.initrd | Immutable official boot payload; exact stock SHA-256 and root/junior identity |
| Original installed-root seed metadata | Immutable provenance: original 2 GiB seed SHA-256 and geometry, PAT/model/build/builder identity |
| *.system.img | Mutable persistent user state from the first possible guest write; configuration, accounts, databases, storage metadata and any later data partitions belong to DSM |
| *.arm.json | Immutable provenance fields plus replaceable atomic runtime observations; never an immutable whole-disk checksum |
| PAT | Regenerable immutable input; source file:// is read-only; private download/extraction workspace is replaceable, removed after construction; no retained PAT cache required |
| Private generation directory | Storage-owned persistent container for immutable boot files and mutable disk; old generations are user recovery state, never garbage collected automatically |
| *.arm-current and public links | Replaceable atomic addressing metadata; repaired only after validating the referenced generation |

A missing/broken pointer, partial public set or orphan generation is evidence
of existing state. Startup stops and preserves it; it cannot authorize a fresh
installation. Only storage with no published/legacy state allows a new build.
Generation payloads must be regular owned files, not symlinks into another
runtime disk. A conflicting real public system image or a public image link pointing at a
different existing disk also stops startup: repairing links cannot discard or
silently switch user runtime disks. Validated legacy adoption first copies the
complete disk before replacing its public name.
Abandoned unpublished .rtd1619b-install-* workspaces remain replaceable.

## Manifest schema 2

artifacts contains only kernel and initrd immutable hashes/sizes. seed retains
system_sha256 of the original unbooted 2 GiB installed root, geometry and hash
origin. Expansion never changes this seed identity. It is diagnostic provenance,
not an expected current runtime-disk hash.

runtime has its own version, virtual_bytes, monotonic launch generation,
lifecycle, launch_pending, launch_utc, last_exit and dsm_evidence. The lifecycle
is SEED until the production launcher durably records BOOT_ATTEMPTED **before**
QEMU starts. A failed launch may conservatively protect an unbooted disk.
BOOTED, first-user initialization, CONFIGURED and DATA_INITIALIZED are distinct
evidence dimensions, not assumed consecutive transitions:

- Boot observation: stock systemd log plus populated runtime configuration and
  passwd; offline corroboration, not a current service-health claim.
- First-user observation: admin_configured=yes plus a named local account in
  administrators. This does **not** imply bootstrap configured=true.
- configured: the actual DSM SessionData/bootstrap field is authoritative for
  what management reports. Offline configured plus administrator evidence is
  labeled heuristic; a missing marker remains unknown.
- Data initialization: an actual mounted data filesystem, DSM pool/volume
  metadata and healthy storage API state must agree. Offline checks currently
  leave data_initialized unknown rather than interpreting a directory as a
  mounted or healthy volume.

Schema 1 migrates in place only after root/boot/provenance validation. Phase 2
seal overwrote the original seed hash; migration preserves that old hash as a
legacy stopped observation, and records seed_system identity as unavailable.
It never invents an original seed hash or checks the old value against runtime.
Manifest migration never rewrites disk contents. An unknown schema fails closed.

## Validation and recovery

Restart validates immutable stock kernel/initrd and PAT/model/build/builder
provenance; readable MBR; the proven p1 start/length/type; ext4 features;
DS124 root VERSION/synoinfo identity; /.syno/patch VERSION and junior match;
systemd and stock network modules/activation. Runtime p2-p4 may exist when their
MBR ranges are readable, in bounds and nonoverlapping. No p2/p3 is created here.

Neither seed hash mismatch, crash, source-URL change, damaged runtime partition,
missing boot payload nor failed stopped observation permits automatic runtime
replacement. Invalid existing state stops with an actionable error. Kernel/root
repair is a deliberate offline operation preserving user state.

There was no project reset/reinstall switch to reuse. This phase adds no
ambiguous RESET flag: an explicit reset means stop the container, retain the
entire previous storage directory for recovery, and deliberately select a new
empty storage directory. Startup never performs that destructive decision.

## Single-disk capacity

For ARM, DISK_SIZE is total raw /dev/sata1 capacity (default remains 256G).
Integer binary K/M/G/T suffixes are supported. The construction minimum is 2 GiB;
this is **not** a demonstrated data-volume minimum. MBR addressing bounds and
sector alignment are enforced. New seeds use the proven fixed ext4 p1 at
sector 2048 with 4,190,917 sectors, then a sparse unallocated tail.

A stopped legacy 2 GiB image grows by extending the backing file only, under the
existing exclusive generation lock. The partition table and every old byte
remain unchanged. Startup rejects shrink; it never moves/reformats p1, creates
another SATA disk, or makes DSM consume free space automatically. Raw expansion
must finish before QEMU opens the disk. DSM-managed volume growth remains a
separate operation whose supported path needs runtime evidence.

## Shutdown observations

A private host-only Unix QMP socket observes SHUTDOWN events. A clean stopped
receipt requires guest=true, reason=guest-shutdown **and** QEMU exit code 0.
An absent event, host quit, nonzero exit or container timeout never counts as
clean. The stopped disk is structurally validated; no whole-disk hash is updated
or compared. The watcher has no guest agent or management credentials.

The production ttyS1 MMIO UART patch is required for stock DS124 poweroff:
without a real port, the reboot syscall writes an unprobed 8250 placeholder
and panics before reaching kernel poweroff. It provides no controller protocol.
A local disposable Phase 3 UI shutdown has demonstrated filesystem unmount,
ARM virt poweroff and a clean QMP/QEMU receipt; see the
[Phase 3 evidence](../research/arm64/production-phase3.md).

Use DSM's normal local shutdown UI. Container-requested shutdown retains the
shared bounded SIGTERM/SIGKILL fallback for a hung/unresponsive guest; ARM no
longer sends immediate SIGTERM before allowing the existing guest-wait window.
x86 disk sizing, PAT installer, command construction and shutdown API are
unchanged.

## Validation

Non-proprietary tests: tests/arm-installer.py and tests/arm-runtime.py. They cover
runtime mutation without a stopped receipt, schema migration with stale hashes,
configured evidence cache reuse, conservative replacement protection, sparse
raw growth preserving the exact old prefix, shrink rejection, and QMP receipts.
Local official evidence is ignored in research/arm64/work/phase3. No DSM payload,
account password or private auth token belongs in CI or tracked documentation.
