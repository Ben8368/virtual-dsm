#!/usr/bin/env bash
# Synthetic AArch64 tests only: no DSM payloads, disks, network or credentials.
set -Eeuo pipefail
directory=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
qemu=$(realpath -e -- "${1:?Patched QEMU binary required}")
out=${2:?Output directory required}
mkdir -p -- "$out"
out=$(realpath -e -- "$out")
"$qemu" --version | tee "$out/qemu-version.txt"
sha256sum "$qemu" > "$out/qemu-sha256.txt"
bash "$directory/system.sh" "$qemu" "$out/system"
timeout 120 python3 "$directory/watchpoint.py" "$qemu" \
  "$out/system/dcz-system.elf" "$out/watchpoint"
timeout 120 python3 "$directory/dirty.py" "$qemu" "$out/migration"
echo 'DC ZVA regression passed: AArch64 system, watchpoint, migration.'
