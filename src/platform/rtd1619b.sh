#!/usr/bin/env bash
set -Eeuo pipefail

platformDefaults() {
  GUEST_ARCH=arm64
  PLATFORM=arm64
  QEMU_BIN=qemu-system-aarch64
  MACHINE=virt
  BOOT_MODE=direct
  BASE=DSM_DS124_72806
  ARM_KVM_REQUEST=${KVM:-Y}
  # The base init.sh rejects missing KVM. This platform probes ARM KVM later
  # and permits the validated TCG fallback independently of DEBUG.
  KVM=N
  WEB=N
}

platformRunStage() {
  case "$1" in
    install)
      local directory
      directory=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
      # shellcheck source=src/platform/arm-install.sh
      . "$directory/arm-install.sh"
      platformPrepareArtifacts && platformValidateArtifacts ;;
    disk|display|boot|serial|balloon) ;;
    network) platformConfigureNetwork ;;
    proc) platformConfigureCpu ;;
    config) platformConfigureArguments ;;
    *)
      # shellcheck source=/dev/null
      . "$1.sh" ;;
  esac
}

platformValidateArtifacts() {
  platformValidateBinary || return $?
  KERNEL_IMAGE="$STORAGE/$BASE.kernel"
  INITRD_IMAGE="$STORAGE/$BASE.initrd"
  SYSTEM_IMAGE="$STORAGE/$BASE.system.img"
  local file
  for file in "$KERNEL_IMAGE" "$INITRD_IMAGE" "$SYSTEM_IMAGE"; do
    [[ -f "$file" && -s "$file" ]] || {
      error "Missing prepared DS124 artifact: $file. ARM automatic preparation did not produce a complete artifact set. See docs/platforms.md."
      return 81
    }
    # QEMU's drive parser treats commas as delimiters even inside argv.
    [[ "$file" != *','* && "$file" != *$'\n'* && "$file" != *$'\r'* ]] || {
      error 'ARM artifact paths must not contain commas or line breaks'; return 64
    }
  done
  python3 /run/platform/validate-arm-image.py "$SYSTEM_IMAGE" || return $?
}

platformPrepareSystemDisks() {
  # The patched sysbus AHCI attaches the first IDE backend; no synoboot/synosys.
  ARM_STORAGE_ARGS=(-drive "file=$SYSTEM_IMAGE,format=raw,if=ide,index=0")
}

platformKvmProbe() {
  # Do not infer ARM KVM support from the presence of a device node. Start the
  # selected machine and CPU paused, then request a clean exit via its monitor.
  printf 'quit\n' | timeout 10 "$QEMU_BIN" -machine virt,gic-version=3 -accel kvm     -cpu host -smp 1 -m 128 -nodefaults -display none -serial none     -monitor stdio -S >/dev/null 2>&1
}

platformKvmNodeExists() { [[ -e /dev/kvm ]]; }
platformKvmDeviceAccessible() { [[ -r /dev/kvm && -w /dev/kvm ]]; }

platformConfigureCpu() {
  ARM_ACCEL='tcg,thread=multi'
  CPU_FLAGS='max,lpa2=off'
  if [[ "$HOST_ARCH" == arm64 ]] && ! disabled "$ARM_KVM_REQUEST"; then
    local fallback_reason=''
    if ! platformKvmNodeExists; then
      fallback_reason='/dev/kvm is missing'
    elif ! platformKvmDeviceAccessible; then
      fallback_reason='/dev/kvm is not accessible to the container user'
    elif ! platformKvmProbe; then
      fallback_reason='QEMU KVM initialization failed'
    else
      ARM_ACCEL=kvm
      CPU_FLAGS=host
      KVM=Y
    fi
    if [[ -n "$fallback_reason" ]]; then
      warn "KVM unavailable ($fallback_reason); ARM DSM is running under TCG and may be substantially slower."
    fi
  fi
  [[ "$CPU_CORES" =~ ^[1-9][0-9]{0,2}$ ]] || { error 'Invalid ARM CPU_CORES (1-999)'; return 64; }
  ARM_CPU_ARGS=(-accel "$ARM_ACCEL" -cpu "$CPU_FLAGS" -smp "$CPU_CORES")
}

platformPort() {
  if [[ ! "$1" =~ ^[0-9]{1,5}$ ]] || (( 10#$1 < 1 || 10#$1 > 65535 )); then
    error "Invalid port: $1 (expected 1-65535)"; return 64
  fi
}

platformNetworkBackend() {
  : "${DSM_HTTPS_PORT:=5001}"
  : "${DSM_BIND:=0.0.0.0}"
  : "${USER_PORTS:=}"
  : "${HOST_PORTS:=}"
  [[ -z "$HOST_PORTS" ]] || { error 'ARM user networking does not use HOST_PORTS; use USER_PORTS'; return 64; }
  # Bind within the container. Publishing to the host remains a Docker setting.
  [[ "$DSM_BIND" == 0.0.0.0 || "$DSM_BIND" == 127.0.0.1 ]] || {
    error 'DSM_BIND must be 0.0.0.0 or 127.0.0.1'; return 64
  }
  platformPort "$WEB_PORT" || return $?
  platformPort "$DSM_HTTPS_PORT" || return $?
  [[ $((10#$WEB_PORT)) != $((10#$DSM_HTTPS_PORT)) ]] || { error 'DSM management ports must differ'; return 64; }
  ARM_NETDEV="user,id=net0,hostfwd=tcp:$DSM_BIND:$((10#$WEB_PORT))-10.0.2.15:5000"
  ARM_NETDEV+=",hostfwd=tcp:$DSM_BIND:$((10#$DSM_HTTPS_PORT))-10.0.2.15:5001"
  local spec port protocol
  local -A occupied=(["tcp:$((10#$WEB_PORT))"]=1 ["tcp:$((10#$DSM_HTTPS_PORT))"]=1)
  local -a ports
  IFS=',' read -r -a ports <<< "$USER_PORTS"
  for spec in "${ports[@]}"; do
    [[ "$spec" =~ ^([0-9]{1,5})(/(tcp|udp))?$ ]] || { error "Invalid USER_PORTS entry: $spec"; return 64; }
    port=${BASH_REMATCH[1]}
    protocol=${BASH_REMATCH[3]:-tcp}
    platformPort "$port" || return $?
    port=$((10#$port))
    [[ -z "${occupied[$protocol:$port]:-}" ]] || { error "Duplicate forwarded port: $spec"; return 64; }
    occupied[$protocol:$port]=1
    ARM_NETDEV+=",hostfwd=$protocol:$DSM_BIND:$port-10.0.2.15:$port"
  done
}

platformNetworkDevice() {
  local mac="${VM_NET_MAC:-${MAC:-00:16:3e:12:34:56}}"
  [[ "$mac" =~ ^([[:xdigit:]]{2}:){5}[[:xdigit:]]{2}$ ]] || { error 'Invalid ARM MAC'; return 64; }
  ARM_NETWORK_ARGS=(-netdev "$ARM_NETDEV" -device "usb-net,netdev=net0,mac=$mac")
}

platformConfigureNetwork() {
  : "${NETWORK:=Y}"
  : "${DHCP:=N}"
  if disabled "$NETWORK"; then
    ARM_NETWORK_ARGS=()
    return 0
  fi
  [[ "$NETWORK" == Y || "$NETWORK" == user ]] || { error 'ARM Phase 1 supports NETWORK=user (or Y) and N only'; return 64; }
  disabled "$DHCP" || { error 'ARM DHCP=Y bridge mode is deferred; the guest uses user-mode DHCP automatically'; return 64; }
  platformNetworkBackend || return $?
  platformNetworkDevice || return $?
  # check.sh can health-check the forwarded management port without qemu-host.
  printf '127.0.0.1:%s\n' "$((10#$WEB_PORT))" > "$QEMU_DIR/dsm.url"
  printf '10.0.2.2\n' > "$QEMU_DIR/qemu.gw"
}

platformConfigureArguments() {
  finalizeMemory
  [[ "$RAM_SIZE" =~ ^[0-9]+([.][0-9]+)?[MmGg]([Bb])?$ ]] || { error 'Invalid ARM RAM_SIZE'; return 64; }
  # Additional free-form arguments could override the validated hardware policy.
  [[ -z "${ARGUMENTS:-}" && -z "${QMP:-}" && -z "${MONITOR:-}" ]] || {
    error 'ARM Phase 1 does not support ARGUMENTS, QMP or MONITOR overrides'; return 64
  }
  local ram="${RAM_SIZE^^}"
  ram="${ram%B}"
  local host_epoch
  host_epoch=$(date -u +%s)
  if [[ ! "$host_epoch" =~ ^[0-9]{10}$ ]] || (( host_epoch < 1704067200 || host_epoch > 4102444800 )); then
    error 'Host UTC clock must be correct before launching ARM DSM (2024-2100)'; return 64
  fi
  QEMU_ARGS=(-machine "virt,gic-version=3" "${ARM_CPU_ARGS[@]}" -m "$ram"
    -name "${APP// /-},process=$PROCESS" -pidfile "$QEMU_PID"
    -nic none -kernel "$KERNEL_IMAGE" -initrd "$INITRD_IMAGE"
    -append "earlycon=uart8250,mmio32,0x0b000000 console=ttyS0,115200 initcall_debug keep_bootcon ignore_loglevel loglevel=8 printk.time=1 rdinit=/init pty.legacy_count=0 root=/dev/sata1p1 libata.force=noncq vdsm.host_epoch=$host_epoch"
    -nographic -monitor none -serial null -serial stdio -serial null -no-reboot
    -qmp "unix:$QEMU_DIR/arm-qmp.sock,server=on,wait=off"
    "${ARM_STORAGE_ARGS[@]}" "${ARM_NETWORK_ARGS[@]}")
  # No x86 host sidecar. Keep shared shutdown cleanup usable.
  HOST_PID="$QEMU_DIR/host.pid"
  HOST_API_SOCKET="$QEMU_DIR/qemu-host-api.sock"
  HOST_AGENT_SOCKET="$QEMU_DIR/qemu-host-agent.sock"
  printf -v ARGS '%q ' "${QEMU_ARGS[@]}"
}

platformBuildCommand() {
  # Durably protect the generation before QEMU can make its first write.
  python3 /run/platform/prepare-arm-artifacts.py begin "$STORAGE" "$BASE"
  rm -f -- "$QEMU_DIR/arm-exit.json"
  python3 /run/platform/arm-lifecycle.py watch "$QEMU_DIR/arm-qmp.sock" "$QEMU_DIR/arm-exit.json" &
  ARM_WATCH_PID=$!
}

platformInteractiveConsole() { return 1; }

platformGuestShutdown() {
  warn "ARM has no guest shutdown agent; shut down DSM through its UI before stopping the container."
  # Shared timeout retains SIGTERM/SIGKILL for guests that do not power off.
  return 0
}

# The inherited shared teardown calls this network-backend lifecycle interface.
# User-mode slirp has no tap, bridge, firewall or daemon state to tear down.
closeNetwork() { return 0; }
