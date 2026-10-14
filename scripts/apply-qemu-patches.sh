#!/usr/bin/env bash
# Shared by production and research: one patch implementation, exact source tag.
set -Eeuo pipefail
source_dir=$(realpath -e -- "${1:?QEMU source directory required}")
patch_dir=$(realpath -e -- "${2:?Production patch directory required}")
qemu_commit=11aa0b1ff115b86160c4d37e7c37e6a6b13b77ea
[[ $(git -c safe.directory="$source_dir" -C "$source_dir" rev-parse HEAD) == "$qemu_commit" ]] || {
  echo 'Expected pristine upstream QEMU v8.2.2 commit' >&2; exit 64
}
[[ $(<"$source_dir/VERSION") == 8.2.2 ]] || exit 64
expected=$(mktemp -d)
trap 'rm -rf -- "$expected"' EXIT
git -c safe.directory="$source_dir" -C "$source_dir" archive HEAD | tar -x -C "$expected"
patches=("$patch_dir/0001-arm-virt-dsm-platform.patch" "$patch_dir/0002-arm-virt-syno-leds.patch" "$patch_dir/0003-arm-virt-dsm-shutdown-uart.patch")
for patch in "${patches[@]}"; do
  (cd "$expected"; git apply --check "$patch"; git apply "$patch")
done
# A whole-series comparison also handles the second patch changing the first
# patch's context. Never accept a mere function name as proof of patch equality.
if cmp -s "$expected/hw/arm/virt.c" "$source_dir/hw/arm/virt.c" &&
   cmp -s "$expected/include/hw/arm/virt.h" "$source_dir/include/hw/arm/virt.h"; then
  echo 'Exact production QEMU patch series already present.'
  exit 0
fi
git -c safe.directory="$source_dir" -C "$source_dir" diff --quiet HEAD -- hw/arm/virt.c include/hw/arm/virt.h || {
  echo 'QEMU hardware sources differ from the production series; use a clean v8.2.2 checkout.' >&2
  exit 65
}
for patch in "${patches[@]}"; do
  git -c safe.directory="$source_dir" -C "$source_dir" apply --check "$patch"
  git -c safe.directory="$source_dir" -C "$source_dir" apply "$patch"
done
echo 'Applied production MMIO UART/AHCI/XHCI Synology LED and shutdown UART patches.'
