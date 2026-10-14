#!/usr/bin/env python3
"""Disposable-container lifecycle observer with one QMP CPU map and snapshot RPC.

This replaces /run/platform/arm-lifecycle.py only in the diagnostic container
overlay. It keeps the existing SHUTDOWN evidence and uses its single QMP
connection, so the production lifecycle client is not raced by a second client.
It never changes guest state; register reads are requested only after a warning.
"""
import json
import os
from pathlib import Path
import select
import socket
import sys
import time


class QMP:
    def __init__(self, sock):
        self.sock = sock
        self.buffer = bytearray()
        self.serial = 0

    def line(self, timeout=5):
        deadline = time.monotonic() + timeout
        while True:
            pos = self.buffer.find(b"\n")
            if pos >= 0:
                raw = bytes(self.buffer[:pos])
                del self.buffer[:pos + 1]
                return json.loads(raw)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("QMP response timeout")
            ready, _, _ = select.select([self.sock], [], [], remaining)
            if not ready:
                raise TimeoutError("QMP response timeout")
            data = self.sock.recv(65536)
            if not data:
                raise EOFError("QMP socket closed")
            self.buffer.extend(data)

    def buffered_line(self):
        return b"\n" in self.buffer

    def execute(self, name, arguments=None, on_event=None):
        self.serial += 1
        request_id = f"phase3-watchdog-{self.serial}"
        request = {"execute": name, "id": request_id}
        if arguments is not None:
            request["arguments"] = arguments
        self.sock.sendall((json.dumps(request) + "\n").encode())
        while True:
            item = self.line()
            if item.get("event") and on_event:
                on_event(item)
            if item.get("id") == request_id:
                if "error" in item:
                    raise RuntimeError(json.dumps(item["error"]))
                return item.get("return")


def atomic_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def watch(address, output):
    output = Path(output)
    deadline = time.monotonic() + 30
    while True:
        sock = socket.socket(socket.AF_UNIX)
        try:
            sock.connect(address)
            break
        except OSError:
            sock.close()
            if time.monotonic() >= deadline:
                return
            time.sleep(0.1)
    sock.setblocking(True)
    qmp = QMP(sock)
    qmp.line()
    map_path = Path("/run/shm/phase3-watchdog-vcpu-map.json")
    map_path.unlink(missing_ok=True)

    def handle_event(item):
        if item.get("event") == "SHUTDOWN":
            data = item.get("data", {})
            atomic_json(output, {"guest": data.get("guest"), "reason": data.get("reason")})

    qmp.execute("qmp_capabilities", on_event=handle_event)
    try:
        cpus = qmp.execute("query-cpus-fast", on_event=handle_event)
        cpu_map = {str(row["cpu-index"]): int(row["thread-id"])
                   for row in cpus if "thread-id" in row}
        map_value = {"guest_cpu_to_namespace_tid": cpu_map, "qmp_cpus": cpus,
                     "method": "query-cpus-fast from existing arm-lifecycle QMP connection"}
    except Exception as exc:
        map_value = {"guest_cpu_to_namespace_tid": {}, "map_error": str(exc)}
    map_value["captured_host_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    atomic_json(map_path, map_value)

    control_path = Path("/run/shm/phase3-watchdog-control.sock")
    control_path.unlink(missing_ok=True)
    listener = socket.socket(socket.AF_UNIX)
    listener.bind(str(control_path))
    os.chmod(control_path, 0o600)
    listener.listen(1)
    listener.setblocking(False)

    while True:
        if qmp.buffered_line():
            ready = [sock]
        else:
            ready = select.select([sock, listener], [], [], 0.2)[0]
        if listener in ready:
            client, _ = listener.accept()
            with client:
                client.settimeout(5)
                request = client.recv(128).decode(errors="replace").strip()
                if request == "snapshot":
                    try:
                        value = {"captured_host_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                 "status": qmp.execute("query-status", on_event=handle_event),
                                 "cpus": qmp.execute("query-cpus-fast", on_event=handle_event),
                                 "registers_by_vcpu": {}}
                        for cpu in value["cpus"]:
                            index = cpu.get("cpu-index")
                            if index is None:
                                continue
                            qmp.execute("human-monitor-command", {"command-line": f"cpu {index}"}, on_event=handle_event)
                            value["registers_by_vcpu"][str(index)] = qmp.execute(
                                "human-monitor-command", {"command-line": "info registers"}, on_event=handle_event)
                        client.sendall((json.dumps(value, indent=2) + "\n").encode())
                    except Exception as exc:  # diagnostic only; keep shutdown watcher alive
                        client.sendall((json.dumps({"snapshot_error": str(exc)}) + "\n").encode())
                else:
                    client.sendall(b'{"error":"unknown request"}\n')
        if sock in ready:
            try:
                item = qmp.line(timeout=0.2)
            except TimeoutError:
                continue
            except (EOFError, OSError):
                return
            if item.get("event"):
                handle_event(item)


def record(output, signal, exit_code):
    output = Path(output)
    data = json.loads(output.read_text()) if output.is_file() else {}
    requested = int(signal) != 0
    if exit_code != "unknown":
        data["qemu_exit_code"] = int(exit_code)
    data["container_requested"] = requested
    guest = (data.get("guest") is True and data.get("reason") == "guest-shutdown" and
             data.get("qemu_exit_code") == 0)
    data["outcome"] = ("guest-poweroff" if guest else
                       "container-timeout-fallback" if requested else "unexpected-qemu-exit")
    atomic_json(output, data)


if __name__ == "__main__":
    if sys.argv[1] == "watch":
        watch(sys.argv[2], sys.argv[3])
    elif sys.argv[1] == "record":
        record(sys.argv[2], sys.argv[3], sys.argv[4])
    else:
        raise SystemExit("Unknown lifecycle operation")
