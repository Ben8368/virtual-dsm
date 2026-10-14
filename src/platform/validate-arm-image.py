#!/usr/bin/env python3
"""Read-only prepared-image check. No loop devices, mounts or journal replay."""
import os
import posixpath
import stat
import struct
import sys
from dissect.extfs import ExtFS
from dissect.util.stream import RangeStream


def first_partition(fh):
    size = os.fstat(fh.fileno()).st_size
    mbr = fh.read(512)
    if len(mbr) != 512 or mbr[510:] != b'\x55\xaa':
        raise ValueError('Prepared system image must have an MBR/GPT partition table')
    entry = mbr[446:462]
    start, sectors = struct.unpack_from('<II', entry, 8)
    if entry[4] == 0xee:
        fh.seek(512)
        header = fh.read(512)
        if header[:8] != b'EFI PART':
            raise ValueError('Invalid GPT header')
        table, count, width = struct.unpack_from('<QII', header, 72)
        if not count or not 128 <= width <= 4096 or table * 512 + width > size:
            raise ValueError('Invalid GPT partition table')
        fh.seek(table * 512)
        first = fh.read(width)
        if first[:16] == bytes(16):
            raise ValueError('Missing first GPT partition')
        start, end = struct.unpack_from('<QQ', first, 32)
        sectors = end - start + 1
    if start < 1 or sectors < 1 or (start + sectors) * 512 > size:
        raise ValueError('Invalid first system partition bounds')
    return start * 512, sectors * 512


def resolve(ext, path, depth=0):
    if depth > 32:
        raise ValueError('Too many image symlinks')
    parts = posixpath.normpath('/' + path.lstrip('/')).strip('/').split('/')
    current = ''
    node = ext.root
    for index, part in enumerate(parts):
        if not part:
            continue
        current += '/' + part
        node = ext.get(current)
        if node.filetype == stat.S_IFLNK:
            target = posixpath.join(posixpath.dirname(current), node.link)
            target = posixpath.join(target, *parts[index + 1:])
            return resolve(ext, target, depth + 1)
    return node


def validate(path, strict=True, junior=None, runtime=False):
    with open(path, 'rb') as fh:
        offset, size = first_partition(fh)
        ext = ExtFS(RangeStream(fh, offset, size))
        if strict:
            import importlib.util
            from pathlib import Path
            contract_spec = importlib.util.spec_from_file_location('arm_contract', Path(__file__).with_name('arm_contract.py'))
            contract = importlib.util.module_from_spec(contract_spec)
            contract_spec.loader.exec_module(contract)
            if offset != contract.START_SECTOR * 512 or size != contract.PARTITION_SECTORS * 512 or (os.fstat(fh.fileno()).st_size < contract.IMAGE_BYTES if runtime else os.fstat(fh.fileno()).st_size != contract.IMAGE_BYTES):
                raise ValueError('Unexpected research-compatible p1 geometry')
            fh.seek(446)
            table = fh.read(64)
            if table[4] != 0x83 or (not runtime and any(table[16:])):
                raise ValueError('Expected Linux system p1 in MBR partition table')
            if runtime:
                regions = [(offset // 512, (offset + size) // 512)]
                for index in range(1, 4):
                    entry = table[index * 16:(index + 1) * 16]
                    start, sectors = struct.unpack_from('<II', entry, 8)
                    if not entry[4] and not start and not sectors:
                        continue
                    end = start + sectors
                    if not entry[4] or start < 1 or not sectors or end * 512 > os.fstat(fh.fileno()).st_size or any(start < b and end > a for a, b in regions):
                        raise ValueError('Invalid or overlapping runtime MBR partition')
                    regions.append((start, end))
            sb = ext.sb
            if not sb.s_feature_incompat & 0x40 or ext.block_size != 4096 or sb.s_inode_size != 256 or not sb.s_feature_compat & 4 or sb.s_feature_ro_compat & 0x400 or sb.s_feature_ro_compat & 0x2100 != 0x2100:
                raise ValueError('Invalid ext4 contract: journal/project/quota, 4096 blocks, 256 inodes, no metadata_csum required')
            def read(path):
                node = resolve(ext, path)
                if node.filetype != stat.S_IFREG or node.size > 1048576:
                    raise ValueError('Invalid root contract file: ' + path)
                return node.open().read()
            contract.validate_version(read('/etc.defaults/VERSION'))
            contract.validate_version(read('/.syno/patch/VERSION'), unique=True)
            if contract.kv(read('/etc.defaults/synoinfo.conf')).get('unique') != contract.BUILD['unique']:
                raise ValueError('Root DS124/rtd1619b identity mismatch')
            init = resolve(ext, '/sbin').listdir()['init']
            if init.filetype != stat.S_IFLNK or not init.link.endswith('/systemd') or not resolve(ext, '/sbin/init').size:
                raise ValueError('/sbin/init must resolve to systemd')
            if read('/' + contract.CDC_PATH) != b'cdc_ether\n':
                raise ValueError('Missing proven CDC activation entry')
            if junior is not None:
                contract.junior_contract(junior, read)
        for name in ('usbnet', 'cdc_ether'):
            node = resolve(ext, '/usr/lib/modules/' + name + '.ko')
            if node.filetype != stat.S_IFREG or not node.size:
                raise ValueError('Missing stock module: ' + name)
        # systemd modules-load precedence: same-named files in /etc override
        # /run, /usr/local/lib, /usr/lib, then legacy /lib. /dev/null masks a file.
        seen = set()
        active = False
        for directory in ('/etc/modules-load.d', '/run/modules-load.d',
                          '/usr/local/lib/modules-load.d', '/usr/lib/modules-load.d',
                          '/lib/modules-load.d'):
            try:
                entries = resolve(ext, directory).iterdir()
                for entry in entries:
                    name = entry.filename
                    if not name.endswith('.conf') or name in seen:
                        continue
                    seen.add(name)
                    try:
                        conf = resolve(ext, directory + '/' + name)
                        if conf.filetype != stat.S_IFREG or conf.size > 65536:
                            continue
                        text = conf.open().read().decode('utf-8', errors='replace')
                        active |= any(line.strip() == 'cdc_ether' for line in text.splitlines())
                    except FileNotFoundError:
                        pass
            except FileNotFoundError:
                pass
        if not active:
            raise ValueError('Prepared image must activate cdc_ether in an effective modules-load.d/*.conf file')
    print('Prepared DS124 system image: stock USB modules and cdc_ether activation verified (read-only)')


if __name__ == '__main__':
    try:
        if len(sys.argv) != 2:
            raise ValueError('Usage: validate-arm-image.py SYSTEM_IMAGE')
        validate(sys.argv[1], runtime=True)
    except Exception as exc:
        print('ARM prepared-image validation failed: ' + str(exc), file=sys.stderr)
        sys.exit(81)
