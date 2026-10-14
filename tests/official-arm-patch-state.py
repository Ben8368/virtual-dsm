#!/usr/bin/env python3
"""Read-only comparison against the previously validated research patch-state tar."""
import argparse
import importlib.util
from pathlib import Path
import tarfile
from dissect.extfs import ExtFS
from dissect.util.stream import RangeStream

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('image', type=Path, help='Stopped production system image')
parser.add_argument('oracle', type=Path, help='Original ignored official-patch-state.tar')
args = parser.parse_args()
source = Path(__file__).resolve().parents[1] / 'src/platform/validate-arm-image.py'
spec = importlib.util.spec_from_file_location('validator', source)
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)
with args.image.open('rb') as fh, tarfile.open(args.oracle) as oracle:
    offset, size = validator.first_partition(fh)
    ext = ExtFS(RangeStream(fh, offset, size))
    expected = oracle.getmembers()
    actual = sorted(node.filename for node in validator.resolve(ext, '/.syno/patch').iterdir() if node.filename not in ('.', '..'))
    assert actual == sorted(Path(member.name).name for member in expected)
    for member in expected:
        node = validator.resolve(ext, '/' + member.name)
        assert node.open().read() == oracle.extractfile(member).read(), member.name
        inode = node.inode
        assert (inode.i_uid | inode.i_uid_high << 16, inode.i_gid | inode.i_gid_high << 16, inode.i_mode & 0o7777) == (member.uid, member.gid, member.mode), member.name
print('Official production /.syno/patch matches research oracle: selected names, file bytes, VERSION, checksum subset, ownership and permissions.')
