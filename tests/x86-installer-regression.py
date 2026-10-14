#!/usr/bin/env python3
"""Reconstitute the pre-Phase-2 installer and prove its exact known byte hash."""
import hashlib
from pathlib import Path
repo = Path(__file__).resolve().parents[1]
installer = (repo / 'src/install.sh').read_text()
common = (repo / 'src/pat.sh').read_text()
original = installer.replace('# shellcheck source=src/pat.sh\n. /run/pat.sh\n\n', common[common.index('downloadFile() {'):common.index('# The caller declares local mirror;')])
mirror = common.split('selectDsmMirror() {\n', 1)[1].rsplit('  return 0\n}', 1)[0]
original = original.replace('  selectDsmMirror || return $?\n\n', mirror)
assert hashlib.sha256(original.encode()).hexdigest() == '81425505360ea2e546c8c32fdc47e3e8f0d86398bdc2391e9a205a5fda564efe'
print('Original x86 installer byte hash verified after rejoining shared PAT functions.')
