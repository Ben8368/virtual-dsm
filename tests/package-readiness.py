#!/usr/bin/env python3
"""Exercise failure classification without credentials or a DSM payload."""
import importlib.util
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('readiness', repo / 'scripts/package-readiness.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
good = {'format': '1', 'epoch': '1704067200', 'arch': 'aarch64',
        'unique': 'synology_rtd1619b_ds124', 'volume': 'btrfs:rw,relatime',
        'pgsql': 'active', 'package.StorageManager': 'active',
        'logs.synopkg.log': 'readable', 'logs.synopkgmgr.log': 'readable',
        'network.pkgupdate.curl': '0', 'network.pkgupdate.http': '404',
        'network.download.curl': '0', 'network.download.http': '403'}
assert module.analyze(good, 1704067200)['prerequisites'] == 'passed'
assert module.analyze(good, 1704067200)['authorization'] == 'unverified'
assert module.analyze(good, 1704067200)['packages']['SurveillanceStation'] == 'unknown'
assert module.analyze({**good, 'package.StorageManager.version': '1.0.0-00502'}, 1704067200)['package_versions']['StorageManager'] == '1.0.0-00502'
for code, failure in [('6', 'dns'), ('7', 'connection'), ('28', 'timeout'), ('60', 'certificate')]:
    report = module.analyze({**good, 'network.pkgupdate.curl': code}, 1704067200)
    assert 'pkgupdate_' + failure + '_failure' in report['blockers']
assert 'guest_clock_skew' in module.analyze({**good, 'epoch': '0'}, 1704067200)['blockers']
assert 'guest_architecture_mismatch' in module.analyze({**good, 'arch': 'x86_64'}, 1704067200)['blockers']
assert 'data_volume_not_writable' in module.analyze({**good, 'volume': 'btrfs:ro'}, 1704067200)['blockers']
assert 'storage_manager_not_ready' in module.analyze({**good, 'package.StorageManager': 'failed'}, 1704067200)['blockers']
no_network = {key: value for key, value in good.items() if not key.startswith('network.')}
assert module.analyze(no_network, 1704067200)['prerequisites'] == 'incomplete'
history = module.analyze({**good, 'history.synopkgmgr.log.hwid': 'yes'}, 1704067200)
assert history['prerequisites'] == 'passed' and 'recent_history_hwid' in history['warnings']
assert 'hwid' not in ' '.join(history['blockers'])
x86 = {**good, 'unique': 'synology_kvmx64_virtualdsm', 'arch': 'x86_64'}
assert module.analyze(x86, 1704067200)['platform'] == 'virtualdsm'
assert module.parse('format\t1\nepoch\t1704067200\n')['epoch'] == '1704067200'
for bad in ('format\t2\n', 'format\t1\nformat\t1\n', 'format\t1\nx\tbad\x00value', 'x' * 65537):
    try:
        module.parse(bad)
    except ValueError:
        pass
    else:
        raise AssertionError('Invalid report accepted')
print('Package diagnostic classification passed (ARM/x86, clock, volume, transport, history, unknown authorization).')
