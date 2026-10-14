#!/usr/bin/env python3
"""Read stock guest logs after production acceptance; no observer is injected."""
import argparse
import importlib.util
import json
from pathlib import Path
import re
from dissect.extfs import ExtFS
from dissect.util.stream import RangeStream

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('image', type=Path, help='Stopped production system image')
parser.add_argument('output', type=Path, help='Ignored directory with first/restart management evidence')
args = parser.parse_args()
source = Path(__file__).resolve().parents[1] / 'src/platform/validate-arm-image.py'
spec = importlib.util.spec_from_file_location('validator', source)
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)
validator.validate(args.image, runtime=True)
logs = {}
with args.image.open('rb') as fh:
    offset, size = validator.first_partition(fh)
    ext = ExtFS(RangeStream(fh, offset, size))
    for name in ('messages', 'systemd.log', 'scemd.log'):
        text = validator.resolve(ext, '/var/log/' + name).open().read().decode(errors='replace')
        logs[name] = text
        (args.output / ('stock-' + name)).write_text(text)
serial = ''.join((args.output / phase / 'arm-serial.log').read_text() for phase in ('first', 'restart'))
result = {
    'systemd_pid1': 'systemd[1]' in serial,
    'sata1p1': 'EXT4-fs (sata1p1): mounted filesystem' in serial,
    'xhci': 'xhci-hcd' in serial,
    'cdc_ether_eth0': bool(re.search(r'cdc_ether .*eth0: register', serial)),
    'dhcp_10_0_2_15': bool(re.search(r'(?:dhcp-client.*eth0 get new IP\s+|bound to\s+|DHCPACK.*|DHCPOFFER.*)10[.]0[.]2[.]15', logs['messages'])),
    'scemd_stock_log_present': bool(logs['scemd.log'].strip()),
    'soft_lockup': any(s in serial + ''.join(logs.values()) for s in ('soft lockup', 'queued_write_lock_slowpath', 'FIRST_SOFT_LOCKUP')),
    'kernel_null_oops': any(s in serial for s in ('Unable to handle kernel NULL pointer', 'Internal error: Oops', 'BUG: unable to handle')),
}
for phase in ('first', 'restart'):
    requests = json.loads((args.output / phase / 'management-requests.json').read_text())
    https = json.loads((args.output / phase / 'https-result.json').read_text())
    result[phase + '_http_30'] = len(requests) == 30 and all(x['status'] == 200 and x['server'] == 'nginx' for x in requests)
    result[phase + '_https_200'] = https['status'] == 200 and https['server'] == 'nginx'
(args.output / 'boot-result.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
assert all(value for key, value in result.items() if key not in ('soft_lockup', 'kernel_null_oops'))
assert not result['soft_lockup'] and not result['kernel_null_oops']
