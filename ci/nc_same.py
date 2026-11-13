#!/usr/bin/env python3
"""nc_same.py A B: compare two NetCDF files variable by variable (raw bytes of every variable's data, its dtype, shape
and attributes) and the global attributes and dimensions. Prints "DATA-SAME" (every variable bit-identical) followed by
the differing global attributes, if any ("ATTR name: a | b"), or "DATA-DIFF var ..." lines. Exit 0 when every
variable is bit-identical."""
import sys
import netCDF4 as nc
import numpy as np

a, b = (nc.Dataset(p) for p in sys.argv[1:3])
for d in (a, b):
    d.set_auto_maskandscale(False)
bad = []
if {k: len(v) for k, v in a.dimensions.items()} != {k: len(v) for k, v in b.dimensions.items()}:
    bad.append("DATA-DIFF dimensions")
va, vb = set(a.variables), set(b.variables)
for v in sorted(va ^ vb):
    bad.append(f"DATA-DIFF {v} only in one file")
for v in sorted(va & vb):
    x, y = a.variables[v], b.variables[v]
    if x.dtype != y.dtype or x.shape != y.shape:
        bad.append(f"DATA-DIFF {v} dtype/shape"); continue
    if {k: str(x.getncattr(k)) for k in x.ncattrs()} != {k: str(y.getncattr(k)) for k in y.ncattrs()}:
        bad.append(f"DATA-DIFF {v} attributes")
    if np.asarray(x[...]).tobytes() != np.asarray(y[...]).tobytes():
        bad.append(f"DATA-DIFF {v} values")
ga = {k: str(a.getncattr(k)) for k in a.ncattrs()}
gb = {k: str(b.getncattr(k)) for k in b.ncattrs()}
attrs = [f"ATTR {k}: {ga.get(k)} | {gb.get(k)}" for k in sorted(set(ga) | set(gb)) if ga.get(k) != gb.get(k)]
print("\n".join(bad) if bad else "DATA-SAME")
if attrs:
    print("\n".join(attrs))
fa, fb = a.data_model, b.data_model
if fa != fb:
    print(f"FORMAT {fa} | {fb}")
sys.exit(1 if bad else 0)
