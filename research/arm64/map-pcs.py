#!/usr/bin/env python3
"""Map QEMU physical PCs to a recovered ARM64 kernel symbol table."""

from __future__ import annotations

import argparse
import bisect
import subprocess
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("elf", type=Path, help="recovered ARM64 ELF")
    parser.add_argument(
        "pcs",
        nargs="+",
        help="QEMU physical PCs or post-MMU kernel VAs, e.g. 0x40a97000",
    )
    parser.add_argument("--load-address", default="0x40200000")
    parser.add_argument("--symbol-base", default="0xffffffc010000000")
    args = parser.parse_args()
    load_address = int(args.load_address, 0)
    symbol_base = int(args.symbol_base, 0)

    result = subprocess.run(
        ["nm", "-n", str(args.elf)], check=True, capture_output=True, text=True
    )
    symbols: list[tuple[int, str, str]] = []
    for line in result.stdout.splitlines():
        fields = line.split(maxsplit=2)
        if len(fields) == 3:
            try:
                symbols.append((int(fields[0], 16), fields[1], fields[2]))
            except ValueError:
                pass
    symbols.sort()
    addresses = [entry[0] for entry in symbols]

    print("QEMU PC | Image offset | ELF virtual address | nearest symbol | confidence")
    print("---|---:|---:|---|---")
    for raw_pc in args.pcs:
        pc = int(raw_pc, 0)
        if pc >= symbol_base:
            offset = pc - symbol_base
            va = pc
        else:
            offset = pc - load_address
            va = symbol_base + offset
        if offset < 0:
            print(
                f"0x{pc:x} | — | — | outside Image (QEMU boot stub) | no mapping"
            )
            continue
        index = bisect.bisect_right(addresses, va) - 1
        if index < 0:
            name, delta, confidence = "no preceding symbol", None, "none"
        else:
            sym_addr, kind, name = symbols[index]
            delta = va - sym_addr
            if delta == 0:
                confidence = "exact address; symbol alias may exist"
            elif kind in "TtWw" and delta <= 0x1000:
                confidence = "near function symbol; instruction range unverified"
            else:
                confidence = "nearest symbol only; may be data/section boundary"
        offset_text = f"+0x{offset:x}" if offset >= 0 else f"-0x{-offset:x}"
        delta_text = "—" if delta is None else f"+0x{delta:x}"
        print(
            f"0x{pc:x} | {offset_text} | 0x{va:x} | "
            f"{name}{delta_text} | {confidence}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
