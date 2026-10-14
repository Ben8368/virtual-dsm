#!/usr/bin/env python3
"""Non-proprietary DS124 builder fixture. Test-only in-process support table override."""
import copy
import hashlib
import importlib.util
import io
import json
import lzma
import os
from pathlib import Path
import stat
import struct
import subprocess
import sys
import tarfile
import tempfile

# Isolate tests from the Docker image's production default capacity.
os.environ.pop('DISK_SIZE', None)
repo = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo / 'src/platform'))
import arm_contract as contract
spec = importlib.util.spec_from_file_location('builder', repo / 'src/platform/prepare-arm-artifacts.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
VERSION = b'productversion="7.2.2"\nbuildnumber="72806"\nsmallfixnumber="0"\nunique="synology_rtd1619b_ds124"\n'


def newc(files):
    data = bytearray()
    for index, (name, mode, payload) in enumerate(files + [('TRAILER!!!', 0, b'')]):
        fields = [index + 1, mode, 0, 0, 1, 1700000000, len(payload), 0, 0, 0, 0, len(name.encode()) + 1, 0]
        data += b'070701' + ''.join(f'{field:08x}' for field in fields).encode() + name.encode() + b'\0'
        data += bytes(-len(data) % 4)
        data += payload
        data += bytes(-len(data) % 4)
    return bytes(data)


def tar_bytes(items):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode='w:gz', format=tarfile.PAX_FORMAT) as archive:
        for name, payload, kind, extra in items:
            header = tarfile.TarInfo(name)
            header.type = kind
            header.mode = 0o777 if kind == tarfile.SYMTYPE else (0o755 if kind == tarfile.DIRTYPE else 0o644)
            header.uid = header.gid = 0
            header.mtime = 1700000000
            header.size = len(payload) if kind == tarfile.REGTYPE else 0
            for key, value in extra.items():
                setattr(header, key, value)
            archive.addfile(header, io.BytesIO(payload) if header.isfile() else None)
    return output.getvalue()


def rejected(action):
    try:
        action()
    except (ValueError, FileNotFoundError, KeyError):
        return
    raise AssertionError('Expected fail-closed rejection')


with tempfile.TemporaryDirectory(prefix='arm-synthetic-') as tmp:
    work = Path(tmp)
    image = bytearray(1024 * 1024)
    image[56:60] = b'ARM\x64'
    archive = newc([('init', stat.S_IFREG | 0o755, b'FAKE INIT'),
                    ('bin', stat.S_IFDIR | 0o755, b''),
                    ('bin/sh', stat.S_IFREG | 0o755, b'FAKE SHELL'),
                    ('etc.defaults', stat.S_IFDIR | 0o755, b''),
                    ('etc.defaults/VERSION', stat.S_IFREG | 0o644, VERSION),
                    ('etc.defaults/synoinfo.conf', stat.S_IFREG | 0o644, b'unique="synology_rtd1619b_ds124"\n')])
    contract.kernel(image)
    contract.cpio(archive)
    good_root = {'/etc.defaults/VERSION': VERSION, '/.syno/patch/VERSION': VERSION,
                 '/etc.defaults/synoinfo.conf': b'unique="synology_rtd1619b_ds124"\n'}
    contract.junior_contract(contract.cpio(archive), good_root.__getitem__)
    mismatched_root = dict(good_root)
    mismatched_root['/.syno/patch/VERSION'] += b'packing_id="wrong"\n'
    rejected(lambda: contract.junior_contract(contract.cpio(archive), mismatched_root.__getitem__))
    rejected(lambda: contract.kernel(b'x86 image'))
    rejected(lambda: contract.cpio(archive[:200]))
    rejected(lambda: contract.validate_version(VERSION.replace(b'72806', b'72807')))
    rejected(lambda: contract.validate_version(VERSION.replace(b'ds124', b'ds125'), unique=True))
    items = []
    for directory in ('etc.defaults', 'sbin', 'lib', 'lib/systemd', 'usr', 'usr/lib', 'usr/lib/modules', 'usr/lib/modules-load.d', 'dev', 'metadata'):
        items.append((directory, b'', tarfile.DIRTYPE, {}))
    for name, payload in [('etc.defaults/VERSION', VERSION), ('etc.defaults/synoinfo.conf', b'unique="synology_rtd1619b_ds124"\n'),
                          ('lib/systemd/systemd', b'FAKE SYSTEMD'), ('usr/lib/modules/cdc_ether.ko', b'FAKE CDC'),
                          ('usr/lib/modules/usbnet.ko', b'FAKE USB')]:
        items.append((name, payload, tarfile.REGTYPE, {}))
    items.extend([('sbin/init', b'', tarfile.SYMTYPE, {'linkname': '../lib/systemd/systemd'}),
                  ('dev/console', b'', tarfile.CHRTYPE, {'devmajor': 5, 'devminor': 1, 'mode': 0o600}),
                  ('metadata/owner', b'ownership', tarfile.REGTYPE, {'uid': 1234, 'gid': 2345, 'mode': 0o6751, 'pax_headers': {'SCHILY.xattr.user.fixture': 'synthetic'}}),
                  ('metadata/hard', b'', tarfile.LNKTYPE, {'linkname': 'metadata/owner', 'uid': 1234, 'gid': 2345, 'mode': 0o6751}),
                  ('metadata/sym', b'', tarfile.SYMTYPE, {'linkname': 'owner'})])
    for bad in [('../escape', b'', tarfile.REGTYPE, {}), ('/escape', b'', tarfile.REGTYPE, {}),
                ('metadata/bad', b'', tarfile.LNKTYPE, {'linkname': '/etc/passwd'}),
                ('metadata/bad', b'', tarfile.SYMTYPE, {'linkname': '../../escape'}),
                ('metadata/sym/escape', b'', tarfile.REGTYPE, {})]:
        payload = tar_bytes(items + [bad])
        with tarfile.open(fileobj=io.BytesIO(payload)) as source:
            rejected(lambda: contract.safe_members(source))
    with tarfile.open(fileobj=io.BytesIO(tar_bytes(items))) as source:
        contract.safe_members(source)
    # Guest-absolute link objects allowed; all writes beneath them rejected.
    absolute = ('guest', b'', tarfile.SYMTYPE, {'linkname': '/etc.defaults'})
    with tarfile.open(fileobj=io.BytesIO(tar_bytes(items + [absolute]))) as source:
        contract.safe_members(source)
    with tarfile.open(fileobj=io.BytesIO(tar_bytes(items + [absolute, ('guest/escape', b'x', tarfile.REGTYPE, {})]))) as source:
        rejected(lambda: contract.safe_members(source))
    updater = b'SYNTHETIC UPDATER - NEVER EXECUTED'
    payloads = {'VERSION': VERSION, 'zImage': lzma.compress(image, format=lzma.FORMAT_ALONE),
                'rd.bin': lzma.compress(archive, format=lzma.FORMAT_ALONE) + bytes(128),
                'hda1.tgz': tar_bytes(items), 'updater': updater,
                'model.dtb': b'\xd0\x0d\xfe\xed' + b'synology_rtd1619b_ds124\0',
                'uboot_DS124.bin': b'FAKE UBOOT', 'uboot_do_upd.sh': b'FAKE BOOT',
                'DiskCompatibilityDB.tar': b'FAKE DB', 'Synology.sig': b'FAKE SIGNATURE',
                'checksum.syno': b''.join(n.encode() + b' original checksum record\n' for n in ('VERSION', 'zImage', 'rd.bin', 'updater', 'model.dtb', 'hda1.tgz')),
                'packages/StorageManager-rtd1619b-1.0.0-00502.spk': b'SYNTHETIC STORAGE PACKAGE',
                'packages/ActiveInsight-armv8-1.0.spk': b'SYNTHETIC OPTIONAL TELEMETRY'}
    pat = work / 'synthetic.pat'
    pat.write_bytes(tar_bytes([(n, d, tarfile.REGTYPE, {'mtime': 0}) for n, d in payloads.items()]))
    rejected(lambda: builder.identity(pat))
    # Overrides exist only here, never in runtime env/CLI or a production bypass.
    contract.BUILD.update(sha256=contract.sha256(pat), updater_sha256=hashlib.sha256(updater).hexdigest(),
                          kernel_sha256=hashlib.sha256(image).hexdigest(), initrd_sha256=hashlib.sha256(archive).hexdigest())
    def fixture_build(directory):
        directory.mkdir(mode=0o700)
        extracted = directory / 'pat'
        extracted.mkdir()
        for name, data in payloads.items():
            (extracted / name).parent.mkdir(parents=True, exist_ok=True)
            (extracted / name).write_bytes(data)
        builder.build(pat, directory)
    first = work / 'first'
    fixture_build(first)
    generated = first / 'generation'
    manifest = json.loads((generated / 'manifest.json').read_text())
    assert manifest['geometry']['partition_sectors'] == 4190917
    assert manifest['pat_sha256'] == contract.sha256(pat)
    assert list(manifest['integrations']['bundled_packages']) == ['StorageManager-rtd1619b-1.0.0-00502.spk']
    # Inspect the built disk, not just the integration source tree.
    from dissect.extfs import ExtFS
    from dissect.util.stream import RangeStream
    with (generated / 'system.img').open('rb') as fh:
        offset, length = builder.validator.first_partition(fh)
        ext = ExtFS(RangeStream(fh, offset, length))
        assert builder.validator.resolve(ext, '/.SynoUpgradePackages/StorageManager-rtd1619b-1.0.0-00502.spk').open().read() == b'SYNTHETIC STORAGE PACKAGE'
        assert b'date -u -s' in builder.validator.resolve(ext, '/usr/local/libexec/virtual-dsm/clock.sh').open().read()
        assert builder.validator.resolve(ext, '/usr/lib/systemd/system/sysinit.target.wants/virtual-dsm-clock.service').size
        assert builder.validator.resolve(ext, '/usr/lib/systemd/system/multi-user.target.wants/virtual-dsm-storage-manager.service').size
    # Exact original updater algorithm oracle: filenames, bytes, checksum, modes.
    entries = builder.pat_entries(pat)
    excluded = {'hda1.tgz', 'indexdb.txz', 'synohdpack_img.txz', 'checksum.syno', 'Synology.sig', 'updater_manutil', 'createvolume', 'SkipCheckPackingMatch', 'autonano.pat', 'RedBoot.msys', 'configupdate'}
    chosen = [n for n, (h, _) in entries.items() if '/' not in n and h.isfile() and n not in excluded]
    with tarfile.open(first / 'patch.tar') as patch:
        assert patch.getnames() == ['.syno/patch/' + n for n in chosen] + ['.syno/patch/checksum.syno']
        for name in chosen:
            assert patch.extractfile('.syno/patch/' + name).read() == payloads[name]
        expected_checksum = b''.join(line for name in chosen for line in payloads['checksum.syno'].splitlines(keepends=True) if name.lower().encode() in line.lower())
        assert patch.extractfile('.syno/patch/checksum.syno').read() == expected_checksum
    storage = work / 'storage'
    storage.mkdir()
    base = 'DSM_DS124_72806'
    builder.publish(storage, base, generated)
    builder.cache(storage, base)
    before = builder.current_directory(storage, base)
    timestamps = {n: (before / n).stat().st_mtime_ns for n in builder.ARTIFACTS}
    builder.cache(storage, base)
    assert timestamps == {n: (before / n).stat().st_mtime_ns for n in builder.ARTIFACTS}
    # Abandoned temp artifacts cannot participate in cache or publication.
    partial = storage / '.rtd1619b-install-abandoned'
    partial.mkdir(mode=0o700)
    (partial / 'kernel.tmp').write_bytes(b'PARTIAL')
    (partial / 'manifest.tmp').write_text('{')
    builder.cache(storage, base)
    assert builder.current_directory(storage, base) == before
    second = work / 'second'
    fixture_build(second)
    # Failed validation leaves the old committed pointer untouched.
    (second / 'generation/kernel').write_bytes(b'corrupted')
    rejected(lambda: builder.publish(storage, base, second / 'generation'))
    assert builder.current_directory(storage, base) == before
    with (before / 'kernel').open('r+b') as fh:
        fh.seek(200)
        fh.write(b'changed')
    rejected(lambda: builder.cache(storage, base))
    recovery = work / 'recovery'
    fixture_build(recovery)
    if manifest['seed']['system_sha256'] != json.loads((recovery / 'generation/manifest.json').read_text())['seed']['system_sha256']:
        with (before / 'system.img').open('rb') as a, (recovery / 'generation/system.img').open('rb') as b:
            differences = []
            offset = 0
            while x := a.read(4096):
                y = b.read(4096)
                if x != y:
                    differences.append((offset, [(i, v, y[i]) for i, v in enumerate(x) if v != y[i]][:20]))
                offset += len(x)
            print('Determinism differences:', differences[:20], flush=True)
        raise AssertionError('System image must be deterministic')
    builder.publish(storage, base, recovery / 'generation')
    builder.cache(storage, base)
    assert builder.current_directory(storage, base) != before
    current = builder.current_directory(storage, base)
    # Missing public alias is repaired without rebuilding or switching generation.
    (storage / (base + '.initrd')).unlink()
    builder.cache(storage, base)
    assert builder.current_directory(storage, base) == current
    assert (storage / (base + '.initrd')).is_file()
    # Missing and zero-size physical artifacts fail closed.
    boot_bytes = (current / 'initrd').read_bytes()
    (current / 'initrd').write_bytes(b'')
    rejected(lambda: builder.cache(storage, base))
    (current / 'initrd').unlink()
    rejected(lambda: builder.cache(storage, base))
    (current / 'initrd').write_bytes(boot_bytes)
    builder.cache(storage, base)
    # Runtime writes are accepted without a stopped-image receipt, including crashes.
    builder.begin(storage, base)
    system = current / 'system.img'
    with system.open('r+b') as fh:
        fh.seek(2147483648 - 16)
        fh.write(b'SYNTHETIC WRITE')
    builder.cache(storage, base)
    before_seal = contract.sha256(system)
    builder.seal(storage, base)
    assert contract.sha256(system) == before_seal
    builder.cache(storage, base)
    # Runtime disks cannot be replaced, even with an independently valid seed.
    rejected(lambda: builder.publish(storage, base, recovery / 'generation'))
    # Generation payloads must be owned files, not aliases into another disk.
    moved_disk = work / 'moved-runtime.img'
    system.rename(moved_disk)
    system.symlink_to(moved_disk)
    rejected(lambda: builder.cache(storage, base))
    assert contract.sha256(moved_disk) == before_seal
    system.unlink()
    moved_disk.rename(system)
    # Repairing addressing metadata must never unlink another runtime disk.
    public_disk = storage / (base + '.system.img')
    target = os.readlink(public_disk)
    public_disk.unlink()
    public_disk.write_bytes(b'SYNTHETIC USER STATE')
    rejected(lambda: builder.cache(storage, base))
    assert public_disk.read_bytes() == b'SYNTHETIC USER STATE'
    public_disk.unlink()
    other_disk = work / 'other-runtime.img'
    other_disk.write_bytes(b'OTHER USER STATE')
    public_disk.symlink_to(other_disk)
    rejected(lambda: builder.cache(storage, base))
    assert other_disk.read_bytes() == b'OTHER USER STATE'
    public_disk.unlink()
    public_disk.symlink_to(target)
    builder.cache(storage, base)
    # Phase 2 migration discards immutable runtime hash semantics, including a stale hash.
    current_manifest = json.loads((current / 'manifest.json').read_text())
    legacy_manifest = copy.deepcopy(current_manifest)
    legacy_manifest['schema_version'] = 1
    legacy_manifest.pop('seed')
    legacy_manifest.pop('runtime')
    legacy_manifest['artifacts']['system.img'] = {'sha256': '0' * 64, 'bytes': contract.IMAGE_BYTES}
    builder.atomic_json(current / 'manifest.json', legacy_manifest)
    builder.cache(storage, base)
    migrated = json.loads((current / 'manifest.json').read_text())
    assert migrated['seed']['system_sha256'] is None
    assert 'system.img' not in migrated['artifacts']
    # Configured corroboration never enables regeneration or immutable hash checking.
    migrated['runtime']['dsm_evidence'] = {'configured': True, 'data_initialized': True,
                                          'source': 'synthetic authoritative evidence'}
    builder.atomic_json(current / 'manifest.json', migrated)
    builder.cache(storage, base)
    assert json.loads((current / 'manifest.json').read_text())['runtime']['dsm_evidence']['configured']
    assert builder.current_directory(storage, base) == current
    # Record clean only with a guest shutdown event AND successful QEMU exit.
    receipt = work / 'exit.json'
    receipt.write_text(json.dumps({'guest': True, 'reason': 'guest-shutdown', 'qemu_exit_code': 0}))
    builder.seal(storage, base, receipt)
    assert json.loads((current / 'manifest.json').read_text())['runtime']['last_exit']['clean']
    receipt.write_text(json.dumps({'guest': True, 'reason': 'guest-shutdown', 'qemu_exit_code': 143}))
    builder.seal(storage, base, receipt)
    assert not json.loads((current / 'manifest.json').read_text())['runtime']['last_exit']['clean']
    # Growth changes only backing-file length; exact old prefix including p1 remains.
    before_growth = contract.sha256(system)
    mbr_before = system.open('rb').read(512)
    os.environ['DISK_SIZE'] = '16G'
    builder.cache(storage, base)
    assert system.stat().st_size == 16 * 1024**3
    with system.open('rb') as fh:
        digest = hashlib.sha256()
        remaining = contract.IMAGE_BYTES
        while remaining:
            chunk = fh.read(min(1024**2, remaining))
            digest.update(chunk)
            remaining -= len(chunk)
    assert digest.hexdigest() == before_growth
    assert system.open('rb').read(512) == mbr_before
    os.environ['DISK_SIZE'] = '2G'
    rejected(lambda: builder.cache(storage, base))
    assert system.stat().st_size == 16 * 1024**3
    os.environ.pop('DISK_SIZE')
    # DSM may add p3 without changing p1. Reject overlapping/out-of-bounds tables.
    def p3(start, sectors):
        with system.open('r+b') as fh:
            fh.seek(478)
            entry = bytearray(16)
            entry[4] = 0x83
            struct.pack_into('<II', entry, 8, start, sectors)
            fh.write(entry)
    p3(4455109, 12107776)
    builder.cache(storage, base)
    p3(0, 1024)
    rejected(lambda: builder.cache(storage, base))
    p3(contract.START_SECTOR + 1, 1024)
    rejected(lambda: builder.cache(storage, base))
    p3(16 * 1024**3 // 512 - 1, 1024)
    rejected(lambda: builder.cache(storage, base))
    with system.open('r+b') as fh:
        fh.seek(478)
        fh.write(bytes(16))
    builder.cache(storage, base)
    # Legacy adoption requires the exact fixture boot hashes and read-only root validation.
    legacy = work / 'legacy'
    legacy.mkdir()
    for name in builder.ARTIFACTS:
        subprocess.run(['cp', '--sparse=always', str(storage / (base + '.' + name)), str(legacy / (base + '.' + name))], check=True)
    # Restrict this separate adoption fixture to its original 2 GiB region.
    with (legacy / (base + '.system.img')).open('r+b') as fh:
        fh.truncate(contract.IMAGE_BYTES)
    old_hash = contract.sha256(legacy / (base + '.system.img'))
    os.environ['ARM_SOURCE_URL'] = 'https://example.invalid/DSM_DS124_72806.pat'
    builder.cache(legacy, base)
    os.environ.pop('ARM_SOURCE_URL')
    assert contract.sha256(legacy / (base + '.system.img')) == old_hash
print('Synthetic ARM installer tests passed: identity, archive safety, metadata, official patch selection, publication, cache, partial recovery, corruption, legacy migration.')
