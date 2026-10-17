#!/usr/bin/env bash
set -Eeuo pipefail
image=${1:?image tag required}
expected=${2:?expected architecture required}
case "$expected" in amd64|arm64) ;; *) echo 'Expected amd64 or arm64' >&2; exit 64 ;; esac

metadata=$(docker image inspect --format '{{.Os}} {{.Architecture}} {{.Id}}' "$image")
read -r os architecture image_id <<<"$metadata"
[[ "$os:$architecture" == "linux:$expected" ]] || {
  echo "Image manifest mismatch: expected linux/$expected, got $os/$architecture ($image_id)" >&2
  exit 1
}

docker run --rm -i --entrypoint python3 "$image" - "$expected" <<'PY'
import os
import shutil
import struct
import sys

expected = {'amd64': 62, 'arm64': 183}[sys.argv[1]]
paths = ['/bin/sh', shutil.which('python3'), shutil.which('qemu-system-x86_64'),
         '/usr/local/bin/qemu-system-aarch64', '/run/host.bin']
for path in paths:
    if not path or not os.path.isfile(path):
        raise SystemExit(f'missing architecture-sensitive executable: {path}')
    with open(path, 'rb') as stream:
        header = stream.read(20)
    if header[:4] != b'\x7fELF':
        raise SystemExit(f'not an ELF executable: {path}')
    endian = '<' if header[5] == 1 else '>' if header[5] == 2 else None
    if endian is None:
        raise SystemExit(f'unknown ELF byte order: {path}')
    machine = struct.unpack(endian + 'H', header[18:20])[0]
    if machine != expected:
        raise SystemExit(f'{path}: ELF machine {machine}, expected {expected}')
print(f'linux/{sys.argv[1]} image and {len(paths)} executable ELF architectures agree')
PY

docker run --rm --entrypoint bash "$image" -ec '
  qemu-system-aarch64 --version
  qemu-system-x86_64 --version
  python3 -c "import dissect.cstruct; import dissect.extfs"
  if ldd /usr/local/bin/qemu-system-aarch64 | grep -q "not found"; then exit 1; fi
  sha256sum /usr/local/bin/qemu-system-aarch64 "$(command -v qemu-system-x86_64)" /run/host.bin
'
echo "Image architecture checks passed: $metadata"
