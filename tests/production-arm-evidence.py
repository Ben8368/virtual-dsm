#!/usr/bin/env python3
"""Read guest observer evidence after the disposable production regression stops."""
import argparse
import importlib.util
import json
from pathlib import Path
import re
from dissect.extfs import ExtFS
from dissect.util.stream import RangeStream

parser = argparse.ArgumentParser()
parser.add_argument('image', type=Path, help='Stopped disposable raw system image')
parser.add_argument('output', type=Path, help='Directory containing serial and HTTP evidence')
opts = parser.parse_args()
source = Path(__file__).resolve().parent.parent / 'src/platform/validate-arm-image.py'
spec = importlib.util.spec_from_file_location('validator', source)
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)
logs = {}
with opts.image.open('rb') as fh:
    offset, size = validator.first_partition(fh)
    ext = ExtFS(RangeStream(fh, offset, size))
    for name in ('network', 'management', 'scemd-lockup'):
        node = validator.resolve(ext, '/var/log/arm64-' + name + '-observer.log')
        text = node.open().read().decode(errors='replace')
        if name != 'scemd-lockup':
            assert text.strip(), name + ' observer did not run'
        logs[name] = text
        (opts.output / ('guest-' + name + '.log')).write_text(text)
serial = (opts.output / 'arm-serial.log').read_text()
requests = json.loads((opts.output / 'management-requests.json').read_text())
https = json.loads((opts.output / 'https-result.json').read_text())
lockup = logs['scemd-lockup']
process_log = lockup or logs['management']
uptimes = [float(value) for value in re.findall(r'UPTIME=([0-9.]+)', process_log)]
scemd_lines = [line for line in process_log.splitlines() if re.search(r'^\s*\d+\s+.* /usr/syno/bin/scemd', line)]
result = {
    'systemd_pid1': 'systemd[1]' in serial,
    'sata1': 'sata1p1' in serial,
    'ttyS0': 'console [ttyS0] enabled' in serial,
    'xhci': 'xhci-hcd' in serial,
    'eth0': 'eth0' in logs['network'] and 'cdc_ether' in serial,
    'dhcp': 'inet 10.0.2.15' in logs['network'] + logs['management'],
    'nginx_listens': bool(re.search(r':5000\s.*LISTEN\s.*nginx', logs['management'])),
    'http_200': len(requests) == 30 and all(item['status'] == 200 for item in requests),
    'https_200': https['status'] == 200,
    'scemd_observed': bool(scemd_lines),
    'scemd_soft_lockup': any(marker in serial + lockup for marker in
                             ('soft lockup', 'FIRST_SOFT_LOCKUP', 'queued_write_lock_slowpath')),
    'last_observed_guest_uptime_seconds': max(uptimes) if uptimes else None,
    'scemd_samples': scemd_lines[-8:],
}
(opts.output / 'boot-result.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
assert all(result[name] for name in ('systemd_pid1', 'sata1', 'ttyS0', 'xhci', 'eth0',
                                    'dhcp', 'nginx_listens', 'http_200', 'https_200', 'scemd_observed'))
assert not result['scemd_soft_lockup']
