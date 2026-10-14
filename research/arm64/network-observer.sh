#!/usr/bin/env bash
# Read-only guest observer for a disposable research disk; ordinary /init stays PID 1.
set -u
exec >/var/log/arm64-network-observer.log 2>&1
if [[ -f /root/arm64-management-observer.sh ]]; then
  /bin/bash /root/arm64-management-observer.sh &
fi
if [[ -f /root/arm64-scemd-lockup-observer.sh ]]; then
  /bin/bash /root/arm64-scemd-lockup-observer.sh &
fi
snapshot=0
network_test_done=0
while [[ $snapshot -lt 24 ]]; do
  echo "ARM64_NETWORK_SNAPSHOT_BEGIN=$snapshot"
  echo "ARM64_NETWORK_PROGRESS_BEGIN=$snapshot" >/dev/ttyS0
  cat /proc/uptime
  dmesg | grep -Ei 'usb|xhci|cdc|eth|netif|r8169' || true
  cat /proc/modules
  readlink -f /sys/bus/platform/devices/b200000.usb/driver || true
  grep -Ei 'xhci|ahci' /proc/interrupts || true
  ls -l /sys/bus/usb /dev/bus/usb 2>/dev/null || true
  ls -l /dev/bus/usb/* 2>/dev/null || true
  find /sys/bus/usb/devices -maxdepth 2 -type f | sort
  for device in /sys/bus/usb/devices/*; do
    [[ -e "$device" ]] || continue
    echo "USB_DEVICE=$device"
    for prop in idVendor idProduct bConfigurationValue bInterfaceClass bInterfaceSubClass bInterfaceProtocol product manufacturer serial; do
      [[ -f "$device/$prop" ]] && echo "$prop=$(cat "$device/$prop")"
    done
    readlink -f "$device/driver" || true
  done
  cat /proc/net/dev
  ls -l /sys/class/net
  for iface in /sys/class/net/*; do
    echo "NET_DEVICE=$iface"
    readlink -f "$iface/device" || true
    readlink -f "$iface/device/driver" || true
    for prop in address carrier operstate; do
      [[ -f "$iface/$prop" ]] && echo "$prop=$(cat "$iface/$prop" 2>/dev/null)"
    done
  done
  echo NETWORK_LINK_DIAG_BEGIN
  timeout 15 ip link 2>/dev/null || true
  echo NETWORK_LINK_DIAG_END
  timeout 15 ip addr 2>/dev/null || true
  timeout 15 ifconfig -a 2>/dev/null || true
  timeout 15 route -n 2>/dev/null || true
  cat /etc/resolv.conf 2>/dev/null || true
  ls -l /etc/sysconfig/network-scripts/ifcfg-* 2>/dev/null || true
  cat /etc/sysconfig/network-scripts/ifcfg-* 2>/dev/null || true
  grep -E 'maxlanport|support_ethernet|netif_seq|forbid_unsupport' /etc.defaults/synoinfo.conf /etc/synoinfo.conf 2>/dev/null || true
  cat /proc/sys/kernel/syno_internal_netif_num /proc/sys/kernel/syno_skip_vender_mac_interfaces 2>/dev/null || true
  gateway=$(timeout 15 ip route 2>/dev/null | awk '/^default/ {print $3; exit}')
  if [[ -n "$gateway" ]]; then
    echo "ACTUAL_DEFAULT_GATEWAY=$gateway"
    ping -c 2 -W 2 "$gateway" || true
    if [[ $network_test_done -eq 0 ]]; then
      getent hosts example.com || true
      curl --connect-timeout 3 --max-time 8 -I http://example.com 2>&1 || true
      network_test_done=1
    fi
  fi
  cat /proc/net/tcp /proc/net/tcp6 2>/dev/null || true
  timeout 15 ss -lntup 2>/dev/null || timeout 15 netstat -lntup 2>/dev/null || true
  if command -v pgrep >/dev/null 2>&1; then
    pgrep -af 'dhcp|network|udev|nginx|sshd|httpd' || true
  else
    timeout 15 ps auxww
    timeout 15 ps -eo pid,ppid,stat,wchan:32,args --width 240 || true
  fi
  timeout 15 systemctl --no-pager status syno-mount-usbfs.service rc-network.service SynoInitEth.service 2>/dev/null || true
  timeout 15 systemctl --no-pager --failed || true
  timeout 15 systemctl --no-pager --state=running || true
  timeout 15 systemctl --no-pager --state=failed || true
  echo "ARM64_NETWORK_SNAPSHOT_END=$snapshot"
  sync
  echo "ARM64_NETWORK_SNAPSHOT_END=$snapshot" >/dev/ttyS0
  snapshot=$((snapshot+1))
  sleep 30
done
echo ARM64_NETWORK_OBSERVER_DONE
echo ARM64_NETWORK_OBSERVER_DONE >/dev/ttyS0
