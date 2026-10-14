#!/usr/bin/env bash
# Clone the proven patch-state root and add only a read-only systemd observer.
set -Eeuo pipefail
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
work_dir=$(realpath -e -- "$script_dir/work")
[[ $EUID == 0 && "$work_dir" == "$script_dir/work" ]] || exit 2
image="$work_dir/test-sata-usb-network.img"
source_image="$work_dir/test-sata-patch-state.img"
[[ ! -e "$image" && ! -L "$image" && -f "$source_image" && ! -L "$source_image" ]] || exit 2
[[ -z $(losetup -j "$source_image") ]] || exit 2
cp --reflink=auto --sparse=always -- "$source_image" "$image"
loop=$(losetup --find --show --offset 1048576 --sizelimit 2145749504 "$image")
mount_dir=$(mktemp -d "$work_dir/network-observer-mount.XXXXXX")
cleanup() {
  if mountpoint -q "$mount_dir"; then umount "$mount_dir" || return; fi
  losetup -d "$loop"
  rmdir "$mount_dir"
}
trap cleanup EXIT
[[ $(realpath -e -- "$image") == "$work_dir/test-sata-usb-network.img" ]] || exit 2
[[ $(losetup -n -O BACK-FILE "$loop") == "$image" ]] || exit 2
mount -t ext4 -o prjquota,barrier=1,noatime "$loop" "$mount_dir"
install -m 0755 -- "$script_dir/network-observer.sh" "$mount_dir/root/arm64-network-observer.sh"
install -m 0755 -- "$script_dir/management-observer.sh" "$mount_dir/root/arm64-management-observer.sh"
cat > "$mount_dir/usr/lib/systemd/system/arm64-network-observer.service" <<'UNIT'
[Unit]
Description=Read-only ARM64 research network observer
DefaultDependencies=no
After=systemd-modules-load.service systemd-udev-trigger.service
Before=shutdown.target
Conflicts=shutdown.target

[Service]
Type=simple
ExecStart=/bin/bash /root/arm64-network-observer.sh
StandardOutput=null
StandardError=null
UNIT
ln -s ../arm64-network-observer.service "$mount_dir/usr/lib/systemd/system/sysinit.target.wants/arm64-network-observer.service"
sync -f "$mount_dir"
echo "Disposable observed normal /init image: $image"
