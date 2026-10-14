# Phase 3 watchdog host-correlation harness

`phase3-watchdog-harness.py` runs inside Ubuntu-24.04/WSL against an existing
Docker container backed by a **disposable configured clone**. It rejects a
Windows host because the host thread evidence must come from the Linux
`/proc` view that schedules QEMU.

The default run is ten cold starts with at least 600 guest-monotonic seconds
per no-warning boot. If printk becomes silent before the observation target,
the sampler uses a conservative host-time fallback and records that choice;
printk silence is never treated as guest clock stoppage. Stop time is extended
to 180 seconds so the container's normal shutdown handler can request DSM
shutdown. A warning ends the matrix after collecting a further 30 seconds. If
a stop is not clean, the run halts instead of restarting against the clone.

Example for the Phase 3 clone already created in `/var/lib/vdsm-phase3/watchdog-clone`:

```bash
sudo python3 /mnt/c/virtual-dsm/research/arm64/phase3-watchdog-harness.py \
  --container vdsm-phase3-watchdog-clone \
  --outdir /mnt/c/virtual-dsm/research/arm64/work/phase3-watchdog/baseline-20261013 \
  --boots 10 --observe-seconds 600 --sample-interval 0.5
```

Each boot directory contains:

* `serial.log`: the complete Docker/QEMU console output, stamped with host
  monotonic time and UTC as it is collected; Docker's own timestamp is kept.
* `host-vcpu-timeline.tsv`: every QEMU thread's state, host CPU placement,
  namespace TID, QMP vCPU mapping (when available), accumulated user/system
  ticks, per-sample CPU use, faults and RSS at 500 ms intervals.
* `host-pressure-timeline.tsv`: load, aggregate CPU counters, memory/swap,
  memory PSI, QEMU RSS/faults, WSL-visible CPU count and cgroup limits at 1 s.
* `time-correlation.tsv`: sparse paired host monotonic and guest printk uptime
  records; soft-lockup lines are always included.
* `qemu-vcpu-map.json`: one QMP guest CPU to Linux namespace-TID lookup.
* On a warning, `watchdog-event-window.txt` and host timeline slices preserve
  the +/-30 s interval, and `qmp-post-event.txt` captures one status, CPU list
  and HMP register snapshot for each vCPU. No GDB connection or continuous
  guest inspection occurs before a warning.
* `summary.json` and the run-level `baseline-matrix.md` record readiness,
  elapsed host/guest time, watchdog outcome and container exit status. Boot
  completion means the guest reached the DSM serial login prompt; HTTP
  readiness remains an independent field because the harness stops the VM
  after observation and Docker commonly reports 143 for that intentional stop.

The sampler reads procfs directly for thread and pressure measurements. Before
the run it saves the container's original `/run/platform/arm-lifecycle.py` and
temporarily copies in `phase3-watchdog-qmp-observer.py` in the container
overlay. That observer retains the original shutdown event receipt, performs
one `query-cpus-fast` request through the existing QMP connection to map guest
vCPUs to Linux TIDs, and exposes a private in-container control socket for one
post-warning status/register snapshot. The original observer is restored and
its SHA256 checked when the run ends. The guest disk, guest kernel, watchdog
policy, DSM configuration and production QEMU arguments are unchanged.

No GDB connection or continuous guest inspection occurs before a warning. The
host CPU-time timeline characterizes whether QEMU's mapped vCPU threads were
scheduled. It does not by itself prove guest instruction forward progress; use
the one post-event register snapshot and the complete guest warning stack
without claiming more than the samples establish.

The container bind must point to the clone, never `/var/lib/vdsm-phase3/fresh`
or another accepted source image. The harness records Docker bind mounts and
CPU/memory limits in each boot's `host-container-constraints.json` before
starting the guest.
