#!/bin/sh
# Explicit migration of an existing ARM runtime; never rebuild its disk.
set -eu
[ "$(id -u)" = 0 ] || { echo 'Run inside DSM as root.' >&2; exit 1; }
grep -qx 'unique="synology_rtd1619b_ds124"' /etc.defaults/synoinfo.conf || {
  echo 'Clock integration is only supported for DS124 ARM DSM.' >&2; exit 1;
}
directory=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
[ -f "$directory/clock.sh" ] && [ -f "$directory/virtual-dsm-clock.service" ] || exit 1
mkdir -p /usr/local/libexec/virtual-dsm
install -m 0755 "$directory/clock.sh" /usr/local/libexec/virtual-dsm/clock.sh
install -m 0644 "$directory/virtual-dsm-clock.service" /usr/lib/systemd/system/virtual-dsm-clock.service
systemctl daemon-reload
systemctl enable virtual-dsm-clock.service
echo 'Clock unit enabled for the next boot. First update the container launcher to pass vdsm.host_epoch; then restart through DSM.'
