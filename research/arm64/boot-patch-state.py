#!/usr/bin/env python3
"""Isolated junior check, then bounded normal /init observation on a new image."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import select
import subprocess
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('isolated', 'normal'))
    options = parser.parse_args()
    script = Path(__file__).resolve().parent
    work = script / 'work'
    image = work / 'test-sata-patch-state.img'
    if image.is_symlink() or not image.is_file() or image.resolve().parent != work.resolve():
        raise SystemExit('Expected regular new disposable research image')
    if subprocess.check_output(['losetup','-j',str(image)],text=True).strip():
        raise SystemExit('Unmount and detach the image first')
    isolated = options.mode == 'isolated'
    if not isolated:
        evidence = json.loads((work/'patch-isolated-result.json').read_text())
        if evidence.get('check_exit_status') != 0 or evidence.get('image') != str(image):
            raise SystemExit('Normal boot requires a proven isolated exit status 0 for this image')
    env = os.environ.copy()
    env['LD_LIBRARY_PATH'] = ':'.join(str(work/path) for path in (
        'tools/qemu-root/usr/lib/x86_64-linux-gnu','tools/root/usr/lib/x86_64-linux-gnu',
        'tools/qemu-build-env/root/usr/lib/x86_64-linux-gnu'))
    stock = {'zImage.Image':'4c6584070c2bfee8a7ab1b73ef74d1872a0469700e61fc806e6b72d23e576b14',
             'rd.bin.cpio':'3177c1be9dbc40224c5ad193d7ad032e74c83ce54e5d436ebec209b26384a2bf'}
    hashes = {name:hashlib.sha256((work/'boot'/name).read_bytes()).hexdigest() for name in ('zImage.Image','rd.bin.cpio')}
    if hashes != stock:
        raise SystemExit('This experiment requires the exact stock DS124 72806 kernel and rd.bin')
    mode_init = '/bin/sh' if isolated else '/init'
    args=[str(work/'qemu-system-aarch64'),'-machine','virt,accel=tcg,gic-version=3',
          '-cpu','max,lpa2=off','-smp','2','-m','2048','-nic','none',
          '-kernel',str(work/'boot/zImage.Image'),'-initrd',str(work/'boot/rd.bin.cpio'),
          '-append','earlycon=uart8250,mmio32,0x0b000000 console=ttyS0,115200 initcall_debug keep_bootcon ignore_loglevel loglevel=8 printk.time=1 rdinit='+mode_init+' pty.legacy_count=0 root=/dev/sata1p1',
          '-nographic','-monitor','none','-serial','null','-serial','stdio','-no-reboot',
          '-drive',f'file={image},format=raw,if=ide,index=0']
    if not isolated:
        args += ['-gdb','tcp:127.0.0.1:12348']
    name = 'patch-isolated' if isolated else 'patch-normal-init'
    (work/f'{name}-command.json').write_text(json.dumps(args,indent=2)+'\n')
    commands = '''
mount -t proc proc /proc 2>/dev/null || true
mount -t sysfs sysfs /sys 2>/dev/null || true
mount -t devtmpfs devtmpfs /dev 2>/dev/null || true
mkdir -p /tmpRoot
mount -t ext4 -o prjquota,rootprjquota,barrier=1,noatime /dev/sata1p1 /tmpRoot
echo MOUNT_RC=$?
echo PATCH_VERSION_BEGIN
ls -ldn /tmpRoot/.syno /tmpRoot/.syno/patch
ls -ln /tmpRoot/.syno/patch
cat /tmpRoot/.syno/patch/VERSION
echo PATCH_VERSION_END
/usr/syno/sbin/check_root_junior_match.sh /tmpRoot >/tmp/junior.stdout 2>/tmp/junior.stderr
check_rc=$?
echo JUNIOR_STDOUT_BEGIN
cat /tmp/junior.stdout
echo JUNIOR_STDOUT_END
echo JUNIOR_STDERR_BEGIN
cat /tmp/junior.stderr
echo JUNIOR_STDERR_END
echo JUNIOR_EXIT_STATUS=$check_rc
cat /proc/partitions
sync
umount /tmpRoot
echo PATCH_ISOLATED_DONE
'''
    started=time.monotonic()
    reason='600-second observation bound'
    sent=False
    debugger=None
    debuglog=None
    check_rc=None
    with (work/f'{name}.log').open('wb') as log:
        proc=subprocess.Popen(args,env=env,stdin=subprocess.PIPE if isolated else subprocess.DEVNULL,
                              stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        buf=b''
        failure_at=None
        try:
            while time.monotonic()-started<600 and proc.poll() is None:
                if debugger is not None and debugger.poll() is not None:
                    reason='debugger exited before boot conclusion'
                    break
                if select.select([proc.stdout],[],[],0.5)[0]:
                    chunk=os.read(proc.stdout.fileno(),65536)
                    if not chunk:
                        reason='serial stream ended';break
                    log.write(chunk);log.flush()
                    buf=(buf+chunk)[-131072:]
                    if isolated and not sent and b'BusyBox v1.30.1' in buf and b'\n# ' in buf:
                        proc.stdin.write(('\n'+commands).encode());proc.stdin.flush()
                        sent=True
                        print('Isolated official consistency check sent',flush=True)
                    if isolated:
                        match=re.search(rb'JUNIOR_EXIT_STATUS=(\d+)\r?\n',buf)
                        if match:check_rc=int(match[1])
                        # Require shell's command-completion line, not echoed input.
                        if b'\r\nPATCH_ISOLATED_DONE\r\n' in buf:
                            reason='isolated consistency check completed';break
                    elif debugger is None and b'Mounting /dev/sata1p1 /tmpRoot' in buf:
                        debuglog=(work/'patch-normal-exec-trace.txt').open('w')
                        debugger=subprocess.Popen([str(work/'tools/root/usr/bin/gdb-multiarch'),'-q','-batch',
                            str(work/'recovered.elf'),'-x',str(script/'trace-patch-state.gdb')],
                            env=env,stdout=debuglog,stderr=subprocess.STDOUT)
                    if not isolated and failure_at is None and any(marker in buf for marker in (
                        b'linuxrc.syno failed on',b'Kernel panic',b'Exit on error [',b'[FAILED]')):
                        failure_at=time.monotonic();reason=('first systemd unit failure captured' if b'[FAILED]' in buf else 'first normal boot fatal failure captured')
                        print(reason,flush=True)
                if failure_at is not None and time.monotonic()-failure_at>5:break
        finally:
            stopped=proc.poll() is None
            if stopped:proc.terminate()
            try:proc.wait(timeout=8)
            except subprocess.TimeoutExpired:proc.kill();proc.wait()
            log.write(proc.stdout.read())
            if debugger is not None:
                try:debugger.wait(timeout=8)
                except subprocess.TimeoutExpired:debugger.terminate();debugger.wait(timeout=8)
                debuglog.close()
    result=dict(image=str(image),check_exit_status=check_rc,elapsed_seconds=round(time.monotonic()-started,2),
                stop_reason=reason,qemu_returncode=proc.returncode,terminated_by_harness=stopped,
                stock_boot_sha256=hashes)
    (work/f'{name}-result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result),flush=True)
    if isolated and check_rc != 0:raise SystemExit('Isolated check did not prove success; do not normal-boot')


if __name__=='__main__':
    main()
