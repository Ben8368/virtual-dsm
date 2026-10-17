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


def record(receipt, signal, exit_code):
    subprocess.run([sys.executable, str(repo / 'src/platform/arm-lifecycle.py'),
                    'record', str(receipt), str(signal), str(exit_code)], check=True)
    data = json.loads(receipt.read_text())
    assert not data.get('clean', False), 'Lifecycle observer must not mark its receipt clean'
    return data


with tempfile.TemporaryDirectory() as tmp:
    directory = Path(tmp)
    base = 'DSM_DS124_72806'
    assert not runtime.has_state(directory, base)
    pointer = directory / (base + '.arm-current')
    pointer.symlink_to('missing-generation')
    assert runtime.has_state(directory, base), 'Broken generation must forbid automatic install'
    pointer.unlink()
    (directory / (base + '.arm.json')).write_text('{')
    assert runtime.has_state(directory, base), 'Partial public manifest must forbid automatic install'
    (directory / (base + '.arm.json')).unlink()
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
    # A valid-looking manifest may never claim a runtime capacity larger than its disk.
    source = importlib.util.spec_from_file_location('arm_contract', repo / 'src/platform/arm_contract.py')
    contract = importlib.util.module_from_spec(source)
    sys.modules[source.name] = contract
    source.loader.exec_module(contract)
    manifest = {'schema_version': 2, 'DSM_PLATFORM': 'rtd1619b', 'model': 'DS124',
                'dsm_version': '7.2.2', 'buildnumber': '72806',
                'pat_sha256': contract.BUILD['sha256'], 'builder_version': 1,
                'seed': {'geometry': {'bytes': contract.IMAGE_BYTES,
                                      'start_sector': contract.START_SECTOR,
                                      'partition_sectors': contract.PARTITION_SECTORS,
                                      'block_size': 4096, 'inode_size': 256}},
                'runtime': {'version': 1, 'lifecycle': 'BOOT_ATTEMPTED',
                            'generation': 1, 'virtual_bytes': disk.stat().st_size + 512}}
    rejected(lambda: runtime.migrate(manifest, disk.stat().st_size))
    manifest['schema_version'] = 999
    rejected(lambda: runtime.migrate(manifest, disk.stat().st_size))
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
    assert record(receipt, 0, 143)['outcome'] == 'unexpected-qemu-exit'
    receipt.write_text(json.dumps({'guest': True, 'reason': 'guest-shutdown'}))
    assert record(receipt, 0, 1)['outcome'] == 'unexpected-qemu-exit'
    receipt.unlink()
    assert record(receipt, 143, 143)['outcome'] == 'container-timeout-fallback'
    receipt.unlink()
    assert record(receipt, 143, 137)['outcome'] == 'container-timeout-fallback'
    # Missing QMP socket and missing SHUTDOWN event leave no receipt and cannot be clean.
    receipt.unlink()
    subprocess.run([sys.executable, str(repo / 'src/platform/arm-lifecycle.py'),
                    'watch', str(directory / 'absent.sock'), str(receipt), '0.05'], check=True)
    assert not receipt.exists()
    assert record(receipt, 0, 1)['outcome'] == 'unexpected-qemu-exit'
    receipt.unlink()
    address = directory / 'qmp-no-event.sock'
    with socket.socket(socket.AF_UNIX) as server:
        server.bind(str(address))
        server.listen()
        child = subprocess.Popen([sys.executable, str(repo / 'src/platform/arm-lifecycle.py'),
                                  'watch', str(address), str(receipt), '0.1'])
        conn, _ = server.accept()
        with conn, conn.makefile('rwb') as stream:
            stream.write(b'{"QMP":{}}\n')
            stream.flush()
            assert json.loads(stream.readline())['execute'] == 'qmp_capabilities'
        assert child.wait(timeout=10) == 0
    assert not receipt.exists()
    assert record(receipt, 143, 137)['outcome'] == 'container-timeout-fallback'
print('ARM runtime tests passed: sparse growth, shrink rejection, broken/partial state protection, QMP receipts.')
