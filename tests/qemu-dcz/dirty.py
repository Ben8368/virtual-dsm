#!/usr/bin/env python3
"""Enable QEMU migration dirty logging around a guest loop of RAM DC ZVA writes."""
import argparse
import json
import os
from pathlib import Path
import re
import shlex
import socket
import subprocess
import tempfile
import time


class QMP:
    def __init__(self, path):
        self.sock = socket.socket(socket.AF_UNIX)
        self.sock.settimeout(10)
        self.sock.connect(str(path))
        self.f = self.sock.makefile('rwb')
        assert 'QMP' in json.loads(self.f.readline())
        self.execute('qmp_capabilities')

    def execute(self, name, arguments=None):
        req = {'execute': name}
        if arguments is not None:
            req['arguments'] = arguments
        self.f.write(json.dumps(req).encode() + b'\n')
        self.f.flush()
        while True:
            line = self.f.readline()
            if not line:
                raise EOFError('QMP disconnected')
            value = json.loads(line)
            if 'return' in value:
                return value['return']
            if 'error' in value:
                raise RuntimeError(value['error'])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('qemu', type=Path)
    p.add_argument('output', type=Path)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=True)
    fixtures = Path(__file__).resolve().parent / 'fixtures'
    cmd = [os.environ.get('AARCH64_CC', 'aarch64-linux-gnu-gcc'), '-DTEST_MIGRATION', '-ffreestanding', '-fno-builtin',
           '-fno-stack-protector', '-mgeneral-regs-only', '-O2', '-g', '-nostdlib',
           '-static', '-Wl,--build-id=none', '-T', str(fixtures / 'link.ld'),
           str(fixtures / 'start.S'),
           str(fixtures / 'system.c'), '-o', str(a.output / 'dirty.elf')]
    subprocess.run(cmd, check=True, capture_output=True)
    syms = subprocess.check_output([os.environ.get('AARCH64_NM', 'aarch64-linux-gnu-nm'), str(a.output / 'dirty.elf')], text=True)
    go = int(re.search(r'^([0-9a-f]+) B migration_go$', syms, re.M)[1], 16)
    with tempfile.TemporaryDirectory(prefix='dcz-dirty-') as temp:
        endpoint = Path(temp) / 'qmp.sock'
        qtest = Path(temp) / 'qtest.sock'
        stream = Path(temp) / 'migration.bin'
        common = [str(a.qemu.resolve()), '-machine', 'virt,gic-version=3',
                  '-accel', 'tcg,thread=multi', '-cpu', 'max', '-smp', '2', '-m', '128M',
                  '-nic', 'none', '-nographic', '-monitor', 'none',
                  '-kernel', str((a.output / 'dirty.elf').resolve())]
        cmd = common + ['-qmp', f'unix:{endpoint},server=on,wait=off',
                        '-qtest', f'unix:{qtest},server=on,wait=off']
        with (a.output / 'serial.log').open('w') as log:
            proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
            dest = None
            try:
                deadline = time.monotonic() + 10
                while not endpoint.exists() and time.monotonic() < deadline:
                    time.sleep(0.02)
                q = QMP(endpoint)
                while 'DCZ_MIGRATION_READY' not in (a.output / 'serial.log').read_text():
                    assert time.monotonic() < deadline
                    time.sleep(0.02)
                q.execute('migrate-set-parameters', {'max-bandwidth': 4 * 1024 * 1024,
                                                    'downtime-limit': 1})
                q.execute('migrate', {'uri': f'exec:cat > {shlex.quote(str(stream))}'})
                deadline = time.monotonic() + 30
                while True:
                    before = q.execute('query-migrate')
                    assert before['status'] not in ('failed', 'completed'), before
                    if before.get('ram', {}).get('transferred', 0) >= 8 * 1024 * 1024:
                        break
                    assert time.monotonic() < deadline, before
                    time.sleep(0.02)
                # Release the guest after >=8MiB of nonzero RAM already migrated.
                # All subsequent 16MiB bulk modifications are DC ZVA instructions.
                with socket.socket(socket.AF_UNIX) as release:
                    release.settimeout(5)
                    release.connect(str(qtest))
                    release.sendall(f'writel 0x{go:x} 1\n'.encode())
                    assert release.recv(128).startswith(b'OK')
                while 'DCZ_MIGRATION_CLEARED' not in (a.output / 'serial.log').read_text():
                    assert time.monotonic() < deadline
                    time.sleep(0.02)
                q.execute('migrate-set-parameters', {'max-bandwidth': 256 * 1024 * 1024})
                while True:
                    result = q.execute('query-migrate')
                    if result['status'] == 'completed':
                        break
                    assert result['status'] != 'failed', result
                    assert time.monotonic() < deadline, result
                    time.sleep(0.05)
                q.execute('quit')
                proc.wait(timeout=10)
                destination_endpoint = Path(temp) / 'dest-qmp.sock'
                dest_log = (a.output / 'destination.log').open('w')
                dest = subprocess.Popen(common + ['-S', '-incoming', f'exec:cat {shlex.quote(str(stream))}',
                     '-qmp', f'unix:{destination_endpoint},server=on,wait=off'],
                     stdout=dest_log, stderr=subprocess.STDOUT)
                deadline = time.monotonic() + 15
                while not destination_endpoint.exists():
                    assert time.monotonic() < deadline
                    time.sleep(0.02)
                d = QMP(destination_endpoint)
                while d.execute('query-status')['status'] == 'inmigrate':
                    assert time.monotonic() < deadline
                    time.sleep(0.05)
                d.execute('stop')
                dump = Path(temp) / 'ram.bin'
                d.execute('pmemsave', {'val': 0x41000000, 'size': 16 * 1024 * 1024,
                                      'filename': str(dump)})
                data = dump.read_bytes()
                assert len(data) == 16 * 1024 * 1024 and not any(data), 'lost migrated ZVA writes'
                d.execute('quit')
                dest.wait(timeout=10)
                dest_log.close()
                result['before_guest_zva'] = before
                result['verified_destination_zero_bytes'] = len(data)
                result['translated_target_pages'] = 4096
                result['test'] = 'migration dirties from DC ZVA retransmitted after >=8MiB sent; destination matches all 16MiB'
                (a.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
            finally:
                for running in (proc, dest):
                    if running and running.poll() is None:
                        running.terminate()
                        try:
                            running.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            running.kill()
                            running.wait(timeout=10)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
