"""New ARM seeds only: authenticated packages and early clock integration."""
import hashlib
import os
from pathlib import Path
import re

STORAGE_PACKAGE = 'StorageManager-rtd1619b-1.0.0-00502.spk'
HERE = Path(__file__).resolve().parent.parent / 'guest'


def directory(root, relative):
    if root.is_symlink() or Path(relative).is_absolute() or '..' in Path(relative).parts:
        raise ValueError('Unsafe guest integration root/path')
    current = root
    for component in Path(relative).parts:
        current /= component
        if current.is_symlink() or (current.exists() and not current.is_dir()):
            raise ValueError('Unsafe guest integration directory: ' + relative)
        current.mkdir(mode=0o755, exist_ok=True)
    return current


def put(root, relative, data, mode=0o644):
    target = directory(root, str(Path(relative).parent)) / Path(relative).name
    if target.is_symlink() or target.exists():
        raise ValueError('Guest integration refuses to overwrite: ' + relative)
    target.write_bytes(data)
    target.chmod(mode)
    os.chown(target, 0, 0)
    return target


def integrate(root, entries):
    packages = {}
    for name, (header, data) in entries.items():
        if not name.startswith('packages/'):
            continue
        filename = name.removeprefix('packages/')
        if not header.isfile() or not re.fullmatch(r'[A-Za-z0-9_.+-]+\.spk', filename):
            raise ValueError('Invalid bundled PAT package: ' + name)
        # Match the upstream installer's optional telemetry-agent exclusion.
        if filename.startswith('ActiveInsight-'):
            continue
        put(root, '.SynoUpgradePackages/' + filename, data)
        packages[filename] = hashlib.sha256(data).hexdigest()
    if STORAGE_PACKAGE not in packages:
        raise ValueError('DS124 PAT is missing the Storage Manager prerequisite')
    payload = entries['packages/' + STORAGE_PACKAGE][1]
    put(root, 'usr/local/share/virtual-dsm/' + STORAGE_PACKAGE, payload)
    put(root, 'usr/local/share/virtual-dsm/StorageManager.sha256',
        (packages[STORAGE_PACKAGE] + '  ' + STORAGE_PACKAGE + '\n').encode())
    for script in ('clock.sh', 'storage-manager.sh'):
        put(root, 'usr/local/libexec/virtual-dsm/' + script, (HERE / script).read_bytes(), 0o755)
    for service, target in (('virtual-dsm-clock.service', 'sysinit.target'),
                            ('virtual-dsm-storage-manager.service', 'multi-user.target')):
        put(root, 'usr/lib/systemd/system/' + service, (HERE / service).read_bytes())
        # DSM rebuilds /etc from its defaults during first-user initialization.
        # Vendor wants survive that transition; existing-runtime enable uses /etc.
        link = directory(root, 'usr/lib/systemd/system/' + target + '.wants') / service
        if link.is_symlink() or link.exists():
            raise ValueError('Unexpected preexisting guest integration unit')
        link.symlink_to('/usr/lib/systemd/system/' + service)
    return {'version': 1, 'clock': 'host-launch-epoch-before-ntp', 'bundled_packages': packages,
            'storage_manager': 'normal synopkg install; no validation bypass'}
