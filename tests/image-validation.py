#!/usr/bin/env python3
"""Synthetic ext4 image tests: no DSM downloads or proprietary files."""
import hashlib
import importlib.util
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile

repo = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('validator', repo / 'src/platform/validate-arm-image.py')
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


def check(image, expected):
    before = hashlib.sha256(image.read_bytes()).digest()
    try:
        validator.validate(image, strict=False)
        success = True
    except (ValueError, FileNotFoundError):
        success = False
    assert success == expected, (image.name, expected)
    assert hashlib.sha256(image.read_bytes()).digest() == before, 'Validator modified the image'


with tempfile.TemporaryDirectory() as directory:
    work = Path(directory)
    root = work / 'root'
    (root / 'usr/lib/modules').mkdir(parents=True)
    (root / 'usr/lib/modules-load.d').mkdir()
    (root / 'etc/modules-load.d').mkdir(parents=True)
    (root / 'dev').mkdir()
    (root / 'dev/null').touch()
    (root / 'lib').symlink_to('usr/lib')
    conf = root / 'usr/lib/modules-load.d/70-cdc.conf'
    conf.write_text('# stock driver activation\ncdc_ether\n')
    for module in ('usbnet', 'cdc_ether'):
        (root / ('usr/lib/modules/' + module + '.ko')).write_bytes(b'synthetic test module')

    def image(name, gpt=False):
        filesystem = work / 'fs.ext4'
        with filesystem.open('wb') as fh:
            fh.truncate(32 * 1024 * 1024)
        subprocess.run(['mkfs.ext4', '-q', '-F', '-d', str(root), str(filesystem)], check=True)
        output = work / (name + '.img')
        with output.open('wb') as fh:
            mbr = bytearray(512)
            mbr[510:] = b'\x55\xaa'
            mbr[450] = 0xee if gpt else 0x83
            struct.pack_into('<II', mbr, 454, 2048, filesystem.stat().st_size // 512)
            fh.write(mbr)
            if gpt:
                header = bytearray(512)
                header[:8] = b'EFI PART'
                struct.pack_into('<QII', header, 72, 2, 128, 128)
                fh.write(header)
                entry = bytearray(128)
                entry[:16] = b'\x01' * 16
                struct.pack_into('<QQ', entry, 32, 2048, 2048 + filesystem.stat().st_size // 512 - 1)
                fh.write(entry)
            fh.seek(1024 * 1024)
            with filesystem.open('rb') as src:
                shutil.copyfileobj(src, fh)
        return output

    check(image('valid-mbr'), True)
    check(image('valid-gpt', gpt=True), True)
    conf.write_text('# cdc_ether is absent\nusbnet\n')
    check(image('missing-activation'), False)
    conf.write_text('cdc_ether\n')
    mask = root / 'etc/modules-load.d/70-cdc.conf'
    mask.symlink_to('/dev/null')
    check(image('masked-activation'), False)
    mask.unlink()
    (root / 'usr/lib/modules/cdc_ether.ko').unlink()
    check(image('missing-module'), False)
    bad = work / 'invalid.img'
    bad.write_bytes(b'invalid image')
    check(bad, False)
print('Read-only image validation tests passed: MBR/GPT, symlinks, masks, missing activation/modules, invalid image.')
