#!/usr/bin/env python3
"""Observe stock QMP shutdown events. No guest agent, credentials or reset API."""
import json
import os
from pathlib import Path
import socket
import sys
import time


def watch(address, output, timeout_seconds=30):
    deadline = time.monotonic() + timeout_seconds
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
    with sock, sock.makefile('rwb') as stream:
        if 'QMP' not in json.loads(stream.readline()):
            return
        stream.write(b'{"execute":"qmp_capabilities"}\n')
        stream.flush()
        for line in stream:
            event = json.loads(line)
            if event.get('event') == 'SHUTDOWN':
                data = event.get('data', {})
                temporary = output.with_suffix('.tmp')
                with temporary.open('w') as fh:
                    json.dump({'guest': data.get('guest'), 'reason': data.get('reason')}, fh)
                    fh.flush()
                    os.fsync(fh.fileno())
                os.replace(temporary, output)


def record(output, signal, exit_code):
    data = json.loads(output.read_text()) if output.is_file() else {}
    requested = int(signal) != 0
    data['container_requested'] = requested
    if exit_code != 'unknown':
        data['qemu_exit_code'] = int(exit_code)
    guest = (data.get('guest') is True and data.get('reason') == 'guest-shutdown' and
             data.get('qemu_exit_code') == 0)
    data['outcome'] = ('guest-poweroff' if guest else
                       'container-timeout-fallback' if requested else 'unexpected-qemu-exit')
    temporary = output.with_suffix('.tmp')
    with temporary.open('w') as fh:
        json.dump(data, fh)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(temporary, output)


if __name__ == '__main__':
    if sys.argv[1] == 'watch':
        watch(sys.argv[2], Path(sys.argv[3]), float(sys.argv[4]) if len(sys.argv) > 4 else 30)
    elif sys.argv[1] == 'record':
        record(Path(sys.argv[2]), sys.argv[3], sys.argv[4])
    else:
        raise SystemExit('Unknown ARM lifecycle operation')
