#!/usr/bin/env bash
set -Eeuo pipefail

platformDefaults() {
  GUEST_ARCH=amd64
  PLATFORM=x64
  QEMU_BIN=qemu-system-x86_64
  : "${MACHINE:=q35}"
  : "${BOOT_MODE:=legacy}"
}

platformRunStage() {
  # Retain the exact original VirtualDSM scripts and their execution order.
  # shellcheck source=/dev/null
  . "$1.sh"
}

platformBuildCommand() {
  # Existing scripts produce whitespace-delimited options; split once without
  # interpreting shell code or expanding wildcards.
  read -r -a QEMU_ARGS <<< "$ARGS"
}

platformPrepareSystemDisks() {

  local boot="$STORAGE/$BASE.boot.img"
  local system="$STORAGE/$BASE.system.img"

  [ ! -s "$boot" ] && error "Virtual DSM boot-image does not exist ($boot)" && return 81
  [ ! -s "$system" ] && error "Virtual DSM system-image does not exist ($system)" && return 82

  setOwner "$boot" || warn "failed to set the owner for \"$boot\" !"
  setOwner "$system" || warn "failed to set the owner for \"$system\" !"

  DISK_OPTS+=$(createDevice "$boot" "$DISK_TYPE" "1" "0xa" "raw" "" "" "synoboot")
  DISK_OPTS+=$(createDevice "$system" "$DISK_TYPE" "2" "0xb" "raw" "" "" "synosys")

  return 0
}


platformInteractiveConsole() { interactive; }
platformGuestShutdown() { return 1; }

platformSealArtifacts() { return 0; }
