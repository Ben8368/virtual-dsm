# Phase 2 automatic preparation

Experimental DS124 / rtd1619b support now automatically prepares installation
images for **DSM 7.2.2-72806 only**. Supply `DSM_PLATFORM=rtd1619b` and
`URL=file:///input/DSM_DS124_72806.pat` (bind the PAT read-only) or its HTTPS URL.
The exact supported PAT SHA-256 is
`17f48a9a4572c9b3b994921d3fb410d8186e9c4bf02cf9334e37897e5752e1dd`.
The default Synology URL selects this same build. Other builds/models fail closed.

This builds a **research-compatible already-installed system root**; it does
not implement canonical DS124 physical disk layout or fresh Synology installer
behavior. p2/p3 are not generated. Physical disk geometry remains unresolved,
and persistent runtime policy is documented in [Phase 3](arm64-runtime-state.md).
Storage and first-user acceptance remain experimental.

The common `src/pat.sh` retains the original downloader/retry and tar/patology
extraction. `platformPrepareArtifacts` invokes the production-owned ARM builder.
It validates PAT hash, VERSION, DS124/rtd1619b unique, model.dtb, ARM64 Image and
newc initramfs before creating persistent artifacts. The stock initramfs has
post-LZMA zero padding; only its first complete LZMA-alone stream is decoded.

GNU tar and mke2fs run in one fakeroot session, preserving numeric owners,
permissions, timestamps, hardlinks, symlinks and device nodes without mounting
or loop devices. Archive validation rejects path traversal, unsafe hardlinks,
relative link escapes and writes through any symlink ancestor. Stock guest
absolute symlink objects remain inert during extraction. Offline inspection
checks every populated archive entry, including device numbers and inode links.

The 2 GiB MBR image uses the proven research p1: start sector 2048, 4190917
sectors, ext4 with 4096-byte blocks, 256-byte inodes, has_journal/project/quota,
and no metadata_csum. The official updater selection and original checksum
record subset recreate /.syno/patch. VERSION is never fabricated; root/junior
build, unique, smallfixnumber, packing and packing_id are checked offline.
Filesystem UUID/hash seed, superblock write time and inode access/change/creation times are fixed for
deterministic builds; original archive modification times remain unchanged.
Kernel/initramfs/DSM binaries/modules remain unmodified. The CDC integration
remains `/usr/lib/modules-load.d/70-network-0007-research-usb-cdc.conf`.
New roots also stage authenticated PAT packages and project-owned clock and
Storage Manager one-shot services; see [package installation](package-installation.md).
The manifest records these optional integrations without changing legacy
provenance checks. Existing runtime roots are never rewritten to add them.

The public kernel/initrd/system.img names remain unchanged. They resolve through
one atomic `DSM_DS124_72806.arm-current` generation pointer, with
`DSM_DS124_72806.arm.json` holding identity, provenance, geometry, builder version,
sizes and SHA-256 values. Private 0700 `.rtd1619b-install-*` workspaces are cleaned
on success/failure and discarded after interrupted builds. A storage writer lock
serializes installation. Complete prior generations remain for recovery until
manually removed; they consume storage. Failed builds never change the committed
pointer or boot partial artifacts.

Cached generations validate immutable kernel/initrd and provenance plus the
writable disk structure and root identity. Schema 2 keeps the original seed
hash separate from current runtime contents. A changed runtime hash, unclean
exit or failed validation never authorizes automatic replacement. Invalid
existing state fails closed and preserves the disk. Schema 1 migrates without
checking its old whole-disk hash. Legacy prepared sets can be adopted after
stock boot hash checks and read-only root validation using sparse copying.
The source file:// PAT is never modified or deleted. See the
[ownership and recovery policy](arm64-runtime-state.md).

CI uses `tests/arm-installer.py` synthetic data only, with no DSM download. Run
it under fakeroot with the runtime Python dependencies installed. Also run
`tests/x86-installer-regression.py`, which reconstructs the original installer
bytes and checks their Phase 1 SHA-256 after the shared-function extraction.

Local official-PAT acceptance (never run in CI):

```bash
python3 tests/production-arm-install.py /path/DSM_DS124_72806.pat \
  /path/empty-storage /path/ignored-evidence --image virtual-dsm:phase2
```

This starts through the normal entrypoint, verifies interrupted-build recovery,
30 HTTP GETs plus HTTPS, stops the container, then checks a cached restart.
ARM has no guest shutdown agent. With the Phase 3 ttyS1 UART patch, the stock
DSM UI can cleanly unmount and power off QEMU. Container-requested stops retain
the bounded termination fallback; shut down through DSM first when possible.
System-image hashes change with guest writes; the generation pointer, immutable
boot hashes and explicit cache-hit logs distinguish reuse from rebuilding.
Guest QMP shutdown receipts are observational and never a cache condition.

See [Phase 2 validation](arm64-phase2-validation.md) for the demonstrated A5
result, test scope and the existing guest shutdown limitation.

Phase 3 treats the system image as user runtime state. See the
[runtime ownership policy](arm64-runtime-state.md) and
[local first-user/storage/shutdown evidence](../research/arm64/production-phase3.md).
