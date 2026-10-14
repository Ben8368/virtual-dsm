#!/usr/bin/env bash
# Refresh only read-only observers on the existing disposable network disk.
set -Eeuo pipefail
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
work_dir=$(realpath -e -- "$script_dir/work")
image="$work_dir/test-sata-usb-network.img"
[[ $EUID == 0 && "$work_dir" == "$script_dir/work" ]] || exit 2
[[ -f "$image" && ! -L "$image" ]] || exit 2
[[ -z $(losetup -j "$image") ]] || exit 2
if fuser "$image" >/dev/null 2>&1; then
  echo "Stop QEMU before refreshing research observers." >&2
  exit 2
fi
loop=$(losetup --find --show --offset 1048576 --sizelimit 2145749504 "$image")
mount_dir=$(mktemp -d "$work_dir/management-observer-mount.XXXXXX")
cleanup() {
  if mountpoint -q "$mount_dir"; then umount "$mount_dir" || return; fi
  losetup -d "$loop"
  rmdir "$mount_dir"
}
trap cleanup EXIT
[[ $(losetup -n -O BACK-FILE "$loop") == "$image" ]] || exit 2
mount -t ext4 -o prjquota,barrier=1,noatime "$loop" "$mount_dir"
install -m 0755 -- "$script_dir/network-observer.sh" "$mount_dir/root/arm64-network-observer.sh"
install -m 0755 -- "$script_dir/management-observer.sh" "$mount_dir/root/arm64-management-observer.sh"
install -m 0755 -- "$script_dir/scemd-lockup-observer.sh" "$mount_dir/root/arm64-scemd-lockup-observer.sh"
sync -f "$mount_dir"
