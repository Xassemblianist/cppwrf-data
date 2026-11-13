#!/usr/bin/env python3
"""Re-pack a tar stream (stdin -> stdout) deterministically: owner and group 0 with empty names, links whose target
is under /home dropped (listed on stderr: the next tar of the data list holds them as files), GNU format."""
import sys
import tarfile

src = tarfile.open(fileobj=sys.stdin.buffer, mode="r|")
dst = tarfile.open(fileobj=sys.stdout.buffer, mode="w|", format=tarfile.GNU_FORMAT)
dropped = 0
for m in src:
    if m.issparse():
        sys.exit(f"repack: sparse member {m.name}")
    if (m.issym() or m.islnk()) and "/home/" in m.linkname:
        dropped += 1
        continue
    m.uid = m.gid = 0
    m.uname = m.gname = ""
    m.mtime = int(m.mtime)
    m.pax_headers = {}
    dst.addfile(m, src.extractfile(m) if m.isfile() else None)
dst.close()
src.close()
print(f"repack: dropped {dropped} links into /home", file=sys.stderr)
