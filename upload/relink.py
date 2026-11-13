#!/usr/bin/env python3
"""relink.py LIST OUT.tar: the links of a tar that point into the reference machine's data trees (LIST: "name target"
lines), as relative links inside the data tree: <home>/wrf_ref480/X -> wrf_ref/X, <home>/wrf_real480/X ->
wrf_runs/X. Links onto their own path in the data tree are left out (an earlier tar holds the file); other targets (WRF's build tree) stay left out, as the re-pack left them."""
import os
import re
import sys
import tarfile

MAP = [(re.compile(r"^/home/[^/]+/wrf_ref480/"), "wrf_ref/"), (re.compile(r"^/home/[^/]+/wrf_real480/"), "wrf_runs/")]
out = tarfile.open(sys.argv[2], "w", format=tarfile.GNU_FORMAT)
n = 0
for line in open(sys.argv[1]):
    name, target = line.split()
    for rx, base in MAP:
        if rx.match(target):
            tgt = rx.sub(base, target)
            if os.path.normpath(tgt) == os.path.normpath(name):
                break  # a link to the file itself on the reference machine: the earlier tar's file stays
            m = tarfile.TarInfo(name)
            m.type = tarfile.SYMTYPE
            m.linkname = os.path.relpath(tgt, os.path.dirname(name))
            m.mode, m.mtime = 0o777, 0
            out.addfile(m)
            n += 1
            print(name, "->", m.linkname)
            break
out.close()
print(f"relink: {n} links", file=sys.stderr)
