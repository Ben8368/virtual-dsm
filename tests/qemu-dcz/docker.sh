#!/usr/bin/env bash
# Install test-only compilers in a disposable container, never in the image.
set -Eeuo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
image=${1:?Production image required}
out=${2:?Output directory required}
mkdir -p -- "$out"
out=$(realpath -e -- "$out")
docker run --rm --entrypoint bash \
  --env DEBIAN_FRONTEND=noninteractive --env PYTHONDONTWRITEBYTECODE=1 \
  --mount "type=bind,src=$repo,dst=/workspace,readonly" \
  --mount "type=bind,src=$out,dst=/results" \
  "$image" -ec '
    apt-get update
    apt-get install -y --no-install-recommends gcc-aarch64-linux-gnu binutils-aarch64-linux-gnu
    bash /workspace/tests/qemu-dcz/run.sh /usr/local/bin/qemu-system-aarch64 /results
  '
