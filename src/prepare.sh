#!/usr/bin/env bash
set -Eeuo pipefail

closeWebserver() {

  disabled "${NETWORK:-Y}" && return 0

  MSG="Booting DSM instance..."
  html "$MSG" || return $?

  if enabled "${DHCP:-N}" || disabled "${WEB:-}"; then
    return 0
  fi

  writeAtomic "$WSD_COMMAND" "portal" || return $?

  sleep 1.2
  stopAllServers

  WEB="N"

  return 0
}

platformPrepareSystemDisks || return $?
closeWebserver || return $?

return 0
