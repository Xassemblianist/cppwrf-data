#!/usr/bin/env python3
"""assemble.py LAYOUTDIR ARTDIR OUTDIR [--previous SHA256SUMS TARS.txt] [--mbps N]: the records of a packs release
from layout.py's output (LAYOUTDIR: packs.txt, INDEX.tsv) and the repack workflow's artifacts (ARTDIR/*/sums.txt,
tars.txt; packs already in the release, kept from an earlier layout: from --previous): OUTDIR/SHA256SUMS (every
part and LAYOUT), TARS.txt (PACK bytes sha256 parts), INDEX.tsv.gz and LAYOUT ("packs", then plan.py options for
the release: "mbps N" its download rate, "diff-jobs N"). Exits 1 if a pack is missing or its size differs from the layout's."""
import argparse
import glob
import gzip
import hashlib
import os
import shutil
import sys

ap = argparse.ArgumentParser()
ap.add_argument("layout")
ap.add_argument("art")
ap.add_argument("out")
ap.add_argument("--previous", nargs=2)
ap.add_argument("--mbps", type=int, default=150)
ap.add_argument("--diff-jobs", type=int, default=3)
a = ap.parse_args()
want = {}
for line in open(os.path.join(a.layout, "packs.txt")):
    f = line.split()
    want[f[0]] = int(f[1])
sums, tars = {}, {}
srcs = [(os.path.join(d, "sums.txt"), os.path.join(d, "tars.txt")) for d in glob.glob(os.path.join(a.art, "*"))]
if a.previous:
    srcs.insert(0, tuple(a.previous))
for s, t in srcs:
    if os.path.exists(s):
        for line in open(s):
            h, n = line.split()
            sums[n] = h
    if os.path.exists(t):
        for line in open(t):
            f = line.split()
            tars[f[0]] = f
bad = 0
for p, size in want.items():
    if p not in tars:
        print(f"missing pack {p}")
        bad += 1
        continue
    f = tars[p]
    parts = [f"{p}.part{i:03d}" for i in range(int(f[3]))]
    if int(f[1]) < size or any(x not in sums for x in parts):  # the tar's bytes: the entries' and their headers
        print(f"pack {p}: {f[1]} bytes for {size} of entries, parts {[x in sums for x in parts]}")
        bad += 1
if bad:
    sys.exit(1)
os.makedirs(a.out, exist_ok=True)
open(os.path.join(a.out, "LAYOUT"), "w").write(f"packs\nmbps {a.mbps}\ndiff-jobs {a.diff_jobs}\n")
lay = hashlib.sha256(open(os.path.join(a.out, "LAYOUT"), "rb").read()).hexdigest()
with open(os.path.join(a.out, "SHA256SUMS"), "w") as f:
    for p in sorted(want):
        for i in range(int(tars[p][3])):
            n = f"{p}.part{i:03d}"
            f.write(f"{sums[n]}  {n}\n")
    f.write(f"{lay}  LAYOUT\n")
with open(os.path.join(a.out, "TARS.txt"), "w") as f:
    for p in sorted(want):
        f.write(" ".join(tars[p]) + "\n")
with open(os.path.join(a.layout, "INDEX.tsv"), "rb") as i, gzip.open(os.path.join(a.out, "INDEX.tsv.gz"), "wb") as o:
    shutil.copyfileobj(i, o)
print(f"packs {len(want)}, parts {sum(int(tars[p][3]) for p in want)}, bytes {sum(int(tars[p][1]) for p in want)}")
