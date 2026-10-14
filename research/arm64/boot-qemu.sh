#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  echo "Usage: $0 <extracted-directory>" >&2
  echo "Optional environment: KERNEL, INITRD, DTB, QEMU, ACCEL=auto|kvm|tcg, CPU, SMP, RAM, APPEND, LOG" >&2
}

if [[ $# -ne 1 || ! -d "$1" ]]; then
  usage
  exit 2
fi

root=$(realpath -- "$1")
qemu="${QEMU:-qemu-system-aarch64}"
if ! command -v "$qemu" >/dev/null 2>&1; then
  echo "ERROR: '$qemu' was not found. Install QEMU's AArch64 system emulator (for example, qemu-system-arm on Debian/Ubuntu)." >&2
  exit 3
fi

find_candidate() {
  local pattern="$1"
  find "$root" -type f -iname "$pattern" -print -quit
}

kernel="${KERNEL:-}"
initrd="${INITRD:-}"
dtb="${DTB:-}"
if [[ -z "$kernel" ]]; then
  for candidate in Image Image.gz zImage vmlinuz; do
    kernel=$(find_candidate "$candidate")
    [[ -n "$kernel" ]] && break
  done
fi
if [[ -z "$initrd" ]]; then
  for candidate in rd.gz rd.bin initrd initrd.gz; do
    initrd=$(find_candidate "$candidate")
    [[ -n "$initrd" ]] && break
  done
fi

# Synology's DS124 zImage and rd.bin are LZMA-alone streams rather than the
# gzip names that many generic boot helpers expect. QEMU's -kernel loader
# needs the unwrapped ARM64 Image, and -initrd needs the decompressed cpio.
work_dir="$(dirname -- "$root")"
mkdir -p -- "$work_dir/boot"
decompress_lzma_stream() {
  local source="$1" destination="$2"
  command -v xz >/dev/null 2>&1 || {
    echo "ERROR: '$source' is LZMA-compressed; install xz-utils to prepare it for QEMU." >&2
    exit 4
  }
  if ! xz --single-stream --format=lzma -dc -- "$source" > "$destination"; then
    rm -f -- "$destination"
    echo "ERROR: Could not decompress LZMA stream: $source" >&2
    exit 4
  fi
}
if xz --single-stream --format=lzma -t -- "$kernel" >/dev/null 2>&1; then
  decompressed_kernel="$work_dir/boot/$(basename -- "$kernel").Image"
  decompress_lzma_stream "$kernel" "$decompressed_kernel"
  kernel="$decompressed_kernel"
fi
if xz --single-stream --format=lzma -t -- "$initrd" >/dev/null 2>&1; then
  decompressed_initrd="$work_dir/boot/$(basename -- "$initrd").cpio"
  decompress_lzma_stream "$initrd" "$decompressed_initrd"
  initrd="$decompressed_initrd"
fi
detected_dtb=""
[[ -n "$dtb" ]] || detected_dtb=$(find_candidate '*.dtb')

if [[ -z "$kernel" || ! -s "$kernel" ]]; then
  echo "ERROR: Could not identify a kernel. Set KERNEL=/path/to/kernel after reviewing research/arm64/work/pat-report.txt." >&2
  exit 4
fi
if [[ -z "$initrd" || ! -s "$initrd" ]]; then
  echo "ERROR: Could not identify an initrd. Set INITRD=/path/to/initrd after reviewing research/arm64/work/pat-report.txt." >&2
  exit 4
fi
if ! command -v xz >/dev/null 2>&1; then
  echo "ERROR: xz-utils is required to identify/decompress compressed kernel and initrd artifacts." >&2
  exit 3
fi

host_arch=$(uname -m)
accel="${ACCEL:-auto}"
case "$accel" in
  auto)
    if [[ "$host_arch" == aarch64 || "$host_arch" == arm64 ]] &&
       [[ -r /dev/kvm && -w /dev/kvm ]]; then
      accel=kvm
    else
      accel=tcg
    fi ;;
  kvm)
    if [[ "$host_arch" != aarch64 && "$host_arch" != arm64 ]]; then
      echo "ERROR: ARM KVM requires an AArch64 host; current host reports '$host_arch'." >&2
      exit 5
    fi
    if [[ ! -r /dev/kvm || ! -w /dev/kvm ]]; then
      echo "ERROR: ACCEL=kvm was requested but /dev/kvm is unavailable or not accessible." >&2
      exit 5
    fi ;;
  tcg) ;;
  *)
    echo "ERROR: Invalid ACCEL='$accel'; expected auto, kvm, or tcg." >&2
    exit 2 ;;
esac

cpu="${CPU:-}"
if [[ -z "$cpu" ]]; then
  if [[ "$accel" == kvm ]]; then cpu=host; else cpu=max; fi
fi
smp="${SMP:-4}"
ram="${RAM:-2048}"
append="${APPEND:-console=ttyAMA0 earlycon=pl011,0x09000000 loglevel=8}"

cmd=("$qemu" -machine "virt,accel=$accel,gic-version=3" \
  -cpu "$cpu" -smp "$smp" -m "$ram" -nic none \
  -kernel "$kernel" -initrd "$initrd" -append "$append" -nographic -no-reboot)
if [[ -n "$dtb" ]]; then
  cmd+=(-dtb "$dtb")
  echo "Using explicitly selected DTB: $dtb"
elif [[ -n "$detected_dtb" ]]; then
  echo "Found DTB candidate: $detected_dtb (not passed automatically; a board DTB is not interchangeable with the QEMU virt tree)."
else
  echo "No standalone DTB detected; QEMU virt will provide its own device tree."
fi

echo "Host architecture: $host_arch"
echo "Guest architecture: arm64"
echo "Acceleration requested: $accel (availability does not prove kernel compatibility)"
echo "Kernel: $kernel"
echo "Initrd: $initrd"
log="${LOG:-$work_dir/boot.log}"
echo "Serial log: $log"
echo "Starting QEMU; press Ctrl-A X to exit nographic mode."
set +e
"${cmd[@]}" 2>&1 | tee "$log"
qemu_status=${PIPESTATUS[0]}
set -e
exit "$qemu_status"
