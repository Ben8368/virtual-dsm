#!/usr/bin/env bash
# Disposable research geometry, not a canonical Synology disk layout.
set -Eeuo pipefail
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
work_dir=$(realpath -e -- "$script_dir/work")
[[ "$work_dir" == "$script_dir/work" ]] || { echo "Work directory must not resolve outside the research workspace." >&2; exit 2; }
image_name="${ROOT_IMAGE_NAME:-test-sata-root-populated.img}"
case "$image_name" in
  test-sata-root-populated.img|test-sata-patch-state.img) ;;
  *) echo 'Unsupported disposable research image name.' >&2; exit 2 ;;
esac
image="$work_dir/$image_name"
archive="$work_dir/extracted/hda1.tgz"
if [[ "$image_name" == test-sata-root-populated.img ]]; then
  report="$work_dir/root-population-report.txt"
else
  report="$work_dir/${image_name%.img}-population-report.txt"
fi
loop=
mount_dir=
[[ $EUID == 0 ]] || { echo 'Run under Linux as root (e.g. WSL).' >&2; exit 2; }
for tool in realpath losetup mkfs.ext4 sfdisk mount umount tar python3 stat file readlink tune2fs fuser mountpoint findmnt truncate sha256sum tee; do
  command -v "$tool" >/dev/null || { echo "Missing $tool" >&2; exit 2; }
done
[[ -s "$archive" ]] || { echo "Missing official payload: $archive" >&2; exit 2; }
[[ ! -L "$image" ]] || { echo 'Image cannot be a symlink.' >&2; exit 2; }
assert_image() {
  [[ $(realpath -m -- "$image") == "$work_dir/$image_name" && -f "$image" && ! -L "$image" ]] || exit 2
}
if [[ -e "$image" ]]; then
  assert_image
  [[ -z $(losetup -j "$image") ]] || { echo 'Image still attached to a loop device.' >&2; exit 2; }
  ! fuser "$image" >/dev/null 2>&1 || { echo 'Image still in use.' >&2; exit 2; }
  rm -- "$image"
fi
exec > >(tee "$report") 2>&1
cleanup() {
  if [[ -n "$mount_dir" ]] && mountpoint -q "$mount_dir"; then
    umount "$mount_dir" || return
  fi
  if [[ -n "$loop" ]]; then losetup -d "$loop"; fi
  if [[ -n "$mount_dir" ]]; then rmdir "$mount_dir"; fi
}
trap cleanup EXIT
printf 'Research root population; UTC: %s\n' "$(date -u +%FT%TZ)"
sha256sum "$archive" "$work_dir/boot/zImage.Image" "$work_dir/boot/rd.bin.cpio"
file "$archive"
# Inspect special objects and metadata BEFORE extraction or formatting.
python3 "$script_dir/inspect-root-payload.py" "$archive"
read -r image_bytes start_sector partition_sectors partition_bytes features < <(
  python3 - "$script_dir/../../src/platform" <<'PYCONTRACT'
import sys
sys.path.insert(0, sys.argv[1])
from arm_contract import IMAGE_BYTES, START_SECTOR, PARTITION_SECTORS, FEATURES
print(IMAGE_BYTES, START_SECTOR, PARTITION_SECTORS, PARTITION_SECTORS * 512, FEATURES)
PYCONTRACT
)
truncate -s "$image_bytes" "$image"
assert_image
printf 'label: dos\nunit: sectors\n\nstart=%s, size=%s, type=83\n' "$start_sector" "$partition_sectors" | sfdisk "$image"
assert_image
sfdisk --dump "$image"
# One offset loop maps ONLY p1 in the explicitly checked file; no host disk scan.
assert_image
loop=$(losetup --find --show --offset 1048576 --sizelimit 2145749504 "$image")
assert_loop() {
  assert_image
  [[ $(losetup -n -O BACK-FILE "$loop") == "$image" ]] || exit 2
  [[ $(losetup -n -O OFFSET "$loop" | tr -d ' ') == 1048576 ]] || exit 2
  [[ $(losetup -n -O SIZELIMIT "$loop" | tr -d ' ') == 2145749504 ]] || exit 2
}
assert_loop
# Match the full previously observed Synology feature set, avoiding new host defaults.
mkfs.ext4 -F -b 4096 -I 256 -O "none,$features" "$loop"
tune2fs -l "$loop"
mount_dir=$(mktemp -d "$work_dir/root-population-mount.XXXXXX")
assert_loop
# The host rejected rootprjquota; the normal guest retains the full mount options.
echo "Host extraction mount: prjquota,barrier=1,noatime; guest contract: prjquota,rootprjquota,barrier=1,noatime"
mount -t ext4 -o prjquota,barrier=1,noatime "$loop" "$mount_dir"
findmnt --target "$mount_dir"
tar --extract --file="$archive" --directory="$mount_dir" --numeric-owner \
  --same-owner --same-permissions --delay-directory-restore --xattrs \
  --xattrs-include='*' --acls --selinux
python3 "$script_dir/inspect-root-payload.py" "$archive" --root "$mount_dir"
for path in etc etc.defaults bin sbin lib usr usr/syno var.defaults etc.defaults/synoinfo.conf etc.defaults/VERSION sbin/init bin/sh .syno/patch .syno/patch/VERSION; do
  printf '\nCritical path: /%s\n' "$path"
  if [[ -e "$mount_dir/$path" || -L "$mount_dir/$path" ]]; then
    stat -c 'type=%F mode=%a uid=%u gid=%g size=%s mtime=%y name=%N' "$mount_dir/$path"
    file -h "$mount_dir/$path"
    if [[ -L "$mount_dir/$path" ]]; then readlink "$mount_dir/$path"; fi
  else
    echo 'ABSENT from official extraction'
  fi
done
sync -f "$mount_dir"
umount "$mount_dir"
losetup -d "$loop"
loop=
rmdir "$mount_dir"
mount_dir=
printf '\nPopulated image ready: %s\n' "$image"
