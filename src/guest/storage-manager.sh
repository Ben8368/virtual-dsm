#!/bin/sh
# Install only the authenticated PAT's system-partition prerequisite.
# Keep normal synopkg validation and failure results.
set -eu
if [ -f /var/packages/StorageManager/INFO ] && [ -e /var/packages/StorageManager/target ]; then
  echo 'vdsm-packages: Storage Manager already installed'
  exit 0
fi
cd /usr/local/share/virtual-dsm
sha256sum -c StorageManager.sha256
/usr/syno/bin/synopkg install StorageManager-rtd1619b-1.0.0-00502.spk
echo 'vdsm-packages: Storage Manager installation completed'
