#!/usr/bin/env bash
set -Eeuo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
work_dir="$script_dir/work"
source_dir="${1:-$work_dir/qemu-src}"
build_dir="$work_dir/qemu-build"
output="$work_dir/qemu-system-aarch64"

if [[ ! -d "$source_dir/.git" ]]; then
  if [[ $# -gt 0 ]]; then
    echo "ERROR: QEMU source directory is not a Git checkout: $source_dir" >&2
    exit 2
  fi
  mkdir -p -- "$work_dir"
  git clone --depth 1 --branch v8.2.2 \
    https://gitlab.com/qemu-project/qemu.git "$source_dir"
fi

bash "$script_dir/../../scripts/apply-qemu-patches.sh" "$source_dir" "$script_dir/../../patches/qemu/8.2.2"

export PATH="$work_dir/tools/bin:$work_dir/tools/qemu-build-env/root/usr/bin:${PATH:-}"
export LD_LIBRARY_PATH="$work_dir/tools/qemu-build-env/root/usr/lib/x86_64-linux-gnu:$work_dir/tools/qemu-root/usr/lib/x86_64-linux-gnu:$work_dir/tools/root/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}"

for tool in python3 meson ninja pkg-config; do
  command -v "$tool" >/dev/null 2>&1 || {
    echo "ERROR: Missing build prerequisite: $tool" >&2
    exit 3
  }
done
command -v cc >/dev/null 2>&1 || {
  echo "ERROR: Missing C compiler (cc)." >&2
  exit 3
}

if [[ ! -f "$build_dir/build.ninja" ]] || ! grep -Eq '^#define CONFIG_SLIRP([[:space:]]|$)' "$build_dir/config-host.h"; then
  mkdir -p -- "$build_dir"
  (
    cd -- "$build_dir"
    "$source_dir/configure" \
      --target-list=aarch64-softmmu \
      --disable-werror \
      --disable-docs \
      --disable-gtk \
      --disable-sdl \
      --disable-vnc \
      --disable-curses \
      --enable-slirp \
      --disable-plugins \
      --disable-tools \
      --disable-user
  )
fi

ninja -C "$build_dir" -j"${JOBS:-$(nproc)}" qemu-system-aarch64
install -m 0755 "$build_dir/qemu-system-aarch64" "$output"
"$output" --version
echo "Research QEMU: $output"
