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
patches=("$patch_dir/0001-arm-virt-dsm-platform.patch" "$patch_dir/0002-arm-virt-syno-leds.patch"
         "$patch_dir/0003-arm-virt-dsm-shutdown-uart.patch"
         "$patch_dir/0004-tcg-dczva-full-page-code-invalidate.patch")
tracked=(hw/arm/virt.c include/hw/arm/virt.h
         accel/tcg/cputlb.c accel/tcg/tb-maint.c accel/tcg/internal-target.h
         include/exec/cpu_ldst.h target/arm/tcg/helper-a64.c)
for patch in "${patches[@]}"; do
  (cd "$expected"; git apply --check "$patch"; git apply "$patch")
done
# A whole-series comparison also handles later patches changing earlier
# context. Never accept a mere function name as proof of patch equality.
series_present=1
for file in "${tracked[@]}"; do
  cmp -s "$expected/$file" "$source_dir/$file" || series_present=0
done
if [[ $series_present == 1 ]]; then
  echo 'Exact production QEMU patch series already present.'
  exit 0
fi
git -c safe.directory="$source_dir" -C "$source_dir" diff --quiet HEAD -- "${tracked[@]}" || {
  echo 'QEMU sources differ from the production series; use a clean v8.2.2 checkout.' >&2
  exit 65
}
for patch in "${patches[@]}"; do
  git -c safe.directory="$source_dir" -C "$source_dir" apply --check "$patch"
  git -c safe.directory="$source_dir" -C "$source_dir" apply "$patch"
done
echo 'Applied production MMIO UART/AHCI/XHCI Synology LED, shutdown UART and DC ZVA code-invalidate patches.'
