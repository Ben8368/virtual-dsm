#!/usr/bin/env python3
"""Bounded normal /init USB host / USB NIC experiment on the observed root copy."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import select
import signal
import subprocess
import time
import tempfile


def capture_guest_log(work, image, label):
    """Read the observer output only after QEMU has exited, without journal replay."""
    if os.geteuid() != 0:
        return b'', 'Read-only loop capture requires root', None
    loop = None
    mounted = False
    try:
        with tempfile.TemporaryDirectory(prefix='network-capture-', dir=work) as directory:
            loop = subprocess.check_output(['losetup', '--read-only', '--find', '--show',
                '--offset', '1048576', '--sizelimit', '2145749504', str(image)], text=True).strip()
            try:
                subprocess.run(['mount', '-t', 'ext4', '-o', 'ro,noload', loop, directory], check=True)
                mounted = True
                source = Path(directory) / 'var/log/arm64-network-observer.log'
                if not source.is_file() or source.is_symlink():
                    return b'', 'No regular guest observer log', None
                management = Path(directory) / 'var/log/arm64-management-observer.log'
                if management.is_file() and not management.is_symlink():
                    (work / f'{label}-guest-management.log').write_bytes(management.read_bytes())
                raw = source.read_bytes()
                output = work / f'{label}-guest-observer.log'
                output.write_bytes(raw)
                # Preserve network unit messages independently of serial progress.
                units = []
                journal = Path(directory) / 'var/log/systemd'
                for name in ('rc-network.service.log', 'SynoInitEth.service.log', 'synonetd.service.log'):
                    source_log = journal / name
                    if source_log.is_file() and not source_log.is_symlink():
                        units.append(b'\nUNIT_LOG=' + name.encode() + b'\n' + source_log.read_bytes())
                (work / f'{label}-network-unit-logs.txt').write_bytes(b''.join(units))
                return raw, None, str(output)
            finally:
                if mounted:
                    subprocess.run(['umount', directory], check=True)
                subprocess.run(['losetup', '-d', loop], check=True)
    except (OSError, subprocess.SubprocessError) as exc:
        return b'', str(exc), None


def loopback_netdev(forwards):
    """QEMU 8.2.2 hostfwd; the bind address is deliberately not configurable."""
    netdev = 'user,id=net0'
    used = set()
    for forward in forwards:
        if not re.fullmatch(r'[0-9]{1,5}:[0-9]{1,5}', forward):
            raise ValueError('Expected HOST_PORT:GUEST_PORT; host address is always 127.0.0.1')
        host, guest = map(int, forward.split(':'))
        if not 1 <= host <= 65535 or not 1 <= guest <= 65535:
            raise ValueError('Forward ports must be between 1 and 65535')
        if host in used:
            raise ValueError('Duplicate host forward port')
        used.add(host)
        netdev += f',hostfwd=tcp:127.0.0.1:{host}-10.0.2.15:{guest}'
    return netdev


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('host', 'network'))
    parser.add_argument('--seconds', type=int, default=1200)
    parser.add_argument('--disable-ncq', action='store_true', help='Diagnose observed AHCI NCQ read aborts with stock libata.force=noncq')
    parser.add_argument('--label')
    parser.add_argument('--snapshots', type=int)
    parser.add_argument('--mac', help='Optional QEMU MAC property; CDC guest MAC starts with 40 in v8.2.2')
    parser.add_argument('--host-forward', action='append', default=[], metavar='HOST_PORT:GUEST_PORT',
                        help='Opt-in TCP forwarding bound only to 127.0.0.1 (e.g. 15000:5000)')
    opts = parser.parse_args()
    if opts.host_forward and opts.mode != 'network':
        parser.error('Host forwarding requires network mode')
    try:
        netdev = loopback_netdev(opts.host_forward)
    except ValueError as exc:
        parser.error(str(exc))
    work = Path(__file__).resolve().parent / 'work'
    image = work / 'test-sata-usb-network.img'
    if not image.is_file() or image.is_symlink() or image.resolve().parent != work.resolve():
        raise SystemExit('Expected disposable observed network root image')
    if subprocess.check_output(['losetup', '-j', str(image)], text=True).strip():
        raise SystemExit('Unmount and detach the research image first')
    if opts.mode == 'network':
        evidence = json.loads((work / 'usb-host-result.json').read_text())
        if not evidence.get('host_proven'):
            raise SystemExit('Network attachment requires prior normal /init root-hub and /dev/bus/usb proof')
    env = os.environ.copy()
    env['LD_LIBRARY_PATH'] = ':'.join(str(work / p) for p in (
        'tools/qemu-build-env/root/usr/lib/x86_64-linux-gnu',
        'tools/qemu-root/usr/lib/x86_64-linux-gnu', 'tools/root/usr/lib/x86_64-linux-gnu'))
    stock = {'zImage.Image': '4c6584070c2bfee8a7ab1b73ef74d1872a0469700e61fc806e6b72d23e576b14',
             'rd.bin.cpio': '3177c1be9dbc40224c5ad193d7ad032e74c83ce54e5d436ebec209b26384a2bf'}
    hashes = {n: hashlib.sha256((work / 'boot' / n).read_bytes()).hexdigest() for n in stock}
    if hashes != stock:
        raise SystemExit('Exact unmodified stock kernel and initramfs required')
    args = [str(work / 'qemu-system-aarch64'), '-machine', 'virt,accel=tcg,gic-version=3',
            '-cpu', 'max,lpa2=off', '-smp', '2', '-m', '2048', '-nic', 'none',
            '-kernel', str(work / 'boot/zImage.Image'), '-initrd', str(work / 'boot/rd.bin.cpio'),
            '-append', 'earlycon=uart8250,mmio32,0x0b000000 console=ttyS0,115200 '
            'initcall_debug keep_bootcon ignore_loglevel loglevel=8 printk.time=1 '
            'rdinit=/init pty.legacy_count=0 root=/dev/sata1p1',
            '-nographic', '-monitor', 'none', '-serial', 'null', '-serial', 'stdio', '-no-reboot',
            '-drive', f'file={image},format=raw,if=ide,index=0']
    if opts.disable_ncq:
        args[args.index('-append') + 1] += ' libata.force=noncq'
    if opts.mode == 'network':
        device = 'usb-net,netdev=net0'
        if opts.mac:
            if not re.fullmatch(r'(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}', opts.mac):
                raise SystemExit('Expected six-byte colon-separated MAC')
            device += ',mac=' + opts.mac
        args += ['-netdev', netdev, '-device', device]
    label = opts.label or ('usb-host' if opts.mode == 'host' else 'usb-network')
    if not label.replace('-', '').isalnum():
        raise SystemExit('Label must be alphanumeric/hyphen')
    (work / f'{label}-command.json').write_text(json.dumps(args, indent=2) + '\n')
    snapshots = opts.snapshots or (1 if opts.mode == 'host' else 24)
    if not 1 <= snapshots <= 24:
        raise SystemExit('Snapshots must be between 1 and 24')
    completion = f'ARM64_NETWORK_SNAPSHOT_END={snapshots - 1}\n'.encode()
    started = time.monotonic()
    reason = 'observation time limit'
    stop_requested = False

    def request_stop(_signum, _frame):
        nonlocal stop_requested
        stop_requested = True

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    output = bytearray()
    with (work / f'{label}.log').open('wb') as log:
        proc = subprocess.Popen(args, env=env, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        try:
            while proc.poll() is None and time.monotonic() - started < opts.seconds:
                if stop_requested:
                    reason = 'explicit research observer stop request'
                    break
                if select.select([proc.stdout], [], [], 0.5)[0]:
                    chunk = os.read(proc.stdout.fileno(), 65536)
                    if not chunk:
                        break
                    log.write(chunk)
                    log.flush()
                    output.extend(chunk)
                    if b'Kernel panic' in chunk:
                        reason = 'kernel panic'
                        break
                    if completion in output.replace(b'\r', b''):
                        reason = f'{snapshots} complete normal-init observations'
                        break
                    if b'ARM64_NETWORK_OBSERVER_DONE\n' in output.replace(b'\r', b''):
                        reason = 'observer complete'
                        break
        finally:
            stopped = proc.poll() is None
            if stopped:
                proc.terminate()
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            tail = proc.stdout.read()
            log.write(tail)
            output.extend(tail)
    guest_log, capture_error, guest_log_path = capture_guest_log(work, image, label)
    raw = bytes(output) + b"\n" + guest_log
    result = dict(guest_observer_log=guest_log_path, guest_log_capture_error=capture_error, mode=opts.mode, image=str(image), command=args,
                  elapsed_seconds=round(time.monotonic() - started, 2), stop_reason=reason,
                  qemu_returncode=proc.returncode, terminated_by_harness=stopped,
                  stock_boot_sha256=hashes,
                  host_proven=all(marker in raw for marker in (
                      b'USB_DEVICE=/sys/bus/usb/devices/usb1', b'idVendor=1d6b',
                      b'/sys/bus/usb/drivers/hub', b'/dev/bus/usb/001:', b'001')),
                  observer_seen=b'ARM64_NETWORK_SNAPSHOT_END=' in raw,
                  systemd_pid1=b'systemd[1]' in raw)
    (work / f'{label}-result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
