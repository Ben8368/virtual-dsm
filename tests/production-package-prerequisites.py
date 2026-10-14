#!/usr/bin/env python3
"""Disposable official-PAT ARM smoke, never reuses or modifies an existing guest."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import time
import urllib.request

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--pat', type=Path, required=True)
parser.add_argument('--image', default='virtual-dsm:package-readiness')
parser.add_argument('--timeout', type=int, default=900)
parser.add_argument('--http-port', type=int, default=15180)
args = parser.parse_args()
args.pat = args.pat.resolve(strict=True)
if not args.pat.is_file() or not 1 <= args.http_port < 65535 or not 60 <= args.timeout <= 1800:
    parser.error('Invalid PAT, port or timeout')
name = 'vdsm-package-smoke-' + str(int(time.time()))
storage = Path(tempfile.mkdtemp(prefix='vdsm-package-readiness-', dir='/var/lib'))
print('Disposable storage: ' + str(storage), flush=True)


def docker(*parts):
    return subprocess.check_output(['docker', *parts], text=True, stderr=subprocess.STDOUT)


created = False
try:
    docker('create', '--name', name, '-e', 'DSM_PLATFORM=rtd1619b', '-e', 'KVM=N',
           '-e', 'NETWORK=user', '-e', 'DISK_SIZE=16G', '-e', 'URL=file:///input/official.pat',
           '-p', f'127.0.0.1:{args.http_port}:5000', '-p', f'127.0.0.1:{args.http_port + 1}:5001',
           '-v', f'{storage}:/storage', '-v', f'{args.pat}:/input/official.pat:ro', args.image)
    created = True
    print('Disposable container: ' + name, flush=True)
    docker('start', name)
    deadline = time.monotonic() + args.timeout
    next_progress = 0
    while time.monotonic() < deadline:
        logs = docker('logs', name)
        if docker('inspect', '--format', '{{.State.Running}}', name).strip() != 'true':
            raise RuntimeError('Disposable guest exited; inspect retained test storage/container')
        clock = 'vdsm-clock: initialized UTC from host launch time' in logs
        package = 'vdsm-packages: Storage Manager installation completed' in logs
        http = False
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{args.http_port}/', timeout=3) as response:
                http = response.status == 200
        except (OSError, TimeoutError):
            pass
        if clock and package and http:
            manifest = json.loads((storage / 'DSM_DS124_72806.arm.json').read_text())
            result = {'clock_seeded': clock, 'storage_manager_installed': package,
                      'management_http': 200, 'image': args.image,
                      'bundled_packages': list(manifest['integrations']['bundled_packages']),
                      'nvr_acceptance': 'not_tested', 'guest': 'DS124 ARM64 on amd64 TCG'}
            (storage / 'package-prerequisites.json').write_text(json.dumps(result, indent=2) + '\n')
            print(json.dumps(result, indent=2), flush=True)
            break
        if time.monotonic() >= next_progress:
            print(f'Waiting: clock={clock}, storage_manager={package}, http={http}', flush=True)
            next_progress = time.monotonic() + 30
        time.sleep(5)
    else:
        raise TimeoutError('Prerequisite smoke timed out; HTTP alone is not acceptance')
finally:
    if created:
        # Only this newly created guest; preserve its disk for postmortem inspection.
        docker('stop', '-t', '30', name)
        print('Stopped disposable container: ' + name, flush=True)
