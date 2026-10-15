# ARM64 DSM DC ZVA watchdog results

Historical watchdog investigation record. Its L4/F4 and pending-task statements
below describe that checkpoint; later strict acceptance is recorded in
[production-phase3.md](../production-phase3.md), and current state belongs only
to [CONTEXT.md](../../../CONTEXT.md). Diagnostic patches, test harnesses and
raw evidence referenced here remain local research material.

Investigation date: 2026-10-14. Classification: **L4 / F4**. Guest watchdog
settings have not changed. Strict F5 remains blocked by management HTTP
readiness, not by the DC ZVA mitigation gates.

## CODE protection correlation

CODE_PROTECTION_CONFIRMED for the repeated-NOTDIRTY mechanism. In the first
stock-initrd production counter run, a complete 64/64 sequence had V/C/M=1/0/1,
129 translated TBs initially, and retained CODE clean plus NOTDIRTY for the first
63 operations. The final operation removed the last TB and unprotected code.
All complete 64-miss sequences in that run had V/C/M=1/0/1 at every miss.
This result does not alone establish watchdog causality; it proves the
pathological TLB_NOTDIRTY loop is code-protection driven.

## Pathological page timeline

Representative first-run CPU0 sequence: RAM page 0x02d2b000, GPA 0x42d2b000,
guest VA 0xffffff8002d2b000. locks=128, lock_scan=range_scan=12658, retries=128,
unprotect=1, current_tb=0, elapsed_ns=703395. The raw timeline is retained under
the ignored code-protection-stock-20261014/run-01/serial.log evidence directory.

## TB invalidation cost

The representative sequence took 703395 ns (0.703395 ms), with 128 calls to
range_fast, 128 page-collection invocations, 12658 nodes visited in collection
locking and another 12658 nodes in range scanning. 129 TBs were invalidated and
unprotect ran once. Retries=128 counts one initial pass per invocation, so there
were no additional collection retries in that sequence. AArch64 does not define
TARGET_HAS_PRECISE_SMC, and no current-TB precise-SMC handling was recorded.
This sub-millisecond sequence cannot by itself explain a 20-second warning; it
does explain why 64/64 pages amplify bookkeeping and can contribute under load.

## Deterministic reproduce

Cold boot of a disposable configured clone through /run/entry.sh, TCG multi,
2 vCPU, original kernel/initrd and the normal rdgz-check.service. Its shipped
script /usr/syno/lib/systemd/scripts/rd.gz.check.sh performs command
substitutions and pipelines that require fork/dup_mm/page-table allocation.
Historical cat pathname recovery was not attempted. The synthetic focused test
additionally deterministically creates TB coverage and a 64-ZVA page clear.

## Uninstrumented baseline

Clean upstream v8.2.2 plus the three hardware production patches (no DC ZVA
0004), compiled with production build options. Each repetition clones the same
stopped source image. Wall duration is the fixed observation interval. Host-
directed diagnostic stops are not clean guest shutdown evidence. All guests
reached login; no oops/panic. HTTP did not become ready within the window.

| Run | Wall s | CPU0 s | CPU1 s | rdgz-check service s | Watchdogs | Continues |
|---:|---:|---:|---:|---:|---:|:---:|
| 1 | 550.190 | 475.53 | 475.24 | 11.858187 | 0 | yes |
| 2 | 550.491 | 478.54 | 458.18 | 33.202448 | 0 | yes |
| 3 | 550.316 | 484.62 | 457.72 | 16.579140 | 0 | yes |
| 4 | 550.402 | 480.55 | 457.29 | 3.369045 | 1 | yes |
| 5 | 552.134 | 479.56 | 464.46 | 32.031432 | 0 | yes |

Service median 16.579140 s, worst 33.202448 s. One uninstrumented warning at
guest 180.489641 s in clear_page (CPU0, cat PID2885, 23 s).

## Candidate optimization

Graduated as `patches/qemu/8.2.2/0004-tcg-dczva-full-page-code-invalidate.patch`
from research `dcz-full-page-invalidation-candidate.patch`. After the two
original DC ZVA write probes succeed for normal RAM, a trapless lookup checks
NOTDIRTY and CODE clean. A locked full-page CPU-write helper invalidates only
TBs, retaining retaddr and the existing precise-SMC unwind. Then the ordinary
block probe reacquires its pointer and performs dirty/TLB bookkeeping. The
memory write remains exactly the advertised DC ZVA block. No dirty bit is
forced, no permission/watchpoint check is bypassed and the I/O byte fallback is
unchanged. Generic TCG behavior; no RTD1619B branding.

## NOTDIRTY distribution

Stock counter run (before), strict ascending 64-block RAM sequences:

| CPU | 0 | 1 | 2..63 | 64 |
|---:|---:|---:|---:|---:|
| 0 | 112291 | 53 | 88 | 21 |
| 1 | 107003 | 89 | 29 | 2 |

Candidate-counter final-evidence (after):

| CPU | 0 | 1 | 2..63 | 64 |
|---:|---:|---:|---:|---:|
| 0 | 250803 | 129 | 0 | 0 |
| 1 | 236228 | 198 | 0 | 0 |

The 64/64 category disappears. Remaining 1-miss pages are the expected first
slow-path hit. Focused tests that deliberately re-execute unaffected same-page
code between zeros can produce 2 misses after reprotection; that variation is
understood.

## Correctness

Both binaries passed exact block/surrounding-byte checks at 64 alignments;
affected code UDF rather than stale execution; unaffected same-page code;
current-TB same-page write with DSB/ISB; cross-page TB invalidation/retranslation;
MMU readonly/unmapped faults; MMIO readonly ID byte fallback; a block-last-byte
write watchpoint stopping before any RAM change; and 128 two-vCPU SMC handoffs
with concurrent execution on the invalidated page. Actual live migration dirty
tracking also passed: >=8MiB sent before the guest DC-ZVA-clears 16MiB, followed
by restoring another QEMU and byte-checking all 16MiB zero. i386-only
precise-SMC code paths are preserved by source/API structure, not claimed
dynamically tested on Arm.

## Performance

### Synthetic TB coverage (entire 64-ZVA clear)

| Initial TBs | Baseline median ms | Candidate median ms | Baseline worst ms | Candidate worst ms |
|---:|---:|---:|---:|---:|
| 1 | 0.046496 | 0.026400 | 0.059792 | 0.038000 |
| 8 | 0.063008 | 0.030096 | 0.083808 | 0.030992 |
| 64 | 0.270400 | 0.165184 | 0.328592 | 0.220912 |
| 256 | 0.958288 | 0.706096 | 1.090992 | 0.873600 |
| 512 | 2.243072 | 1.434384 | 2.770272 | 1.652880 |

### Production-derived five-run matrix

| Metric | Baseline (no 0004) | Candidate |
|---|---:|---:|
| Watchdogs | 1 | 0 |
| rdgz-check median s | 16.579 | 4.970 |
| rdgz-check worst s | 33.202 | 31.481 |
| HTTP ready | 0/5 | 0/5 |
| oops / panic | 0 / 0 | 0 / 0 |

Candidate per-run rdgz-check: 4.970, 2.641, 4.681, 22.049, 31.481 s. Long
tails remain under concurrent boot work and are not exclusive clear_page
timers; no soft-lockup string appeared in any candidate serial log.

## Production integration

Promoted to `patches/qemu/8.2.2/0004-tcg-dczva-full-page-code-invalidate.patch`.
`scripts/apply-qemu-patches.sh` verifies virt and TCG tracked files.
`tests/qemu-patches.sh` asserts the new symbols. Research counters remain
out of the production series. The five production-like candidate cold boots
satisfy the Stage 21 watchdog gate (0 warnings). Management HTTP readiness
did not pass in those windows, so Stage 22 HTTP and Stage 23 F5 remain open.

## F5 regression

Not run. No diagnostic SIGINT/container-stop is counted as guest shutdown.
Management HTTP readiness succeeds on production 0004 with a sufficient
observe window (~438–470 s to first 200). Strict F5 still requires two
QMP-confirmed guest UI shutdowns; Auth for the temporary administrator is
currently failing (API 499).

## Historical classification

**L4 / F4**: mechanism established and QEMU mitigation validated on the
production-derived fork/clear_page path with focused SMC/dirty/MTTCG gates.
**L5 / F5** not reached: management HTTP readiness and the strict Phase 3
acceptance sequence remain outstanding.

## Repository changes

Production 0004 patch; apply helper and qemu-patches test updates; research
README/results; research dcz-patches composition against graduated 0004;
historical candidate retained for 0001-0003 composition checks; counters and
focused SMC/dirty/watchpoint harnesses remain research-only. Raw DSM
artifacts, cloned disks, credentials and lengthy serial logs remain ignored.

## Tests

Passed previously and revalidated after promotion where local tools allow:
requested shellcheck set; research smoke.sh; git diff --check; production
qemu-patches.sh clean application; research dcz-patches.sh; focused
RAM/SMC/current-TB/cross-page/fault/MMIO/MTTCG/watchpoint tests; live migration
dirty test. Full Docker image rebuild and interactive sudo cold boots may
require host credentials beyond this session.

## Next task at this checkpoint

HTTP readiness isolation completed: five-run 0/5 was an observe-budget
issue; production 0004 image reaches HTTP ~7–8 minutes and Stage-22 three
cold boots passed (see `research/arm64/phase3-http-readiness.md`). Strict F5
remains blocked on disposable DSM Auth (API 499). Restore/rotate credentials,
finish F5, then Production Integration Phase 4.
