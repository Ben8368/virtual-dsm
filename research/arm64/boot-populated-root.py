#!/usr/bin/env python3
"""Bounded normal /init boot of the disposable, manually populated p1 image."""
import json
import os
from pathlib import Path
import select
import subprocess
import time


def main():
    work = Path(__file__).resolve().parent / 'work'
    image = work / 'test-sata-root-populated.img'
    if image.is_symlink() or not image.is_file() or image.resolve().parent != work.resolve():
        raise SystemExit('Expected regular disposable image inside research work directory')
    attached = subprocess.check_output(['losetup', '-j', str(image)], text=True)
    if attached.strip():
        raise SystemExit('Unmount and detach the population loop before booting')
    env = os.environ.copy()
    env['LD_LIBRARY_PATH'] = ':'.join(str(work / path) for path in (
        'tools/qemu-root/usr/lib/x86_64-linux-gnu',
        'tools/root/usr/lib/x86_64-linux-gnu',
        'tools/qemu-build-env/root/usr/lib/x86_64-linux-gnu',
    ))
    args = [str(work / 'qemu-system-aarch64'),
            '-machine', 'virt,accel=tcg,gic-version=3', '-cpu', 'max,lpa2=off',
            '-smp', '2', '-m', '2048', '-nic', 'none',
            '-kernel', str(work / 'boot/zImage.Image'),
            '-initrd', str(work / 'boot/rd.bin.cpio'),
            '-append', 'earlycon=uart8250,mmio32,0x0b000000 console=ttyS0,115200 initcall_debug keep_bootcon ignore_loglevel loglevel=8 printk.time=1 rdinit=/init pty.legacy_count=0 root=/dev/sata1p1',
            '-nographic', '-monitor', 'none', '-serial', 'null', '-serial', 'stdio',
            '-no-reboot', '-drive', f'file={image},format=raw,if=ide,index=0']
    trace = os.environ.get('TRACE_EXEC') == '1'
    debugger = None
    debuglog = None
    if trace:
        import hashlib
        if hashlib.sha256((work / 'boot/zImage.Image').read_bytes()).hexdigest() != '4c6584070c2bfee8a7ab1b73ef74d1872a0469700e61fc806e6b72d23e576b14':
            raise SystemExit('Trace addresses require the stock recovered DS124 72806 Image')
        args += ['-gdb', 'tcp:127.0.0.1:12347']
    suffix = '-traced' if trace else ''
    (work / f'root-populated-boot-command{suffix}.json').write_text(json.dumps(args, indent=2) + '\n')
    logpath = work / f'root-populated-normal-init{suffix}.log'
    started = time.monotonic()
    reason = '600-second observation limit'
    print(f'Normal /init boot; full serial log: {logpath}', flush=True)
    with logpath.open('wb') as log:
        proc = subprocess.Popen(args, env=env, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        buf = b''
        failure_at = None
        try:
            while time.monotonic() - started < 600 and proc.poll() is None:
                if debugger is not None and debugger.poll() is not None:
                    reason = 'execution debugger exited before normal boot conclusion'
                    print(reason, flush=True)
                    break
                if select.select([proc.stdout], [], [], 0.5)[0]:
                    chunk = os.read(proc.stdout.fileno(), 65536)
                    if not chunk:
                        reason = 'serial stream ended'
                        break
                    log.write(chunk)
                    log.flush()
                    buf = (buf + chunk)[-65536:]
                    if trace and debugger is None and b'Mounting /dev/sata1p1 /tmpRoot' in buf:
                        debuglog = (work / 'root-populated-exec-trace.txt').open('w')
                        debugger = subprocess.Popen([
                            str(work / 'tools/root/usr/bin/gdb-multiarch'), '-q', '-batch',
                            str(work / 'recovered.elf'), '-x',
                            str(Path(__file__).resolve().parent / 'trace-populated-root.gdb')],
                            env=env, stdout=debuglog, stderr=subprocess.STDOUT)
                    if failure_at is None and any(marker in buf for marker in (
                            b'linuxrc.syno failed on', b'Kernel panic', b'Exit on error [')):
                        failure_at = time.monotonic()
                        reason = 'first normal boot fatal failure captured'
                        print(reason, flush=True)
                if failure_at is not None and time.monotonic() - failure_at > 5:
                    break
        finally:
            terminated_by_harness = proc.poll() is None
            if terminated_by_harness:
                proc.terminate()
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            log.write(proc.stdout.read())
            if debugger is not None:
                try:
                    debugger.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    debugger.terminate()
                    debugger.wait(timeout=8)
                debuglog.close()
    result = dict(elapsed_seconds=round(time.monotonic() - started, 2),
                  stop_reason=reason, qemu_returncode=proc.returncode,
                  terminated_by_harness=terminated_by_harness, serial_bytes=logpath.stat().st_size)
    (work / f'root-populated-boot-result{suffix}.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
