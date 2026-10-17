#!/usr/bin/env bash
set -Eeuo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf -- "$tmp"' EXIT
# Optional local Git source avoids a network download during development.
if [[ $# == 1 ]]; then
  [[ $(git -c safe.directory="$1" -C "$1" rev-parse HEAD) == 11aa0b1ff115b86160c4d37e7c37e6a6b13b77ea ]]
  git -c safe.directory="$1" -C "$1" archive HEAD | tar -x -C "$tmp"
else
  rmdir "$tmp"
  "$repo/scripts/fetch-qemu-source.sh" "$tmp"
fi
for patch in "$repo"/patches/qemu/8.2.2/*.patch; do
  if ! (cd "$tmp"; git apply --check "$patch" && git apply "$patch"); then
    echo "QEMU_PATCH_APPLY_FAILED: $patch did not apply to pinned QEMU v8.2.2." >&2
    exit 65
  fi
done
grep -q create_dsm_uart "$tmp/hw/arm/virt.c"
grep -q create_dsm_ahci "$tmp/hw/arm/virt.c"
grep -q create_dsm_xhci "$tmp/hw/arm/virt.c"
grep -q create_dsm_syno_leds "$tmp/hw/arm/virt.c"
grep -q 'create_dsm_uart(vms, sysmem, 1)' "$tmp/hw/arm/virt.c"
grep -q tb_invalidate_phys_page_dcz "$tmp/accel/tcg/tb-maint.c"
grep -q tlb_invalidate_code_dcz "$tmp/target/arm/tcg/helper-a64.c"
echo 'All production patches cleanly apply to pristine QEMU v8.2.2.'
