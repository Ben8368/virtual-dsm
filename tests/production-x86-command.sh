#!/usr/bin/env bash
# Capture the actual production argv with synthetic disks, without installing DSM.
set -Eeuo pipefail
image=${1:-virtual-dsm:phase1}
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf -- "$tmp"' EXIT
mkdir "$tmp/storage" "$tmp/bin"
printf DSM_VirtualDSM_test > "$tmp/storage/dsm.ver"
truncate -s 8M "$tmp/storage/DSM_VirtualDSM_test.boot.img"
truncate -s 8M "$tmp/storage/DSM_VirtualDSM_test.system.img"
cat > "$tmp/bin/qemu-system-x86_64" <<'QEMU'
#!/usr/bin/env bash
if [[ ${1:-} == --version ]]; then
  echo 'QEMU emulator version 11.1.0 (argument capture)'
else
  printf '%s\0' "$@" > /storage/captured-args
fi
QEMU
chmod +x "$tmp/bin/qemu-system-x86_64"
docker run --rm -v "$tmp/storage:/storage" -v "$tmp/bin:/capture-bin:ro" \
  -e PATH=/capture-bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
  -e KVM=N -e NETWORK=user -e WEB=N -e SHUTDOWN=N -e DISK_SIZE=6G \
  "$image" > "$tmp/startup.log" 2>&1 || { cat "$tmp/startup.log"; exit 1; }
python3 - "$tmp/storage/captured-args" <<'PY'
from pathlib import Path
import sys
args = Path(sys.argv[1]).read_bytes().decode().rstrip('\0').split('\0')
assert args[args.index('-machine') + 1] == 'type=q35,smm=off,usb=off,vmport=off,dump-guest-core=off,hpet=off'
assert args[args.index('-boot') + 1] == 'strict=on'
for name, address in [('synoboot', '0xa'), ('synosys', '0xb')]:
    assert any('id=' + name in arg and 'file=/storage/DSM_VirtualDSM_test.' in arg for arg in args)
    assert any('id=' + name in arg and 'bus=pcie.0,addr=' + address in arg for arg in args)
for device in ('virtio-scsi-pci', 'virtio-serial-pci', 'virtio-net-pci', 'virtio-rng-pci', 'virtio-balloon-pci'):
    assert any(arg.startswith(device + ',') for arg in args), device
assert not any('usb-net' in arg or 'rtd1619b' in arg for arg in args)
print('Default production x86 command passed: q35, PCI, VirtIO, synoboot/synosys, legacy boot.')
PY
