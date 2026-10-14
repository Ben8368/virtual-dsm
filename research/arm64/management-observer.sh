#!/usr/bin/env bash
# Read-only management evidence on the disposable research root.
set -u
exec >/var/log/arm64-management-observer.log 2>&1
sample=0
while [[ $sample -lt 1800 ]]; do
  echo "MANAGEMENT_SAMPLE=$sample UPTIME=$(cut -d ' ' -f 1 /proc/uptime)"
  cat /proc/net/dev
  # Preserve active management connections and their socket inodes.
  awk 'NR == 1 || ($2 ~ /:(1388|1389)$/ && $4 != "0A")' /proc/net/tcp
  if [[ $((sample % 30)) -eq 0 ]]; then
    echo MANAGEMENT_STATE_BEGIN
    ip addr 2>/dev/null || true
    ip route 2>/dev/null || true
    systemctl --failed --no-pager 2>/dev/null || true
    systemctl --state=running --no-pager 2>/dev/null || true
    netstat -lntp 2>/dev/null || true
    # Include process state and parent IDs; the stock guest lacks pgrep.
    # shellcheck disable=SC2009
    ps -eo pid,ppid,stat,args --width 240 | grep -E 'nginx|synoscgi|httpd|scemd|pkgctl' || true
    for process in /proc/[0-9]*; do
      [[ -r "$process/comm" ]] || continue
      [[ $(cat "$process/comm") == nginx ]] || continue
      echo "NGINX_PID=${process##*/}"
      ls -l "$process/fd" 2>/dev/null || true
    done
    dmesg | tail -n 60
    for log in /var/log/nginx/access.log /var/log/nginx/error.log /var/log/httpd/access_log; do
      [[ -f "$log" ]] && { echo "LOG=$log"; tail -n 12 "$log"; }
    done
    echo MANAGEMENT_STATE_END
    sync
  fi
  sample=$((sample+1))
  sleep 1
done
