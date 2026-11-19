#!/usr/bin/env python3
"""diff_split.py K N TIMES < names: the differential tests (ctest -L diff names, one per line) of part K of N, the
tests packed longest first (TIMES: "name seconds"; unknown tests 60 s), each to the part that ends earliest; one name
per line, and "#ctest" for the part with the least time (it runs the other ctest tests too)."""
import sys

k, n = int(sys.argv[1]), int(sys.argv[2])
times = {}
for line in open(sys.argv[3]):
    f = line.split()
    if len(f) == 2 and not line.startswith("#"):
        times[f[0]] = float(f[1])
names = sorted({x.strip() for x in sys.stdin if x.strip()})
parts = [[0.0, i, []] for i in range(n)]
for t in sorted(names, key=lambda t: (-times.get(t, 60.0), t)):
    p = min(parts)
    p[0] += times.get(t, 60.0)
    p[2].append(t)
print("\n".join(parts[k - 1][2]))
if min(parts)[1] == k - 1:  # the lightest part also runs the other ctest tests
    print("#ctest")
print(f"diff part {k}/{n}: {len(parts[k - 1][2])} tests, {parts[k - 1][0]:.0f} s recorded", file=sys.stderr)
