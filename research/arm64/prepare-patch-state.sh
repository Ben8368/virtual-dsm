#!/usr/bin/env bash
# Reproduce the proven updater flash-backup state on a NEW populated p1 image.
set -Eeuo pipefail
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
work_dir=$(realpath -e -- "$script_dir/work")
[[ "$work_dir" == "$script_dir/work" && $EUID == 0 ]] || exit 2
image="$work_dir/test-sata-patch-state.img"
[[ ! -e "$image" && ! -L "$image" ]] || { echo 'New experiment requires an unused image path.' >&2; exit 2; }
archive="$work_dir/patch-analysis/official-patch-state.tar"
[[ -s "$archive" ]] || { echo 'Run build-official-patch-state.py with the PAT extraction venv first.' >&2; exit 2; }
ROOT_IMAGE_NAME=test-sata-patch-state.img bash "$script_dir/prepare-populated-root.sh"
[[ $(realpath -e -- "$image") == "$work_dir/test-sata-patch-state.img" && ! -L "$image" ]] || exit 2
[[ -z $(losetup -j "$image") ]] || exit 2
loop=$(losetup --find --show --offset 1048576 --sizelimit 2145749504 "$image")
mount_dir=$(mktemp -d "$work_dir/patch-state-mount.XXXXXX")
cleanup() {
  if mountpoint -q "$mount_dir"; then umount "$mount_dir" || return; fi
  losetup -d "$loop"
  rmdir "$mount_dir"
}
trap cleanup EXIT
[[ $(losetup -n -O BACK-FILE "$loop") == "$image" ]] || exit 2
[[ $(losetup -n -O OFFSET "$loop" | tr -d ' ') == 1048576 ]] || exit 2
[[ $(losetup -n -O SIZELIMIT "$loop" | tr -d ' ') == 2145749504 ]] || exit 2
mount -t ext4 -o prjquota,barrier=1,noatime "$loop" "$mount_dir"
[[ ! -e "$mount_dir/.syno/patch" && ! -L "$mount_dir/.syno" ]] || exit 2
umask 022
# With new directories, umask 022 gives the official mkdir -p -m 0755 result.
mkdir -p "$mount_dir/.syno/patch"
# The archive contains only the selected original PAT files and the proven checksum subset.
# Root ownership and modes match root cp -rf under umask 022, with original PAT octal header modes.
tar -xpf "$archive" -C "$mount_dir" --numeric-owner --same-owner --same-permissions
{
  echo 'Source: DSM_DS124_72806.pat; official updater backup-flash selection; no invented VERSION.'
  echo 'Creation: updater cp -rf selected top-level PAT files, grep checksum subset, directory swap; reproduced final persistent state.'
  echo 'Directories: mkdir -p -m 0755, root:root, umask 022.'
  echo 'Original PAT permissions recovered from decrypted octal headers; host DrvFS permissions are not used.'
  echo 'No modifications to kernel, initramfs, consistency script, or previous populated image.'
  cat "$work_dir/patch-analysis/official-backup-selection.json"
  for path in "$mount_dir/.syno" "$mount_dir/.syno/patch" "$mount_dir/.syno/patch/"*; do
    stat -c 'type=%F mode=%a uid=%u gid=%g size=%s name=%N' "$path"
  done
  echo 'VERSION contents:'
  cat "$mount_dir/.syno/patch/VERSION"
  echo 'Per-file source proof (matching SHA256):'
  for file in "$mount_dir/.syno/patch/"*; do
    name=$(basename -- "$file")
    if [[ "$name" != checksum.syno ]]; then
      cmp -- "$file" "$work_dir/extracted/$name"
      sha256sum "$file" "$work_dir/extracted/$name"
    else
      sha256sum "$file"
    fi
  done
  echo 'Partition table:'
  sfdisk --dump "$image"
} > "$work_dir/patch-state-report.txt"
sync -f "$mount_dir"
echo "Official patch state ready: $image"
