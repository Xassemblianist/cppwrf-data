#!/usr/bin/env python3
"""Prove one-rank dmpar reproduces one serial N3 run before making moving references.

wrfref_repro.py RUNS BUILD... (default r8dm r8dmmove): run_serial and run_BUILD hold the N3 run without moves; r8dm
must equal the serial run in every variable, a moving build (MOVE_NESTS) in every variable but NEST_POS, which must
differ."""
import sys
from pathlib import Path

import netCDF4 as nc


def outputs(root, build):
    return {p.name: p for p in (root / f"run_{build}").glob("wrfout_d0[12]_*")}


def different(a, b):
    if (a.dtype, a.dimensions, a.shape) != (b.dtype, b.dimensions, b.shape):
        return True
    if a.dimensions[:1] == ("Time",):
        return any(a[i].tobytes() != b[i].tobytes() for i in range(a.shape[0]))
    return a[...].tobytes() != b[...].tobytes()


def check(root, builds):
    serial = outputs(root, "serial")
    counts = {"d01": 0, "d02": 0}
    for name, path in serial.items():
        with nc.Dataset(path) as ds:
            counts[name[7:10]] += len(ds["Times"])
    if counts != {"d01": 11, "d02": 11}:
        raise ValueError(f"serial N3 frames {counts}; expected 11 in each domain")
    for build in builds:
        other = outputs(root, build)
        if serial.keys() != other.keys():
            raise ValueError(f"{build}: history files differ: {sorted(serial.keys() ^ other.keys())}")
        for name in sorted(serial):
            expected = {"NEST_POS"} if build != "r8dm" else set()
            with nc.Dataset(serial[name]) as a, nc.Dataset(other[name]) as b:
                a.set_auto_maskandscale(False)
                b.set_auto_maskandscale(False)
                if a.variables.keys() != b.variables.keys():
                    raise ValueError(f"{build} {name}: history variable sets differ")
                if {k: len(v) for k, v in a.dimensions.items()} != {k: len(v) for k, v in b.dimensions.items()}:
                    raise ValueError(f"{build} {name}: history dimensions differ")
                differences = {v for v in a.variables if different(a[v], b[v])}
                print(f"{build} {name}: {len(a['Times'])} frames; differences {sorted(differences)}", flush=True)
                if differences != expected:
                    raise ValueError(f"{build} {name}: expected differences {sorted(expected)}")


if __name__ == "__main__":
    try:
        check(Path(sys.argv[1]), sys.argv[2:] or ["r8dm", "r8dmmove"])
    except (OSError, KeyError, ValueError) as exc:
        sys.exit(f"REPRO FAILED: {exc}")
    print("REPRO OK")
