#!/usr/bin/env python3
"""Collect read-only DSM prerequisites via existing SSH, or analyze a saved report."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import time


def parse(text):
    if len(text) > 65536:
        raise ValueError('Diagnostic report is oversized')
    result = {}
    for line in text.splitlines():
        key, separator, value = line.partition('\t')
        if not separator or not re.fullmatch(r'[A-Za-z0-9_.]+', key) or key in result:
            raise ValueError('Invalid/duplicate diagnostic field')
        if len(value) > 512 or any(ord(c) < 32 for c in value):
            raise ValueError('Invalid diagnostic value')
        result[key] = value
    if result.get('format') != '1':
        raise ValueError('Expected guest diagnostic format 1')
    return result


def analyze(data, host_epoch):
    blockers, warnings, unknown = [], [], []
    try:
        skew = int(data['epoch']) - int(host_epoch)
    except (KeyError, ValueError):
        skew = None
        unknown.append('guest_clock_unknown')
    if skew is not None and abs(skew) > 300:
        blockers.append('guest_clock_skew')
    if not 1704067200 <= host_epoch <= 4102444800:
        blockers.append('host_clock_invalid')
    unique, arch = data.get('unique', ''), data.get('arch', '')
    if unique == 'synology_rtd1619b_ds124':
        platform = 'rtd1619b'
        if arch not in ('aarch64', 'arm64'):
            blockers.append('guest_architecture_mismatch')
    elif 'kvmx64' in unique.lower():
        platform = 'virtualdsm'
        if arch != 'x86_64':
            blockers.append('guest_architecture_mismatch')
    else:
        platform = 'unknown'
        unknown.append('guest_platform_unknown')
    volume = data.get('volume', '')
    if not volume or ':' not in volume:
        blockers.append('data_volume_not_mounted')
    elif 'rw' not in volume.partition(':')[2].split(','):
        blockers.append('data_volume_not_writable')
    if data.get('pgsql') != 'active':
        blockers.append('database_not_active')
    if data.get('package.StorageManager') in (None, 'absent', 'failed', 'inactive'):
        blockers.append('storage_manager_not_ready')
    for endpoint in ('pkgupdate', 'download'):
        code = data.get('network.' + endpoint + '.curl')
        http = data.get('network.' + endpoint + '.http', '')
        if code is None:
            unknown.append(endpoint + '_transport_not_checked')
        elif code != '0':
            kind = {'6': 'dns', '7': 'connection', '28': 'timeout',
                    '35': 'tls', '60': 'certificate', '77': 'ca_file'}.get(code, 'curl')
            blockers.append(endpoint + '_' + kind + '_failure')
        elif not re.fullmatch(r'[1-5][0-9]{2}', http):
            blockers.append(endpoint + '_http_response_missing')
    for category in ('hwid', 'authorization', 'dependency', 'timeout', 'tls', 'install_failure'):
        if any(data.get('history.' + log + '.' + category) == 'yes'
               for log in ('synopkg.log', 'synopkgmgr.log')):
            warnings.append('recent_history_' + category)
    if any(data.get('logs.' + log) != 'readable' for log in ('synopkg.log', 'synopkgmgr.log')):
        unknown.append('package_logs_unavailable')
    return {'schema_version': 1, 'platform': platform, 'clock_skew_seconds': skew,
            'blockers': blockers, 'warnings': warnings, 'unknown': unknown,
            'prerequisites': 'blocked' if blockers else ('incomplete' if unknown else 'passed'),
            'packages': {name: data.get('package.' + name, 'unknown') for name in
                         ('StorageManager', 'SurveillanceVideoExtension', 'SurveillanceStation')},
            'package_versions': {name: data.get('package.' + name + '.version') or None for name in
                                 ('StorageManager', 'SurveillanceVideoExtension', 'SurveillanceStation')},
            'authorization': 'unverified',
            'note': 'Transport checks do not test install authorization. History is not proof of the current failure. No raw logs or device identity exported.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--guest', help='Existing SSH target user@host; no credentials are stored')
    source.add_argument('--from-report', type=Path, help='TSV output of src/guest/package-diagnostics.sh')
    parser.add_argument('--port', type=int, default=22)
    parser.add_argument('--sudo', action='store_true', help='Use cached/noninteractive sudo in DSM')
    parser.add_argument('--network', action='store_true', help='Probe public HTTPS transport from inside DSM')
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('Invalid SSH port')
    if args.guest:
        if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]*@[A-Za-z0-9][A-Za-z0-9.:-]*', args.guest):
            parser.error('Expected SSH target user@host')
        repo_collector = Path(__file__).resolve().parent.parent / 'src/guest/package-diagnostics.sh'
        collector = repo_collector if repo_collector.is_file() else Path(__file__).with_name('guest') / 'package-diagnostics.sh'
        remote = ('sudo -n ' if args.sudo else '') + '/bin/sh -s --' + (' --network' if args.network else '')
        try:
            completed = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8',
                                        '-p', str(args.port), args.guest, remote],
                                       input=collector.read_text(), text=True, capture_output=True, timeout=50)
        except (OSError, subprocess.TimeoutExpired) as exc:
            parser.exit(2, 'SSH collector unavailable (' + type(exc).__name__ + '); no guest changes performed.\n')
        if completed.returncode:
            parser.exit(2, 'SSH collector failed; check existing SSH access and sudo permissions.\n')
        raw = completed.stdout
    else:
        raw = args.from_report.read_text()
    try:
        report = analyze(parse(raw), int(time.time()))
    except ValueError as exc:
        parser.exit(2, str(exc) + '\n')
    print(json.dumps(report, indent=2))
    return {'passed': 0, 'blocked': 2, 'incomplete': 3}[report['prerequisites']]


if __name__ == '__main__':
    raise SystemExit(main())
