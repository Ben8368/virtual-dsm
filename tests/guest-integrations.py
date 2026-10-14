#!/usr/bin/env python3
"""Verify new-seed writes cannot follow a guest-absolute symlink outside root."""
import importlib.util
from pathlib import Path
import tarfile
import tempfile
from unittest.mock import patch

repo = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('integration', repo / 'src/platform/guest_integrations.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def entry(name):
    return tarfile.TarInfo(name), b'SYNTHETIC PACKAGE'


def rejected(action):
    try:
        action()
    except ValueError:
        return
    raise AssertionError('Unsafe integration accepted')


with tempfile.TemporaryDirectory() as temporary, patch.object(module.os, 'chown'):
    base = Path(temporary)
    outside = base / 'outside'
    outside.mkdir()
    root = base / 'root'
    root.mkdir()
    (root / '.SynoUpgradePackages').symlink_to(outside, target_is_directory=True)
    rejected(lambda: module.integrate(root, {'packages/' + module.STORAGE_PACKAGE: entry(module.STORAGE_PACKAGE)}))
    assert not list(outside.iterdir())
    rejected(lambda: module.integrate(root, {'packages/../escape.spk': entry('../escape.spk')}))
    (root / '.SynoUpgradePackages').unlink()
    rejected(lambda: module.integrate(root, {}))
    rejected(lambda: module.put(root, '../outside/escape', b'ESCAPE'))
    rejected(lambda: module.put(root, str(outside / 'escape'), b'ESCAPE'))
    assert not list(outside.iterdir())
    marker = root / 'already'
    marker.write_bytes(b'PRESERVE')
    rejected(lambda: module.put(root, 'already', b'REPLACE'))
    assert marker.read_bytes() == b'PRESERVE'
print('Guest integration safety passed (absolute links, path traversal, missing prerequisite, no overwrite).')
