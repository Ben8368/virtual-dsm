# Bare-metal ARM64 acceptance plan

This is a separate future hardware check; it does not block completion of
Phase 4B integration work. Current Phase 4A K5 covers only Apple M5 / macOS /
Colima Apple VZ / ARM64 Ubuntu / nested KVM.

Prefer at least one non-Apple ARM64 Linux host. Preserve the host details,
kernel, firmware, QEMU identity, and container image identity with the evidence.

1. Confirm Linux `uname -m=aarch64`, `/dev/kvm` device ownership/mode, and
   access from the same unprivileged container user used for production.
2. Run the selected production ARM QEMU with `-machine virt,gic-version=3
   -accel kvm -cpu host`; record the host-visible guest CPU features and
   verify no TCG fallback.
3. Verify the exact DS124 PAT identity before extraction:
   `DSM_DS124_72806.pat`, SHA256
   `17f48a9a4572c9b3b994921d3fb410d8186e9c4bf02cf9334e37897e5752e1dd`.
   Use a fresh empty storage directory for fresh-install acceptance, or a
   separately copied configured runtime for compatibility-only testing.
4. Observe early serial output; fail on `__no_granule_support`, kernel panic,
   or equivalent CPU/boot failure. Do not accept TCG fallback as KVM evidence.
5. Complete DSM first-user setup and the single-disk Basic/Btrfs path; verify
   management HTTP/HTTPS, PostgreSQL, volume health, and a test-file hash.
6. Shut down from the DSM UI and require unmounted filesystems, QMP
   `guest=true` / `reason=guest-shutdown`, QEMU exit 0, and a clean manifest
   receipt. Reboot from the same storage and recheck volume, services, and
   test-file hash.

Keep the PAT and all extracted DSM payloads, disk images, credentials, and
serial logs in ignored local storage. Record unsupported CPU/firmware results
as host-specific evidence; do not generalize them to all ARM64 Linux hosts.
