#!/usr/bin/env bash
# Hermetic default x86 production command regression; no Docker or DSM runtime.
set -Eeuo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
exec python3 "$repo/tests/production-x86-command.py"
