#!/usr/bin/env python3
"""groups.py SHA256SUMS N [NAME ...]: the tars (and TAR.links) of a data release in at most N groups balanced by
size, as a GitHub matrix ({"include": [{"g": i, "tars": "A,B"}]}) on stdout. Sizes: the number of parts (512 MiB
each). NAME ...: only these tars."""
import json
import re
import sys
from collections import Counter

sums, n = sys.argv[1], int(sys.argv[2])
only = set(sys.argv[3:])
parts = Counter()
for line in open(sums):
    f = line.split()
    if len(f) == 2:
        parts[re.sub(r"\.part\d+$", "", f[1])] += 1
names = [t for t in parts if t.endswith((".tar", ".links")) and (not only or t in only)]
g = [[0, i, []] for i in range(min(n, len(names)))]
for t in sorted(names, key=lambda t: -parts[t]):
    x = min(g)
    x[0] += parts[t]
    x[2].append(t)
print(json.dumps({"include": [{"g": i, "tars": ",".join(ts)} for _, i, ts in sorted(g, key=lambda x: x[1]) if ts]}))
