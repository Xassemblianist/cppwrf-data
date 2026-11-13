#!/usr/bin/env python3
"""INDEX.tsv.gz of the data release: "tar<TAB>type<TAB>name<TAB>link" for every member of the uploaded tars
(sums/tars.txt), from the scan's member lists (scan/X.tar.names, tab-separated) or, for the tars scanned before the
lists had link targets, the `tar tv` lists of f13/tarlist. Links into /home are left out (the upload dropped them)."""
import gzip
import os
import sys

D = os.path.expanduser("~/cppwrf_scratch/ci3")
F13 = os.path.expanduser("~/cppwrf_scratch/f13/tarlist")
TY = {"-": "0", "l": "2", "h": "1", "d": "5"}
up = [l.split()[0] for l in open(os.path.join(D, "sums/tars.txt")) if l.strip()]
out = gzip.open(sys.argv[1], "wt")
for t in up:
    p = os.path.join(D, "scan", t + ".names")
    rows = []
    if os.path.exists(p) and "\t" in open(p).readline():
        for line in open(p):
            f = line.rstrip("\n").split("\t")
            if len(f) == 4:
                rows.append((f[0], f[2], f[3]))
    elif os.path.exists(os.path.join(F13, t + ".txt")):
        for line in open(os.path.join(F13, t + ".txt")):
            f = line.rstrip("\n").split(None, 5)
            if len(f) < 6 or f[0][0] not in TY:
                continue
            name, link = f[5], ""
            if f[0][0] in "lh":
                name, _, link = f[5].partition(" -> " if f[0][0] == "l" else " link to ")
            rows.append((TY[f[0][0]], name, link))
    else:
        sys.exit(f"no member list for {t}")
    for ty, name, link in rows:
        if ty in ("1", "2") and "/home/" in link:
            continue
        out.write(f"{t}\t{ty}\t{name}\t{link}\n")
out.close()
