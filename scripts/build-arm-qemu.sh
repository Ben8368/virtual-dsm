#!/usr/bin/env bash
set -Eeuo pipefail
[[ "$QEMU_VERSION" == 8.2.2 ]] || { echo 'Only validated QEMU 8.2.2 is supported' >&2; exit 64; }
builder_arch=$(dpkg --print-architecture)
echo "QEMU builder target=$TARGETARCH runtime=$builder_arch guest=aarch64-softmmu"
case "$TARGETARCH:$builder_arch" in
  amd64:amd64|arm64:arm64) ;;
  *) echo 'QEMU builder architecture does not match TARGETARCH' >&2; exit 64 ;;
esac
# Match the pinned upstream commit exactly. A GitHub mirror is only a transport
# fallback; fetch-qemu-source.sh verifies the tag's commit before patching.
/fetch-qemu-source.sh /qemu
if ! bash /apply-qemu-patches.sh /qemu /patches; then
  echo 'QEMU_PATCH_APPLY_FAILED: pinned source downloaded, but the production patch series did not apply.' >&2
  exit 65
fi
mkdir /qemu/build /out
cd /qemu/build
if ! ../configure --target-list=aarch64-softmmu --without-default-features \
    --enable-tcg --enable-kvm --enable-slirp --enable-fdt \
    --disable-werror --disable-docs --disable-tools --disable-user \
    2>&1 | tee /tmp/qemu-configure.log; then
  if grep -Eqi 'could not resolve host|temporary failure in name resolution|name or service not known|nodename nor servname provided' /tmp/qemu-configure.log; then
    echo 'QEMU_SOURCE_DNS_FAILURE: a pinned QEMU subproject could not be resolved during configure.' >&2
    exit 69
  elif grep -Eqi 'subproject|git clone|failed to download|unable to access' /tmp/qemu-configure.log; then
    echo 'QEMU_SOURCE_UNAVAILABLE: a pinned QEMU subproject could not be fetched during configure.' >&2
    exit 69
  else
    echo 'QEMU_CONFIGURE_FAILED: sources and production patches were available, but QEMU configuration failed.' >&2
    exit 71
  fi
fi
if ! ninja -j8 qemu-system-aarch64; then
  echo 'QEMU_COMPILE_FAILED: QEMU source and patch application succeeded, but compilation failed.' >&2
  exit 70
fi
install -m 0755 qemu-system-aarch64 /out/qemu-system-aarch64
/out/qemu-system-aarch64 --version
ldd /out/qemu-system-aarch64
