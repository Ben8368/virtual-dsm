#!/usr/bin/env bash
set -Eeuo pipefail
[[ "$QEMU_VERSION" == 8.2.2 ]] || { echo 'Only validated QEMU 8.2.2 is supported' >&2; exit 64; }
case "$TARGETARCH:$(dpkg --print-architecture)" in
  amd64:amd64|arm64:arm64) ;;
  *) echo 'QEMU builder architecture does not match TARGETARCH' >&2; exit 64 ;;
esac
# Match the research tag exactly; patches apply sequentially to pristine source.
git clone --depth 1 --branch "v$QEMU_VERSION" https://gitlab.com/qemu-project/qemu.git /qemu
bash /apply-qemu-patches.sh /qemu /patches
mkdir /qemu/build /out
cd /qemu/build
../configure --target-list=aarch64-softmmu --without-default-features   --enable-tcg --enable-kvm --enable-slirp --enable-fdt   --disable-werror --disable-docs --disable-tools --disable-user
ninja -j8 qemu-system-aarch64
install -m 0755 qemu-system-aarch64 /out/qemu-system-aarch64
/out/qemu-system-aarch64 --version
ldd /out/qemu-system-aarch64
