# Research-only DC ZVA code-protection experiment

Historical mechanism record; later acceptance is recorded in
[production-phase3.md](../production-phase3.md), with current state only in
[CONTEXT.md](../../../CONTEXT.md). Diagnostic patches and harnesses mentioned
below remain local research material. Generic correctness fixtures have since
been promoted to [tests/qemu-dcz](../../../tests/qemu-dcz/README.md).

Status at this checkpoint: CODE_PROTECTION_CONFIRMED for repeated NOTDIRTY. The conservative
full-page invalidation graduated to production
`patches/qemu/8.2.2/0004-tcg-dczva-full-page-code-invalidate.patch`. Research
counters remain out of the production series. Watchdog causality is mitigated
on the measured production path (L4); strict F5 remains gated on management
HTTP readiness.

## Source and API contracts

The exact source is QEMU v8.2.2, commit
11aa0b1ff115b86160c4d37e7c37e6a6b13b77ea. Apply the existing three production
hardware patches first. The counters patch and candidate patch both apply to
that base; the counters patch can also apply after the candidate.

`tb_invalidate_phys_range_fast` documents length <=8 and natural alignment.
Do not extend its size to 4096. `tb_invalidate_phys_page` and
`tb_invalidate_phys_range` pass retaddr=0 to the locked helper. They are not the
right CPU-write interface when preserving precise SMC semantics.

The candidate introduces `tb_invalidate_phys_page_dcz(addr, retaddr)` in
accel/tcg/tb-maint.c. It locks the page collection, including both physical pages
of intersecting cross-page TBs, and calls the existing
`tb_invalidate_phys_page_range__locked` with the original CPU helper retaddr.
PageDesc fields are read only while those locks are held. The existing helper
performs TB removal, hash removal, jump-cache clearing, jump unlinking, and
unprotects the page only after its TB list becomes empty.

## Semantic argument and limits

The two original DC ZVA write probes run first, including the original address
fault probe and the complete aligned block watchpoint probe. Full-page code
invalidation is considered only after they return a normal RAM host pointer.
The new check rejects invalid translations, MMIO and discarded writes and
requires NOTDIRTY with CODE clean. The locked helper additionally requires TBs
on that RAM page. It does not write RAM, alter guest page tables, force dirty
bits or retain a host pointer across invalidation. The normal block probe is
then repeated to reacquire a pointer and perform dirty/TLB bookkeeping before
`memset` of exactly the architectural block length. The I/O byte-store fallback
is unchanged. Migration/VGA marking remains in normal `notdirty_write`.

Invalidating extra TBs removes cached translations of unchanged bytes; a late
execution retranslates the same RAM. It cannot introduce a stale translation
or a memory write. Invalidation is allowed to be more conservative than the
actual write range. Cross-page TBs are removed from both page lists through the
existing API. MTTCG uses the existing page locks and TB invalidation machinery;
this argument still needs focused multi-vCPU tests, not just source inspection.

The locked helper retains TARGET_HAS_PRECISE_SMC processing: it looks up the
current TB with retaddr, restores CPU state when needed, releases collection
locks, sets single-instruction CF_NOIRQ flags and exits to reexecute. This
avoids losing precise SMC unwind as the retaddr=0 public page API would.
AArch64 in v8.2.2 does not define TARGET_HAS_PRECISE_SMC (i386 does). Its test
uses same-page execution followed by DSB/ISB; successful Arm testing does not
claim that the i386-only precise SMC branch was dynamically exercised.

Permissions and watchpoints must already have succeeded before conservative
invalidation. Any additional probe uses the same original retaddr. A guest fault
before those probes completes therefore performs no new full-page operation.
If precise SMC exits before the write, retrying the instruction must still pass
the original probes. The candidate is generic DC ZVA handling, with no DSM,
DS124, RTD1619B or guest-kernel address checks.

## Instrumentation

`dcz-code-protection-counters.patch` uses bounded per-vCPU records and never
prints per helper call. A sequence is exactly 64 ascending 64-byte operations
starting at offset 0 of a 4 KiB RAM range. RAM addresses, GPA and VA are kept
separate. Nonconforming runs are counted separately. All initial NOTDIRTY hits
sample V/C/M before the first write probe; complete-run histograms retain
combinations by miss count. TB presence/count and traversal work are sampled
inside the existing locked traversals, without a new list walk. There is one
clock read at the first miss and one at the end of a repeated-miss sequence,
not a clock read around each helper. Four first and four slowest repeated-miss
sequences are retained per CPU; only repeated-miss sequences are dumped.

Event fields `locks` and `fast_calls` count collection invocations, not mutex
wait time; `retries` includes the first pass. `lock_scan` and `range_scan` count
visited TB nodes in the two original traversals. These counters alone cannot
separate allocation/lock time from scanning time. `current_tb` is meaningful
only when TARGET_HAS_PRECISE_SMC is compiled. `unprotect` records the current ZVA thread. `unprotect_all` is a cumulative
atomic count across all vCPUs for this active 4 KiB RAM sequence; it is sampled
at each slow ZVA completion. This also captures foreign-vCPU unprotect calls.
Bounded trapless reads of at most 12 guest frame records occur only on the
second NOTDIRTY; they stop at a missing TLB entry, watchpoint, page boundary o
invalid frame-chain order. These reads cannot fault or access I/O. `start_ns`
uses QEMU realtime (host monotonic), for comparison to host event timestamps.

## Execution and acceptance

The production reproducer clones a stopped configured image into a new Linux
scratch directory for every repetition. It keeps production entrypoint,
original initrd, TCG multi and two CPUs. It temporarily installs the existing
read-only lifecycle observer in the disposable container for one QMP vCPU TID
mapping, then restores and checks the original file. It records CPU seconds,
serial warnings and management readiness. A diagnostic host stop is not a
clean guest shutdown. No watchdog settings are changed.

A cold boot runs the shipped rdgz-check.service and its script at
/usr/syno/lib/systemd/scripts/rd.gz.check.sh. That script uses command
substitution and pipelines (`dmesg | grep`, `uname | egrep`), requiring normal
fork/address-space duplication. Its ARM path exits normally. No historical cat
pathname is required. A smaller deterministic trigger than a configured cold
boot has not yet been established.

Production promotion of 0004 required CODE_PROTECTION_CONFIRMED, focused
correctness plus MTTCG, and at least five production-derived candidate runs
with zero watchdogs. Management HTTP readiness and F5 (two guest-initiated
QMP-confirmed clean shutdowns, configured/PostgreSQL/volume/persistence
evidence, 30/30 HTTP, HTTPS 200, >=30 minutes without soft lockup/oops/panic)
remain separate open gates.

## Focused correctness commands

The maintained correctness suite and its prerequisites are documented in
[tests/qemu-dcz](../../../tests/qemu-dcz/README.md). Run with Linux cross-GCC
and a selected production-patched binary. Each QEMU uses TCG multi with
2 vCPUs. No DSM software, account or watchdog setting is needed.

```sh
bash tests/qemu-dcz/run.sh /path/to/qemu /path/to/output
```

The system test checks 64 different RAM blocks and all surrounding bytes,
zeroed-code UDF rather than stale execution, unaffected same-page code,
same-page current execution with ISB, an AArch64 function spanning two pages and separate TBs,
permission/translation faults under a real guest MMU, PL011 read-only MMIO
registers, and 128 multi-vCPU code handoffs while CPU1 also executes unaffected
code on the invalidated page. The RSP test installs a write watchpoint on the
last byte of the block and verifies the stop precedes any zeroing.

The migration test initializes 16 MiB with nonzero pseudorandom data. Once at
least 8 MiB have been transferred, a qtest write releases a waiting guest loop;
DC ZVA performs all bulk memory modifications. Migration completes and a
second QEMU restores the stream. Its entire 16 MiB is then dumped and checked
for zero. This exercises active migration dirty tracking and catches loss of
writes to already-transmitted RAM, rather than relying on dirty-rate estimates.

Historical local cost mode swept 1/8/64/256/512 TBs with five repetitions each. Only two guest
counter reads surround a complete 64-ZVA clear. It does not time individual
helpers. These are synthetic measurements, distinct from DSM boot/service
latency and from watchdog causality. Cost mode is not part of the maintained
correctness suite.
