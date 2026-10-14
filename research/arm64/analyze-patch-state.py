#!/usr/bin/env python3
"""Read-only recursive PAT/initrd inventory; proprietary output stays in work/."""
import bz2
import gzip
import io
import lzma
from pathlib import Path, PurePosixPath
import re
import tarfile
import zipfile

WORK = Path(__file__).resolve().parent / 'work'
OUT = WORK / 'patch-analysis'
TERMS = re.compile(rb'\.syno/patch|patch/VERSION|check_root_junior_match|root_junior|junior|synoupgradepreserve|smallupdate|smallfix|patch version', re.I)
NAMES = re.compile(r'update|upgrade|patch|smallfix|junior|system|root|VERSION|package|index|manifest|checksum', re.I)
PRINTABLE = re.compile(rb'[\x20-\x7e\t]{4,}')
LIMIT = 1024 * 1024 * 1024
TOTAL_LIMIT = 8 * LIMIT
consumed = 0


def main():
    global consumed
    OUT.mkdir(exist_ok=True)
    saved = OUT / 'artifacts'
    saved.mkdir(exist_ok=True)
    with (WORK / 'patch-reference-map.txt').open('w') as refs, (WORK / 'pat-update-inventory.txt').open('w') as inv, (WORK / 'version-metadata.txt').open('w') as versions:
        refs.write('artifact | path | reference | role\nRole is lexical evidence; strings alone do not prove a creation operation.\n')
        inv.write('Recursive read-only listing. No archive member is extracted by its supplied path.\n')
        def scan(artifact, name, data, meta='', depth=0):
            global consumed
            consumed += len(data)
            if consumed > TOTAL_LIMIT or len(data) > LIMIT or depth > 12:
                raise RuntimeError('Archive safety budget exceeded')
            tag = artifact + '!' + name
            if NAMES.search(name) or depth == 0:
                inv.write(f'{tag} | {len(data)} bytes | {meta}\n')
            matches = [m for m in PRINTABLE.finditer(data) if TERMS.search(m.group())]
            for match in matches:
                text = match.group().decode('ascii')
                role = 'ELF string (trace callers)' if data.startswith(b'\x7fELF') else 'text/reference (inspect context)'
                refs.write(f'{artifact} | {name} | offset=0x{match.start():x}: {text} | {role}\n')
            if artifact == 'PAT!hda1.tgz' and name == 'usr/lib/libsynocodesign.so.7':
                (OUT/'libsynocodesign.so.7').write_bytes(data)
            leaf = PurePosixPath(name).name
            if leaf in ('VERSION', 'VERSION.init') or leaf.startswith('VERSION.'):
                if b'\0' not in data and len(data) < 65536:
                    versions.write(f'\nSOURCE {tag} | {meta}\n' + data.decode('utf-8', 'replace') + '\n')
            if (matches and (data.startswith(b'\x7fELF') or name.endswith(('.sh','.subr')) or 'linuxrc' in name)) or leaf in ('updater', 'synoupgrade', 'synoupdate', 'synoupgradepreserve'):
                import hashlib
                dest = saved / (hashlib.sha256(tag.encode()).hexdigest()[:12] + '-' + leaf)
                dest.write_bytes(data)
                inv.write(f'  SAVED {dest.relative_to(WORK)} <= {tag}\n')
            if data.startswith(bytes.fromhex('8cadbeef')):
                import importlib.util
                import logging
                logging.disable(logging.CRITICAL)
                spec = importlib.util.spec_from_file_location('patology', WORK/'patology.py')
                decoder = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(decoder)
                # SPKs use a separate official archive key class. Both signature verification
                # and authenticated decryption stay enabled; no key bytes are stored in the repo.
                import hashlib
                keylib = (OUT/'libsynocodesign.so.7').read_bytes()
                if hashlib.sha256(keylib).hexdigest() != '4fcd40ba28d882b29d93615389c495ea0f17cbcde8cb804e566badbc42887927':
                    raise RuntimeError('Expected official DS124 72806 codesign library')
                decoder.PUBLIC_KEY = keylib[0x23c40:0x23c60]
                decoder.SUBKEY = keylib[0x23c68:0x23c88]
                encrypted = decoder.Synocrack(io.BytesIO(data))
                if not encrypted.entries:
                    raise RuntimeError('Encrypted package decoder produced no entries')
                for member, entry in encrypted.entries.items():
                    header = entry['header']
                    mode = int(str(header.mode), 8)  # upstream parses lexical octal as decimal
                    inv.write(f'ENCRYPTED MEMBER {tag}!{member} | size={len(entry["entry"])} mode={mode:o} uid={header.uid} gid={header.gid}\n')
                    scan(tag, member, entry['entry'], f'mode={mode:o} uid={header.uid} gid={header.gid}', depth+1)
                return
            stream = io.BytesIO(data)
            try:
                archive = tarfile.open(fileobj=stream, mode='r:*')
            except (tarfile.TarError, EOFError):
                archive = None
            if archive is not None:
                with archive:
                    for member in archive:
                        inv.write(f'MEMBER {tag}!{member.name} | size={member.size} mode={member.mode:o} uid={member.uid} gid={member.gid} type={member.type!r} link={member.linkname}\n')
                        if member.isfile():
                            if member.size > LIMIT:
                                raise RuntimeError('Oversized member')
                            scan(tag, member.name, archive.extractfile(member).read(), f'mode={member.mode:o} uid={member.uid} gid={member.gid}', depth+1)
                return
            if data.startswith(b'PK\x03\x04'):
                with zipfile.ZipFile(io.BytesIO(data)) as archive:
                    for member in archive.infolist():
                        if not member.is_dir():
                            if member.file_size > LIMIT:
                                raise RuntimeError('Oversized zip member')
                            scan(tag, member.filename, archive.read(member), depth=depth+1)
                return
            # newc/CRC cpio, including compressed nested initramfs
            if data[:6] in (b'070701', b'070702'):
                pos=0
                while pos+110 <= len(data):
                    header=data[pos:pos+110]
                    if header[:6] not in (b'070701', b'070702'):
                        raise RuntimeError('Invalid cpio header')
                    fields=[int(header[i:i+8],16) for i in range(6,110,8)]
                    size, namesize=fields[6], fields[11]
                    path=data[pos+110:pos+110+namesize-1].decode('utf-8','replace')
                    start=(pos+110+namesize+3)&~3
                    if path=='TRAILER!!!': break
                    inv.write(f'MEMBER {tag}!{path} | size={size} mode={fields[1]:o} uid={fields[2]} gid={fields[3]}\n')
                    if fields[1]&0o170000 == 0o100000:
                        scan(tag,path,data[start:start+size],f'mode={fields[1]&0o7777:o} uid={fields[2]} gid={fields[3]}',depth+1)
                    pos=(start+size+3)&~3
                return
            for magic, opener in ((b'\x1f\x8b',gzip.GzipFile),(b'\xfd7zXZ\x00',lzma.LZMAFile),(b'BZh',bz2.BZ2File)):
                if data.startswith(magic):
                    with (opener(fileobj=io.BytesIO(data), mode='rb') if opener is gzip.GzipFile else opener(io.BytesIO(data),'rb')) as compressed:
                        expanded=compressed.read(LIMIT+1)
                    scan(tag,'<decompressed>',expanded,depth=depth+1)
                    return
        for path in sorted((WORK/'extracted').rglob('*')):
            if path.is_file() and not path.is_symlink():
                scan('PAT',str(path.relative_to(WORK/'extracted')),path.read_bytes())
        # Include the exact stock newc, not host-extracted symlink semantics.
        scan('rd.bin', 'stock rd.bin.cpio', (WORK/'boot/rd.bin.cpio').read_bytes())
        inv.write(f'\nTOTAL SCANNED BYTES (nested levels counted): {consumed}\n')
    print('Reports written:', WORK/'patch-reference-map.txt', WORK/'pat-update-inventory.txt', WORK/'version-metadata.txt')


if __name__ == '__main__':
    main()
