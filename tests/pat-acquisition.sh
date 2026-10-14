#!/usr/bin/env bash
# Synthetic common PAT tests; no DSM downloads, extraction or proprietary data.
set -Eeuo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
. "$repo/src/pat.sh"
tmp=$(mktemp -d)
trap 'rm -rf -- "$tmp"' EXIT
info() { :; }
html() { :; }
error() { printf '%s\n' "$*" >&2; }
setCountry() { COUNTRY=CN; detected=Y; }
COUNTRY=CN URL=https://global.synologydownload.com/custom mirror=''
selectDsmMirror
[[ "$mirror" == https://global.synologydownload.com/download/DSM ]]
COUNTRY=US URL=https://cndl.synology.cn/custom mirror=''
selectDsmMirror
[[ "$mirror" == https://cndl.synology.cn/download/DSM ]]
COUNTRY='' URL='' mirror='' detected=N
selectDsmMirror
[[ "$mirror" == https://cndl.synology.cn/download/DSM && "$detected" == Y ]]
source_file="$tmp/source with spaces.pat"
printf 'synthetic PAT input' > "$source_file"
source_hash=$(sha256sum "$source_file")
URL="file://$source_file" BASE=synthetic CONNECTIONS=4
(downloadPat "$tmp/copied.pat")
cmp "$source_file" "$tmp/copied.pat"
[[ $(sha256sum "$source_file") == "$source_hash" ]]
downloadRetry() {
  [[ "$1:$2:$3:$4:$5:$6:$7:$8" == "$tmp/downloaded.pat:4:5:synthetic.pat:0:https://example.invalid/synthetic.pat:$tmp/downloaded.pat:Downloading DSM" ]]
  printf 'synthetic downloaded PAT' > "$1"
}
URL=https://example.invalid/synthetic.pat
downloadPat "$tmp/downloaded.pat"
[[ -s "$tmp/downloaded.pat" ]]
echo 'Common PAT regression passed: mirror precedence/detection, local source preservation, existing retry arguments.'
