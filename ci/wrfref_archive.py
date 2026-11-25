#!/usr/bin/env python3
"""Stream a portable wrfref tar. Store linked inputs and tables once, using tar hard links."""
import os
import sys
import tarfile
from pathlib import Path

root = Path(sys.argv[1]).resolve()
directories = set(sys.argv[2:])
with tarfile.open(fileobj=sys.stdout.buffer, mode="w|", format=tarfile.GNU_FORMAT) as archive:
    for dirname in sys.argv[2:]:
        for p in sorted((root / dirname).rglob("*")):
            if p.name.endswith(".exe") or p.is_dir():
                continue
            source = p.resolve()
            if not source.is_file():
                if p.name.startswith(("wrfinput_", "wrfbdy_", "wrflowinp_", "wrffdda_")):
                    sys.exit(f"missing reference input {p} -> {source}")
                print(f"skipping unresolved optional file {p} -> {source}", file=sys.stderr)
                continue
            arcname = str(p.relative_to(root))
            internal = source.is_relative_to(root) and source.relative_to(root).parts[0] in directories
            if p.is_symlink() and internal:
                member = archive.gettarinfo(str(p), arcname=arcname)
                member.linkname = os.path.relpath(source, p.parent)
                member.uid = member.gid = 0
                member.uname = member.gname = ""
                archive.addfile(member)
                continue
            member = archive.gettarinfo(str(source), arcname=arcname)
            member.uid = member.gid = 0
            member.uname = member.gname = ""
            with source.open("rb") as f:
                archive.addfile(member, f)
