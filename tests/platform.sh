#!/usr/bin/env bash
# shellcheck disable=SC2016
set -Eeuo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo"
tmp=$(mktemp -d)
trap 'rm -rf -- "$tmp"' EXIT
error() { printf '%s\n' "$*" >&2; }
warn() { error "$*"; }
enabled() { [[ "${1:-}" == Y ]]; }
disabled() { [[ "${1:-}" == N ]]; }
finalizeMemory() { :; }
. src/platform/common.sh
unset DSM_PLATFORM PLATFORM QEMU_BIN MACHINE BOOT_MODE
platformInit
[[ "$DSM_PLATFORM:$GUEST_ARCH:$PLATFORM:$QEMU_BIN:$MACHINE:$BOOT_MODE" == virtualdsm:amd64:x64:qemu-system-x86_64:q35:legacy ]]
# Original x86 argument snapshot and byte-identical install/config/serial logic.
bash tests/fixtures/x86-baseline.sh > "$tmp/x86.args"
diff -u tests/fixtures/virtualdsm.args "$tmp/x86.args"
sha256sum -c tests/fixtures/x86-scripts.sha256
ARGS=$(<"$tmp/x86.args")
platformBuildCommand
[[ "${QEMU_ARGS[2]}" == type=q35,* ]]
STORAGE=$tmp BASE=dsm DISK_TYPE=scsi DISK_OPTS=''
printf boot > "$tmp/dsm.boot.img"
printf system > "$tmp/dsm.system.img"
setOwner() { :; }
createDevice() { printf '[%s|%s|%s|%s|%s|%s|%s|%s]' "$@"; }
platformPrepareSystemDisks
[[ "$DISK_OPTS" == "[$tmp/dsm.boot.img|scsi|1|0xa|raw|||synoboot][$tmp/dsm.system.img|scsi|2|0xb|raw|||synosys]" ]]
# Dispatch still invokes the existing script in the shared working directory.
stage_loaded=''
printf 'stage_loaded=install\n' > "$tmp/install.sh"
(cd "$tmp"; platformRunStage install; [[ "$stage_loaded" == install ]])
if (DSM_PLATFORM='rtd1619b;touch injected'; platformInit) >/dev/null 2>&1; then exit 1; fi
if (DSM_PLATFORM=unknown; platformInit) >/dev/null 2>&1; then exit 1; fi
DSM_PLATFORM=rtd1619b
# Stable host launch time for the ARM argument snapshot.
date() { if [[ "$*" == '-u +%s' ]]; then printf '1704067200\n'; else command date "$@"; fi; }
platformInit
[[ "$GUEST_ARCH:$PLATFORM:$QEMU_BIN:$MACHINE:$BOOT_MODE" == arm64:arm64:qemu-system-aarch64:virt:direct ]]
HOST_ARCH=amd64 CPU_CORES=2 RAM_SIZE=2G APP='Virtual DSM' PROCESS=virtual-dsm
QEMU_DIR=/run/shm QEMU_PID=/run/shm/qemu.pid WEB_PORT=5000 DSM_HTTPS_PORT=5001
KERNEL_IMAGE=/storage/DSM_DS124_72806.kernel INITRD_IMAGE=/storage/DSM_DS124_72806.initrd
SYSTEM_IMAGE=/storage/DSM_DS124_72806.system.img
platformConfigureCpu
[[ "$ARM_ACCEL:$CPU_FLAGS:$KVM" == tcg,thread=multi:max,lpa2=off:N ]]
platformPrepareSystemDisks
platformConfigureNetwork
platformConfigureArguments
printf '%s\n' "${QEMU_ARGS[@]}" > "$tmp/arm.args"
diff -u tests/fixtures/rtd1619b.args "$tmp/arm.args"
if grep -E 'q35|smm=|vmport=|hpet=|pcie[.]|virtio-.*-pci|synoboot|synosys|e1000' "$tmp/arm.args"; then exit 1; fi
for port in 0 65536 -1 '5000,hostfwd=tcp::22-:22' '5000;touch injected' '$(touch injected)'; do
  if (WEB_PORT="$port"; platformNetworkBackend) >/dev/null 2>&1; then exit 1; fi
done
for ports in '22,22' '5000' '22/tcp,22/tcp' '22,0' '22;touch injected' '22,hostfwd=tcp::23-:23'; do
  if (USER_PORTS="$ports"; platformNetworkBackend) >/dev/null 2>&1; then exit 1; fi
done
if (DSM_HTTPS_PORT=5000; platformNetworkBackend) >/dev/null 2>&1; then exit 1; fi
if (DSM_BIND='0.0.0.0,hostfwd=tcp::22-:22'; platformNetworkBackend) >/dev/null 2>&1; then exit 1; fi
if (MAC='00:16:3e:12:34:56,netdev=bad'; platformNetworkDevice) >/dev/null 2>&1; then exit 1; fi
if (CPU_CORES='2 -device e1000'; platformConfigureCpu) >/dev/null 2>&1; then exit 1; fi
if (ARGUMENTS='-machine q35'; platformConfigureArguments) >/dev/null 2>&1; then exit 1; fi
if (date() { printf '0\n'; }; platformConfigureArguments) >/dev/null 2>&1; then exit 1; fi
if (DHCP=Y; platformConfigureNetwork) >/dev/null 2>&1; then exit 1; fi
if (NETWORK=tap; platformConfigureNetwork) >/dev/null 2>&1; then exit 1; fi
if (QEMU_BIN='bash -c injected'; platformValidateBinary) >/dev/null 2>&1; then exit 1; fi
# Missing artifacts must stop before any x86 installer is sourced.
platformValidateBinary() { :; }
if platformValidateArtifacts >"$tmp/missing" 2>&1; then exit 1; fi
grep -q 'ARM automatic preparation did not produce a complete artifact set' "$tmp/missing"
# Custom ports use the existing WEB_PORT and USER_PORTS interfaces.
WEB_PORT=5080 DSM_HTTPS_PORT=5443 USER_PORTS=22,53/udp
platformNetworkBackend
[[ "$ARM_NETDEV" == *':5080-10.0.2.15:5000'* && "$ARM_NETDEV" == *':5443-10.0.2.15:5001'* && "$ARM_NETDEV" == *'udp:0.0.0.0:53-10.0.2.15:53' ]]
# Artifact spaces remain one argv item, without shell evaluation.
SYSTEM_IMAGE='/storage/space and $(touch injected).system.img'
platformPrepareSystemDisks
[[ "${#ARM_STORAGE_ARGS[@]}" == 2 && "${ARM_STORAGE_ARGS[1]}" == 'file=/storage/space and $(touch injected).system.img,format=raw,if=ide,index=0' ]]
[[ ! -e injected ]]
echo 'Platform tests passed (default x86, storage, ARM argv, inputs, artifact validation policy).'
