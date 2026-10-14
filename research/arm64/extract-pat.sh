#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  echo "Usage: $0 /path/to/DSM_DS124_*.pat" >&2
}

if [[ $# -ne 1 ]]; then
  usage
  exit 2
fi

pat=$(realpath -- "$1") || {
  echo "ERROR: PAT file does not exist: $1" >&2
  exit 2
}
if [[ ! -f "$pat" || ! -s "$pat" ]]; then
  echo "ERROR: PAT path is not a non-empty regular file: $pat" >&2
  exit 2
fi

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
work="$script_dir/work"
out="$work/extracted"
report="$work/pat-report.txt"
image="${PAT_IMAGE:-vdsm/virtual-dsm}"
extractor="${PAT_EXTRACTOR:-}"

getUv() {
  local uv_bin target archive
  uv_bin="$(command -v uv || true)"
  if [[ -n "$uv_bin" ]]; then
    printf '%s\n' "$uv_bin"
    return 0
  fi

  case "$(uname -m)" in
    x86_64) target="x86_64-unknown-linux-gnu" ;;
    aarch64|arm64) target="aarch64-unknown-linux-gnu" ;;
    *)
      echo "ERROR: No automatic uv bootstrap for host architecture $(uname -m); install python3-venv or uv." >&2
      return 3 ;;
  esac

  archive="$work/tools/uv.tar.gz"
  curl -fL --retry 3 \
    "https://github.com/astral-sh/uv/releases/latest/download/uv-${target}.tar.gz" \
    -o "$archive"
  tar -xzf "$archive" -C "$work/tools"
  printf '%s\n' "$work/tools/uv-${target}/uv"
}

case "$pat" in
  "$out"/*)
    echo "ERROR: Keep the PAT outside the extraction directory: $out" >&2
    exit 2 ;;
esac

mkdir -p -- "$work"
rm -rf -- "$out"
mkdir -p -- "$out"

if tar -tf "$pat" >/dev/null 2>&1; then
  echo "Extracting tar PAT with the same tar mode used by src/install.sh..."
  tar -xpf "$pat" -C "$out"
else
  # Prefer the project image when a Docker daemon is usable. On development
  # hosts without one, run the exact same upstream patology.py used by
  # Dockerfile directly with its project dependencies in an ignored venv.
  if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    echo "Using the project's /run/extract.py from Docker image '$image'..."
    docker run --rm \
      --workdir /work \
      --entrypoint python3 \
      --volume "$pat:/input.pat:ro" \
      --volume "$out:/work" \
      "$image" /run/extract.py -i /input.pat -d 2
  else
    tool_dir="$work/tools"
    venv="$work/venv"
    mkdir -p -- "$tool_dir"

    if [[ -z "$extractor" ]]; then
      extractor="$tool_dir/patology.py"
      if [[ ! -s "$extractor" ]]; then
        echo "Docker is unavailable; fetching the existing patology.py extractor into the ignored work directory..."
        curl -fL --retry 3 \
          "https://raw.githubusercontent.com/sud0woodo/patology/main/patology.py" \
          -o "$extractor"
      fi
    elif [[ ! -s "$extractor" ]]; then
      echo "ERROR: PAT_EXTRACTOR does not exist or is empty: $extractor" >&2
      exit 3
    fi

    if [[ ! -x "$venv/bin/python" ]]; then
      if ! python3 -m venv "$venv"; then
        echo "python3-venv is unavailable; bootstrapping the ignored venv with uv..." >&2
        rm -rf -- "$venv"
        uv_bin=$(getUv)
        "$uv_bin" venv --python python3 "$venv"
      fi
    fi
    if [[ ! -f "$venv/.patology-deps-ready" ]]; then
      if "$venv/bin/python" -m pip --version >/dev/null 2>&1; then
        "$venv/bin/python" -m pip install --disable-pip-version-check \
          msgpack pysodium "dissect.cstruct==4.7"
      else
        uv_bin=$(getUv)
        "$uv_bin" pip install --python "$venv/bin/python" \
          msgpack pysodium "dissect.cstruct==4.7"
      fi
      touch "$venv/.patology-deps-ready"
    fi

    echo "Using the project's patology.py extractor in the ignored host venv..."
    extractor_help=$("$venv/bin/python" "$extractor" --help 2>&1 || true)
    if grep -Eq -- '\[-d\]' <<< "$extractor_help"; then
      dump_args=(-d)
    else
      dump_args=(-d 2)
    fi
    (cd "$out" && "$venv/bin/python" "$extractor" -i "$pat" "${dump_args[@]}")
  fi
fi

# src/install.sh unpacks the PAT's *.bin.zip boot archive with 7z before
# attaching it as a boot disk. Do the same in this disposable workspace so
# kernel/initrd candidates inside the archive show up in the report.
if command -v 7z >/dev/null 2>&1; then
  while IFS= read -r archive; do
    destination="$out/boot-images/$(basename -- "${archive%.zip}")"
    mkdir -p -- "$destination"
    echo "Unpacking boot archive: ${archive#"$out"/}"
    7z x -y -o"$destination" "$archive" >/dev/null
  done < <(find "$out" -type f -name '*.bin.zip' -print)
else
  echo "NOTE: 7z is unavailable; nested *.bin.zip boot archives remain unopened." >&2
fi

{
  echo "PAT: $pat"
  echo "Extracted to: $out"
  echo
  echo "Likely boot artifacts and root filesystem components:"
  find "$out" -type f -printf '%P\t%s bytes\n' | sort | \
    awk 'tolower($0) ~ /(kernel|zimage|vmlinuz|initrd|rd\.gz|\.dtb|\.fdt|boot|hda[0-9]|rootfs|synoboot|\.bin\.zip|\.tgz|\.txz)/ { print }'
  echo
  echo "All extracted files:"
  find "$out" -type f -printf '%P\t%s bytes\n' | sort
} | tee "$report"

echo
echo "Report: $report"
echo "Review candidate paths before running boot-qemu.sh; extraction does not imply they are compatible with QEMU virt."
