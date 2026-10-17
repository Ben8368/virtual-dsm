#!/usr/bin/env bash
set -Eeuo pipefail

version=8.2.2
expected_commit=11aa0b1ff115b86160c4d37e7c37e6a6b13b77ea
destination=${1:?QEMU destination directory required}
parent=$(dirname -- "$destination")
mkdir -p -- "$parent"
[[ ! -e "$destination" ]] || { echo 'QEMU source destination already exists' >&2; exit 64; }
tmp=$(mktemp -d "$parent/.qemu-source.XXXXXX")
trap 'rm -rf -- "$tmp"' EXIT

if [[ -n "${QEMU_SOURCE_OVERRIDE:-}" ]]; then
  sources=("$QEMU_SOURCE_OVERRIDE")
else
  sources=(
    https://gitlab.com/qemu-project/qemu.git
    https://github.com/qemu/qemu.git
  )
fi
dns_attempts=0

for source in "${sources[@]}"; do
  checkout="$tmp/checkout"
  log="$tmp/git.log"
  rm -rf -- "$checkout"
  echo "Fetching pinned QEMU v$version from $source" >&2
  if git clone --depth 1 --branch "v$version" "$source" "$checkout" 2>"$log"; then
    actual_commit=$(git -C "$checkout" rev-parse HEAD)
    actual_version=$(<"$checkout/VERSION")
    if [[ "$actual_commit" != "$expected_commit" || "$actual_version" != "$version" ]]; then
      echo "QEMU source identity mismatch from $source: expected v$version ($expected_commit), got $actual_version ($actual_commit)" >&2
      exit 65
    fi
    mv -- "$checkout" "$destination"
    echo "QEMU source identity verified: v$version ($expected_commit)" >&2
    exit 0
  fi

  cat "$log" >&2
  if grep -Eqi 'could not resolve host|temporary failure in name resolution|name or service not known|nodename nor servname provided' "$log"; then
    ((dns_attempts += 1))
  fi
done

if (( dns_attempts == ${#sources[@]} )); then
  echo 'QEMU_SOURCE_DNS_FAILURE: all pinned QEMU sources were unavailable; no patch or compile step ran.' >&2
else
  echo 'QEMU_SOURCE_UNAVAILABLE: all pinned QEMU sources were unavailable; no patch or compile step ran.' >&2
fi
exit 69
