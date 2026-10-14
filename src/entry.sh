#!/usr/bin/env bash
set -Eeuo pipefail

: "${APP:="Virtual DSM"}"
: "${SUPPORT:="https://github.com/vdsm/virtual-dsm"}"

: "${USB:="N"}"
: "${AUDIO:="N"}"
: "${VGA:="none"}"
: "${DISPLAY:="none"}"
: "${WEB_PORT:="5000"}"
: "${DISK_OFFSET:="2"}"
: "${DISK_SIZE:="256G"}"
: "${RAM_MINIMUM:="1G"}"
: "${DISK_MINIMUM:="6G"}"

cd /run

. start.sh      # Startup hook
. utils.sh      # Load functions
. platform/common.sh
platformInit

. init.sh       # Initialize system
. memory.sh     # Check memory
. server.sh     # Start webserver
. download.sh   # Load functions
platformRunStage install    # Run installation
platformRunStage disk       # Initialize disks
platformRunStage display    # Initialize graphics
. prepare.sh    # Prepare for launch
platformRunStage network    # Initialize network
platformRunStage boot       # Configure boot
platformRunStage proc       # Initialize processor
platformRunStage serial     # Initialize serialport
. power.sh      # Configure shutdown
platformRunStage balloon    # Initialize ballooning
platformRunStage config     # Configure arguments
. finish.sh     # Finish initialization

trap - ERR

platformValidateBinary
platformBuildCommand
cmd=("$QEMU_BIN")
version=$("${cmd[@]}" --version | awk 'NR==1 { print $4 }')
info "Booting $APP using QEMU v$version..." && echo

if ! enabled "$SHUTDOWN"; then
  exec "${cmd[@]}" "${QEMU_ARGS[@]}"
fi

if ! platformInteractiveConsole; then
  "${cmd[@]}" "${QEMU_ARGS[@]}" &
else
  startConsole
  startQemu "${cmd[@]}" "${QEMU_ARGS[@]}"
fi

pid=$!
if [[ "$DSM_PLATFORM" == rtd1619b ]]; then ARM_QEMU_PID=$pid; fi
rc=0

wait "$pid" || rc=$?
[ -f "$QEMU_END" ] && exit "$rc"

sleep 1 & wait $!
if [[ "$DSM_PLATFORM" == rtd1619b ]]; then
  wait "${ARM_WATCH_PID:-0}" 2>/dev/null || :
  python3 - "$QEMU_DIR/arm-exit.json" "$rc" <<'PY'
import json, os, sys
from pathlib import Path
path = Path(sys.argv[1])
data = json.loads(path.read_text()) if path.is_file() else {}
data['qemu_exit_code'] = int(sys.argv[2])
data['container_requested'] = False
with path.open('w') as fh:
    json.dump(data, fh)
    fh.flush()
    os.fsync(fh.fileno())
PY
fi
finish "$rc"
