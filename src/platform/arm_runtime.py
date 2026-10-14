"""Writable DS124 runtime policy. Caller holds the generation lock; QEMU is stopped."""
import os
import re
from datetime import datetime, timezone

from arm_contract import BUILD, IMAGE_BYTES, PARTITION_SECTORS, START_SECTOR

SCHEMA = 2

def now():
    return datetime.now(timezone.utc).isoformat()


def capacity(value):
    match = re.fullmatch(r'([1-9][0-9]*)([KMGT]?)(?:I?B)?', value.upper())
    if not match:
        raise ValueError('ARM DISK_SIZE must be an integer byte count or K/M/G/T binary size')
    size = int(match[1]) * 1024 ** ('KMGT'.index(match[2]) + 1 if match[2] else 0)
    if size < IMAGE_BYTES or size > (2**32 - 1) * 512 or size % 512:
        raise ValueError('ARM DISK_SIZE must be sector aligned, at least 2 GiB and within MBR capacity')
    return size


def grow(image, size):
    """Only extend backing-file length. Never change the MBR or filesystem."""
    with image.open('r+b') as fh:
        current = os.fstat(fh.fileno()).st_size
        if size < current:
            raise ValueError('ARM DISK_SIZE shrink rejected; existing runtime disk is preserved')
        if size > current:
            fh.truncate(size)
            fh.flush()
            os.fsync(fh.fileno())


def migrate(manifest, disk_bytes):
    if manifest.get('schema_version') == 1:
        # Phase 2 seal overwrote the seed hash. Never mislabel it as original seed.
        observation = manifest['artifacts'].pop('system.img')
        manifest['schema_version'] = SCHEMA
        manifest['seed'] = {'system_sha256': None, 'hash_origin': 'unavailable: Phase 2 hash may be sealed runtime',
                            'geometry': manifest['geometry'].copy()}
        manifest['runtime'] = {'version': 1, 'lifecycle': 'BOOT_ATTEMPTED', 'generation': 0,
                               'virtual_bytes': disk_bytes, 'last_exit': None,
                               'legacy_stopped_observation': observation,
                               'dsm_evidence': {'configured': None, 'data_initialized': None}}
    if manifest.get('schema_version') != SCHEMA:
        raise ValueError('Unsupported ARM manifest schema; preserve runtime disk')
    expected = {'DSM_PLATFORM': 'rtd1619b', 'model': 'DS124', 'dsm_version': '7.2.2',
                'buildnumber': '72806', 'pat_sha256': BUILD['sha256'], 'builder_version': 1}
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise ValueError('ARM provenance mismatch: ' + key)
    geometry = manifest.get('seed', {}).get('geometry', {})
    if any(geometry.get(key) != value for key, value in
           {'bytes': IMAGE_BYTES, 'start_sector': START_SECTOR, 'partition_sectors': PARTITION_SECTORS,
            'block_size': 4096, 'inode_size': 256}.items()):
        raise ValueError('ARM seed geometry provenance mismatch')
    runtime = manifest.get('runtime', {})
    if runtime.get('version') != 1 or runtime.get('lifecycle') not in ('SEED', 'BOOT_ATTEMPTED'):
        raise ValueError('Invalid ARM runtime state; preserve runtime disk')
    if type(runtime.get('generation')) is not int or runtime['generation'] < 0:
        raise ValueError('Invalid ARM runtime generation')
    if type(runtime.get('virtual_bytes')) is not int or runtime['virtual_bytes'] > disk_bytes:
        raise ValueError('Runtime disk is shorter than its recorded capacity')
    return manifest


def disk_evidence(image, validator):
    """Offline corroboration only. WebAPI completion/mounted health remains authoritative."""
    from dissect.extfs import ExtFS
    from dissect.util.stream import RangeStream
    with image.open('rb') as fh:
        offset, length = validator.first_partition(fh)
        ext = ExtFS(RangeStream(fh, offset, length))
        def read(path):
            try:
                node = validator.resolve(ext, path)
                return node.open().read() if node.size <= 1024 * 1024 else b''
            except FileNotFoundError:
                return b''
        from arm_contract import kv
        conf = kv(read('/etc/synoinfo.conf'))
        passwd = read('/etc/passwd').decode(errors='replace').splitlines()
        groups = read('/etc/group').decode(errors='replace').splitlines()
        admins = [line.rsplit(':', 1)[-1].split(',') for line in groups if line.startswith('administrators:')]
        named = any(line.split(':', 1)[0] not in ('root', 'admin', 'guest') and
                    any(line.split(':', 1)[0] in group for group in admins) for line in passwd)
        logs = read('/var/log/systemd.log')
        return {'booted': bool(logs and passwd and conf), 'admin_configured': conf.get('admin_configured'), 'named_local_administrator': named,
                'first_user_initialized': conf.get('admin_configured') == 'yes' and named,
                'configured': False if conf.get('configured') == 'no' else
                    True if conf.get('configured') == 'yes' and conf.get('admin_configured') == 'yes' and named else None,
                'data_initialized': None, 'source': 'offline files; heuristic; API and volume health required'}


def has_state(storage, base):
    # Broken pointers, partial public artifacts and orphan generations also protect state.
    return any(os.path.lexists(storage / (base + '.' + suffix)) for suffix in
               ('arm-current', 'arm.json', 'kernel', 'initrd', 'system.img')) or any(
               storage.glob('.' + base + '.arm-generation-*'))
