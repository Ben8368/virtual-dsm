#!/usr/bin/env python3
"""Inspect an official root tarball; verify metadata without extracting on DrvFS."""
import argparse
import collections
import os
from pathlib import Path, PurePosixPath
import stat
import tarfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--root', type=Path)
    args = parser.parse_args()
    counts = collections.Counter()
    pax = collections.Counter()
    mismatches = []
    members = []
    with tarfile.open(args.archive, 'r:*') as archive:
        for member in archive:
            path = PurePosixPath(member.name)
            if path.is_absolute() or '..' in path.parts:
                raise ValueError(f'Unsafe archive member: {member.name}')
            if member.islnk():
                target = PurePosixPath(member.linkname)
                if target.is_absolute() or '..' in target.parts:
                    raise ValueError(f'Unsafe hardlink: {member.name}')
            counts[member.type.decode('ascii', 'replace')] += 1
            pax.update(member.pax_headers.keys())
            members.append(member)
    print(f'Archive: {args.archive.resolve()}')
    print(f'Members: {len(members)}; regular file bytes: {sum(m.size for m in members if m.isfile())}')
    print(f'Tar type counts: {dict(counts)} (0=regular, 1=hardlink, 2=symlink, 3=char, 4=block, 5=directory, 6=FIFO)')
    print(f'PAX header counts: {dict(pax)}')
    for m in members:
        if m.isdev() or m.isfifo() or m.islnk() or m.pax_headers:
            print(f'Special/metadata: {m.name} type={m.type!r} mode={m.mode:o} uid={m.uid} gid={m.gid} link={m.linkname} device={m.devmajor}:{m.devminor} pax={m.pax_headers!r}')
    if args.root is None:
        return
    root = args.root.resolve(strict=True)
    if not os.path.ismount(root):
        raise ValueError('Verification root must be a mounted filesystem')
    # Archive may include absolute symlinks; resolve them within the guest namespace.
    def guest_path(name):
        pending = list(PurePosixPath(name).parts)
        current = root
        hops = 0
        while pending:
            part = pending.pop(0)
            if part in ('', '.', '/'):
                continue
            if part == '..':
                current = current.parent if current != root else root
                continue
            current /= part
            if pending and current.is_symlink():
                hops += 1
                if hops > 40:
                    raise ValueError('Symlink loop')
                target = os.readlink(current)
                current = root if target.startswith('/') else current.parent
                pending = list(PurePosixPath(target).parts) + pending
        return current
    for m in members:
        try:
            path = guest_path(m.name)
            s = path.lstat()
            if (s.st_uid, s.st_gid, stat.S_IMODE(s.st_mode)) != (m.uid, m.gid, m.mode):
                mismatches.append(f'{m.name}: ownership/mode mismatch')
            if abs(s.st_mtime - m.mtime) > 0.001:
                mismatches.append(f'{m.name}: mtime mismatch')
            if m.issym() and (not stat.S_ISLNK(s.st_mode) or os.readlink(path) != m.linkname):
                mismatches.append(f'{m.name}: symlink mismatch')
            if m.islnk():
                target = guest_path(m.linkname).stat()
                if (s.st_dev, s.st_ino) != (target.st_dev, target.st_ino):
                    mismatches.append(f'{m.name}: hardlink inode mismatch')
            if m.ischr() or m.isblk():
                predicate = stat.S_ISCHR if m.ischr() else stat.S_ISBLK
                if not predicate(s.st_mode) or (os.major(s.st_rdev), os.minor(s.st_rdev)) != (m.devmajor, m.devminor):
                    mismatches.append(f'{m.name}: device mismatch')
            if m.isfifo() and not stat.S_ISFIFO(s.st_mode):
                mismatches.append(f'{m.name}: FIFO mismatch')
            if m.isdir() and not stat.S_ISDIR(s.st_mode):
                mismatches.append(f'{m.name}: directory type mismatch')
            if m.isfile() and (not stat.S_ISREG(s.st_mode) or s.st_size != m.size):
                mismatches.append(f'{m.name}: regular file type/size mismatch')
            for key, value in m.pax_headers.items():
                if key.startswith('SCHILY.xattr.'):
                    if os.getxattr(path, key[len('SCHILY.xattr.'):], follow_symlinks=False) != value.encode('utf-8', 'surrogateescape'):
                        mismatches.append(f'{m.name}: xattr mismatch {key}')
        except (OSError, ValueError) as error:
            mismatches.append(f'{m.name}: {error}')
    print(f'Verified {len(members)} members: numeric UID/GID, modes, mtime, type/size, symlink targets, hardlink inodes, special devices/FIFOs and encoded xattrs.')
    print(f'Metadata mismatches: {len(mismatches)}')
    for mismatch in mismatches:
        print(mismatch)
    if mismatches:
        raise SystemExit(1)
    expectations = [
        ('etc.defaults', 'linuxrc.syno.impl:853-857; check_root_junior_match.sh:24', 'seed /etc and validate defaults'),
        ('etc.defaults/synoinfo.conf', 'check_root_junior_match.sh:40', 'compare unique'),
        ('etc.defaults/VERSION', 'check_root_junior_match.sh:41', 'compare buildnumber'),
        ('etc', 'linuxrc.syno.impl:853-859', 'reuse or replace passwd/group symlink template'),
        ('usr/syno/etc.defaults', 'linuxrc.syno.impl:860-865', 'seed /usr/syno/etc if absent'),
        ('usr/syno/etc', 'linuxrc.syno.impl:860-865', 'optional before mount; generated from defaults'),
        ('var.defaults', 'linuxrc.syno.impl:867-872', 'seed /var if absent'),
        ('var', 'linuxrc.syno.impl:867-872', 'optional before mount; generated from defaults'),
        ('sbin/init', 'linuxrc.syno.impl:891-893', 'must resolve to an executable'),
        ('.syno/patch', 'check_root_junior_match.sh:45', 'AssertDirectory; fatal if absent'),
        ('.syno/patch/VERSION', 'check_root_junior_match.sh:46-50', 'compare buildnumber/smallfixnumber/packing/packing_id'),
        ('usr/syno/sbin/synoupgradepreserve', 'dsmupdate/datadevice.sh:129-140', 'optional executable upgrade fallback'),
    ]
    checklist = ['Pre-boot /tmpRoot expectations: official payload only', 'path | required by | operation | present yes/no']
    for name, required, operation in expectations:
        p = guest_path(name)
        exists = p.exists() or p.is_symlink()
        checklist.append(f'/tmpRoot/{name} | {required} | {operation} | {"yes" if exists else "no"}')
    for name in ('etc.defaults/synoinfo.conf', 'etc.defaults/VERSION'):
        values = guest_path(name).read_text().splitlines()
        checklist.extend(f'{name}: {line}' for line in values if line.split('=', 1)[0] in ('unique', 'buildnumber', 'smallfixnumber', 'packing', 'packing_id'))
    print('\n' + '\n'.join(checklist))
    (args.archive.resolve().parent.parent / 'root-expectations-checklist.txt').write_text('\n'.join(checklist) + '\n')


if __name__ == '__main__':
    main()
