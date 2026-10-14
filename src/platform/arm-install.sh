#!/usr/bin/env bash
# The common downloader/extractor is shared with VirtualDSM; root building is ARM-only.
set -Eeuo pipefail

platformPrepareArtifacts() {
  # Retain the lock in the entrypoint shell until QEMU/teardown have finished.
  exec {ARM_INSTALL_LOCK}>"$STORAGE/.$BASE.arm.lock"
  flock -x "$ARM_INSTALL_LOCK"
  platformBuildArtifacts
}

platformBuildArtifacts() (
  local directory workspace='' existing incoming status
  directory=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
  . "$directory/../pat.sh"
  : "${URL:=}"
  : "${COUNTRY:=}"
  : "${CONNECTIONS:=1}"
  [[ "$STORAGE" != *','* && "$STORAGE" != *$'\n'* && "$STORAGE" != *$'\r'* ]] || {
    error 'ARM storage paths must not contain commas or line breaks'; return 64;
  }
  # Obsolete private workspaces never count as generations. Lock protects writers.
  for existing in "$STORAGE"/.rtd1619b-install-*; do
    [[ -d "$existing" && ! -L "$existing" ]] && rm -rf -- "$existing"
  done
  export ARM_SOURCE_URL="$URL"
  export DISK_SIZE
  if [[ "$URL" == file://* && -f "${URL:7}" ]]; then
    python3 "$directory/prepare-arm-artifacts.py" identity "${URL:7}" || return $?
  fi
  if python3 "$directory/prepare-arm-artifacts.py" cache "$STORAGE" "$BASE"; then
    info 'Install: ARM artifact cache hit (validated generation; no PAT extraction or filesystem rebuild).'
    return 0
  else
    status=$?
    if (( status != 80 )); then
      error 'Existing ARM runtime state failed validation; preserved without rebuilding. Repair offline or explicitly reset storage.'
      return "$status"
    fi
  fi
  workspace=$(mktemp -d "$STORAGE/.rtd1619b-install-XXXXXX")
  chmod 0700 "$workspace"
  trap 'rm -rf -- "$workspace"' EXIT
  trap 'exit 143' TERM
  trap 'exit 130' INT
  if [[ -z "$URL" ]]; then
    local mirror=""
    selectDsmMirror || return $?
    URL="$mirror/release/7.2.2/72806/DSM_DS124_72806.pat"
  fi
  if (( $(df --output=avail -B 1 "$STORAGE" | tail -n 1) < 8589934592 )); then
    error 'Not enough free disk space: ARM preparation with bundled packages requires at least 8 GiB.'; return 94
  fi
  incoming="$workspace/source.pat"
  downloadPat "$incoming" || return $?
  info 'Install: Validating DS124 ARM PAT identity...'
  python3 "$directory/prepare-arm-artifacts.py" identity "$incoming" || return $?
  mkdir "$workspace/pat"
  extractPat "$incoming" "$workspace/pat" "$(stat -c%s "$incoming")" || return $?
  # One fakeroot session covers GNU tar and mke2fs, including device nodes/UIDs.
  declare -f html escape writeAtomic > "$workspace/progress-functions.sh"
  export ARM_PROGRESS_HELPER="$workspace/progress-functions.sh"
  export APP FOOTER1 FOOTER2 TEMPLATE PAGE INFO
  if fakeroot -- python3 "$directory/prepare-arm-artifacts.py" build "$incoming" "$workspace"; then
    status=0
  else
    status=$?
  fi
  (( status == 0 )) || return "$status"
  python3 "$directory/prepare-arm-artifacts.py" publish "$STORAGE" "$BASE" "$workspace/generation"
)

platformSealArtifacts() {
  # Called only after the QEMU process has exited. DSM's system image is writable.
  local directory
  directory=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
  local exit_code="unknown"
  if (( ${SHUTDOWN_SIGNAL:-0} != 0 )); then
    # Shared teardown has confirmed QEMU is stopped. Reap the real child.
    if wait "${ARM_QEMU_PID:-0}"; then exit_code=0; else exit_code=$?; fi
    [[ "$exit_code" == 127 ]] && exit_code="unknown"
    wait "${ARM_WATCH_PID:-0}" 2>/dev/null || :
  fi
  python3 "$directory/arm-lifecycle.py" record "$QEMU_DIR/arm-exit.json" "${SHUTDOWN_SIGNAL:-0}" "$exit_code"
  python3 "$directory/prepare-arm-artifacts.py" seal "$STORAGE" "$BASE" "$QEMU_DIR/arm-exit.json" || {
    warn 'ARM stopped state could not be recorded; disk preserved and next start will validate without rebuilding.'
    return 0
  }
}
