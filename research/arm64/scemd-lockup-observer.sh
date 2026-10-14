#!/usr/bin/env bash
# Research-only lockup observer for disposable ARM64 DSM root.
# Records soft-lockup timing, scemd state, and key /proc snapshots.
set -u
exec >/var/log/arm64-scemd-lockup-observer.log 2>&1
echo "LOCKUP_OBSERVER_START UPTIME=$(cut -d ' ' -f 1 /proc/uptime)"
sample=0
lockup_seen=0
while [[ $sample -lt 2400 ]]; do
  up=$(cut -d ' ' -f 1 /proc/uptime)
  if dmesg | grep -q 'soft lockup'; then
    if [[ $lockup_seen -eq 0 ]]; then
      lockup_seen=1
      echo "FIRST_SOFT_LOCKUP_WALL UPTIME=$up SAMPLE=$sample"
      echo LOCKUP_DMESG_BEGIN
      dmesg | grep -E 'soft lockup|queued_write_lock|synobios|ledtrig_syno|Unable to handle|Oops|Call trace|Comm:' | tail -n 120
      echo LOCKUP_DMESG_END
      echo LOCKUP_PROC_BEGIN
      ps -eLo pid,tid,psr,stat,wchan,comm,args --width 240 2>/dev/null || ps -eLo pid,tid,psr,stat,comm --width 200
      echo '--- /proc/interrupts ---'
      cat /proc/interrupts 2>/dev/null || true
      echo '--- /proc/locks ---'
      cat /proc/locks 2>/dev/null || true
      echo '--- /proc/loadavg ---'
      cat /proc/loadavg 2>/dev/null || true
      echo LOCKUP_PROC_END
      sync
    fi
  fi
  if [[ $((sample % 60)) -eq 0 ]]; then
    echo "LOCKUP_SAMPLE=$sample UPTIME=$up"
    # shellcheck disable=SC2009
    ps -eo pid,tid,psr,stat,wchan,comm,args --width 240 2>/dev/null | grep -E 'scemd|syno_led|synobios' || true
    dmesg | tail -n 5
  fi
  sample=$((sample + 1))
  sleep 1
done
echo LOCKUP_OBSERVER_DONE
