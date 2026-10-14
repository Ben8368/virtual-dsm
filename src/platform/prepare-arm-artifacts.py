#!/usr/bin/env python3
"""Production DS124 PAT builder. No research dependency; never executes guest binaries."""
import argparse
import importlib.util
import json
import logging
import lzma
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tarfile
import uuid

import arm_runtime as runtime
from guest_integrations import integrate


class NoArtifacts(ValueError):
    pass


from arm_contract import (BUILD, CDC_PATH, FEATURES, IMAGE_BYTES, PARTITION_SECTORS,
                          START_SECTOR, UNSUPPORTED, cpio, junior_contract, kernel,
                          patch_archive, safe_members, sha256, validate_version)

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('arm_validator', HERE / 'validate-arm-image.py')
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)
ARTIFACTS = ('kernel', 'initrd', 'system.img')


def progress(message):
    print('Install: ' + message + '...', flush=True)
    if os.environ.get('ARM_PROGRESS_HELPER'):
        subprocess.run(['bash', '-c', '. "$1"; html "$2..."', 'arm-progress',
                        os.environ['ARM_PROGRESS_HELPER'], message], check=True)


def identity(pat):
    actual = sha256(pat)
    if actual != BUILD['sha256']:
        raise ValueError(UNSUPPORTED + ' PAT SHA-256 mismatch: ' + actual)
    return actual


def pat_entries(pat):
    """Retain original header modes/order, correcting patology decimal mode parsing.

    Common extractPat already extracted the payload. Read authenticated metadata
    again to reproduce the official updater algorithm, never execute updater.
    """
    if tarfile.is_tarfile(pat):
        with tarfile.open(pat) as archive:
            return {m.name: (m, archive.extractfile(m).read()) for m in archive if m.isfile()}
    logging.disable(logging.CRITICAL)
    spec = importlib.util.spec_from_file_location('patology', HERE.parent / 'extract.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class OctalHeaders(module.Synocrack):
        def _decode_header_field(self, tarinfo, field, value, needs_atol=False):
            if field == 'mode':
                tarinfo.mode = int(value.decode().split('\x00')[0], 8)
                return tarinfo
            return super()._decode_header_field(tarinfo, field, value, needs_atol)

    with pat.open('rb') as fh:
        parsed = OctalHeaders(fh)
    return {n: (entry['header'], entry['entry']) for n, entry in parsed.entries.items()}


def decompress(source, target, kind):
    # Stock rd.bin has zero padding after its one LZMA-alone stream; zImage
    # has a four-byte trailer. LZMAFile mistakes these for another stream.
    try:
        decoder = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE, memlimit=256 * 1024 * 1024)
        data = decoder.decompress(source.read_bytes(), max_length=128 * 1024 * 1024 + 1)
        if not decoder.eof or len(data) > 128 * 1024 * 1024:
            raise ValueError(kind + ' decompression failure: truncated or oversized stream.')
        target.write_bytes(data)
    except (lzma.LZMAError, EOFError) as exc:
        raise ValueError(kind + ' decompression failure.') from exc


def audit_metadata(image, members):
    """Read every populated inode: ownership, mode, timestamp, links and devices."""
    import stat
    from dissect.extfs import ExtFS
    from dissect.util.stream import RangeStream
    with image.open('rb') as fh:
        offset, size = validator.first_partition(fh)
        ext = ExtFS(RangeStream(fh, offset, size))
        directories = {}
        def inode_at(path):
            parent, _, leaf = path.removeprefix('./').rpartition('/')
            if parent not in directories:
                directories[parent] = validator.resolve(ext, '/' + parent).listdir()
            return directories[parent][leaf]
        for member in members:
            name = member.name.removeprefix('./').rstrip('/')
            if name in ('', '.'):
                continue
            node = inode_at(name)
            inode = node.inode
            uid = inode.i_uid | inode.i_uid_high << 16
            gid = inode.i_gid | inode.i_gid_high << 16
            if (uid, gid, stat.S_IMODE(inode.i_mode)) != (member.uid, member.gid, member.mode & 0o7777):
                raise ValueError('Filesystem metadata mismatch: ' + name)
            if member.issym() and node.link != member.linkname:
                raise ValueError('Filesystem symlink mismatch: ' + name)
            if member.islnk() and node.inum != inode_at(member.linkname).inum:
                raise ValueError('Filesystem hardlink mismatch: ' + name)
            if member.ischr() or member.isblk():
                if stat.S_IFMT(inode.i_mode) != (stat.S_IFCHR if member.ischr() else stat.S_IFBLK):
                    raise ValueError('Filesystem device type mismatch: ' + name)
                old, new = struct.unpack_from('<II', inode.i_block)
                major, minor = ((old >> 8) & 255, old & 255) if old else ((new >> 8) & 4095, (new & 255) | ((new >> 12) & 0xfff00))
                if (major, minor) != (member.devmajor, member.devminor):
                    raise ValueError('Filesystem device number mismatch: ' + name)
            # The two directories below intentionally gain integration entries.
            if name not in ('.syno', 'usr/lib/modules-load.d') and abs(node.mtime_ns / 1e9 - member.mtime) > 0.001:
                raise ValueError('Filesystem mtime mismatch: ' + name)
            xattrs = {x.name: x.value for x in node.xattr}
            for key, value in member.pax_headers.items():
                if key.startswith('SCHILY.xattr.') and xattrs.get(key[13:]) != value.encode(errors='surrogateescape'):
                    raise ValueError('Filesystem xattr mismatch: ' + name)
    print(f'Offline metadata audit: {len(members)} archive entries verified.', flush=True)


def build(pat, workspace):
    digest = identity(pat)
    extracted = workspace / 'pat'
    validate_version((extracted / 'VERSION').read_bytes(), unique=True)
    for name in ('hda1.tgz', 'zImage', 'rd.bin', 'model.dtb', 'updater', 'checksum.syno'):
        if not (extracted / name).is_file() or not (extracted / name).stat().st_size:
            raise ValueError('Missing PAT payload: ' + name)
    dtb = (extracted / 'model.dtb').read_bytes()
    if dtb[:4] != b'\xd0\x0d\xfe\xed' or BUILD['unique'].encode() + b'\0' not in dtb:
        raise ValueError(UNSUPPORTED + ' model.dtb identity mismatch.')
    if sha256(extracted / 'updater') != BUILD['updater_sha256']:
        raise ValueError('Unsupported official updater; patch-state algorithm is build-specific.')
    generation = workspace / 'generation'
    generation.mkdir(mode=0o700)
    progress('Preparing ARM64 kernel')
    decompress(extracted / 'zImage', generation / 'kernel', 'kernel')
    kernel((generation / 'kernel').read_bytes())
    if sha256(generation / 'kernel') != BUILD['kernel_sha256']:
        raise ValueError('ARM64 kernel differs from validated stock Image.')
    progress('Preparing initramfs')
    decompress(extracted / 'rd.bin', generation / 'initrd', 'initramfs')
    junior = cpio((generation / 'initrd').read_bytes())
    if sha256(generation / 'initrd') != BUILD['initrd_sha256']:
        raise ValueError('Initramfs differs from validated stock newc archive.')
    progress('Preparing DSM system root')
    archive = extracted / 'hda1.tgz'
    try:
        with tarfile.open(archive) as source:
            members = safe_members(source)
    except (tarfile.TarError, ValueError) as exc:
        raise ValueError('Unsafe or invalid root archive: ' + str(exc)) from exc
    staging = workspace / 'root'
    staging.mkdir(mode=0o755)
    acl_option = '--acls' if any(k.startswith('SCHILY.acl.') for m in members for k in m.pax_headers) else '--no-acls'
    subprocess.run(['tar', '--extract', '--file=' + str(archive), '--directory=' + str(staging),
                    '--numeric-owner', '--same-owner', '--same-permissions', '--delay-directory-restore',
                    '--xattrs', '--xattrs-include=*', acl_option, '--selinux'], check=True)
    progress('Preparing Synology patch state')
    entries = pat_entries(pat)
    for name, (_, data) in entries.items():
        if name.startswith('/') or '..' in name.split('/') or (extracted / name).read_bytes() != data:
            raise ValueError('PAT extraction/metadata mismatch.')
    integrations = integrate(staging, entries)
    patch = workspace / 'patch.tar'
    selected = patch_archive(entries, patch)
    if (staging / '.syno').is_symlink() or (staging / '.syno/patch').exists():
        raise ValueError('Unexpected preexisting patch state in root payload.')
    (staging / '.syno/patch').mkdir(parents=True, mode=0o755)
    subprocess.run(['tar', '-xpf', str(patch), '-C', str(staging), '--numeric-owner', '--same-owner'], check=True)
    # Resolve guest absolute symlinks using the archive filesystem, never host /.
    def root_read(name):
        candidate = staging / name.lstrip('/')
        if candidate.is_symlink():
            raise ValueError('Unexpected root contract symlink: ' + name)
        return candidate.read_bytes()
    junior_contract(junior, root_read)
    activation = staging / CDC_PATH
    if activation.is_symlink() or activation.parent.is_symlink():
        raise ValueError('Unsafe CDC activation path.')
    activation.parent.mkdir(parents=True, exist_ok=True)
    activation.write_bytes(b'cdc_ether\n')
    activation.chmod(0o644)
    os.chown(activation, 0, 0)
    # Official encrypted PAT headers have mtime=0. e2fsprogs treats fake time
    # zero as unset, so use one fixed nonzero filesystem creation epoch. Original
    # root payload modification times are restored independently below.
    epoch = max(1, entries['VERSION'][0].mtime)
    for member in members:
        if member.isdir():
            os.utime(staging / member.name, (member.mtime, member.mtime), follow_symlinks=False)
    original_names = {m.name.removeprefix('./').rstrip('/') for m in members}
    for parent, directories, files in os.walk(staging, followlinks=False):
        for name in directories + files:
            path = Path(parent) / name
            if path.relative_to(staging).as_posix() not in original_names:
                os.utime(path, (epoch, epoch), follow_symlinks=False)
    for integration in (staging, staging / '.syno', staging / '.syno/patch', activation):
        os.utime(integration, (epoch, epoch), follow_symlinks=False)
    progress('Building system filesystem')
    image = generation / 'system.img'
    filesystem = workspace / 'filesystem.img'
    filesystem.touch()
    with image.open('wb') as fh:
        fh.truncate(IMAGE_BYTES)
        mbr = bytearray(512)
        mbr[446 + 4] = 0x83
        struct.pack_into('<II', mbr, 446 + 8, START_SECTOR, PARTITION_SECTORS)
        mbr[510:] = b'\x55\xaa'
        fh.write(mbr)
    # Same p1 byte bounds as research. A partial final block stays outside ext4.
    subprocess.run(['mke2fs', '-q', '-t', 'ext4', '-F', '-b', '4096', '-I', '256',
                    '-O', 'none,' + FEATURES, '-U', str(uuid.UUID(digest[:32])),
                    '-E', 'hash_seed=' + str(uuid.UUID(digest[32:])) + ',lazy_itable_init=0,lazy_journal_init=0',
                    '-d', str(staging), str(filesystem), str(PARTITION_SECTORS * 512 // 4096)], check=True,
                   env={**os.environ, 'E2FSPROGS_FAKE_TIME': str(int(epoch))})
    # GNU tar cannot set inode ctime; mke2fs copies it from staging. Normalize
    # only atime/ctime/crtime offline for deterministic build bytes.
    from dissect.extfs import ExtFS
    import stat
    commands = workspace / 'inode-times.txt'
    with filesystem.open('rb') as fh, commands.open('w') as output:
        ext = ExtFS(fh)
        pending = [ext.root]
        seen = set()
        while pending:
            node = pending.pop()
            if node.inum in seen:
                continue
            seen.add(node.inum)
            for field in ('atime', 'ctime', 'crtime'):
                output.write(f'set_inode_field <{node.inum}> {field} {int(epoch)}\n')
                output.write(f'set_inode_field <{node.inum}> {field}_extra 0\n')
            if node.filetype == stat.S_IFDIR:
                pending.extend(child for child in node.iterdir() if child.filename not in ('.', '..'))
        output.write(f'set_super_value wtime {int(epoch)}\n')
    subprocess.run(['debugfs', '-w', '-f', str(commands), str(filesystem)],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True,
                   env={**os.environ, 'E2FSPROGS_FAKE_TIME': str(int(epoch))})
    # Copy only populated extents into p1, preserving sparse image allocation.
    with filesystem.open('rb') as src, image.open('r+b') as dst:
        cursor = 0
        while cursor < filesystem.stat().st_size:
            try:
                data = os.lseek(src.fileno(), cursor, os.SEEK_DATA)
            except OSError as exc:
                import errno
                if exc.errno == errno.ENXIO:
                    break
                raise
            end = os.lseek(src.fileno(), data, os.SEEK_HOLE)
            src.seek(data)
            dst.seek(START_SECTOR * 512 + data)
            remaining = end - data
            while remaining:
                chunk = src.read(min(remaining, 1024 * 1024))
                dst.write(chunk)
                remaining -= len(chunk)
            cursor = end
    progress('Validating ARM system image')
    validator.validate(image, strict=True, junior=junior)
    audit_metadata(image, members)
    manifest = manifest_for(generation)
    manifest['patch_selected'] = selected
    manifest['pat_sha256'] = digest
    manifest['source_url'] = os.environ.get('ARM_SOURCE_URL', '')
    manifest['provenance'] = 'official PAT; installed root; CDC, clock and bundled-package integrations'
    manifest['integrations'] = integrations
    atomic_json(generation / 'manifest.json', manifest)


def manifest_for(directory):
    geometry = {'bytes': IMAGE_BYTES, 'start_sector': START_SECTOR,
                'partition_sectors': PARTITION_SECTORS, 'block_size': 4096, 'inode_size': 256}
    return {'schema_version': runtime.SCHEMA, 'DSM_PLATFORM': 'rtd1619b', 'model': 'DS124',
            'dsm_version': '7.2.2', 'buildnumber': '72806', 'pat_sha256': BUILD['sha256'],
            'builder_version': 1, 'geometry': geometry,
            'seed': {'system_sha256': sha256(directory / 'system.img'),
                     'hash_origin': 'original unbooted 2 GiB installed-root seed', 'geometry': geometry},
            'runtime': {'version': 1, 'lifecycle': 'SEED', 'generation': 0,
                        'virtual_bytes': (directory / 'system.img').stat().st_size,
                        'last_exit': None, 'dsm_evidence': {'configured': None, 'data_initialized': None}},
            'artifacts': {name: {'sha256': sha256(directory / name), 'bytes': (directory / name).stat().st_size}
                          for name in ('kernel', 'initrd')}}


def requested_capacity(image):
    value = os.environ.get('DISK_SIZE', '')
    return runtime.capacity(value) if value else image.stat().st_size


def atomic_json(path, data):
    temporary = path.with_name(path.name + '.tmp')
    with temporary.open('w') as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
        fh.write('\n')
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(temporary, path)


def sync_dir(directory):
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def valid_set(directory, seed=False):
    for name in ARTIFACTS:
        if (directory / name).is_symlink() or not (directory / name).is_file() or not (directory / name).stat().st_size:
            raise ValueError('Missing/empty or indirect ARM generation artifact: ' + name)
    if sha256(directory / 'kernel') != BUILD['kernel_sha256'] or sha256(directory / 'initrd') != BUILD['initrd_sha256']:
        raise ValueError('Artifact validation failure: immutable stock boot hash mismatch.')
    kernel((directory / 'kernel').read_bytes())
    junior = cpio((directory / 'initrd').read_bytes())
    validator.validate(directory / 'system.img', strict=True, junior=junior, runtime=not seed)


def public_links(storage, base, adopting=False):
    # All public paths resolve through one generation pointer; QEMU argv unchanged.
    for suffix, filename in [(n, n) for n in ARTIFACTS] + [('arm.json', 'manifest.json')]:
        target = base + '.arm-current/' + filename
        destination = storage / (base + '.' + suffix)
        if suffix == 'system.img' and not adopting and os.path.lexists(destination):
            expected = current_directory(storage, base) / filename
            if not destination.is_symlink() or (destination.exists() and destination.resolve() != expected):
                raise ValueError('Conflicting public ARM runtime disk; preserve both disks and repair offline')
        if destination.is_symlink() and os.readlink(destination) == target:
            continue
        temporary = storage / ('.' + base + '.' + suffix + '.link')
        temporary.unlink(missing_ok=True)
        temporary.symlink_to(target)
        os.replace(temporary, destination)
    sync_dir(storage)


def publish(storage, base, directory, adopting=False):
    if runtime.has_state(storage, base) and not adopting:
        old = json.loads((current_directory(storage, base) / "manifest.json").read_text())
        if old.get("schema_version") != 2 or old.get("runtime", {}).get("lifecycle") != "SEED":
            raise ValueError("Refusing to replace ARM runtime state; explicit offline reset required")
    valid_set(directory)
    manifest = json.loads((directory / 'manifest.json').read_text())
    runtime.migrate(manifest, (directory / 'system.img').stat().st_size)
    for name in ('kernel', 'initrd'):
        if manifest['artifacts'][name] != {'sha256': sha256(directory / name), 'bytes': (directory / name).stat().st_size}:
            raise ValueError('Immutable manifest mismatch: ' + name)
    if manifest['runtime']['lifecycle'] == 'SEED' and manifest['seed']['system_sha256'] != sha256(directory / 'system.img'):
        raise ValueError('Unpublished seed hash mismatch')
    runtime.grow(directory / 'system.img', requested_capacity(directory / 'system.img'))
    manifest['runtime']['virtual_bytes'] = (directory / 'system.img').stat().st_size
    atomic_json(directory / 'manifest.json', manifest)
    destination = storage / ('.' + base + '.arm-generation-' + uuid.uuid4().hex)
    os.rename(directory, destination)
    for name in (*ARTIFACTS, 'manifest.json'):
        with (destination / name).open('rb') as fh:
            os.fsync(fh.fileno())
    sync_dir(destination)
    pointer = storage / (base + '.arm-current')
    temporary = storage / ('.' + base + '.arm-pointer.tmp')
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(destination.name, target_is_directory=True)
    os.replace(temporary, pointer)
    sync_dir(storage)
    public_links(storage, base, adopting=adopting)
    print('Install: Published complete ARM artifact generation.', flush=True)


def current_directory(storage, base):
    pointer = storage / (base + '.arm-current')
    if not pointer.is_symlink():
        raise ValueError('No committed ARM generation.')
    directory = pointer.resolve(strict=True)
    if directory.parent != storage.resolve() or not directory.name.startswith('.' + base + '.arm-generation-'):
        raise ValueError('Invalid ARM generation pointer.')
    return directory


def cache(storage, base):
    if not runtime.has_state(storage, base):
        raise NoArtifacts('No committed ARM artifacts; new installation allowed')
    pointer = storage / (base + '.arm-current')
    if not pointer.is_symlink():
        # Legacy sets are already runtime state, even without a manifest.
        paths = {n: storage / (base + '.' + n) for n in ARTIFACTS}
        if not all(p.is_file() and not p.is_symlink() for p in paths.values()) or os.path.lexists(pointer):
            raise ValueError('Incomplete legacy ARM state; preserve storage and repair offline')
        if sha256(paths['kernel']) != BUILD['kernel_sha256'] or sha256(paths['initrd']) != BUILD['initrd_sha256']:
            raise ValueError('Legacy boot artifacts are not the validated DS124 build')
        junior = cpio(paths['initrd'].read_bytes())
        validator.validate(paths['system.img'], strict=True, junior=junior, runtime=True)
        import tempfile
        with tempfile.TemporaryDirectory(prefix='.rtd1619b-install-', dir=storage) as tmp:
            generation = Path(tmp) / 'generation'
            generation.mkdir(mode=0o700)
            for name, source in paths.items():
                subprocess.run(['cp', '--reflink=auto', '--sparse=always', '--preserve=all', str(source), str(generation / name)], check=True)
            manifest = manifest_for(generation)
            manifest['seed']['system_sha256'] = None
            manifest['seed']['hash_origin'] = 'unavailable: adopted legacy runtime'
            manifest['runtime']['lifecycle'] = 'BOOT_ATTEMPTED'
            manifest['source_url'] = os.environ.get('ARM_SOURCE_URL', '')
            manifest['provenance'] = 'legacy; exact stock kernel/initrd and read-only root validation'
            atomic_json(generation / 'manifest.json', manifest)
            publish(storage, base, generation, adopting=True)
    directory = current_directory(storage, base)
    disk = directory / 'system.img'
    manifest = runtime.migrate(json.loads((directory / 'manifest.json').read_text()), disk.stat().st_size)
    selection = os.environ.get('ARM_SOURCE_URL', '')
    if selection and manifest.get('source_url', '') != selection and not selection.startswith('file://'):
        raise ValueError('ARM cache source selection changed; runtime preserved, explicit reset required')
    for name in ('kernel', 'initrd'):
        expected = {'sha256': sha256(directory / name), 'bytes': (directory / name).stat().st_size}
        if manifest['artifacts'].get(name) != expected:
            raise ValueError('Immutable boot artifact mismatch: ' + name)
    valid_set(directory)
    runtime.grow(disk, requested_capacity(disk))
    manifest['runtime']['virtual_bytes'] = disk.stat().st_size
    # No seed or stopped disk hash comparison. DSM owns all runtime writes.
    atomic_json(directory / 'manifest.json', manifest)
    sync_dir(directory)
    public_links(storage, base)
    print('ARM cache verified: ' + json.dumps({'generation': directory.name, 'artifacts': manifest['artifacts'],
          'runtime': manifest['runtime'], 'mtimes_ns': {n: (directory / n).stat().st_mtime_ns for n in ARTIFACTS}}, sort_keys=True), flush=True)


def begin(storage, base):
    directory = current_directory(storage, base)
    manifest = json.loads((directory / 'manifest.json').read_text())
    manifest['runtime']['lifecycle'] = 'BOOT_ATTEMPTED'
    manifest['runtime']['generation'] += 1
    manifest['runtime']['launch_pending'] = True
    manifest['runtime']['launch_utc'] = runtime.now()
    atomic_json(directory / 'manifest.json', manifest)
    sync_dir(directory)


def seal(storage, base, exit_file=None):
    directory = current_directory(storage, base)
    manifest = json.loads((directory / 'manifest.json').read_text())
    valid_set(directory)
    for name in ('kernel', 'initrd'):
        if manifest['artifacts'][name]['sha256'] != sha256(directory / name):
            raise ValueError('Immutable boot artifact changed while running')
    observation = json.loads(exit_file.read_text()) if exit_file and exit_file.is_file() else {}
    clean = observation.get('qemu_exit_code') == 0 and observation.get('guest') is True and observation.get('reason') == 'guest-shutdown'
    manifest['runtime']['last_exit'] = {'utc': runtime.now(), 'clean': clean, **observation}
    manifest['runtime']['launch_pending'] = False
    manifest['runtime']['virtual_bytes'] = (directory / 'system.img').stat().st_size
    manifest['runtime']['dsm_evidence'] = runtime.disk_evidence(directory / 'system.img', validator)
    atomic_json(directory / 'manifest.json', manifest)
    sync_dir(directory)
    print('Install: Recorded ARM stopped runtime (clean=' + str(clean).lower() + '; disk hash is not a cache condition).', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('identity', 'build', 'publish', 'cache', 'begin', 'seal'))
    parser.add_argument('paths', nargs='+', type=Path)
    args = parser.parse_args()
    if args.operation == 'identity':
        print('Validated DS124 DSM 7.2.2-72806 PAT SHA-256: ' + identity(args.paths[0]))
    elif args.operation == 'build':
        build(*args.paths)
    else:
        storage, base, *rest = args.paths
        if base.name != 'DSM_DS124_72806' or str(base) != base.name:
            raise ValueError('Unsupported ARM artifact base.')
        globals()[args.operation](storage, str(base), *rest)


if __name__ == '__main__':
    try:
        main()
    except NoArtifacts as exc:
        print('Install: ' + str(exc), flush=True)
        sys.exit(80)
    except Exception as exc:
        print('ARM artifact preparation failed: ' + str(exc), file=sys.stderr)
        sys.exit(81)
