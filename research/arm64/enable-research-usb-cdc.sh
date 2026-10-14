#!/usr/bin/env bash
# Enable the supplied CDC module only after normal-init evidence proves missing autoload.
set -Eeuo pipefail
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
work_dir=$(realpath -e -- "$script_dir/work")
[[ $EUID == 0 && "$work_dir" == "$script_dir/work" ]] || exit 2
python3 - "$work_dir" <<'PY'
import json
import sys
from pathlib import Path
w = Path(sys.argv[1])
evidence = json.loads((w / 'usb-network-result.json').read_text())
log = (w / 'usb-network.log').read_text(errors='replace')
# File-based observation avoids the serial/getty stall on later DSM startup.
guest_log = w / 'usb-network-guest-observer.log'
if guest_log.is_file() and evidence.get('guest_log_capture_error') is None:
    log += '\n' + guest_log.read_text(errors='replace')
assert evidence['systemd_pid1'] and evidence['observer_seen']
assert all(x in log for x in ('idVendor=0525', 'idProduct=a4a2', 'bConfigurationValue=1', 'bInterfaceSubClass=06'))
assert not any(line.startswith(('cdc_ether ', 'usbnet ')) for line in log.splitlines())
assert 'ARM64_NETWORK_SNAPSHOT_END=0' in log
PY
image="$work_dir/test-sata-usb-network.img"
[[ -f "$image" && ! -L "$image" && -z $(losetup -j "$image") ]] || exit 2
loop=$(losetup --find --show --offset 1048576 --sizelimit 2145749504 "$image")
mount_dir=$(mktemp -d "$work_dir/network-cdc-mount.XXXXXX")
cleanup() {
  if mountpoint -q "$mount_dir"; then umount "$mount_dir" || return; fi
  losetup -d "$loop"
  rmdir "$mount_dir"
}
trap cleanup EXIT
[[ $(realpath -e -- "$image") == "$work_dir/test-sata-usb-network.img" ]] || exit 2
[[ $(losetup -n -O BACK-FILE "$loop") == "$image" ]] || exit 2
mount -t ext4 -o prjquota,barrier=1,noatime "$loop" "$mount_dir"
[[ -f "$mount_dir/usr/lib/modules/cdc_ether.ko" && -f "$mount_dir/usr/lib/modules/usbnet.ko" ]] || exit 2
# The shipped modules.dep already resolves USB framework dependencies.
printf 'cdc_ether\n' > "$mount_dir/usr/lib/modules-load.d/70-network-0007-research-usb-cdc.conf"
chmod 0644 "$mount_dir/usr/lib/modules-load.d/70-network-0007-research-usb-cdc.conf"
install -m 0755 "$script_dir/network-observer.sh" "$mount_dir/root/arm64-network-observer.sh"
{
  echo 'Only stock-driver activation added: cdc_ether via modules-load.d; network policy unchanged.'
  echo 'Reason: normal /init CDC configuration 1 enumerated; usbnet and cdc_ether absent from runtime /proc/modules.'
  cat "$mount_dir/usr/lib/modules-load.d/70-network-0007-research-usb-cdc.conf"
  cat "$mount_dir/etc/sysconfig/network-scripts/ifcfg-eth0"
  sha256sum "$mount_dir/usr/lib/modules/cdc_ether.ko" "$mount_dir/usr/lib/modules/usbnet.ko"
} > "$work_dir/usb-cdc-activation.txt"
sync -f "$mount_dir"
