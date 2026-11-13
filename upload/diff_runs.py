#!/usr/bin/env python3
"""diff_runs.py: diff_data.tar (stdin) -> diff_runs.tar (stdout): its WRF run files (wrf_runs_diff/) without the
reference machine's WRF build trees (wrf_build/: their configure.wrf and libraries name the machine's paths; the
workflow fetches WRF builds of ci/wrf_build.sh instead). Hard links into wrf_build/ become relative symbolic links
(the build trees have the same run/ tables); owner 0, GNU format, as bin/repack.py."""
import os
import sys
import tarfile

src = tarfile.open(fileobj=sys.stdin.buffer, mode="r|")
dst = tarfile.open(fileobj=sys.stdout.buffer, mode="w|", format=tarfile.GNU_FORMAT)
n = 0
for m in src:
    if m.name.startswith("wrf_build"):
        continue
    if (m.issym() or m.islnk()) and "/home/" in m.linkname:
        sys.exit(f"diff_runs: link into /home {m.name}")
    if m.islnk() and m.linkname.startswith("wrf_build/"):
        m.type = tarfile.SYMTYPE
        m.linkname = os.path.relpath(m.linkname, os.path.dirname(m.name))
    m.uid = m.gid = 0
    m.uname = m.gname = ""
    m.mtime = int(m.mtime)
    m.pax_headers = {}
    dst.addfile(m, src.extractfile(m) if m.isfile() else None)
    n += 1
dst.close()
print(f"diff_runs: {n} members", file=sys.stderr)
