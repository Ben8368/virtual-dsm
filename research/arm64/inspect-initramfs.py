#!/usr/bin/env python3
"""Read-only entrypoint/ELF audit, retaining permissions from the newc archive."""

import argparse
import re
import stat
import subprocess
from pathlib import Path


def command(*args):
    result = subprocess.run(args, capture_output=True, text=True, check=False)
    return result.stdout.strip() or result.stderr.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("tree", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    data = args.archive.read_bytes()
    entries = {}
    offset = 0
    while data[offset:offset + 6] in (b"070701", b"070702"):
        fields = [int(data[offset + 6 + i * 8:offset + 14 + i * 8], 16)
                  for i in range(13)]
        mode, size, namesize = fields[1], fields[6], fields[11]
        start = offset + 110
        name = data[start:start + namesize - 1].decode()
        start = (start + namesize + 3) & ~3
        payload = data[start:start + size]
        offset = (start + size + 3) & ~3
        if name == "TRAILER!!!":
            break
        entries["/" + name.removeprefix("./").lstrip("/")] = (mode, payload)

    def resolve(path):
        parts = path.strip("/").split("/")
        done = []
        for _ in range(80):
            if not parts:
                return "/" + "/".join(done)
            part = parts.pop(0)
            if part in ("", "."):
                continue
            if part == "..":
                if done:
                    done.pop()
                continue
            done.append(part)
            entry = entries.get("/" + "/".join(done))
            if entry and stat.S_ISLNK(entry[0]):
                done.pop()
                target = entry[1].decode()
                if target.startswith("/"):
                    done = []
                parts = target.strip("/").split("/") + parts
        raise ValueError("symlink loop: " + path)

    def elf(path):
        local = str(args.tree / path.lstrip("/"))
        header = command("readelf", "-h", local)
        program = command("readelf", "-l", local)
        dynamic = command("readelf", "-d", local)
        machine = re.search(r"Machine:\s*(.*)", header)
        interp = re.search(r"Requesting program interpreter: ([^\]]+)", program)
        needed = re.findall(r"\(NEEDED\).*\[([^\]]+)\]", dynamic)
        return (machine.group(1) if machine else "not ELF",
                interp.group(1) if interp else None, needed)

    lines = ["Read-only audit; archive modes are authoritative (DrvFS extraction can show 0777).",
             "No foreign executable was run; libraries checked recursively with readelf."]
    for candidate in ("/init", "/linuxrc", "/linuxrc.syno", "/linuxrc.syno.impl",
                      "/sbin/init", "/bin/init", "/bin/sh", "/etc/rc"):
        lines += ["", "path: " + candidate]
        if candidate not in entries:
            lines += ["exists: no"]
            continue
        mode, payload = entries[candidate]
        real = resolve(candidate)
        local = str(args.tree / candidate.lstrip("/"))
        lines += ["exists: yes", "type: " + ("symlink" if stat.S_ISLNK(mode) else "regular"),
                  f"mode: {mode:07o} ({stat.filemode(mode)})",
                  "symlink target: " + (payload.decode() if stat.S_ISLNK(mode) else "none"),
                  "resolved target: " + real,
                  f"resolved mode: {entries[real][0]:07o}",
                  "resolved executable: " + str(bool(entries[real][0] & 0o111)),
                  "ls -l: " + command("ls", "-l", local),
                  "stat: " + command("stat", "-c", "%F %a %N", local),
                  "file: " + command("file", "-L", local)]
        machine, interp, needed = elf(real)
        if machine == "not ELF" and entries[real][1].startswith(b"#!"):
            interp = entries[real][1].splitlines()[0][2:].decode().strip().split()[0]
        lines += ["ELF architecture: " + machine, "interpreter: " + (interp or "none"),
                  "linkage: " + ("dynamic" if needed or machine != "not ELF" and interp else "static" if machine != "not ELF" else "script"),
                  "DT_NEEDED: " + (", ".join(needed) or "none (script interpreter audited below)" )]
        pending = [real] + ([resolve(interp)] if interp else [])
        visited = set()
        missing = []
        while pending:
            path = pending.pop(0)
            if path in visited:
                continue
            visited.add(path)
            if path not in entries:
                missing.append(path)
                continue
            arch, loader, libs = elf(path)
            lines.append(f"dependency audit: {path}: {arch}; DT_NEEDED={','.join(libs) or 'none'}")
            if loader:
                pending.append(resolve(loader))
            for lib in libs:
                found = next((resolve(d + lib) for d in ("/lib/", "/usr/lib/")
                              if resolve(d + lib) in entries), None)
                lines.append(f"library {lib}: present={'yes: ' + found if found else 'no'}")
                if found:
                    pending.append(found)
                else:
                    missing.append(lib)
        lines += ["libraries present: " + ("no: " + ", ".join(missing) if missing else "yes")]
    args.output.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
