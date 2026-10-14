#!/bin/sh
# Read-only guest collection. No account/identity values or raw log lines leave DSM.
set -eu
network=N
case "${1:-}" in '' ) ;; --network) network=Y ;; *) echo 'Usage: package-diagnostics.sh [--network]' >&2; exit 64 ;; esac
emit() { printf '%s\t%s\n' "$1" "$2"; }
key() { sed -n "s/^$2=\"\{0,1\}\([^\"]*\)\"\{0,1\}$/\1/p" "$1" 2>/dev/null | head -n 1; }
emit format 1
emit epoch "$(date -u +%s)"
emit arch "$(uname -m)"
emit unique "$(key /etc.defaults/synoinfo.conf unique)"
emit version "$(key /etc.defaults/VERSION productversion)"
emit build "$(key /etc.defaults/VERSION buildnumber)"
emit clock_service "$(systemctl is-active virtual-dsm-clock.service 2>/dev/null || :)"
emit volume "$(awk '$2 == "/volume1" {print $3 ":" $4}' /proc/mounts)"
emit pgsql "$(systemctl is-active pgsql-adapter.service 2>/dev/null || :)"
for package in StorageManager SurveillanceVideoExtension SurveillanceStation; do
  state=absent
  if [ -f "/var/packages/$package/INFO" ]; then
    state=$(systemctl is-active "pkgctl-$package.service" 2>/dev/null || :)
    [ -n "$state" ] || state=unknown
  fi
  emit "package.$package" "$state"
  emit "package.$package.version" "$(key "/var/packages/$package/INFO" version)"
done
for file in synopkg.log synopkgmgr.log; do
  if [ ! -r "/var/log/$file" ]; then
    emit "logs.$file" unavailable
    continue
  fi
  emit "logs.$file" readable
  # Classify bounded recent history; do not export URLs, serials, license keys,
  # request bodies or package script output containing credentials.
  recent=$(tail -n 200 "/var/log/$file")
  for rule in hwid authorization dependency timeout tls install_failure; do
    case "$rule" in
      hwid) pattern='Failed to init hwid' ;;
      authorization) pattern='[Aa]uthoriz.*[Ff]ail|[Ff]ail.*[Aa]uthoriz|[Uu]nable.*[Aa]uthoriz|[Ll]icense.*([Ee]rror|[Ff]ail)' ;;
      dependency) pattern='[Dd]ependen.*([Ff]ail|[Mm]iss)|([Ff]ail|[Mm]iss).*[Dd]ependen|SurveillanceVideoExtension.*(ret=\[[1-9]|[Ff]ail)|([Ff]ail|[Uu]nable).*SurveillanceVideoExtension|CodecPack.*[Ff]ail' ;;
      timeout) pattern='code=28([ ,]|$)|curl (ret|returned|code)[=: ]+28([ ,]|$)|[Tt]imed out|[Tt]imeout' ;;
      tls) pattern='(SSL|TLS|[Cc]ertificate).*([Ee]rror|[Ff]ail|[Ii]nvalid|[Ee]xpired)|[Ee]rror.*(SSL|TLS)|curl (ret|returned|code)[=: ]+(35|60|77)([ ,]|$)|code=(35|60|77)([ ,]|$)' ;;
      install_failure) pattern='install.*([Ff]ail|ret=\[[1-9])|[Ff]ail.*install' ;;
    esac
    found=no
    if printf '%s\n' "$recent" | grep -Eq "$pattern"; then found=yes; fi
    emit "history.$file.$rule" "$found"
  done
done
if [ "$network" = Y ]; then
  command -v curl >/dev/null || { emit network unavailable; exit 0; }
  for endpoint in pkgupdate download; do
    case "$endpoint" in
      pkgupdate) url=https://pkgupdate7.synology.com/ ;;
      download) url=https://global.synologydownload.com/ ;;
    esac
    # A root-path HTTP 403/404 still proves TLS transport, not authorization.
    rc=0
    status=$(curl --connect-timeout 8 --max-time 15 --silent --output /dev/null --write-out '%{http_code}' "$url") || rc=$?
    emit "network.$endpoint.curl" "$rc"
    emit "network.$endpoint.http" "$status"
  done
else
  emit network not_checked
fi
