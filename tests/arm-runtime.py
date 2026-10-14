#!/usr/bin/env python3
"""Non-proprietary capacity, recovery gating and QMP receipt tests."""
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile

repo = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo / 'src/platform'))
import arm_runtime as runtime


def rejected(action):
    try:
        action()
    except ValueError:
        return
    raise AssertionError('Unsafe operation accepted')


for value in ('0', '1G', '16.5G', '-16G', '16G;touch x', '3', '2T'):
    rejected(lambda: runtime.capacity(value))
assert runtime.capacity('16G') == 16 * 1024**3
assert runtime.capacity('32GiB') == 32 * 1024**3
with tempfile.TemporaryDirectory() as tmp:
    directory = Path(tmp)
    base = 'DSM_DS124_72806'
    assert not runtime.has_state(directory, base)
    pointer = directory / (base + '.arm-current')
    pointer.symlink_to('missing-generation')
    assert runtime.has_state(directory, base), 'Broken generation must forbid automatic install'
    pointer.unlink()
    orphan = directory / ('.' + base + '.arm-generation-orphan')
    orphan.mkdir()
    assert runtime.has_state(directory, base)
    orphan.rmdir()
    disk = directory / (base + '.system.img')
    disk.write_bytes(os.urandom(4096))
    assert runtime.has_state(directory, base), 'Partial runtime must fail closed'
    before = disk.read_bytes()
    runtime.grow(disk, 1024**3)
    with disk.open('rb') as fh:
        assert fh.read(4096) == before
        fh.seek(1024**3 - 4096)
        assert fh.read(4096) == bytes(4096)
    if hasattr(disk.stat(), 'st_blocks'):
        assert disk.stat().st_blocks * 512 < 1024**2, 'Growth preallocated the sparse tail'
    rejected(lambda: runtime.grow(disk, 4096))
    assert disk.stat().st_size == 1024**3
    # Observe the actual QMP wire protocol; guest=false never becomes guest=true.
    for guest, reason in ((True, 'guest-shutdown'), (False, 'host-qmp-quit'), (True, 'guest-reset')):
        address = directory / 'qmp.sock'
        receipt = directory / 'exit.json'
        with socket.socket(socket.AF_UNIX) as server:
            server.bind(str(address))
            server.listen()
            server.settimeout(10)
            child = subprocess.Popen([sys.executable, str(repo / 'src/platform/arm-lifecycle.py'),
                                      'watch', str(address), str(receipt)])
            conn, _ = server.accept()
            with conn, conn.makefile('rwb') as stream:
                stream.write(b'{"QMP":{}}\n')
                stream.flush()
                assert json.loads(stream.readline())['execute'] == 'qmp_capabilities'
                event = {'event': 'SHUTDOWN', 'data': {'guest': guest, 'reason': reason}}
                stream.write(json.dumps(event).encode() + b'\n')
                stream.flush()
            assert child.wait(timeout=10) == 0
        assert json.loads(receipt.read_text()) == {'guest': guest, 'reason': reason}
        address.unlink()
        subprocess.run([sys.executable, str(repo / 'src/platform/arm-lifecycle.py'),
                        'record', str(receipt), '0', '0'], check=True)
        data = json.loads(receipt.read_text())
        assert data['outcome'] == ('guest-poweroff' if guest and reason == 'guest-shutdown' else 'unexpected-qemu-exit')
        assert data['container_requested'] is False and data['qemu_exit_code'] == 0
    receipt.write_text(json.dumps({'guest': True, 'reason': 'guest-shutdown'}))
    subprocess.run([sys.executable, str(repo / 'src/platform/arm-lifecycle.py'),
                    'record', str(receipt), '0', '143'], check=True)
    assert json.loads(receipt.read_text())['outcome'] == 'unexpected-qemu-exit'
    receipt.unlink()
    subprocess.run([sys.executable, str(repo / 'src/platform/arm-lifecycle.py'),
                    'record', str(receipt), '143', '143'], check=True)
    assert json.loads(receipt.read_text())['outcome'] == 'container-timeout-fallback'
print('ARM runtime tests passed: sparse growth, shrink rejection, broken/partial state protection, QMP receipts.')
