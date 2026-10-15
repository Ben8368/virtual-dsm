#!/usr/bin/env python3
"""RSP test of DC ZVA's whole-block watchpoint before any RAM change."""
import argparse
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import tempfile
import time


class RSP:
    def __init__(self, sock):
        self.sock = sock

    def receive(self, size):
        data = bytearray()
        while len(data) < size:
            chunk = self.sock.recv(size - len(data))
            if not chunk:
                raise EOFError('GDB disconnected')
            data.extend(chunk)
        return bytes(data)

    def send(self, text):
        data = text.encode()
        self.sock.sendall(b'$' + data + b'#' + f'{sum(data) & 255:02x}'.encode())
        while True:
            ch = self.receive(1)
            if ch == b'$':
                break
        packet = bytearray()
        while True:
            ch = self.receive(1)
            if ch == b'#':
                break
            packet.extend(ch)
        checksum = self.receive(2)
        assert int(checksum, 16) == sum(packet) & 255
        try:
            self.sock.sendall(b'+')
        except BrokenPipeError:
            if not packet.startswith(b'W'):
                raise
        return packet.decode()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('qemu', type=Path)
    p.add_argument('elf', type=Path)
    p.add_argument('output', type=Path)
    a = p.parse_args()
    syms = subprocess.check_output([os.environ.get('AARCH64_NM', 'aarch64-linux-gnu-nm'), str(a.elf)], text=True)
    marker = int(re.search(r'^([0-9a-f]+) T watchpoint_marker$', syms, re.M)[1], 16)
    data = int(re.search(r'^([0-9a-f]+) b data$', syms, re.M)[1], 16)
    a.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='dcz-rsp-') as temp:
        endpoint = Path(temp) / 'gdb.sock'
        cmd = [str(a.qemu.resolve()), '-machine', 'virt,gic-version=3',
               '-accel', 'tcg,thread=multi', '-cpu', 'max', '-smp', '2', '-m', '128M',
               '-nic', 'none', '-nographic', '-monitor', 'none',
               '-semihosting-config', 'enable=on,target=native', '-kernel', str(a.elf.resolve()),
               '-S', '-gdb', f'unix:{endpoint},server=on,wait=off']
        with (a.output / 'serial.log').open('w') as log:
            proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
            try:
                deadline = time.monotonic() + 10
                while not endpoint.exists() and time.monotonic() < deadline:
                    time.sleep(0.02)
                with socket.socket(socket.AF_UNIX) as sock:
                    sock.settimeout(30)
                    sock.connect(str(endpoint))
                    r = RSP(sock)
                    assert r.send(f'Z0,{marker:x},4') == 'OK'
                    assert r.send('c').startswith('T05')
                    assert r.send(f'z0,{marker:x},4') == 'OK'
                    # Watch only the last byte; the architectural input is block start.
                    assert r.send(f'Z2,{data + 63:x},1') == 'OK'
                    before = r.send(f'm{data:x},40')
                    stopped = r.send('c')
                    assert stopped.startswith('T05') and 'watch:' in stopped, stopped
                    after = r.send(f'm{data:x},40')
                    assert before == after, 'watchpoint must stop before memset'
                    watch_stops = [stopped]
                    assert r.send(f'z2,{data + 63:x},1') == 'OK'
                    exited = r.send('c')
                    assert exited == 'W00', exited
                proc.wait(timeout=10)
                assert proc.returncode == 0
                (a.output / 'result.json').write_text(json.dumps({'watch_stops': watch_stops, 'count': len(watch_stops)}, indent=2) + '\n')
                (a.output / 'result.txt').write_text(
                    f'PASS last-byte block watchpoint before RAM change: {stopped}\n'
                    'PASS normal watchpoint removal/resume executes the original ZVA and remaining SMC tests\n')
            finally:
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=10)
    print((a.output / 'result.txt').read_text(), end='')


if __name__ == '__main__':
    main()
