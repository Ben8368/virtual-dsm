# ARM64 DSM host management experiment

This uses the stock DS124 kernel/initramfs and the proven disposable USB
network root on research QEMU v8.2.2. The forwarding interface accepts only
HOST_PORT:GUEST_PORT pairs and always binds 127.0.0.1. With no option it
retains the previous unforwarded network experiment. Invalid ports, duplicate
host ports, explicit addresses and injected QEMU options are rejected.

## Reproduction

Stop the research QEMU before refreshing the existing disposable observers:

```sh
sudo bash research/arm64/prepare-management-observer.sh
sudo python3 research/arm64/boot-usb-network.py network --disable-ncq \
  --mac 00:16:3e:12:34:56 --label host-management --seconds 1800 \
  --snapshots 24 --host-forward 15000:5000 --host-forward 15001:5001
```

The exact v8.2.2 netdev argument is:

```text
user,id=net0,hostfwd=tcp:127.0.0.1:15000-10.0.2.15:5000,hostfwd=tcp:127.0.0.1:15001-10.0.2.15:5001
```

Check the actual listener with ss -lntp before HTTP. On Windows/WSL also check
netstat -ano -p tcp and the associated wslrelay process. Do not create wildcard
listeners or external forwarding. Ports 80/443 are not forwarded.

The management observer records counters and active management socket inodes,
and periodically captures IP configuration, running/failed units, nginx socket
file descriptors, actual backend processes and recent kernel messages. It
changes no guest configuration; its logs stay under /var/log on the disposable
disk. The existing network observer launches it when installed. After QEMU
exits, the launcher captures both observer logs using a read-only ext4 mount
with noload, without replaying the guest journal.

## Evidence

Full headers, bodies, verbose curl logs, listener ownership, guest snapshots,
and the command/result JSON remain gitignored under research/arm64/work/.
Only concise observations belong in tracked documentation. No account, setup,
installation, disk layout, external access or production changes are part of
this experiment.

## Measured result (2026-10-12)

Classification: **W5**, limited to host management transport and unauthenticated
page/bootstrap access during this bounded run. Complete DSM application health
and authenticated management remain unproved; no login or setup was attempted.

Linux ss associated both loopback listeners with QEMU PID 671 (fd 11 for 15000,
fd 10 for 15001). Windows netstat showed the same loopback addresses owned by
wslrelay PID 42628. Both Windows curl and Linux curl reached DSM. The launch
used explicit guest address 10.0.2.15, without forwarding guest ports 80/443.

The initial successful HTTP GET / returned **200**, Server nginx, Content-Type
text/html; charset="UTF-8", and no Location header. Title: SynologyNAS -
Synology NAS. /webman/ returned **301** with Location
http://127.0.0.1:15000/; only after saving that response was curl -L used,
which reached the same 200 root page. The actual entrypoint is /.

Page state: **LOGIN**. The returned entry bundle invokes
SYNO.SDS.LoginInitUtils.initLoginInstance(). The page-referenced
SYNO.Core.Desktop.SessionData getjs endpoint returned HTTP 200 JavaScript and
isLogined: false. The referenced Desktop.Defs getjs endpoint also returned
HTTP 200 JavaScript. These read-only bootstrap checks establish live synoscgi
responses, not only a static nginx placeholder. The session data also reports
configured: false, dsm_upgrade_all_done: false, and
dsm_upgrade_pgsql_status: "failed". These are application health limitations;
no initialization was performed to change them.

HTTPS / on 15001 returned **200** after TLS 1.3 negotiation
(TLS_AES_256_GCM_SHA384). Certificate subject metadata: C=TW, L=Taipei,
O=Synology Inc., CN=synology. The research curl used -k; certificate trust
was not claimed. No redirect was returned. Windows HTTPS also returned 200.
No certificate/key material is included in tracked evidence.

Guest confirmation includes established /proc/net/tcp entries with local
0F02000A:1388 (10.0.2.15:5000) and slirp peer 10.0.2.2. Guest netstat maps
5000/5001 listeners to nginx master PID 5640. nginx and synoscgi are active
running; synoscgi workers are present. Access logging is disabled in the
installed nginx configuration, so no access-log entry is claimed.

The repeat observation returned 200 for **20/20** Windows requests spaced
three seconds apart and **10/10** additional low-rate keepalive requests on
one WSL host connection. There were no TCP/curl or HTTP failures in these
series. The recorded before/after counters were RX errors/frame **6 -> 6**,
TX errors **0 -> 0**, and drops **0 -> 0**. During the longer observation
after those request series, RX/frame errors increased to **8** before QEMU
was stopped (extended observation: **6 -> 8**); TX errors and drops remained
zero. This growth is a remaining network reliability limitation. An extra RX/frame error accumulated
before that repeated-request window (the earlier snapshot had 5); the interface
is not asserted to be error-free. Readiness probes before nginx startup timed
out/reset; they are recorded separately from the post-readiness series. A
single intentionally incomplete request used for socket observation was closed
by nginx without a response and is not a successful GET in either series.

The LED NULL-pointer oops occurred at guest uptime 217.82 s in
ledtrig_syno_disk_led_on; it was **nonfatal to observed management access**.
The missing dev-mtd0.device timed out, with MTD/burn-in dependencies failing,
but it did not block the root page or the two checked bootstrap endpoints.
Observed failed units include SynoSwInitLed, selfcheck_bootHealth,
synoindex-checkpackage, and pgsql-adapter. Their failures did not block these
requests, though PostgreSQL-dependent functionality remains unproved.

**A kernel fault did occur during the initial W5 observation:** watchdog soft
lockups in scemd, first at uptime 700.38 s, with queued_write_lock_slowpath
through ds124_synobios/synobios_ioctl. Further reports at 728.38 s and 760.38 s
showed this was persistent through uptime 968.38 s while HTTP still returned
200. Diagnosis later proved the earlier LED NULL oops abandoned `LedSetLock`
during `SYNOIO_SET_DISK_LED`; see the soft-lockup section in
[arm64-development.md](../../docs/arm64-development.md).

### Soft-lockup fix verification (post register-bit-led OF shim)

Reproduction after
`qemu/0002-arm-virt-add-research-syno-leds.patch` (syscon + register-bit-led +
`internal_slot@1`): no `can't get class`, no `ledtrig_syno_disk_led_on` NULL
oops, and no `scemd` soft lockup through guest uptime past 980 s (beyond the
prior 700 s first-hit). A spaced **30/30** HTTP GET / on 127.0.0.1:15000
returned 200. SynoSwInitLed may still fail for unrelated microP/ttyS1 reasons;
that path is out of scope unless it reintroduces LedSetLock abandonment.

## Evidence files and validation

Ignored work contains host-http-5000.{headers,body,curl.log},
host-https-5001.{headers,body,curl.log}, Windows equivalents,
host-webman* evidence, the two bootstrap API bodies/headers,
host-stability-results.json, host-keepalive-results.json,
host-management-listeners-linux.txt, host-management-netstat-windows.txt,
and host-management-{command,result}.json. The guest-management and network
observer logs retain IP/route, failed/running units, listeners and processes.
The before/after-stability logs bound the counter comparison. The serial log
retains the LED oops, MTD failure and later scemd watchdog reports.

Required validation: bash research/arm64/tests/smoke.sh; shellcheck -x over
research/arm64/*.sh and research/arm64/tests/*.sh; git diff --check.
The smoke test checks accepted loopback forwards and rejects wildcard-address
inputs, option injection, invalid port ranges and duplicate host ports.
The observer refresh refuses a disk held open by running QEMU.

The next highest-value task is production integration planning for the proven
ARM64 research platform (research QEMU LED/syscon OF contract and existing
UART/SATA/XHCI/CDC path) without expanding into unrelated DSM setup work.

The bounded run ended at 1048.19 seconds with an explicit harness stop,
QEMU exit 0, and successful read-only guest-log capture. No QEMU process,
15000/15001 listener, or loop device attached to the research disk remains.
