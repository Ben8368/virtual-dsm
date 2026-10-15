# Production Integration Phase 3: DS124 persistent runtime

This is an experimental single-disk virtual layout, not a claim of physical
DS124 partition-table compatibility. Tests use the exact official DS124
7.2.2-72806 PAT, production entry.sh, loopback publication, amd64 TCG and a
16 GiB sparse sata1 disk. Proprietary evidence and disposable credentials stay
under ignored research/arm64/work/phase3 and Linux disposable storage.

## Ownership and transitions

See docs/arm64-runtime-state.md for schema 2, fail-closed recovery and artifact
ownership. The installer protects a runtime before the first possible guest
write. Immutable seed identity cannot authorize restoring an original root
onto a booted disk. Existing invalid generations stop without reinstalling.

Observed stock transitions:

| Stage | Management configured | Upgrade completion | PostgreSQL |
|---|---|---|---|
| p1-only boot | false | false | failed: No volume to start PostgreSQL |
| Official local administrator wizard | false | false | still no volume |
| Official Basic/Btrfs creation, in progress | false | false | initialization deferred/in progress |
| Subsequent configured boot of cloned installation | true | true | active; accepting connections |

The first-user wizard and installed/configured completion are distinct. A
named administrator plus admin_configured=yes is not proof of configured=true.
The running bootstrap is authoritative for the management state. Offline
synoinfo/passwd/group observations are explicitly heuristic. Mounted filesystem
plus storage metadata and healthy Volume API corroborate actual data state.

## Official local mechanisms

The shipped WelcomeApp.js drives Security.AutoBlock/set, Network/set
(server_name), User/set for defaultadmin, User/create for the new user,
Group.Member/add for administrators, stopping synoagentregisterd when discovery
is unchecked, defaultadmin expiry, Auth/logout and named-account login. No
configured setter was used. Update installation is manual, discovery and
telemetry unchecked, and Synology account/QuickConnect are not enabled.

The Phase 2 installed-root seed does not install bundled PAT SPKs. Initially
Storage APIs returned 102 and Storage Manager was absent. The exact PAT's
StorageManager-rtd1619b-1.0.0-00502.spk was installed through Package Center's
Manual Install path, retaining normal checks. The official installer explicitly
chooses the system partition, so no data volume is needed for this package.
No Package Center compatibility claim or external package download is involved.
This prerequisite remains a local manual setup step in this experimental path.

The installed StorageManager UI's storage_wizard.js uses
SYNO.Storage.CGI.Volume v1 estimate_size and create. Creation parameters include
disk_id from the selected sole disk, device_type for Basic, is_disk_check=false,
fs_type=btrfs, pool_path, is_pool_child, allocate_size, spare_disk_count=0,
vol_desc, desc and atime_opt=relatime. Native space_operation.log confirms the
create handler and its actual tools. Read-only inspection uses
SYNO.Core.Storage.Volume v1 list (offset=0, limit=-1, location=internal), as
published by quick_wizard.js. Endpoints/methods were read from stock code/UI;
no brute-force requests or fake setup state were used.

### Local setup API ledger

Parameters below are field names or stock constants, never test credentials.
The sequence comes from the shipped WelcomeApp.js, not guessed method probing.

| API / version / method | Parameters | State transition / persistent impact |
|---|---|---|
| SYNO.Core.Security.AutoBlock / 1 / set | attempts=10, enable=true, enable_expire=false, within_mins=5 | local security configuration on root |
| SYNO.Core.Network / 1 / set | server_name from wizard | system hostname/configuration on root |
| SYNO.Core.User / 1 / set | name=admin, generated password | stock default account credentials; values excluded |
| SYNO.Core.User / 1 / create | name, password from local wizard | local account database on root; values excluded |
| SYNO.Core.Group.Member / 1 / add | group=administrators, name=[new local account] | administrator membership on root |
| SYNO.Core.Service / 1 / control | service_id=synoagentregisterd, action=stop | unchecked discovery option; no external registration |
| SYNO.Core.User / 1 / set | name=admin, expired=now | disable ordinary use of default administrator |
| SYNO.API.Auth / 6 / logout | no credential parameters | end bootstrap session; named account login follows |
| SYNO.Storage.CGI.Volume / 1 / estimate_size | selected sole disk and Basic options | calculate capacity; no observed partition creation |
| SYNO.Storage.CGI.Volume / 1 / create | sole disk_id; Basic; fs_type=btrfs; allocate_size; pool/description/atime fields | native p3 creation, Btrfs initialization and volume metadata |
| SYNO.Core.Storage.Volume / 1 / list | offset=0, limit=-1, location=internal | read-only corroboration of actual volume state |
| SYNO.Core.Desktop.SessionData / 1 / getjs | shipped page bootstrap query | read-only configured/upgrade/pgsql observations |
| SYNO.Core.System / 2 / shutdown | stock UI request | official shutdown hooks, service stop, unmount and poweroff; handler confirmed by synopoweroff.log |

The immediate first-user result did not create p2/p3 and still reported
configured=false. The subsequent boot after volume initialization reported
configured=true; findhostd logged Found admin password not empty, configured =
yes. This is the observed sequence, not proof that a data volume is the sole
prerequisite for the configured flag. The exact marker-writing component was
not independently established. The database has a separately demonstrated
data-volume requirement. API and file evidence corroborate completion without
manually changing a marker.

## Actual DSM-created layout

Both the expanded Phase 2 clone and a new Phase 3 16 GiB installation produced:

| Partition | Start sector | Sector count | MBR type | Purpose |
|---|---:|---:|---|---|
| p1 | 2048 | 4190917 | 0x83 | original ext4 system root, unchanged geometry |
| p2 | absent | - | - | no swap partition created in this experiment |
| p3 | 4455109 | 12107776 | 0x83 | DSM-created Btrfs data volume |
| p4 | absent | - | - | unused |

Stock sfdisk --fast-delete 3:128 precedes
sfdisk -N3 -uS -q -f -j262144 -z12107776 -t83 -F /dev/sata1.
DSM then runs mdadm --zero-superblock (no MD component found), mkfs.btrfs
--nodiscard --force --metadata dup, creates @syno, sets default subvolume 256,
and mounts /dev/sata1p3 at /volume1. /proc/mdstat has no active arrays; Basic
uses the partition directly in the demonstrated path. No host mkfs, manual
p2/p3, second SATA port, physical partition table, or system MD array was used.

DSM recognizes 16 GiB physical capacity but creates a 6,199,181,312-byte p3
(about 5.77 GiB); the Volume API reports 5,930,745,856 filesystem bytes
(about 5.52 GiB usable before subsequent contents).
A large unallocated tail remains. The exact unused-space sizing rationale is
not established; it is not evidence of automatic expansion to all capacity.
synopartition --check still says unrecognised partition for this virtual system
layout; that check must not be presented as a healthy physical installation.

## Persistent mutation inventory

Stopped-root comparisons cover /etc, /etc.defaults, /var and /usr/syno/etc.
Only path/type/size/links/content digests are compared; secret/auth contents are
excluded and there are no huge binary diffs. Against the booted p1-only seed,
the configured clone had the following semantic changes:

| Category/path | Mutation | Purpose |
|---|---|---|
| /etc/hostname, synoinfo.conf | modified | local name, administrator/setup flags |
| /etc/passwd, group, shadow | modified | local account, membership and credentials; contents not published |
| /etc/postgresql | modified | stock database configuration |
| /etc/space/space_table and history | created | storage topology/history |
| /etc/systemd/system/...pkgctl-StorageManager.service | created | supported package service activation |
| /etc.defaults/rc.first_login_after_upgrade | created | stock first-login bookkeeping |
| /var/packages/StorageManager | created | installed official local storage package |
| /var/lib/space | created/modified | pool compatibility, resources, volume state |
| /var/services/pgsql | created symlink | /volume1/@database/pgsql |
| /usr/syno/etc/volume.conf | created | persistent DSM volume metadata |
| /var/log and /usr/syno/etc databases/preferences | created/modified | runtime logs, schedules and local settings |
| /volume1/@database and test file | created | actual data filesystem state |

Changes in root categories total: /etc 80 created/142 modified/32 removed;
/etc.defaults 1 created; /var 286 created/612 modified/15 removed;
/usr/syno/etc 36 created/20 modified/4 removed. These counts include routine
boot/log churn, not only setup. Persistence of individual arbitrary log entries
is not assumed. Account, hostname, setup and actual data acceptance must be
corroborated after restart.

## Shutdown blocker and minimum hardware change

The first stock UI shutdown reached All filesystems unmounted, then panicked
in io_serial_out via syno_uart_write/syno_ttys_write. Recovered stock-kernel
disassembly confirms __do_sys_reboot writes ttyS1 before kernel_power_off.
An unprobed 8250 placeholder had iobase=0 and faulted at the I/O virtual base.
QMP reported guest-reset, QEMU exited 0; schema 2 correctly recorded clean=false.
This is not counted as a clean restart or a controlled crash test.

The Phase 3 QEMU patch supplies serial1 as a real MMIO 16550 at 0x0b010000,
IRQ 13, using a null host backend. It supplies no microcontroller protocol,
fan/RTC emulation, guest agent or kernel patch. Production keeps its ttyS0
console and one SATA disk. The final clean-shutdown result must distinguish
PSCI guest-shutdown from guest-reset, even when QEMU returns zero.

## Clean shutdown evidence

The first shutdown with the real ttyS1 completed on October 13, 2026:
all filesystems unmounted, the kernel printed reboot: Power down, QMP emitted
guest=true/reason=guest-shutdown, and QEMU/container returned 0. The schema 2
receipt records clean=true and outcome=guest-poweroff at
2026-10-13T09:49:50.687498Z. No host timeout/termination fallback was used.
The guest therefore reaches stock kernel poweroff/ARM virt SYSTEM_OFF without
a custom guest agent. Evidence: ignored clean1-stopped serial and manifest.

Before this shutdown, the named local account successfully logged in after boot,
bootstrap configured and upgrade completion were true, PostgreSQL accepted
connections, and the Volume API reported normal/noncrashed/writable Btrfs.
The test file retained inode 464, size 90 and SHA256
85c85894c2c5e1168f2c046c3d23dbc9dddd57fd8d6ef0e8c7f37c49d62b7e31.
The Network UI refused a later hostname update; it is not counted as successful.
The Region UI successfully saved Greenwich Mean Time instead (/etc/TZ GMT0).
Both data and this configuration were subsequently corroborated through two
clean restart cycles and the single controlled crash recovery.

The new real ttyS1 lets SynoSwInitLed complete, but scemd repeatedly times out
and restarts while waiting for unsupported controller behavior. There was no
serial kernel soft lockup/oops during this boot. Successful management, volume
and shutdown do not imply full hardware-monitor compatibility. No fan/RTC or
microcontroller response emulation was added.


## First clean restart acceptance

Clean stop 1 completed at 09:49:50 UTC. Production restart reused generation
.DSM_DS124_72806.arm-generation-9207cb64baa54e91ba30c37558051fb8 and recorded
launch generation 4, with no PAT extraction or root rebuild. Fresh boot task
evidence at 10:08:03 UTC re-read the test file with the same SHA256, inode 464
and size 90 from mounted writable Btrfs /volume1. Volume API status was normal,
crashed=false and readonly=false. /etc/TZ remained GMT0. The named account
successfully logged in again; configured/admin_configured stayed yes.

The boot task sampled pgsql-adapter while it was still activating. Later stock
pgsql.sh logged accepting connections and completion at 10:10:06 UTC; current
bootstrap independently reported configured=true, dsm_upgrade_all_done=true
and dsm_upgrade_pgsql_status=active. Early snapshots are not mislabeled as final
service state. Evidence is ignored clean1-verified/acceptance.json, manifest
and stock guest diagnostic/log exports. One clean persistence cycle is now
demonstrated; this is F4 until further restart and management acceptance.


## Persistent categories after the first clean restart

| Category/path | Mutation / purpose | Reboot evidence |
|---|---|---|
| /etc/synoinfo.conf | modified; first-user/configured flags | yes; fresh boot diagnostic and bootstrap agree |
| /etc/passwd, group, shadow | modified; local account and administrator membership | yes; account/membership observed and normal login succeeds; no secret contents exported |
| /etc/TZ and database timezone setting | modified through Region UI | yes; GMT0 persists and PostgreSQL reads GMT after restart |
| /etc/hostname and network state | wizard name, normal DHCP configuration | name persists; eth0 DHCP/management work; later hostname change was rejected |
| /etc.defaults/rc.first_login_after_upgrade | created; stock first-login bookkeeping | restart persistence and full behavior not independently verified |
| /var/packages/StorageManager and systemd package unit | created; official package activation | package/volume service survive boot; no assertion that all systemd units are healthy |
| /var/services/pgsql -> /volume1/@database/pgsql | created; persistent database path | yes; symlink persists and PostgreSQL reopens existing state |
| /var/lib/space, /etc/space and /usr/syno/etc/volume.conf | created/modified; storage metadata | yes; same Basic/Btrfs volume remounts and reports normal |
| /usr/syno/etc task/preferences state | modified; local diagnostic task and preferences | enabled boot task runs again; arbitrary preferences not exhaustively checked |
| /var/log | created/modified; boot/runtime diagnostics | new boot logs observed; rotation and arbitrary old log retention are not guaranteed |
| /volume1 test data | created; actual user data filesystem | yes; SHA256, inode and size unchanged after clean restart |

This is a semantic persistence report, not an immutable root checksum. Runtime
logs, database files and configuration continue changing by design.


## Second clean stop and sparse allocation

Clean stop 2 completed at 2026-10-13T10:16:59.365437Z, again with filesystem
unmount, guest-shutdown, QEMU/container exit 0 and no timeout fallback.
The second restart is a production cache reuse of the same disk/generation.
A post-setup backing-file stat reported 17,179,869,184 virtual bytes and
1,355,657,216 allocated bytes. The 16 GiB virtual disk is sparse, not fully
preallocated; allocation changes with ordinary DSM writes.

The 2 GiB construction minimum preserves the proven p1 region. It is not a
data-volume acceptance minimum. Only 16 GiB has completed the demonstrated
Basic/Btrfs creation; no claim is made about smaller data-capable capacities or
automatically using every trailing byte. Growth is file-length extension only.


## Two clean persistence cycles

The second restart (launch generation 5) produced a fresh diagnostic at
2026-10-13T10:35:52Z. It again verified the identical generation pointer,
test-file SHA256/inode/size, GMT0 timezone, local administrator membership,
normal writable/noncrashed volume, and PostgreSQL active(exited). Stock
pgsql.sh confirmed readiness at 10:35:35Z. Bootstrap again reported configured
and dsm_upgrade_all_done true, dsm_upgrade_pgsql_status active.

Both clean stops were DSM UI shutdowns, both returned QEMU/container exit 0
and guest-shutdown, and both following starts reused the runtime generation.
No PAT extraction, p1/root rebuild or automatic partition recreation occurred.
These are two clean stop/start cycles, excluding the earlier old-UART panic
experiments and host interruption. The controlled unclean experiment is gated
on these successful cycles and uses one ordinary container-requested timeout
fallback only. It cannot trigger a second crash because of an exclusive
one-time marker. Recovery succeeded as recorded below.


## Single controlled unclean stop

After both clean cycles succeeded, docker stop -t 120 exercised the production
ARM timeout (default 105 seconds) once. ARM has no guest shutdown agent, so
this stop reached the retained SIGTERM fallback. QMP reported guest=false,
reason=host-signal; QEMU returned 0. The manifest correctly recorded clean=false,
container_requested=true and outcome=container-timeout-fallback at
2026-10-13T10:38:03.540230Z. A host-triggered QEMU exit is never evidence of
a guest filesystem unmount. No SIGKILL or second controlled crash was issued.

Production restart reused the same configured image with launch generation 6,
without restoring hda1.tgz or using the original seed hash as an expected disk
value. Recovery succeeded; the final management and strict stability results
are recorded below.

The controlled recovery boot explicitly logged EXT4-fs (sata1p1): recovery
complete before mounting the existing root. The junior also logged Partition
layout is not DiskStation style. Skip checking rootfs and ForceNewestLayout:
Skipped. This reinforces that the demonstrated virtual layout is not canonical
physical DiskStation geometry. Ordinary ext4 journal recovery occurred without
our installer recreating p1.


## Recovery acceptance

Launch generation 6 after the one controlled timeout fallback produced fresh
guest evidence at 2026-10-13T10:55:30Z. The existing Basic/Btrfs /volume1
remounted writable, volume status was normal, crashed=false/readonly=false.
The file still had SHA256
85c85894c2c5e1168f2c046c3d23dbc9dddd57fd8d6ef0e8c7f37c49d62b7e31,
inode 464 and size 90. GMT0 and the local account/membership persisted.
Bootstrap returned configured=true, dsm_upgrade_all_done=true and PostgreSQL
active. Stock pgsql.sh completed at 10:55:53Z.

PostgreSQL itself logged that its previous shutdown was unclean, performed
automatic WAL redo, then became ready to accept connections. No separate
database repair/reverse engineering or fake configured marker was needed.
The early task sampled pgsql-adapter activating; subsequent stock readiness
logs and current bootstrap establish completion. The offline manifest correctly
retained the last_exit clean=false fallback receipt throughout this boot.
This observation is one recovery demonstration, not a claim of arbitrary crash
resilience or exhaustive database transaction durability.


## Final management and stability acceptance

The final recovery boot completed 30/30 management HTTP GETs with status 200
and nginx responses; HTTPS also returned 200 (the local self-signed certificate
was not verified). Loopback-only forwarding and the production QEMU arguments
were verified. The strict production-arm-management.py helper nevertheless
returned exit 1: its cumulative serial check found one watchdog soft lockup
on the second clean restart, rather than silently ignoring an earlier boot.

The warning reports CPU 0 stuck for 23 seconds in systemd-modules:2822, at
__memcpy, with a load_module -> sysfs/kernfs -> kstrdup_const call stack.
It is duplicated by early console output, not evidence of two separate events.
The affected boot subsequently completed and the final recovery boot has no
such warning. Its cause is unresolved; TCG scheduling is not a proven cause.
No scemd soft-lockup stack, queued_write_lock_slowpath, kernel NULL-pointer
fault or kernel oops appears in this final acceptance log. Stock scemd still
experiences controller timeout/restart behavior, and selfcheck_bootHealth.service plus synoindex-checkpackage.service remain
failed in the guest diagnostic evidence; this is not a claim
that every DSM service or hardware monitor is healthy.

Evidence: ignored final-management/management-requests.json, https-result.json,
arm-process.json and arm-serial.log; clean1-verified, clean2-verified and
crash-recovery-verified/acceptance.json. No second controlled crash or altered
watchdog acceptance criterion was used to seek a passing result.

Highest demonstrated classification: **F4**. Official setup, persistent
configuration and a DSM-created data volume survive two clean restart cycles
and one controlled timeout recovery. The DC ZVA TCG mitigation graduated as
QEMU patch 0004 (watchdog **L4**). Management HTTP cold-boot readiness under
production 0004 answers in ~7–8 minutes; earlier diagnostic 0/5 scores were
observe-budget artefacts. Strict F5 remains incomplete pending a working
disposable administrator session for stock UI shutdown. See
`phase3-http-readiness.md`.


## 2026-10-15 Auth 499 classification

The controlled DS124 DSM 7.2.2-72806 reproduction classifies **OTHER**:
DSM login services were not ready. At `2026-10-15T03:19:54.108315Z`, the single
POST login attempt returned API 499 while HTTP/HTTPS returned 200 and
`configured=true`; PostgreSQL was still inactive. The shipped login frontend
maps 499 to `error_system_not_ready`, separately from 400/401/407/408.
Stock systemd logs reached `syno-login.target` (Web console login available)
at `03:20:26Z`; PostgreSQL became ready at `03:21:55Z`. There was no new PAM
authentication entry for that premature attempt. This is independent of HTTP
readiness and is not evidence that QEMU or networking regressed.

`phase3local` exists, is AUTH_LOCAL, Expired=false, has no shadow lock prefix,
and belongs to administrators. The retained old secret does not match its
stored hash; that separate drift does not explain the observed 499. The
AutoBlockIP table was empty. Installed `synoautoblock --help` confirms a
`--deny ip` check; it returned rc=0 (not denied) for the slirp peer 10.0.2.2.
No auto-block reset or global security change was performed.

On a fresh disposable copy, the established stock-initramfs `rdinit=/bin/sh`
maintenance path mounted p1 and ran exact installed `synouser`, `synogroup`,
and `synoautoblock` help. Temporary proc/sys/dev mounts, tmpfs `/run`, and
`/run/synosdk/lock` allowed stock user/group database rebuild and queries.
`phase3f51015` was created with `synouser --add`; a fresh random secret was set
with `synouser --filesetpw` using its private file input, removed immediately.
No direct passwd/shadow/group edits were made. `synogroup --memberadd`
returned 1, but both `synouser --get` and `synogroup --get administrators`
confirmed actual membership. The user is AUTH_LOCAL and Expired=false;
its fresh secret matches the stored hash. The password is kept only at
`research/arm64/work/phase3-f5/temp-admin-password.txt` (0600, ignored);
contents, hashes, sessions, and payloads are excluded from evidence.

The maintenance root was fully unmounted before guest poweroff. Kernel and
initrd SHA256 remain the official values. A separate copy booted through
the unchanged production entrypoint for normal-login validation: HTTP/HTTPS
200, configured=true and PostgreSQL active at `2026-10-15T03:45:51Z`
(572.4 host seconds); stock login target reached at `03:44:10Z`. Windows
localhost access also returned HTTP 200. Its complete current serial log has
zero soft/hard lockup, watchdog BUG, RCU stall, Oops, kernel BUG, panic, NULL
pointer and queued_write_lock_slowpath matches. This boot is not strict Boot 1.
The stopped prepared copy's persistence marker was read without mounting the
volume, using read-only btrfs restore of subvolume 256; SHA256 equals the
required `85c85894c2c5e1168f2c046c3d23dbc9dddd57fd8d6ef0e8c7f37c49d62b7e31`.
The protected
configured source `/var/lib/vdsm-phase3/phase3-acceptance-ready` has SHA256
`60f97e39a884356677a1ed27d65112c2045d9b27841c4aeb8a7ab0dd7603db42`
and was only read; the post-work source hash matches the pre-work value.
At that diagnostic checkpoint, strict Boot 1–3 had not started: successful normal browser
login, two user UI shutdowns, and all persistence/stability gates remain
required. The temporary account and secret remain because F5 has not passed.

The subsequent browser connection refusal was a host-lifecycle interruption:
WSL systemd stopped Docker at `2026-10-15T03:48:50Z`, and the normal-login
container was later reported exited (255), leaving port 15840 without a
listener. This is separate from Auth 499 and is not a demonstrated DSM or
networking regression. The same disposable login-validation copy was restarted
at `03:55:09Z` with the unchanged production image; a hidden Windows-owned
`sleep infinity` WSL process keeps the distro session alive during manual
validation. This interrupted copy is excluded from strict F5. The clean
account-prepared copy remains available for a fresh acceptance clone.
Recovery reached HTTP/HTTPS 200, configured=true and PostgreSQL active at
`2026-10-15T04:04:22Z` (553.8 host seconds); the stock login target was
available at `04:02:40Z`. Windows localhost returned 200 again. Full recovery
boot logs contain zero matches for the stability fault signatures above.
At that recovery checkpoint, normal user login was unconfirmed and strict F5 had not started.
Evidence: `browser-refused-cause.json`, `wsl-docker-previous-boot.log`, and
`account-normal-interrupted.log` in the ignored evidence directory.

Private evidence is under ignored `research/arm64/work/phase3-f5/`:
`auth-classification.json`, `controlled-auth-result.json`,
`live-auth-evidence.json`, `auth-services-static.json`,
`account-offline-verified.json`, and complete diagnostic serial logs.
The production QEMU SHA256 is
`a6d76b56ec166c8df897387cbc708fffbfd9d1600dc9a0700cb7226671ecbfda`;
8.2.2 includes production 0001–0004 and both DC-ZVA invalidation symbols.
All four requested shellcheck/smoke/patch-apply/diff checks returned 0.

## 2026-10-15 Strict F5 attempt after successful local login

The user confirmed a successful normal DSM browser login for `phase3f51015`;
the confirmation was recorded at `2026-10-15T04:26:23.8187658Z`. The login evidence
contains only success, timestamp and username. No session or authentication
payload was retained.

A fresh strict candidate was copied from the stopped account-prepared clone.
Read-only e2fsck found quota accounting discrepancies without inode, directory
or reference-count errors. Standard e2fsck corrected quotas only on the new
disposable candidate; a subsequent full read-only check returned 0. The
protected source and account-prepared copy were not modified. Read-only Btrfs
restore found the required marker SHA256, PostgreSQL `PG_VERSION` and an
8192-byte `global/pg_control`. Offline root metadata confirms configured state,
the enabled temporary administrator and administrator membership.

Strict Boot 1 started at `2026-10-15T04:30:06Z` using the production entrypoint,
production image containing 0001–0004, `DSM_PLATFORM=rtd1619b`, TCG multi and
2 vCPU. The separate strict clone and complete evidence are recorded under
ignored `research/arm64/work/phase3-f5/`. A disabled stock Task Scheduler task
is manually invoked to measure guest uptime, service/process state, mounted
writable volume and marker SHA. It has no enabled schedule or boot trigger.
Boot 1 first returned HTTP 200 at 401.247 host seconds and PostgreSQL active
at 562.833 host seconds. After scemd also reached systemd active, the strict
observation baseline was guest uptime 708.40 seconds (guest UTC 04:42:00Z).
Earlier provisional samples with scemd activating are retained and excluded
from the observation duration. Required fault scans still cover the complete
boot log without signature exemptions.
Both acceptance shutdowns must still be performed by the user in DSM UI.
No strict acceptance promotion is implied by these preparatory checks.

Boot 1 passed its active gates at `2026-10-15T05:13:30Z`: 1877.97 guest
seconds after the full-service baseline, 30 sequential HTTP GET responses
all 200, HTTPS 200, PostgreSQL and scemd active, volume1 normal and writable
with actual write probes, and the exact required marker SHA256 unchanged.
The complete 437413-byte boot/observation log had zero soft/hard lockup,
watchdog BUG, RCU stall, Oops, kernel BUG, panic, NULL pointer and
queued_write_lock_slowpath matches. Private evidence includes
`boot1-pre-shutdown-gates.json`, `boot1-guest-probes.jsonl`, `boot1-http-30.json`
and `boot1-complete.log`. At that checkpoint UI shutdown #1 was required;
neither clean shutdown had been counted and Boot 2/3 had not started. The temporary account and
password file remain because strict F5 has not completed.


### Strict F5 shutdown #1 and Boot 2 restart evidence

The user confirmed DSM UI shutdown #1. At 2026-10-15T06:14:46Z the
production lifecycle receipt recorded guest=true, reason=guest-shutdown,
clean=true, container_requested=false, outcome=guest-poweroff and QEMU rc=0;
the container exited 0. Complete Boot 1 logs include systemd shutdown,
All filesystems unmounted and reboot: Power down, with zero complete-log
stability signature matches. The verifier initially misclassified guest
systemd PID 1's cleanup SIGKILL messages as host fallback; source attribution
was corrected in the ignored verifier, with all matching lines retained in
shutdown1-signal-provenance.json. No production code or fault scan changed.
A stopped-clone read-only Btrfs restore confirmed the expected marker SHA256
in after-shutdown1-persistence.json. Boot 2 restarted the same strict clone
and production container at 2026-10-15T06:16:54Z; full readiness and the second
UI shutdown remain pending at this checkpoint. The temporary account and
password file remain until all strict gates pass.


Boot 2 passed its active gates at 2026-10-15T06:27:04Z. First HTTP 200
was measured at 407.629 host seconds; HTTP/HTTPS 200, configured=true and
PostgreSQL active were measured together at 537.703 host seconds. Stock
manual probes verified scemd active, PostgreSQL processes/data, volume1
normal, unlocked and writable, administrator membership, and the unchanged
persistence marker SHA256. The same disk inode and artifact generation were
retained, the launch generation incremented once, and the production binary
and 0001–0004 identities matched. The complete 242024-byte Boot 2 log had zero
stability fault signatures. Evidence: boot2-pre-shutdown-gates.json,
boot2-guest-probes.jsonl, boot2-production-identity.json and boot2-complete.log.
At this checkpoint, user DSM UI shutdown #2 and Boot 3 remain required.


### Strict F5 shutdown #2 and Boot 3 restart evidence

The user confirmed normal DSM UI shutdown #2. At 2026-10-15T06:45:50Z
the production receipt recorded clean guest-shutdown / guest-poweroff,
QEMU rc=0, container_requested=false; the container also exited 0. Full logs
show systemd shutdown, all filesystems unmounted and reboot: Power down,
with no host fallback. Complete Boot 2 logs (362727 bytes) contain zero
stability fault signatures. Read-only stopped-clone marker extraction again
matched the expected SHA256. Evidence: shutdown2-receipt.json,
shutdown2-manifest.json, shutdown2-qmp-live.log and
after-shutdown2-persistence.json. Boot 3 restarted the same strict clone at
2026-10-15T06:46:17Z. Full readiness and at least 1800 guest seconds of
observation remain pending at this checkpoint; cleanup is not yet authorized.


### Strict F5 completed acceptance evidence — 2026-10-15

The complete three-boot sequence passed on the same disposable configured
clone, with both shutdowns initiated by the user through DSM UI. Boot 1/3
observations started only after PostgreSQL and scemd were active and volume1
was mounted, healthy and writable. Guest durations use /proc/uptime.

| Boot | First HTTP 200 (host s) | HTTP/HTTPS/configured/pgsql ready (host s) | HTTPS | configured | PostgreSQL / scemd | volume1 | Observation (guest s) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 401.247 | 562.833 | 200 | true | active | normal / writable | 1877.97 |
| 2 | 407.629 | 537.703 | 200 | true | active | normal / writable | 31.40 |
| 3 | 391.015 | 533.529 | 200 | true | active | normal / writable | 1869.03 |

Boot 1 and Boot 3 each passed 30 sequential HTTP GETs (30/30 HTTP 200)
and HTTPS 200. Every complete boot log, including shutdowns #1/#2, had zero
soft/hard lockup, watchdog BUG, RCU stall, Oops, kernel BUG, panic, NULL pointer
and queued_write_lock_slowpath matches; no signatures were exempted.

Both shutdowns recorded systemd shutdown, All filesystems unmounted,
reboot: Power down, QMP guest-shutdown, QEMU/container rc=0 and no host
fallback or QEMU SIGKILL. Production guest-poweroff timestamps were
2026-10-15T06:14:46Z and 2026-10-15T06:45:50Z.

The marker SHA256 before Boot 1, after restart #1, after restart #2 and
final Boot 3 was unchanged:

`85c85894c2c5e1168f2c046c3d23dbc9dddd57fd8d6ef0e8c7f37c49d62b7e31`

All boots used production QEMU 8.2.2 (v8.2.2-dirty), SHA256
`a6d76b56ec166c8df897387cbc708fffbfd9d1600dc9a0700cb7226671ecbfda`,
with the exact 0001–0004 series, TCG multi, 2 vCPU, normal rdinit=/init and
900-second HEALTHCHECK start-period. Cache hits and unchanged immutable
artifacts/generation pointer confirmed no PAT extraction or reconstruction.
Launch generations were 10, 11 and 12. Inode capture began after Boot 1
while stopped (before Boot 2); that inode was retained through Boot 3.
Boot 1 continuity is established by the unchanged container bind mount, disk
path, generation, manifests and marker; no Boot 1 start inode was invented.
The protected source was rehashed read-only and remained unchanged.

After strict acceptance, stock synouser --del removed phase3f51015 from the
acceptance clone and running diagnostic copy. Stock user enumeration/get,
id and synogroup --get administrators verified account and membership removal.
PostgreSQL/scemd and the marker remained valid after removal. A 423-file
source/evidence scan found no plaintext secret outside its designated file;
three random overwrites, a zero overwrite, fsync and unlink removed that file,
with Windows and WSL absence checks passing. The disabled manual cleanup task
remains on each disposable running clone: task deletion after user removal
was denied (code 105 captured on the strict clone). It contains no password
and has no scheduled or boot execution. Offline preparation copies remain
research snapshots, outside the accepted running clone.

Private evidence: strict-f5-pass-before-cleanup.json,
final-protected-source-verification.json, temporary-admin-cleanup.json,
final-secret-evidence-scan.json and strict-f5-final.json under the ignored
work/phase3-f5 directory. No production file changed during this acceptance
continuation; the validated production image was reused.

#### Production Integration Phase 4 validation entry

| Workstream | Required evidence / next action | Available boundary |
| --- | --- | --- |
| Native ARM64 KVM | ARM64 host, accessible /dev/kvm, actual -accel kvm / -cpu host, official-PAT readiness and lifecycle/stability evidence | Local inventory is x86_64; ARM64 KVM remains unverified |
| Lifecycle hardening | Evaluate the existing TD-001 shutdown-agent gap; preserve guest-shutdown and rc=0 receipt semantics; keep UI shutdown as proven baseline | Two real UI shutdowns are recorded; Docker stop is not accepted as a replacement |
| Multi-arch builds | Native amd64/arm64 build jobs, per-architecture patched QEMU identity and smoke checks, manifest platform verification | This run verified an amd64 production image; arm64 build needs its native runner |
| Release readiness | CI six-job gate, protected-source/secret checks, documentation and experimental ARM boundaries | No push, publication or release was performed |

Phase 4 begins with target-environment validation; these remaining hardware
and release requirements are not inferred from TCG acceptance.

## Final cleanup and validation

After recovery acceptance, the temporary Phase3Persistence boot diagnostic
task was disabled and saved through the stock Task Scheduler UI. Evidence:
ignored task-disabled.png. The final DSM UI shutdown again unmounted all
filesystems, reached kernel Power down and returned QEMU/container exit 0.
At 2026-10-13T11:23:21.686815Z the manifest recorded guest-shutdown,
clean=true, launch_pending=false and guest-poweroff, without host fallback.
This final stop is cleanup, not a third stop/start persistence cycle. The
configured disposable disk is retained stopped under /var/lib/vdsm-phase3/fresh.
Temporary credential and authentication-response files were deleted; the
password was absent from 454 source/evidence files in the final audit.
Temporary browser tabs were closed and the viewport override was reset.

All source regressions passed: shellcheck over production/platform/research/
test scripts; research smoke; platform and PAT acquisition tests; original
x86 installer byte-hash regression; synthetic ARM runtime/installer/image
validation tests; proprietary-artifact policy; production x86 argument capture;
and git diff --check with repository line-ending settings. QEMU 8.2.2 patch
clean application and the patched production binary build/run also passed.
The x86 results cover installer preservation and production command regression,
not a separate official-PAT x86 guest boot.

The official-PAT disposable production integration demonstrated F4 with the
strict management/stability helper failing as explained above. The running
acceptance container used the previously built Phase 3 image with the current
prepare-arm-artifacts.py and validate-arm-image.py copied into its production
/run/platform directory; its QEMU binary and platform launcher already matched.
The final image was rebuilt and synthetic regression used the current source.
All guest experiments used the production entrypoint, never research launchers.
