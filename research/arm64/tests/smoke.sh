#!/usr/bin/env bash
set -Eeuo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
repo_root=$(cd -- "$script_dir/../.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf -- "$tmp"' EXIT

bash -n "$script_dir/"*.sh "$script_dir/tests/"*.sh
bash "$repo_root/tests/platform.sh"

mkdir -p "$tmp/bin" "$tmp/image"
printf 'fake-kernel' > "$tmp/image/Image"
printf 'fake-initrd' > "$tmp/image/rd.gz"
cat > "$tmp/bin/qemu-system-aarch64" <<'QEMU'
#!/usr/bin/env bash
printf '%s\n' "$@" > "$QEMU_ARGS_FILE"
QEMU
chmod +x "$tmp/bin/qemu-system-aarch64"

QEMU_ARGS_FILE="$tmp/mmio-args" \
  QEMU="$tmp/bin/qemu-system-aarch64" \
  KERNEL="$tmp/image/Image" INITRD="$tmp/image/rd.gz" \
  LOG="$tmp/mmio.log" \
  bash "$script_dir/boot-qemu-mmio16550.sh" >/dev/null
grep -Fxq 'virt,accel=tcg,gic-version=3' "$tmp/mmio-args"
grep -Fxq 'max,lpa2=off' "$tmp/mmio-args"
grep -Fxq 'earlycon=uart8250,mmio32,0x0b000000 console=ttyS0,115200 initcall_debug keep_bootcon ignore_loglevel loglevel=8 printk.time=1' "$tmp/mmio-args"
grep -Fxq 'null' "$tmp/mmio-args"
grep -Fxq 'stdio' "$tmp/mmio-args"

QEMU_ARGS_FILE="$tmp/mmio-trace-args" \
  QEMU="$tmp/bin/qemu-system-aarch64" TRACE=1 \
  KERNEL="$tmp/image/Image" INITRD="$tmp/image/rd.gz" \
  LOG="$tmp/mmio-trace.log" TRACE_LOG="$tmp/init.trace" \
  bash "$script_dir/boot-qemu-mmio16550.sh" >/dev/null
grep -Fxq -- '-dfilter' "$tmp/mmio-trace-args"
grep -Fxq 'in_asm,guest_errors' "$tmp/mmio-trace-args"

QEMU_ARGS_FILE="$tmp/mmio-cpu-args" \
  QEMU="$tmp/bin/qemu-system-aarch64" CPU=max \
  KERNEL="$tmp/image/Image" INITRD="$tmp/image/rd.gz" \
  LOG="$tmp/mmio-cpu.log" \
  bash "$script_dir/boot-qemu-mmio16550.sh" >/dev/null
grep -Fxq 'max' "$tmp/mmio-cpu-args"

printf 'fake-dtb' > "$tmp/image/model.dtb"
QEMU_ARGS_FILE="$tmp/mmio-dtb-args" \
  QEMU="$tmp/bin/qemu-system-aarch64" \
  KERNEL="$tmp/image/Image" INITRD="$tmp/image/rd.gz" \
  DTB="$tmp/image/model.dtb" LOG="$tmp/mmio-dtb.log" \
  bash "$script_dir/boot-qemu-mmio16550.sh" >/dev/null
grep -Fxq -- '-dtb' "$tmp/mmio-dtb-args"
grep -Fxq "$tmp/image/model.dtb" "$tmp/mmio-dtb-args"

QEMU_ARGS_FILE="$tmp/args" PATH="$tmp/bin:$PATH" \
  KERNEL="$tmp/image/Image" INITRD="$tmp/image/rd.gz" ACCEL=tcg \
  bash "$script_dir/boot-qemu.sh" "$tmp/image"

grep -Fxq 'virt,accel=tcg,gic-version=3' "$tmp/args"
grep -Fxq 'max' "$tmp/args"
grep -Fxq -- '-nic' "$tmp/args"
grep -Fxq 'none' "$tmp/args"
grep -Fxq 'console=ttyAMA0 earlycon=pl011,0x09000000 loglevel=8' "$tmp/args"
grep -Fxq -- '-nographic' "$tmp/args"

if QEMU_ARGS_FILE="$tmp/invalid-args" PATH="$tmp/bin:$PATH" \
  KERNEL="$tmp/image/Image" INITRD="$tmp/image/rd.gz" ACCEL=invalid \
  bash "$script_dir/boot-qemu.sh" "$tmp/image" >/dev/null 2>&1; then
  echo "Expected invalid ACCEL to fail." >&2
  exit 1
fi

if bash "$script_dir/extract-pat.sh" >/dev/null 2>&1; then
  echo "Expected missing PAT argument to fail." >&2
  exit 1
fi

# The research forward interface must not accept an address or QEMU options.
python3 - "$script_dir/boot-usb-network.py" <<'PY'
import importlib.util
import sys
spec = importlib.util.spec_from_file_location('usb_network', sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
assert module.loopback_netdev([]) == 'user,id=net0'
assert module.loopback_netdev(['15000:5000', '15001:5001']) == (
    'user,id=net0,hostfwd=tcp:127.0.0.1:15000-10.0.2.15:5000'
    ',hostfwd=tcp:127.0.0.1:15001-10.0.2.15:5001')
for invalid in (['0:5000'], ['65536:5000'], ['15000:0'], ['15000:65536'],
                ['0.0.0.0:15000:5000'], ['[::]:15000:5000'],
                ['15000:5000,hostfwd=tcp::15001-:5001'],
                ['15000:5000', '15000:5001']):
    try:
        module.loopback_netdev(invalid)
    except ValueError:
        pass
    else:
        raise AssertionError(invalid)
PY

echo "ARM research smoke checks passed."
