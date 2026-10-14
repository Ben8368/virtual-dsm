"""DS124 installed-root contract promoted from the validated ARM research tools."""
import hashlib
import posixpath
import stat
import struct
import tarfile

SUPPORTED = {
    ('DS124', '7.2.2', '72806'): {
        'sha256': '17f48a9a4572c9b3b994921d3fb410d8186e9c4bf02cf9334e37897e5752e1dd',
        'unique': 'synology_rtd1619b_ds124',
        'kernel_sha256': '4c6584070c2bfee8a7ab1b73ef74d1872a0469700e61fc806e6b72d23e576b14',
        'initrd_sha256': '3177c1be9dbc40224c5ad193d7ad032e74c83ce54e5d436ebec209b26384a2bf',
        'updater_sha256': '9d207ec7156abc1f70ab5970e2a53606cbc31a1b3e02ea30bbc3bf55c7c49c32',
    },
}
BUILD = SUPPORTED[('DS124', '7.2.2', '72806')]
UNSUPPORTED = 'This rtd1619b installer currently supports only DS124 DSM 7.2.2-72806.'
# Promoted verbatim from prepare-populated-root.sh; NOT physical DS124 geometry.
IMAGE_BYTES = 2147483648
START_SECTOR = 2048
PARTITION_SECTORS = 4190917
FEATURES = ('has_journal,ext_attr,resize_inode,filetype,extent,64bit,flex_bg,'
            'sparse_super,large_file,huge_file,uninit_bg,dir_nlink,extra_isize,quota,project')
CDC_PATH = 'usr/lib/modules-load.d/70-network-0007-research-usb-cdc.conf'
PATCH_EXCLUDE = {'hda1.tgz', 'indexdb.txz', 'synohdpack_img.txz', 'checksum.syno',
                 'Synology.sig', 'updater_manutil', 'createvolume', 'SkipCheckPackingMatch',
                 'autonano.pat', 'RedBoot.msys', 'configupdate'}


def sha256(path):
    with open(path, 'rb') as fh:
        return hashlib.file_digest(fh, 'sha256').hexdigest()


def kv(data):
    result = {}
    for line in data.decode().splitlines():
        if '=' in line and not line.startswith('#'):
            key, value = line.split('=', 1)
            result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def validate_version(data, unique=False):
    fields = kv(data)
    if fields.get('buildnumber') != '72806' or fields.get('productversion') != '7.2.2':
        raise ValueError(UNSUPPORTED + ' VERSION mismatch.')
    if unique and fields.get('unique') != BUILD['unique']:
        raise ValueError(UNSUPPORTED + ' DS124/rtd1619b identity mismatch.')
    return fields


def kernel(data):
    if not 1024 * 1024 <= len(data) <= 128 * 1024 * 1024 or data[56:60] != b'ARM\x64':
        raise ValueError('Invalid ARM64 Linux Image: size or ARMd header.')
    image_size = struct.unpack_from('<Q', data, 16)[0]
    if image_size > 128 * 1024 * 1024:
        raise ValueError('Invalid ARM64 Linux Image size header.')


def cpio(data):
    entries = {}
    offset = 0
    while offset + 110 <= len(data):
        if data[offset:offset + 6] not in (b'070701', b'070702'):
            raise ValueError('Invalid initramfs: expected SVR4/newc cpio.')
        fields = [int(data[offset + 6 + i * 8:offset + 14 + i * 8], 16) for i in range(13)]
        mode, size, namesize = fields[1], fields[6], fields[11]
        start = offset + 110
        if namesize < 1 or start + namesize > len(data) or data[start + namesize - 1] != 0:
            raise ValueError('Invalid initramfs name bounds.')
        name = data[start:start + namesize - 1].decode()
        start = (start + namesize + 3) & ~3
        if start + size > len(data):
            raise ValueError('Invalid initramfs data bounds.')
        payload = data[start:start + size]
        if fields[12] and data[offset:offset + 6] == b'070702' and sum(payload) & 0xffffffff != fields[12]:
            raise ValueError('Invalid initramfs CRC.')
        offset = (start + size + 3) & ~3
        if name == 'TRAILER!!!':
            break
        normalized = posixpath.normpath('/' + name.lstrip('/'))
        if normalized in entries:
            raise ValueError('Duplicate initramfs member.')
        entries[normalized] = (mode, payload)
    else:
        raise ValueError('Invalid initramfs: missing trailer.')

    def read(name, depth=0):
        if depth > 32:
            raise ValueError('Invalid initramfs symlink cycle.')
        current = ''
        parts = posixpath.normpath(name).strip('/').split('/')
        for i, part in enumerate(parts):
            current += '/' + part
            mode, payload = entries[current]
            if stat.S_ISLNK(mode):
                target = posixpath.join(posixpath.dirname(current), payload.decode())
                return read(posixpath.join(target, *parts[i + 1:]), depth + 1)
        if not stat.S_ISREG(mode) or not payload:
            raise ValueError('Invalid initramfs required file: ' + name)
        return payload

    for name in ('/init', '/bin/sh', '/etc.defaults/synoinfo.conf'):
        read(name)
    validate_version(read('/etc.defaults/VERSION'))
    if kv(read('/etc.defaults/synoinfo.conf')).get('unique') != BUILD['unique']:
        raise ValueError(UNSUPPORTED + ' Initramfs identity mismatch.')
    return read


def junior_contract(junior_read, root_read):
    junior_info = kv(junior_read('/etc.defaults/synoinfo.conf'))
    root_info = kv(root_read('/etc.defaults/synoinfo.conf'))
    junior = validate_version(junior_read('/etc.defaults/VERSION'))
    base = validate_version(root_read('/etc.defaults/VERSION'))
    patch = validate_version(root_read('/.syno/patch/VERSION'), unique=True)
    if junior_info.get('unique') != BUILD['unique'] or root_info.get('unique') != BUILD['unique']:
        raise ValueError('Root/junior mismatch: synoinfo unique.')
    if base['buildnumber'] != junior['buildnumber']:
        raise ValueError('Root/junior mismatch: root buildnumber.')
    for key in ('buildnumber', 'smallfixnumber', 'packing', 'packing_id'):
        if junior.get(key, '') != patch.get(key, ''):
            raise ValueError('Root/junior mismatch: patch ' + key)


def safe_members(archive):
    """Check complete archive before GNU tar. Never write through any link ancestor.

    Stock DSM has guest-absolute symlinks (e.g. /etc.defaults/passwd). These
    remain inert link objects: no member may be extracted beneath ANY symlink,
    and hardlinks must resolve to regular archive members, never host paths.
    """
    members = archive.getmembers()
    names = {}
    for item in members:
        name = item.name
        if name.startswith('/') or '..' in name.split('/') or '\x00' in name:
            raise ValueError('Unsafe root archive member path.')
        name = posixpath.normpath(name)
        if name in names or name == '..':
            raise ValueError('Unsafe root archive duplicate member.')
        if not (item.isdir() or item.isfile() or item.issym() or item.islnk() or item.ischr() or item.isblk() or item.isfifo()):
            raise ValueError('Unsafe root archive member type.')
        names[name] = item
    for name, item in names.items():
        parent = posixpath.dirname(name)
        while parent not in ('', '.'):
            if parent in names and not names[parent].isdir():
                raise ValueError('Unsafe root archive: extraction through link/non-directory.')
            parent = posixpath.dirname(parent)
        if item.issym():
            target = item.linkname
            if not target or (not target.startswith('/') and posixpath.normpath(posixpath.join(posixpath.dirname(name), target)).startswith('../')):
                raise ValueError('Unsafe root archive symlink target.')
        if item.islnk():
            target = item.linkname
            if target.startswith('/') or '..' in target.split('/'):
                raise ValueError('Unsafe root archive hardlink target.')
            target = posixpath.normpath(target)
            visited = {name}
            while target in names and names[target].islnk():
                if target in visited:
                    raise ValueError('Unsafe root archive hardlink cycle.')
                visited.add(target)
                target = posixpath.normpath(names[target].linkname)
            if target not in names or not names[target].isfile():
                raise ValueError('Unsafe root archive hardlink target type.')
    return members


def patch_archive(entries, output):
    """Exact official updater backup-loop selection/grep semantics from research."""
    import copy
    import io
    chosen = [name for name, (header, _) in entries.items()
              if '/' not in name and header.isfile() and name not in PATCH_EXCLUDE]
    lines = entries['checksum.syno'][1].splitlines(keepends=True)
    checksum = b''.join(line for name in chosen for line in lines if name.lower().encode() in line.lower())
    with tarfile.open(output, 'w') as archive:
        for name in chosen:
            header, data = entries[name]
            header = copy.copy(header)
            header.name = '.syno/patch/' + name
            header.uid = header.gid = 0
            header.mode &= ~0o022
            archive.addfile(header, io.BytesIO(data))
        header = tarfile.TarInfo('.syno/patch/checksum.syno')
        header.mode = 0o644
        header.size = len(checksum)
        archive.addfile(header, io.BytesIO(checksum))
    return chosen
