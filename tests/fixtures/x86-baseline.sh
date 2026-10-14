#!/usr/bin/env bash
set -Eeuo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
enabled() { [[ "${1:-}" == Y ]]; }
disabled() { [[ "${1:-}" == N ]]; }
strip() { printf '%s' "${1:-}"; }
getPciBus() { echo pcie.0; }
finalizeMemory() { :; }
DEBUG=N CPU_FLAGS=host CPU_CORES=2 RAM_SIZE=2G MACHINE=q35 KVM_OPTS=',accel=kvm -enable-kvm -global kvm-pit.lost_tick_policy=discard'
APP='Virtual DSM' PROCESS=virtual-dsm QEMU_PID=/run/shm/qemu.pid
DISPLAY_OPTS='-display none' SERIAL_OPTS='-serial mon:stdio' NET_OPTS='-netdev user,id=net0 -device virtio-net-pci,netdev=net0,bus=pcie.0,addr=0x12'
DISK_OPTS='-drive file=/storage/dsm.boot.img,id=synoboot -drive file=/storage/dsm.system.img,id=synosys'
BOOT_OPTS='' ARGUMENTS=''
. "$repo/src/config.sh"
printf '%s\n' "${ARGS% }"
