#!/usr/bin/env bash
set -Eeuo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf -- "$tmp"' EXIT
mkdir "$tmp/bin"
cat > "$tmp/bin/cat" <<'MOCK'
#!/bin/sh
printf 'console=ttyS0 vdsm.host_epoch=%s\n' "$TEST_EPOCH"
MOCK
cat > "$tmp/bin/date" <<'MOCK'
#!/bin/sh
printf '%s\n' "$*" > "$TEST_DATE_OUTPUT"
MOCK
chmod +x "$tmp/bin/"*
export PATH="$tmp/bin:$PATH" TEST_DATE_OUTPUT="$tmp/date-call"
TEST_EPOCH=1704067200 sh "$repo/src/guest/clock.sh"
grep -Eq '^-u -s @[0-9]+$' "$tmp/date-call"
for epoch in '' 0 -1 '1704067200;touch injected' 999999999999999999999 4102444801; do
  rm -f "$tmp/date-call"
  if TEST_EPOCH="$epoch" sh "$repo/src/guest/clock.sh" >/dev/null 2>&1; then exit 1; fi
  [[ ! -e "$tmp/date-call" ]]
done
echo 'Guest clock validation passed; host date was never changed.'
