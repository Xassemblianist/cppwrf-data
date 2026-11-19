#!/usr/bin/env python3
"""check.py EXPECTED.tsv INDEX.tsv SCANDIR: the scan of the packs release (the scan workflow on data-v2) against
layout.py's expected.tsv (the data as data-v1's tars unpack in vm_data.txt's order, from data-v1's own scan) and its
INDEX.tsv: every entry once, in its pack, with the same type, size, sha256, link target, mode and time. Prints the
differences and a summary; exit 1 if any."""
import os
import sys

exp, packs = {}, {}
for line in open(sys.argv[1]):
    n, ty, size, sha, link, mode, mtime = line.rstrip("\n").split("\t")
    exp[n] = (ty, int(size), sha, link, mode, mtime)
for line in open(sys.argv[2]):
    f = line.rstrip("\n").split("\t")
    packs[f[2]] = f[0]
got, bad, nbytes = {}, 0, 0
for fn in sorted(os.listdir(sys.argv[3])):
    if not fn.endswith(".tsv"):
        continue
    for line in open(os.path.join(sys.argv[3], fn)):
        f = line.rstrip("\n").split("\t")
        if f[0] == "#END":
            continue
        t, ty, n = f[0], f[1], f[2].rstrip("/")
        if n in got:
            print(f"TWICE {n}: {got[n]} and {t}")
            bad += 1
        got[n] = t
        if n not in exp:
            print(f"EXTRA {n} in {t}")
            bad += 1
            continue
        e = exp[n]
        x = (ty, int(f[3]), f[11], f[10], f[4], f[5])
        if x != e:
            print(f"DIFFERS {n} in {t}: {x} expected {e}")
            bad += 1
        if packs.get(n) != t:
            print(f"PACK {n}: in {t}, INDEX {packs.get(n)}")
            bad += 1
        nbytes += int(f[3])
for n in exp:
    if n not in got:
        print(f"MISSING {n}")
        bad += 1
print(f"SUMMARY entries {len(got)} of {len(exp)}, bytes {nbytes}, differences {bad}")
sys.exit(1 if bad else 0)
