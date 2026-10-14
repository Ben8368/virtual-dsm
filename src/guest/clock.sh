#!/bin/sh
# ARM virt has no working stock RTC. Seed UTC before network services.
set -efu
epoch=''
# Kernel arguments are whitespace-delimited words, not records.
# shellcheck disable=SC2013
for argument in $(cat /proc/cmdline); do
  case "$argument" in vdsm.host_epoch=*) epoch=${argument#vdsm.host_epoch=} ;; esac
done
case "$epoch" in ''|*[!0-9]*) echo 'vdsm-clock: missing/invalid host epoch' >&2; exit 1 ;; esac
if [ "${#epoch}" -gt 10 ] || [ "$epoch" -lt 1704067200 ] || [ "$epoch" -gt 4102444800 ]; then
  echo 'vdsm-clock: host clock is outside supported 2024-2100 range' >&2; exit 1
fi
read -r uptime _ < /proc/uptime
uptime=${uptime%%.*}
case "$uptime" in ''|*[!0-9]*) exit 1 ;; esac
target=$((epoch + uptime))
date -u -s "@$target" >/dev/null
echo 'vdsm-clock: initialized UTC from host launch time; NTP remains authoritative'
