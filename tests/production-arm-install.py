#!/usr/bin/env python3
"""Local official-PAT acceptance; excluded from CI, uses only production entrypoint.

Supply a NEW storage directory on a Linux filesystem and the official PAT.
No research artifact preparation or guest configuration injection is performed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time
import urllib.request

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('pat', type=Path)
parser.add_argument('storage', type=Path)
parser.add_argument('output', type=Path)
parser.add_argument('--image', default='virtual-dsm:phase2')
parser.add_argument('--name', default='vdsm-arm-install-acceptance')
parser.add_argument('--disk-size', default='16G', help='Total single ARM disk capacity')
parser.add_argument('--http-port', type=int, default=15000)
parser.add_argument('--https-port', type=int, default=15001)
parser.add_argument('--boot-timeout', type=int, default=1800)
args = parser.parse_args()
repo = Path(__file__).resolve().parents[1]
base = 'DSM_DS124_72806'
args.storage = args.storage.resolve()
args.pat = args.pat.resolve(strict=True)
if args.storage.exists() and any(args.storage.iterdir()):
    parser.error('Use an empty storage directory; existing artifacts are never removed.')
args.storage.mkdir(parents=True, exist_ok=True)
args.output.mkdir(parents=True, exist_ok=True)


def docker(*parts):
    return subprocess.check_output(['docker', *parts], text=True, stderr=subprocess.STDOUT)


def wait_management():
    deadline = time.monotonic() + args.boot_timeout
    while time.monotonic() < deadline:
        if docker('inspect', '--format', '{{.State.Running}}', args.name).strip() != 'true':
            raise RuntimeError('Production container exited: ' + docker('logs', '--tail', '25', args.name))
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{args.http_port}/', timeout=5) as response:
                if response.status == 200:
                    return
        except (OSError, TimeoutError):
            pass
        time.sleep(10)
    raise TimeoutError('DSM management boot timeout; retain storage and inspect container logs.')


def snapshot():
    manifest = json.loads((args.storage / (base + '.arm.json')).read_text())
    return {'generation': str((args.storage / (base + '.arm-current')).resolve()),
            'manifest': manifest,
            'mtimes_ns': {n: (args.storage / (base + '.' + n)).stat().st_mtime_ns for n in ('kernel', 'initrd', 'system.img')},
            'sha256': {n: hashlib.file_digest((args.storage / (base + '.' + n)).open('rb'), 'sha256').hexdigest()
                       for n in ('kernel', 'initrd')}}


# Simulate a previous interrupted attempt, containing no usable generation.
abandoned = args.storage / '.rtd1619b-install-interrupted'
abandoned.mkdir(mode=0o700)
(abandoned / 'kernel.tmp').write_bytes(b'partial kernel')
(abandoned / 'system.img.tmp').write_bytes(b'partial filesystem')
(abandoned / 'manifest.tmp').write_text('{')
docker('create', '--name', args.name, '-e', 'DSM_PLATFORM=rtd1619b', '-e', 'NETWORK=user',
       '-e', 'DEBUG=Y', '-e', 'DISK_SIZE=' + args.disk_size, '-e', 'URL=file:///input/official.pat',
       '-p', f'127.0.0.1:{args.http_port}:5000', '-p', f'127.0.0.1:{args.https_port}:5001',
       '-v', f'{args.storage}:/storage', '-v', f'{args.pat}:/input/official.pat:ro', args.image)
docker('start', args.name)
wait_management()
assert not abandoned.exists(), 'Abandoned private build was not cleaned'
subprocess.run(['python3', str(repo / 'tests/production-arm-management.py'), args.name,
                str(args.output / 'first'), '--requests', '30', '--interval', '6'], check=True)
docker('stop', '-t', '60', args.name)
first = snapshot()
(args.output / 'stopped-first.json').write_text(json.dumps(first, indent=2) + '\n')
# Cache-only restart: prove boot has not needed the source PAT/extracted root.
second_start = docker('inspect', '--format', '{{.State.FinishedAt}}', args.name).strip()
docker('start', args.name)
# Check hashes before guest writes by observing cache logging and generation/mtime.
wait_management()
second_logs = docker('logs', '--since', second_start, args.name)
assert 'ARM artifact cache hit' in second_logs
assert 'Extracting installation image' not in second_logs and 'Building system filesystem' not in second_logs
assert str((args.storage / (base + '.arm-current')).resolve()) == first['generation']
receipt = json.loads(next(line.split(': ', 1)[1] for line in second_logs.splitlines() if line.startswith('ARM cache verified: ')))
assert receipt['artifacts'] == first['manifest']['artifacts']
assert receipt['mtimes_ns'] == first['mtimes_ns']
subprocess.run(['python3', str(repo / 'tests/production-arm-management.py'), args.name,
                str(args.output / 'restart'), '--requests', '30', '--interval', '6'], check=True)
docker('stop', '-t', '60', args.name)
second = snapshot()
(args.output / 'stopped-restart.json').write_text(json.dumps(second, indent=2) + '\n')
(args.output / 'restart-startup.log').write_text(second_logs)
assert first['sha256']['kernel'] == second['sha256']['kernel']
assert first['sha256']['initrd'] == second['sha256']['initrd']
docker('run', '--rm', '--entrypoint', 'python3', '-v', f'{repo}:/repo:ro',
       '-v', f'{args.storage}:/storage:ro', '-v', f'{args.output.resolve()}:/output', args.image,
       '/repo/tests/production-arm-install-evidence.py', '/storage/' + base + '.system.img', '/output')
print('A5: official PAT, production first boot, 30 HTTP/HTTPS checks, interrupted recovery, cached restart.')
print('System image is guest-writable; use immutable boot provenance and generation reuse as cache evidence.')
