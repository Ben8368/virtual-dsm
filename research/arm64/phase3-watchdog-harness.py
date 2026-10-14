#!/usr/bin/env python3
"""Low-disturbance host/guest watchdog capture for a disposable Phase 3 clone.

Run this on the Linux/WSL Docker host. It never changes guest kernel policy or
touches the configured source image. The container must already be a clone.
Host thread data comes directly from procfs; Docker logs are time-stamped and
kept in full. A single read-only QMP CPU/status snapshot is requested only
after a soft-lockup line is seen.
"""
from __future__ import annotations

import argparse
from collections import deque
import datetime as dt
import json
import os
from pathlib import Path
import hashlib
import queue
import re
import shlex
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

SOFT_LOCKUP = re.compile(r"watchdog: BUG: soft lockup", re.I)
GUEST_BOOT_COMPLETE = re.compile(r"Phase3Final login:", re.I)
KERNEL_TIME = re.compile(r"\[\s*(\d+\.\d+)\]")
DOCKER_TIME = re.compile(r"^(\d{4}-\d\d-\d\dT\S+)\s+(.*)$")


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")


def command(args: list[str], *, check: bool = True, timeout: float = 30,
            capture: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, check=check, timeout=timeout,
                          stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
                          stderr=subprocess.PIPE if capture else subprocess.DEVNULL)


def docker_json(*args: str) -> object:
    result = command(["docker", *args])
    return json.loads(result.stdout)


def inspect(container: str) -> dict:
    data = docker_json("inspect", container)
    return data[0]


def parse_proc_stat(stat_path: Path, status_path: Path) -> dict | None:
    """Read one task's proc stat/status, accounting for ')' in comm."""
    try:
        raw = stat_path.read_text()
        close = raw.rfind(")")
        comm = raw[raw.find("(") + 1:close]
        fields = raw[close + 2:].split()  # starts at stat field 3 (state)
        status = status_path.read_text()
        nspid_match = re.search(r"^NSpid:\s*(.*)$", status, re.M)
        rss_match = re.search(r"^VmRSS:\s*(\d+)\s+kB", status, re.M)
        return {
            "comm": comm, "state": fields[0],
            "ppid": int(fields[1]), "minor_faults": int(fields[7]),
            "major_faults": int(fields[9]), "utime": int(fields[11]),
            "stime": int(fields[12]), "threads": int(fields[17]),
            "processor": int(fields[36]),
            # Namespace PID is not guaranteed for host-side tasks, and this
            # parser is also used on host procfs entries outside containers.
            "nspid": int(nspid_match[1].split()[-1]) if nspid_match else 0,
            "rss_kb": int(rss_match[1]) if rss_match else 0,
            "affinity": (re.search(r"^Cpus_allowed_list:\s*(\S+)", status, re.M).group(1)
                         if re.search(r"^Cpus_allowed_list:\s*(\S+)", status, re.M) else ""),
        }
    except (OSError, ValueError, IndexError):
        return None


def proc_stat(pid: int) -> dict | None:
    value = parse_proc_stat(Path(f"/proc/{pid}/stat"), Path(f"/proc/{pid}/status"))
    if value:
        value["pid"] = pid
    return value


def descendants(root_pid: int) -> list[int]:
    parent_map: dict[int, int] = {}
    for entry in Path("/proc").iterdir():
        if entry.name.isdigit():
            value = proc_stat(int(entry.name))
            if value:
                parent_map[value["pid"]] = value["ppid"]
    result = {root_pid}
    changed = True
    while changed:
        changed = False
        for pid, ppid in parent_map.items():
            if ppid in result and pid not in result:
                result.add(pid)
                changed = True
    return sorted(result)


def locate_qemu(container_pid: int) -> int | None:
    candidates = []
    for pid in descendants(container_pid):
        try:
            cmdline = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
        except OSError:
            continue
        if "qemu-system-aarch64" in cmdline or "qemu-system-aarch64" in Path(f"/proc/{pid}/comm").read_text(errors="replace"):
            candidates.append((cmdline.count(" "), pid))
    return max(candidates)[1] if candidates else None


def read_vcpu_map(container: str) -> tuple[dict[int, int], str]:
    """Read the one-time QMP result written by the lifecycle observer's client."""
    try:
        result = command(["docker", "exec", container, "cat", "/run/shm/phase3-watchdog-vcpu-map.json"], timeout=2)
        data = json.loads(result.stdout)
        mapping = {int(cpu): int(tid) for cpu, tid in data["guest_cpu_to_namespace_tid"].items()}
        return mapping, json.dumps(data, sort_keys=True)
    except subprocess.CalledProcessError as exc:
        return {}, f"QMP vCPU map not ready: {(exc.stderr or exc.stdout or str(exc)).strip()}"
    except (subprocess.SubprocessError, json.JSONDecodeError, KeyError, ValueError) as exc:
        return {}, f"QMP vCPU map unavailable: {exc}"


def qmp_event_snapshot(container: str, target: Path) -> None:
    """Request one post-event snapshot through the lifecycle observer's QMP client."""
    script = r'''import json,socket
p="/run/shm/phase3-watchdog-control.sock"
s=socket.socket(socket.AF_UNIX); s.settimeout(3); s.connect(p); f=s.makefile("rwb")
s.sendall(b"snapshot\n"); print(f.readline().decode(),end=""); s.close()
'''
    try:
        result = command(["docker", "exec", container, "python3", "-c", script], timeout=12)
        target.write_text(f"host_utc={utc_now()}\nhost_monotonic_ns={time.monotonic_ns()}\n{result.stdout}", encoding="utf-8")
    except subprocess.SubprocessError as exc:
        target.write_text(f"QMP post-event snapshot failed: {exc}\n", encoding="utf-8")


def install_diagnostic_observer(container: str, outdir: Path) -> tuple[Path, str]:
    """Back up and replace only this stopped container's /run observer."""
    target = outdir / "arm-lifecycle.original.py"
    if not target.exists():
        command(["docker", "cp", f"{container}:/run/platform/arm-lifecycle.py", str(target)])
    original = target.read_bytes()
    if b"phase3-watchdog-control.sock" in original:
        raise RuntimeError("saved lifecycle observer is already the diagnostic version")
    observer = Path(__file__).with_name("phase3-watchdog-qmp-observer.py")
    command(["docker", "cp", str(observer), f"{container}:/run/platform/arm-lifecycle.py"])
    return target, hashlib.sha256(original).hexdigest()


def restore_diagnostic_observer(container: str, backup: Path, expected_sha256: str) -> None:
    state = inspect(container)["State"]
    if state.get("Running"):
        raise RuntimeError("refusing to restore lifecycle file while the diagnostic guest is running")
    command(["docker", "cp", str(backup), f"{container}:/run/platform/arm-lifecycle.py"])
    verify = backup.with_suffix(".verify.py")
    command(["docker", "cp", f"{container}:/run/platform/arm-lifecycle.py", str(verify)])
    if hashlib.sha256(verify.read_bytes()).hexdigest() != expected_sha256:
        raise RuntimeError("restored lifecycle observer SHA256 does not match the original")
    verify.unlink()


def read_qemu_tids(qemu_pid: int | None, cpu_map: dict[int, int]) -> list[dict]:
    if not qemu_pid:
        return []
    inverse = {ns_tid: cpu for cpu, ns_tid in cpu_map.items()}
    rows = []
    try:
        tids = sorted(int(x.name) for x in Path(f"/proc/{qemu_pid}/task").iterdir())
    except (OSError, ValueError):
        return []
    for tid in tids:
        s = parse_proc_stat(Path(f"/proc/{qemu_pid}/task/{tid}/stat"),
                            Path(f"/proc/{qemu_pid}/task/{tid}/status"))
        if not s:
            continue
        try:
            comm = Path(f"/proc/{qemu_pid}/task/{tid}/comm").read_text().strip()
        except OSError:
            comm = s["comm"]
        rows.append({**s, "pid": qemu_pid, "tid": tid, "comm": comm,
                     "guest_cpu": inverse.get(s["nspid"], "")})
    return rows


def host_pressure(qemu_pid: int | None) -> dict:
    def read(path: str) -> str:
        try:
            return Path(path).read_text().strip().replace("\n", " | ")
        except OSError:
            return ""
    stat = read("/proc/stat").split(" | ")[0]
    mem = read("/proc/meminfo")
    pressure = read("/proc/pressure/memory")
    qemu = proc_stat(qemu_pid) if qemu_pid else None
    cg_cpu_max = cg_cpuset = cg_mem_max = ""
    if qemu_pid:
        try:
            cg = Path(f"/proc/{qemu_pid}/cgroup").read_text()
            entry = next((line.split("::", 1)[1] for line in cg.splitlines() if "::" in line), "")
            cg_root = Path("/sys/fs/cgroup") / entry.lstrip("/")
            def cg_read(name: str) -> str:
                try:
                    return (cg_root / name).read_text().strip()
                except OSError:
                    return ""
            cg_cpu_max, cg_cpuset, cg_mem_max = cg_read("cpu.max"), cg_read("cpuset.cpus.effective"), cg_read("memory.max")
        except OSError:
            pass
    try:
        statm = Path(f"/proc/{qemu_pid}/statm").read_text().split() if qemu_pid else []
        rss_pages = int(statm[1]) if len(statm) > 1 else 0
        rss_kb = rss_pages * os.sysconf("SC_PAGE_SIZE") // 1024
    except (OSError, ValueError):
        rss_kb = qemu["rss_kb"] if qemu else 0
    return {"loadavg": read("/proc/loadavg"), "cpu_stat": stat,
            "mem_available": re.search(r"MemAvailable:\s*\d+\s+kB", mem).group(0) if re.search(r"MemAvailable:\s*\d+\s+kB", mem) else "",
            "swap_free": re.search(r"SwapFree:\s*\d+\s+kB", mem).group(0) if re.search(r"SwapFree:\s*\d+\s+kB", mem) else "",
            "memory_pressure": pressure, "qemu_rss_kb": rss_kb,
            "qemu_major_faults": qemu["major_faults"] if qemu else "",
            "wsl_cpus": os.cpu_count() or "", "cpu_max": read("/sys/fs/cgroup/cpu.max"),
            "cpuset": read("/sys/fs/cgroup/cpuset.cpus.effective"),
            "qemu_cgroup_cpu_max": cg_cpu_max, "qemu_cgroup_cpuset": cg_cpuset,
            "qemu_cgroup_memory_max": cg_mem_max}


def capture_constraints(container: str, target: Path) -> None:
    data = inspect(container)
    host = data.get("HostConfig", {})
    result = {
        "captured_utc": utc_now(), "container": data.get("Name"),
        "docker_image": data.get("Config", {}).get("Image"),
        "bind_mounts": [{"source": m.get("Source"), "destination": m.get("Destination"),
                         "rw": m.get("RW")} for m in data.get("Mounts", [])],
        "cpu_quota": host.get("CpuQuota"), "cpu_period": host.get("CpuPeriod"),
        "nano_cpus": host.get("NanoCpus"), "cpuset_cpus": host.get("CpusetCpus"),
        "memory_limit_bytes": host.get("Memory"), "pids_limit": host.get("PidsLimit"),
        "wsl_visible_cpus": os.cpu_count(), "wsl_cpu_max": Path("/sys/fs/cgroup/cpu.max").read_text().strip()
            if Path("/sys/fs/cgroup/cpu.max").exists() else "unavailable",
        "wsl_cpuset": Path("/sys/fs/cgroup/cpuset.cpus.effective").read_text().strip()
            if Path("/sys/fs/cgroup/cpuset.cpus.effective").exists() else "unavailable",
        "cpu_affinity": sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else "unavailable",
        "environment": {key: value for env in data.get("Config", {}).get("Env", [])
                        for key, value in [env.split("=", 1)]
                        if key in ("CPU_CORES", "RAM_SIZE", "DSM_PLATFORM", "NETWORK")},
    }
    target.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


def log_reader(container: str, since: str, out: queue.Queue, stop: threading.Event) -> None:
    try:
        proc = subprocess.Popen(["docker", "logs", "--follow", "--timestamps", "--since", since, container],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        while not stop.is_set():
            line = proc.stdout.readline() if proc.stdout else ""
            if not line:
                if proc.poll() is not None:
                    break
                time.sleep(0.05)
                continue
            out.put((time.monotonic_ns(), utc_now(), line.rstrip("\n")))
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
    except OSError as exc:
        out.put((time.monotonic_ns(), utc_now(), f"[harness docker logs error] {exc}"))


def http_status(url: str, timeout: float) -> tuple[int | None, float]:
    start = time.monotonic()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.status, time.monotonic() - start
    except urllib.error.HTTPError as exc:
        return exc.code, time.monotonic() - start
    except (OSError, urllib.error.URLError):
        return None, time.monotonic() - start


def launch_boot(container: str, boot_num: int, outdir: Path, args: argparse.Namespace) -> tuple[bool, dict]:
    boot_dir = outdir / f"boot-{boot_num:02d}"
    boot_dir.mkdir(parents=True, exist_ok=True)
    before = inspect(container)
    if before["State"]["Running"]:
        raise RuntimeError(f"{container} is already running; refuse to overlap or reset a live guest")
    capture_constraints(container, boot_dir / "host-container-constraints.json")
    since = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    start_mono = time.monotonic()
    start_ns = time.monotonic_ns()
    start_utc = utc_now()
    logs: queue.Queue = queue.Queue()
    log_stop = threading.Event()
    log_thread = threading.Thread(target=log_reader, args=(container, since, logs, log_stop), daemon=True)
    command(["docker", "start", container])
    with (boot_dir / "serial.log").open("w", encoding="utf-8", buffering=1024 * 1024) as serial, \
         (boot_dir / "host-vcpu-timeline.tsv").open("w", encoding="utf-8", buffering=256 * 1024) as cpu_file, \
         (boot_dir / "host-pressure-timeline.tsv").open("w", encoding="utf-8", buffering=64 * 1024) as pressure_file, \
         (boot_dir / "time-correlation.tsv").open("w", encoding="utf-8", buffering=64 * 1024) as corr_file:
        cpu_file.write("boot\thost_monotonic_ns\thost_utc\tqemu_pid\ttid\tnamespace_tid\tguest_cpu\tcomm\tstate\tpsr\taffinity\tdelta_cpu_ticks\ttotal_cpu_ticks\tuser_ticks\tsystem_ticks\tpcpu_since_last\tminor_faults\tmajor_faults\trss_kb\n")
        pressure_file.write("boot\thost_monotonic_ns\thost_utc\tloadavg\tcpu_stat\tMemAvailable\tSwapFree\tmemory_pressure\tqemu_rss_kb\tqemu_major_faults\twsl_cpus\tcpu_max\tcpuset\tqemu_cgroup_cpu_max\tqemu_cgroup_cpuset\tqemu_cgroup_memory_max\n")
        corr_file.write("boot\thost_monotonic_ns\thost_utc\tdocker_log_timestamp\tguest_monotonic_seconds\tline\n")
        # Start following only after Docker has started the container. Docker
        # may terminate `logs --follow` immediately when the container is
        # stopped, so the previous order silently lost serial output. The
        # earlier --since timestamp replays logs emitted during docker start.
        log_thread.start()
        event_host_ns = None
        event_guest = None
        event_lines: list[tuple[int, str]] = []
        serial_ring: deque[tuple[int, str]] = deque()
        snapshot_started = False
        snapshot_thread: threading.Thread | None = None
        all_guest_times: list[tuple[int, float]] = []
        last_corr_guest: float | None = None
        seen_readiness = False
        guest_boot_completed = False
        readiness_sec = None
        boot_success = False
        stop_started = False
        observe_deadline_reason = None
        stop_proc: subprocess.Popen | None = None
        cpu_map: dict[int, int] = {}
        mapping_saved = False
        mapping_try = 0
        qemu_pid = None
        prev_cpu: dict[int, tuple[int, int]] = {}
        prev_sample_at = time.monotonic()
        next_cpu = start_mono
        next_pressure = start_mono
        next_http = start_mono
        qmp_map_raw = "not yet queried"
        sampled_until = start_mono
        next_state_poll = start_mono
        next_mapping_poll = start_mono
        next_flush = start_mono + 5.0
        state = before["State"]
        qemu_cmd_saved = False

        def drain_logs() -> None:
            nonlocal event_host_ns, event_guest, event_lines, last_corr_guest, guest_boot_completed
            while True:
                try:
                    mono_ns, host_utc, line = logs.get_nowait()
                except queue.Empty:
                    return
                serial.write(f"host_monotonic_ns={mono_ns}\thost_utc={host_utc}\t{line}\n")
                docker_match = DOCKER_TIME.match(line)
                docker_ts, payload = (docker_match.group(1), docker_match.group(2)) if docker_match else ("", line)
                if GUEST_BOOT_COMPLETE.search(payload):
                    guest_boot_completed = True
                gmatch = KERNEL_TIME.search(payload)
                guest = float(gmatch.group(1)) if gmatch else None
                rendered = f"{host_utc}\t{docker_ts}\tguest={guest if guest is not None else ''}\t{payload}"
                serial_ring.append((mono_ns, rendered))
                while serial_ring and mono_ns - serial_ring[0][0] > 30_000_000_000:
                    serial_ring.popleft()
                if guest is not None:
                    if last_corr_guest is None or guest - last_corr_guest >= 30 or SOFT_LOCKUP.search(payload):
                        corr_file.write(f"{boot_num}\t{mono_ns}\t{host_utc}\t{docker_ts}\t{guest:.6f}\t{payload}\n")
                        last_corr_guest = guest
                    all_guest_times.append((mono_ns, guest))
                if event_host_ns is not None:
                    event_lines.append((mono_ns, rendered))
                if SOFT_LOCKUP.search(payload) and event_host_ns is None:
                    event_host_ns = mono_ns
                    event_guest = guest
                    event_lines = list(serial_ring)

        while True:
            now = time.monotonic()
            drain_logs()
            if now >= next_state_poll:
                state = inspect(container)["State"]
                next_state_poll = now + 5.0
            if state.get("Pid", 0):
                if qemu_pid is None:
                    qemu_pid = locate_qemu(int(state["Pid"]))
                if qemu_pid and not qemu_cmd_saved:
                    try:
                        cmdline = Path(f"/proc/{qemu_pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
                        cgroup = Path(f"/proc/{qemu_pid}/cgroup").read_text()
                        status = Path(f"/proc/{qemu_pid}/status").read_text()
                        (boot_dir / "qemu-command-and-host-state.txt").write_text(
                            f"captured_utc={utc_now()}\nhost_pid={qemu_pid}\ncmdline={cmdline}\n"
                            f"cgroup={cgroup}status={status}", encoding="utf-8")
                        qemu_cmd_saved = True
                    except OSError:
                        pass
                if not mapping_saved and mapping_try < 20 and now >= next_mapping_poll:
                    mapping_try += 1
                    cpu_map, qmp_map_raw = read_vcpu_map(container)
                    next_mapping_poll = now + 1.0
                if cpu_map and qemu_pid and not mapping_saved:
                    (boot_dir / "qemu-vcpu-map.json").write_text(json.dumps({"captured_utc": utc_now(), "host_pid": qemu_pid,
                        "guest_cpu_to_namespace_tid": cpu_map, "qmp": qmp_map_raw}, indent=2) + "\n", encoding="utf-8")
                    mapping_saved = True
                elif mapping_try >= 20 and not mapping_saved:
                    (boot_dir / "qemu-vcpu-map.json").write_text(qmp_map_raw + "\n", encoding="utf-8")
                    mapping_saved = True
            if now >= next_cpu:
                sample_ns = time.monotonic_ns()
                sample_utc = utc_now()
                current = read_qemu_tids(qemu_pid, cpu_map)
                elapsed = max(now - prev_sample_at, 0.001)
                ticks_per_sec = os.sysconf("SC_CLK_TCK")
                for row in current:
                    tid = row["tid"]
                    total = row["utime"] + row["stime"]
                    old = prev_cpu.get(tid)
                    delta = total - old[0] if old else 0
                    pcpu = (delta / ticks_per_sec / elapsed * 100) if old else 0.0
                    cpu_file.write(f"{boot_num}\t{sample_ns}\t{sample_utc}\t{qemu_pid or ''}\t{tid}\t{row['nspid']}\t{row['guest_cpu']}\t{row['comm']}\t{row['state']}\t{row['processor']}\t{row['affinity']}\t{delta}\t{total}\t{row['utime']}\t{row['stime']}\t{pcpu:.1f}\t{row['minor_faults']}\t{row['major_faults']}\t{row['rss_kb']}\n")
                    prev_cpu[tid] = (total, sample_ns)
                prev_sample_at = now
                next_cpu = now + args.sample_interval
            if now >= next_pressure:
                sample_ns = time.monotonic_ns()
                values = host_pressure(qemu_pid)
                pressure_file.write("\t".join(str(x) for x in (boot_num, sample_ns, utc_now(), values["loadavg"], values["cpu_stat"], values["mem_available"], values["swap_free"], values["memory_pressure"], values["qemu_rss_kb"], values["qemu_major_faults"], values["wsl_cpus"], values["cpu_max"], values["cpuset"], values["qemu_cgroup_cpu_max"], values["qemu_cgroup_cpuset"], values["qemu_cgroup_memory_max"])) + "\n")
                next_pressure = now + 1.0
            if now >= next_flush:
                for fh in (serial, cpu_file, pressure_file, corr_file):
                    fh.flush()
                next_flush = now + 5.0
            if not seen_readiness and now >= next_http:
                status, _ = http_status(args.ready_url, args.http_timeout)
                if status is not None and 200 <= status < 500:
                    seen_readiness = True
                    readiness_sec = now - start_mono
                    (boot_dir / "management-readiness.txt").write_text(f"status={status}\nelapsed_host_seconds={readiness_sec:.3f}\nhost_utc={utc_now()}\n", encoding="utf-8")
                next_http = now + args.http_interval
            if event_host_ns is not None and not snapshot_started:
                snapshot_started = True
                snapshot_thread = threading.Thread(target=qmp_event_snapshot,
                    args=(container, boot_dir / "qmp-post-event.txt"), daemon=True)
                snapshot_thread.start()
            if event_host_ns is not None and now - event_host_ns / 1e9 >= 30 and not stop_started:
                stop_started = True
                stop_proc = subprocess.Popen(["docker", "stop", "--time", str(args.stop_timeout), container], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
            guest_runtime = (all_guest_times[-1][1] - all_guest_times[0][1]) if len(all_guest_times) >= 2 else 0.0
            host_elapsed = now - start_mono
            # printk can be silent for minutes after boot. In that case the
            # last serial timestamp cannot measure guest runtime, so use a
            # conservative host fallback (startup offset plus TCG slowdown
            # margin) and record that the guest duration was not directly
            # observed. Never infer that guest time stopped from printk silence.
            host_fallback = host_elapsed >= args.observe_seconds + args.host_fallback_margin
            if event_host_ns is None and (guest_runtime >= args.observe_seconds or host_fallback) and not stop_started:
                observe_deadline_reason = "guest_printk_runtime" if guest_runtime >= args.observe_seconds else "host_fallback_printk_silent"
                stop_started = True
                stop_proc = subprocess.Popen(["docker", "stop", "--time", str(args.stop_timeout), container], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
            if stop_started and (not state.get("Running") or (stop_proc and stop_proc.poll() is not None)):
                # Drain one last serial segment after the container exits.
                drain_logs()
                break
            if not state.get("Running") and state.get("Status") in ("exited", "dead"):
                drain_logs()
                break
            sampled_until = now
            time.sleep(0.05)
        log_stop.set()
        log_thread.join(timeout=3)
        if snapshot_thread:
            snapshot_thread.join(timeout=12)
        drain_logs()
        for fh in (serial, cpu_file, pressure_file, corr_file):
            fh.flush()
        final_state = inspect(container)["State"]
        # The harness intentionally stops the VM after its observation window,
        # which normally gives Docker exit status 143. Boot completion is the
        # DSM serial login prompt; HTTP readiness is tracked independently.
        boot_success = guest_boot_completed
        runtime = time.monotonic() - start_mono
        summary = {
            "boot": boot_num, "start_utc": start_utc, "start_host_monotonic_ns": start_ns,
            "end_utc": utc_now(), "host_elapsed_seconds": round(runtime, 3),
            "guest_last_timestamp": all_guest_times[-1][1] if all_guest_times else None,
            "guest_elapsed_from_first_printk": round(all_guest_times[-1][1] - all_guest_times[0][1], 3) if len(all_guest_times) >= 2 else None,
            "watchdog": event_host_ns is not None, "watchdog_guest_timestamp": event_guest,
            "watchdog_host_monotonic_ns": event_host_ns, "readiness_http": seen_readiness,
            "readiness_elapsed_host_seconds": readiness_sec, "boot_success": boot_success,
            "guest_boot_completed": guest_boot_completed,
            "observe_deadline_reason": observe_deadline_reason,
            "container_exit_code": final_state.get("ExitCode"),
            "qemu_pid": qemu_pid, "qmp_vcpu_map": cpu_map, "qmp_mapping_detail": qmp_map_raw,
            "sample_interval_seconds": args.sample_interval,
        }
        (boot_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        if event_host_ns is not None:
            low, high = event_host_ns - 30_000_000_000, event_host_ns + 30_000_000_000
            with (boot_dir / "watchdog-event-window.txt").open("w", encoding="utf-8") as fh:
                fh.write(f"event_host_monotonic_ns={event_host_ns}\nevent_guest_timestamp={event_guest}\n")
                fh.write("This includes only lines received within +/-30 seconds of the warning; host timelines remain authoritative.\n\n")
                for mono_ns, line in event_lines:
                    if low <= mono_ns <= high:
                        fh.write(f"host_monotonic_ns={mono_ns}\t{line}\n")
            for source_name, output_name in (("host-vcpu-timeline.tsv", "watchdog-host-vcpu-window.tsv"),
                                             ("host-pressure-timeline.tsv", "watchdog-host-pressure-window.tsv")):
                source = boot_dir / source_name
                with source.open(encoding="utf-8") as src, (boot_dir / output_name).open("w", encoding="utf-8") as dst:
                    for line in src:
                        fields = line.split("\t", 3)
                        if len(fields) > 1 and fields[1].isdigit() and low <= int(fields[1]) <= high:
                            dst.write(line)
        return event_host_ns is not None, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", default="vdsm-phase3-watchdog-clone")
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--boots", type=int, default=10)
    parser.add_argument("--observe-seconds", type=int, default=600,
                        help="minimum guest runtime per no-event cold boot")
    parser.add_argument("--sample-interval", type=float, default=0.5)
    parser.add_argument("--ready-url", default="http://127.0.0.1:15610/")
    parser.add_argument("--http-interval", type=float, default=2.0)
    parser.add_argument("--http-timeout", type=float, default=0.2,
                        help="keep readiness probing below the 500 ms sampler period")
    parser.add_argument("--stop-timeout", type=int, default=180)
    parser.add_argument("--host-fallback-margin", type=int, default=120,
                        help="extra host seconds beyond the guest target if serial printk becomes silent")
    args = parser.parse_args()
    if not sys.platform.startswith("linux"):
        parser.error("Run inside Ubuntu-24.04/WSL with Docker access; Windows procfs is not valid evidence")
    if args.boots < 1 or args.observe_seconds < 600 or args.sample_interval < 0.25 or args.host_fallback_margin < 60:
        parser.error("Use >=1 boot, >=600 seconds per no-event boot, and >=250ms host sampling")
    args.outdir.mkdir(parents=True, exist_ok=True)
    backup, original_observer_sha256 = install_diagnostic_observer(args.container, args.outdir)
    (args.outdir / "experiment.json").write_text(json.dumps({
        "created_utc": utc_now(), "container": args.container,
        "docker_ps": command(["docker", "ps", "-a", "--no-trunc", "--filter", f"name=^{args.container}$"]).stdout,
        "docker_info": command(["docker", "info", "--format", "{{json .}}"], check=False).stdout,
        "boots_requested": args.boots, "observe_seconds": args.observe_seconds,
        "qemu_mode": "production clone configuration; expected -accel tcg,thread=multi -smp 2",
        "watchdog_policy_changed": False,
        "guest_kernel_modified": False,
        "diagnostic_observer": "temporary lifecycle observer copy; one startup QMP CPU map; event-triggered read-only register RPC",
        "original_lifecycle_observer_sha256": original_observer_sha256,
    }, indent=2) + "\n", encoding="utf-8")
    rows = []
    try:
        for boot in range(1, args.boots + 1):
            event, summary = launch_boot(args.container, boot, args.outdir, args)
            rows.append(summary)
            matrix = ["# Watchdog baseline matrix", "", "| Boot | QEMU mode | vCPU | Host runtime | Guest elapsed | Watchdog | HTTP ready | Boot result |",
                      "|---:|---|---:|---:|---:|---|---|---|"]
            for row in rows:
                matrix.append(f"| {row['boot']} | TCG multi | 2 | {row['host_elapsed_seconds']}s | {row['guest_elapsed_from_first_printk']}s | {'yes' if row['watchdog'] else 'no'} | {'yes' if row['readiness_http'] else 'no'} | {'success' if row['boot_success'] else 'incomplete'} |")
            matrix += ["", "Boots stop after the first event has been preserved or after the requested cold-boot count. A no-event boot is observed for at least the requested guest-runtime window before graceful container shutdown.", ""]
            (args.outdir / "baseline-matrix.md").write_text("\n".join(matrix), encoding="utf-8")
            print(f"boot {boot}: watchdog={'yes' if event else 'no'}, HTTP={'yes' if summary['readiness_http'] else 'no'}, clean-result={'yes' if summary['boot_success'] else 'no'}; artifacts={args.outdir / f'boot-{boot:02d}' }", flush=True)
            if event:
                break
            if summary["container_exit_code"] != 0:
                print("Container did not exit cleanly; stopping the matrix to protect clone state.", file=sys.stderr, flush=True)
                break
    finally:
        state = inspect(args.container)["State"]
        if state.get("Running"):
            command(["docker", "stop", "--timeout", str(args.stop_timeout), args.container], timeout=args.stop_timeout + 30)
        restore_diagnostic_observer(args.container, backup, original_observer_sha256)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
