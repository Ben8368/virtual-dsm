#!/usr/bin/env python3
"""Exercise the default production x86 command with a fake QEMU executable."""
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile


repo = Path(__file__).resolve().parent.parent
bash_candidates = ['/opt/homebrew/bin/bash', shutil.which('bash')]
bash = next((candidate for candidate in bash_candidates if candidate and
             subprocess.run([candidate, '-c', '((BASH_VERSINFO[0] >= 4))'],
                            check=False).returncode == 0), None)
if bash is None:
    raise SystemExit('FAIL: Bash 4 or newer is required by the production scripts')
with tempfile.TemporaryDirectory(prefix='virtualdsm-x86-command-') as tmp:
    directory = Path(tmp)
    bin_dir = directory / 'bin'
    bin_dir.mkdir()
    capture = directory / 'argv.json'
    network_log = directory / 'unexpected-network.log'

    qemu = bin_dir / 'qemu-system-x86_64'
    qemu.write_text(
        f'#!{sys.executable}\n'
        'import json, os, sys\n'
        'from pathlib import Path\n'
        'Path(os.environ["ARGV_CAPTURE"]).write_text(json.dumps(sys.argv[1:]))\n'
        'raise SystemExit(37)\n'
    )
    qemu.chmod(0o755)

    # Any accidental attempt to use a common downloader fails locally and is
    # recorded. The harness itself does not source installer or PAT code.
    for name in ('curl', 'wget'):
        stub = bin_dir / name
        stub.write_text(
            '#!/bin/sh\n'
            'printf "%s\\n" "$0 $*" >> "$NETWORK_ATTEMPT_LOG"\n'
            'echo UNEXPECTED_NETWORK_ACCESS >&2\n'
            'exit 86\n'
        )
        stub.chmod(0o755)

    bash_script = r'''
set -Eeuo pipefail
[[ "${X86_TEST_TRACE:-}" != 1 ]] || set -x
cd "$REPO"
. src/platform/common.sh
unset DSM_PLATFORM PLATFORM GUEST_ARCH QEMU_BIN MACHINE BOOT_MODE
platformInit
[[ "$DSM_PLATFORM:$GUEST_ARCH:$PLATFORM:$QEMU_BIN:$MACHINE:$BOOT_MODE" == \
   virtualdsm:amd64:x64:qemu-system-x86_64:q35:legacy ]]
ARGS=$(bash tests/fixtures/x86-baseline.sh)
diff -u tests/fixtures/virtualdsm.args <(printf '%s\n' "$ARGS")
platformBuildCommand
platformValidateBinary
last=$((${#QEMU_ARGS[@]} - 1))
[[ "${QEMU_ARGS[$last]}" == "virtio-balloon-pci,id=balloon0,bus=pcie.0,addr=0x4" ]]
[[ "${QEMU_ARGS[$last-1]}" == -device ]]
"$QEMU_BIN" "${QEMU_ARGS[@]}"
'''
    env = os.environ.copy()
    env.update({
        'REPO': str(repo),
        'PATH': str(bin_dir) + os.pathsep + str(Path(bash).parent) + os.pathsep + env.get('PATH', '/usr/bin:/bin'),
        'ARGV_CAPTURE': str(capture),
        'NETWORK_ATTEMPT_LOG': str(network_log),
        'X86_TEST_TRACE': env.get('X86_TEST_TRACE', ''),
    })
    process = subprocess.Popen(
        [bash, '-c', bash_script], cwd=repo, env=env,
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=30)
    except subprocess.TimeoutExpired as exc:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.communicate()
        raise SystemExit('FAIL: x86 production command timed out after 30 seconds') from exc

    if process.returncode != 37:
        sys.stderr.write(stdout)
        sys.stderr.write(stderr)
        raise SystemExit(f'FAIL: fake QEMU expected exit 37, got {process.returncode}')
    if network_log.exists():
        raise SystemExit('FAIL: downloader stub observed unexpected network access')
    if not capture.is_file():
        raise SystemExit('FAIL: fake QEMU did not capture argv')

    actual = json.loads(capture.read_text())
    expected = shlex.split((repo / 'tests/fixtures/virtualdsm.args').read_text())
    if actual != expected:
        raise SystemExit('FAIL: production QEMU argv differs from accepted x86 snapshot')
    if actual[actual.index('-machine') + 1] != (
        'type=q35,smm=off,usb=off,vmport=off,dump-guest-core=off,hpet=off,accel=kvm'
    ):
        raise SystemExit('FAIL: expected accepted q35 machine arguments')
    if actual[actual.index('-boot') + 1] != 'strict=on':
        raise SystemExit('FAIL: expected legacy strict boot arguments')

print('Default x86 production command passed: virtualdsm/x64, snapshot argv, fake QEMU exit 37, no PAT/network, 30s timeout.')
