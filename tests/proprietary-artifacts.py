#!/usr/bin/env python3
"""Keep proprietary DSM payloads and private build trees out of tracked files."""
from pathlib import PurePosixPath
import subprocess

root = subprocess.check_output(['git', 'rev-parse', '--show-toplevel'], text=True).strip()

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
dockerignore = open(root + '/.dockerignore', encoding='utf-8').read().splitlines()
required_context_exclusions = {'research/', 'storage/', '*.pat', '*.img', '*.bin', '*.kernel', '*.initrd'}
if not required_context_exclusions.issubset({line.strip() for line in dockerignore}):
    raise AssertionError('Docker context does not exclude proprietary/private runtime artifacts')
gitignore = open(root + '/.gitignore', encoding='utf-8').read()
if 'research/arm64/work/' not in gitignore:
    raise AssertionError('Private ARM research work tree is not ignored')
dockerfile = open(root + '/Dockerfile', encoding='utf-8').read()
if 'COPY research/' in dockerfile or 'COPY storage/' in dockerfile:
    raise AssertionError('Dockerfile copies a private runtime or research tree')
publish = open(root + '/.github/workflows/build.yml', encoding='utf-8').read()
if 'path: ${{ runner.temp }}/digests/*' not in publish:
    raise AssertionError('Release workflow artifact must remain limited to image digest receipts')
print('Artifact policy passed: no tracked DSM payloads; PAT/runtime trees are excluded from Git, Docker context, and CI artifacts.')
