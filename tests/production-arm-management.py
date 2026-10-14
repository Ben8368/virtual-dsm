#!/usr/bin/env python3
"""Read-only checks against an ARM guest launched through the production entrypoint."""
import argparse
import json
from pathlib import Path
import ssl
import subprocess
import time
import urllib.request

parser = argparse.ArgumentParser()
parser.add_argument('container', help='Already running production container; never starts a research launcher')
parser.add_argument('output', type=Path, help='Ignored output directory')
parser.add_argument('--requests', type=int, default=30)
parser.add_argument('--interval', type=float, default=6)
parser.add_argument('--timeout', type=float, default=45)
opts = parser.parse_args()
if not 1 <= opts.requests <= 100 or not 0 <= opts.interval <= 60:
    parser.error('Invalid request count or interval')
opts.output.mkdir(parents=True, exist_ok=True)


def docker(*args):
    return subprocess.check_output(['docker', *args], text=True, stderr=subprocess.STDOUT)


inspection = json.loads(docker('inspect', opts.container))[0]
assert inspection['Config']['Entrypoint'] == ['/usr/bin/tini', '-s', '/run/entry.sh']
assert 'DSM_PLATFORM=rtd1619b' in inspection['Config']['Env']
ports = inspection['NetworkSettings']['Ports']
http_port = ports['5000/tcp'][0]
https_port = ports['5001/tcp'][0]
assert http_port['HostIp'] == https_port['HostIp'] == '127.0.0.1', 'Regression requires loopback publication'
process = json.loads(docker('exec', opts.container, 'python3', '-c',
    "import json,os; from pathlib import Path; pid=Path('/run/shm/qemu.pid').read_text().strip(); "
    "print(json.dumps({'executable':os.readlink('/proc/'+pid+'/exe'), "
    "'argv':Path('/proc/'+pid+'/cmdline').read_bytes().decode().rstrip(chr(0)).split(chr(0))}))"))
assert process['executable'] == '/usr/local/bin/qemu-system-aarch64'
argv = process['argv']
for required in ('virt,gic-version=3', 'max,lpa2=off', 'tcg,thread=multi',
                 '/storage/DSM_DS124_72806.kernel', '/storage/DSM_DS124_72806.initrd',
                 'file=/storage/DSM_DS124_72806.system.img,format=raw,if=ide,index=0'):
    assert required in argv, required
assert not any(any(bad in arg for bad in ('q35', 'smm=', 'hpet=', 'vmport=', 'virtio-', 'synoboot', 'synosys')) for arg in argv)
assert 'null' in argv and 'stdio' in argv and any(arg.startswith('usb-net,') for arg in argv)
(opts.output / 'arm-process.json').write_text(json.dumps(process, indent=2) + '\n')
results = []
for count in range(opts.requests):
    started = time.monotonic()
    with urllib.request.urlopen('http://127.0.0.1:' + http_port['HostPort'] + '/', timeout=opts.timeout) as response:
        result = {'request': count + 1, 'status': response.status,
                  'server': response.headers.get('Server'), 'bytes': len(response.read()),
                  'seconds': round(time.monotonic() - started, 3)}
    results.append(result)
    assert result['status'] == 200 and result['server'] == 'nginx', result
    (opts.output / 'management-requests.json').write_text(json.dumps(results, indent=2) + '\n')
    if (count + 1) % 5 == 0:
        print(f'Management HTTP 200: {count + 1}/{opts.requests}', flush=True)
    if count + 1 < opts.requests:
        time.sleep(opts.interval)
with urllib.request.urlopen('https://127.0.0.1:' + https_port['HostPort'] + '/',
                            context=ssl._create_unverified_context(), timeout=opts.timeout) as response:
    assert response.status == 200
    response.read()
    https = {'status': response.status, 'server': response.headers.get('Server'),
             'certificate_verification': 'disabled for DSM self-signed test certificate'}
(opts.output / 'https-result.json').write_text(json.dumps(https, indent=2) + '\n')
serial = docker('logs', opts.container)
(opts.output / 'arm-serial.log').write_text(serial)
assert 'systemd[1]' in serial and 'sata1p1' in serial and 'console [ttyS0] enabled' in serial
assert 'xhci-hcd' in serial and 'cdc_ether' in serial and 'eth0' in serial
assert not any(marker in serial for marker in ('soft lockup', 'queued_write_lock_slowpath',
    'Unable to handle kernel NULL pointer', 'Internal error: Oops', 'BUG: unable to handle'))
print(f'Production ARM management checks passed: {len(results)} HTTP 200, HTTPS 200, no serial soft lockup.', flush=True)
