#!/usr/bin/env python3
"""The job matrix of a CPPWRF suite run on GitHub-hosted runners.

  plan.py SRC OUTDIR [--cases A,B] [--full] [--data T1,T2] [--slow] [--suite-jobs N] [--files-jobs N]
          [--index INDEX.tsv] [--tars TARS.txt] [--times times.txt]

SRC: the CPPWRF source under test (its tests/verify/wrf_suite.py, cases and vm_data.txt decide the cases and the
data). Writes OUTDIR/matrix.json ({"include": [...]}: one entry per job: name, kind = suite | files | idealfiles |
diff | checks, cases, tars) and OUTDIR/expected.txt (the suite cases that must PASS). Without --cases: the full suite
(every CPU FP64 case but the slow ones, the files tests, the ideal files test, the differential and ctest tests, the
translator tests and the comparators' self-test). --cases: only these suite cases (exact names; with --full also the
other jobs). Suite cases are packed into --suite-jobs jobs by their recorded time (times.txt; unknown cases 150 s)
plus the download time of the tars a job needs (TARS.txt sizes at 60 MB/s), each case going to the job that ends
earliest with it. The tars of a job come from wrf_suite.py's DATA (suite cases) or, for the files tests and the
translator tests, from the run directories they read and the data index (INDEX.tsv: tar, type, name, link target),
following links; without the index every tar of vm_data.txt.
"""
import argparse
import json
import os
import re
import sys
from collections import defaultdict

ap = argparse.ArgumentParser()
ap.add_argument("src")
ap.add_argument("outdir")
ap.add_argument("--cases", default="")
ap.add_argument("--full", action="store_true")
ap.add_argument("--data", default="")
ap.add_argument("--slow", action="store_true")
ap.add_argument("--suite-jobs", type=int, default=13)
ap.add_argument("--files-jobs", type=int, default=2)
ap.add_argument("--index")
ap.add_argument("--tars")
ap.add_argument("--times")
a = ap.parse_args()

V = os.path.join(a.src, "tests", "verify")
sys.path.insert(0, V)
import wrf_suite as w  # noqa: E402

vm = [x.strip() for x in open(os.path.join(V, "vm_data.txt")) if x.strip() and not x.startswith("#")]
order = {t: i for i, t in enumerate(vm)}


def ordered(tars):
    return sorted(set(tars), key=lambda t: (order.get(t, 10 ** 6), t))


size = defaultdict(lambda: 1 << 30)
if a.tars and os.path.exists(a.tars):
    for line in open(a.tars):
        f = line.split()
        if len(f) >= 2:
            size[f[0]] = int(f[1])
times = {}
if a.times and os.path.exists(a.times):
    for line in open(a.times):
        f = line.split()
        if len(f) >= 2:
            times[f[0]] = float(f[1])

allcases = [c[0] for c in w.CASES if c[1] == "cpu_dp" and (a.slow or not w.slow(c[3]))]
allcases += ["straka_wrf"] + [f"restart_{t}_fp64" for t, _, _ in w.RESTARTS]
if a.cases:
    cases = [c for c in a.cases.split(",") if c]
    bad = [c for c in cases if c not in [x[0] for x in w.CASES] + w.SPECIAL]
    if bad:
        sys.exit(f"plan: no case named {', '.join(bad)}")
else:
    cases = allcases
full = a.full or not a.cases
forced = ordered(a.data.split(",")) if a.data else None


def data_of(names):
    if forced is not None:
        return forced
    out = []
    for n in names:
        d = w.DATA.get(n, "")
        if not d:
            sys.exit(f"plan: no data tar recorded for {n}")
        out += [t for t in d.split(",") if t]
    return ordered(out)


# the data index: which tars hold the files under a run directory (links followed)
index = defaultdict(list)  # top directory (wrf_runs/run_X) -> [(tar, name, type, link)]
if a.index and os.path.exists(a.index):
    for line in open(a.index):
        f = line.rstrip("\n").split("\t")
        if len(f) < 4:
            continue
        tar, typ, name, link = f[0], f[1], f[2].rstrip("/"), f[3]
        parts = name.split("/")
        top = "/".join(parts[:2]) if len(parts) >= 2 else name
        index[top].append((tar, name, typ, link))


def tars_for_dirs(dirs):
    """The tars holding these top directories (wrf_runs/run_X, wrf_ref/run_Y), following relative links into other
    top directories."""
    if not index:
        return ordered([t for t in vm if "diff" not in t])
    seen, todo, out = set(), list(dirs), set()
    while todo:
        d = todo.pop()
        if d in seen:
            continue
        seen.add(d)
        for tar, name, typ, link in index.get(d, []):
            out.add(tar)
            if typ == "2" and link and not link.startswith("/"):
                tgt = os.path.normpath(os.path.join(os.path.dirname(name), link)).split("/")
                if len(tgt) >= 2:
                    todo.append("/".join(tgt[:2]))
    return ordered(out)


jobs = []
# suite jobs: longest first, each to the job that ends earliest with it (compute + new data at 60 MB/s)
K = max(1, min(a.suite_jobs, len(cases)))
groups = [{"cases": [], "t": 0.0, "tars": set()} for _ in range(K)]
for c in sorted(cases, key=lambda c: -times.get(c, 150.0)):
    tc = times.get(c, 150.0)
    need = set(data_of([c]))

    def cost(g):
        new = sum(size[t] for t in need - g["tars"]) / 60e6
        return g["t"] + tc + new
    g = min(groups, key=cost)
    g["t"] = cost(g)
    g["cases"].append(c)
    g["tars"] |= need
groups = [g for g in groups if g["cases"]]
groups.sort(key=lambda g: -g["t"])
for i, g in enumerate(groups):
    jobs.append({"name": f"suite-{i + 1:02d}", "kind": "suite", "cases": ",".join(g["cases"]),
                 "tars": ",".join(ordered(g["tars"])), "est": int(g["t"])})

if full:
    # the output files tests (run_wrf_files_test.sh's CASES: run, restart and resumed directories)
    txt = open(os.path.join(V, "run_wrf_files_test.sh")).read()
    block = re.search(r'^CASES="\n(.*?)^"', txt, re.S | re.M).group(1)
    fcases = []
    for line in block.splitlines():
        f = line.split("|")
        if len(f) < 4:
            continue
        dirs = set()
        for x in f[2:4]:
            m = re.match(r"\$R/([^/]+)", x)
            if m:
                dirs.add(f"wrf_runs/{m.group(1)}")
                base = re.sub(r"^(run|rst|rsm)_", "", m.group(1))
                dirs |= {f"wrf_runs/rst_{base}", f"wrf_runs/rsm_{base}"}
        for m in re.finditer(r"\$R/([^/ ]+)", f[4] if len(f) > 4 else ""):
            dirs.add(f"wrf_runs/{m.group(1)}")
        cfg = os.path.join(a.src, f[1])  # the configuration's own directories (real.dir, phys.table_dir)
        if os.path.exists(cfg):
            for m in re.finditer(r"\$\{CPPWRF_WRF_RUNS\}/([^/\s]+)", open(cfg).read()):
                dirs.add(f"wrf_runs/{m.group(1)}")
        fcases.append((f[0], dirs))
    F = max(1, min(a.files_jobs, len(fcases)))
    fg = [{"cases": [], "dirs": set()} for _ in range(F)]
    for i, (n, d) in enumerate(fcases):
        fg[i % F]["cases"].append(n)
        fg[i % F]["dirs"] |= d
    for i, g in enumerate(fg):
        jobs.append({"name": f"files-{i + 1}", "kind": "files", "cases": ",".join(g["cases"]),
                     "tars": ",".join(forced or tars_for_dirs(g["dirs"]))})
    ideal = [c[0] for c in w.CASES if c[0].startswith("ideal_") and c[1] == "cpu_dp"]
    jobs.append({"name": "idealfiles", "kind": "idealfiles", "cases": "", "tars": ",".join(data_of(ideal))})
    jobs.append({"name": "diff", "kind": "diff", "cases": "", "tars": ",".join(forced or [t for t in vm if "diff" in t])})
# always (suite_body.sh runs them with every suite): the translator tests read the namelists of these run directories; the comparators' self-test needs no data
tt = open(os.path.join(a.src, "tests", "tools", "test_wrf2cppwrf.py")).read()
dirs = {f"wrf_runs/{m}" for m in re.findall(r'wrf_runs_path\(\s*"([^"/]+)/', tt)}
dirs |= {f"wrf_runs/{m}" for m in re.findall(r'_compare_configs\(\s*"([^"/]+)/', tt)}
dirs |= {f"wrf_ref/{m}" for m in re.findall(r'wrf_ref_path\(\s*"([^"/]+)/', tt)}
jobs.append({"name": "checks", "kind": "checks", "cases": "", "tars": ",".join(forced or tars_for_dirs(dirs))})

os.makedirs(a.outdir, exist_ok=True)
json.dump({"include": jobs}, open(os.path.join(a.outdir, "matrix.json"), "w"))
open(os.path.join(a.outdir, "expected.txt"), "w").write("".join(c + "\n" for c in cases))
open(os.path.join(a.outdir, "mode.txt"), "w").write("full\n" if not a.cases else ("cases+full\n" if a.full else "cases\n"))
for j in jobs:
    print(f"{j['name']:12s} {j.get('est', 0) / 60:6.1f} min  {len(j['cases'].split(',')) if j['cases'] else 0:3d} cases"
          f"  {sum(size[t] for t in j['tars'].split(',') if t) / 2 ** 30:6.1f} GiB  {j['tars']}", file=sys.stderr)
