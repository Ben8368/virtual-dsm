# Phase 3 management HTTP readiness

Historical HTTP-readiness checkpoint: **Watchdog L4 / Phase 3 F4**.
This note predates strict acceptance; see [current state](../../CONTEXT.md) and
[the later strict F5 evidence](production-phase3.md#strict-f5-completed-acceptance-evidence--2026-10-15).
Patch 0004 stays promoted.
HTTP readiness is an independent observe-budget issue, not a reason to revert
0004.

## Docker environment

WSL user `xiaoluo` was not in group `docker` (`root:docker` socket mode 0660).
Fixed with `wsl -u root usermod -aG docker xiaoluo` and `wsl --shutdown`.
Subsequent agent sessions use Docker directly without `sudo docker`.

## Production QEMU

Image tags `virtual-dsm:phase3-http-0004` / `virtual-dsm:phase3-acceptance`
rebuild applied production patches 0001–0004. Binary
`/usr/local/bin/qemu-system-aarch64` reports `8.2.2 (v8.2.2-dirty)` and
contains `tb_invalidate_phys_page_dcz` / `tlb_invalidate_code_dcz`.
SHA256 `a6d76b56ec166c8df897387cbc708fffbfd9d1600dc9a0700cb7226671ecbfda`.

## HTTP failure layer

**READINESS_PROBE** for the earlier DCZ five-run 0/5 result (~550 s observe).
Not GUEST_NETWORK, DSM_WEB_SERVICE, QEMU_HOSTFWD, or CONTAINER_NETWORK once
observation covers cold-boot bring-up.

## Boot timeline (representative isolate)

| Event | Host elapsed |
|-------|-------------:|
| QEMU argv captured | ~19 s |
| eth0 register (guest) | ~162.5 s guest |
| first HTTP/HTTPS 200 (host + container hostfwd) | ~470.2 s |

Three Stage-22 cold boots: first HTTP 200 at 438–460 s; HTTPS 200;
`configured=true`; zero soft lockup / oops / panic.

## Guest-local management

No guest shell on the production entrypoint. Container
`curl http://127.0.0.1:5000/` (QEMU hostfwd) succeeds with the host publish
path. Direct container→`10.0.2.15:5000` times out and is unsupported.

## Hostfwd management

HTTP 200 and HTTPS 200 on Docker-published loopback ports.

## Root cause

Cold-boot management HTTP under amd64→ARM TCG multi typically answers after
~7–8 minutes. Diagnostic five-runs stopped near 550 s and scored 0/5 even
though the same networking stack later serves nginx 200.

## Production fix

`Dockerfile` HEALTHCHECK `start-period` increased **45s → 900s** so ARM TCG
bring-up is not marked unhealthy for the entire readiness window. No change to
USB CDC Ethernet, hostfwd formula, or x86 paths beyond the shared healthcheck
grace period.

## Watchdog regression

Isolate + three cold boots: **zero** soft lockup / hard lockup / RCU stall /
Oops / panic with production 0004.

## Three cold boots

| Boot | HTTP ready s | HTTPS | configured | stability |
|-----:|-------------:|:-----:|:----------:|:---------:|
| 1 | 453.1 | 200 | true | clean |
| 2 | 437.7 | 200 | true | clean |
| 3 | 460.0 | 200 | true | clean |

## F5 acceptance

Auth 499 was later classified as DSM login services not ready; the old
secret also had independent drift. See the [controlled reproduction and stock
account rotation](production-phase3.md#2026-10-15-auth-499-classification).
Normal browser login must succeed before strict F5 begins; two user UI
shutdowns remain required. Temporary account cleanup follows successful F5.

## Historical classification

```text
Watchdog: L4
Phase 3: F4
```

## Next task at this checkpoint

Restore or rotate a disposable administrator credential for the configured
clone, complete strict F5 (two QMP-confirmed guest-shutdown cycles + 30/30
HTTP with ≥30 minute observation), then Production Integration Phase 4.
