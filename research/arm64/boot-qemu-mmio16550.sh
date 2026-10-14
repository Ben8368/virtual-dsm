#!/usr/bin/env bash
set -Eeuo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
work_dir="$script_dir/work"
qemu="${QEMU:-$work_dir/qemu-system-aarch64}"
kernel="${KERNEL:-$work_dir/boot/zImage.Image}"
initrd="${INITRD:-$work_dir/boot/rd.bin.cpio}"
dtb="${DTB:-}"
uart_addr="${UART_ADDR:-0x0b000000}"
cpu="${CPU:-max,lpa2=off}"
append="${APPEND:-earlycon=uart8250,mmio32,$uart_addr console=ttyS0,115200 initcall_debug keep_bootcon ignore_loglevel loglevel=8 printk.time=1}"
log="${LOG:-$work_dir/boot-mmio16550.log}"
trace_log="${TRACE_LOG:-$work_dir/qemu-mmio16550.trace}"
# Stock DS124 72806 recovered addresses; do_basic_setup is inlined here.
trace_filter="${TRACE_FILTER:-0xffffffc010003fb0+0x240,0xffffffc01087fdfc+0x100,0xffffffc01088da94+0x12c,0xffffffc010df104c+0x344,0xffffffc010df1924+0x400,0xffffffc010e178a0+0x13c,0xffffffc0105bd974+0x63c}"

for path in "$qemu" "$kernel" "$initrd"; do
  [[ -s "$path" ]] || {
    echo "ERROR: Required file is missing or empty: $path" >&2
    exit 2
  }
done

cmd=("$qemu" -machine "virt,accel=tcg,gic-version=3" -cpu "$cpu" -smp 2 -m 2048
  -nic none -kernel "$kernel" -initrd "$initrd" -append "$append"
  -nographic -monitor none -serial null -serial stdio -no-reboot)
if [[ -n "$dtb" ]]; then
  cmd+=(-dtb "$dtb")
  echo "Explicit DTB: $dtb"
else
  echo "DTB: QEMU virt generated tree"
fi
if [[ "${TRACE:-0}" == 1 ]]; then
  cmd+=(-d "in_asm,guest_errors" -dfilter "$trace_filter" -D "$trace_log")
  echo "QEMU trace: $trace_log"
fi

echo "QEMU: $qemu"
echo "UART: $uart_addr (MMIO 16550, regshift=2, little endian, SPI ID 42 / GIC input 10)"
echo "CPU: $cpu"
echo "Kernel: $kernel"
echo "Initrd: $initrd"
echo "Command line: $append"
echo "Serial log: $log"
set +e
"${cmd[@]}" 2>&1 | tee "$log"
qemu_status=${PIPESTATUS[0]}
set -e
exit "$qemu_status"
