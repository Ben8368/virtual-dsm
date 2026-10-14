#!/usr/bin/env python3
"""Keep proprietary DSM payloads and private build trees out of tracked files."""
from pathlib import PurePosixPath
import subprocess

tracked = subprocess.check_output(['git', 'ls-files', '-z'], text=True).rstrip('\0').split('\0')
for name in tracked:
    path = PurePosixPath(name)
    if path.suffix.lower() in {'.pat', '.img', '.kernel', '.initrd', '.ko', '.cpio', '.initramfs', '.spk'}:
        raise AssertionError('Tracked runtime payload: ' + name)
    if path.name in {'Image', 'zImage', 'hda1.tgz'} or path.name.startswith('rd.bin'):
        raise AssertionError('Tracked DSM boot/root payload: ' + name)
    if any(part in {'.syno', 'hda1', 'storage'} or part.startswith('.rtd1619b-install-') or '.arm-generation-' in part for part in path.parts):
        raise AssertionError('Tracked private install tree: ' + name)
    if name.startswith('research/arm64/work/'):
        raise AssertionError('Tracked research work file: ' + name)
print('Tracked-artifact policy passed: no DSM PAT, boot/root/module payloads or private work trees.')
