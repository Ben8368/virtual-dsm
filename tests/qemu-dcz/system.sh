#!/usr/bin/env bash
set -Eeuo pipefail
directory=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
qemu=$(realpath -e -- "${1:?QEMU binary required}")
out=${2:?Output directory required}
mkdir -p -- "$out"
"${AARCH64_CC:-aarch64-linux-gnu-gcc}" -ffreestanding -fno-builtin -fno-stack-protector -mgeneral-regs-only \
  -O2 -g -nostdlib -static -Wl,--build-id=none \
  -T "$directory/fixtures/link.ld" \
  "$directory/fixtures/start.S" \
  "$directory/fixtures/system.c" -o "$out/dcz-system.elf"
if ! timeout 120 "$qemu" -machine virt,gic-version=3 -accel tcg,thread=multi \
  -cpu max -smp 2 -m 128M -nic none -nographic -monitor none \
  -semihosting-config enable=on,target=native \
  -kernel "$out/dcz-system.elf" >"$out/serial.log" 2>&1; then
  cat "$out/serial.log" >&2
  exit 1
fi
grep -Fxq 'DCZ_TEST_RESULT failures=0' "$out/serial.log"
cat "$out/serial.log"
