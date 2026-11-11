#!/usr/bin/env python3
"""Merge the logs of a suite run's jobs into one result directory as tools/gcp/suite_body.sh leaves it, and add a FAIL
line for every expected case or files test that no job reported (a lost job is no silent SKIP).

  gate.py LOGS PLAN OUT

LOGS: one directory per job (the jobs' log artifacts, logs-<job>), PLAN: the plan directory (matrix.json,
expected.txt, mode.txt), OUT: gets suite.log (every job's case lines, the missing cases as FAIL, the SUITE line and
"exit N"), files.log, idealfiles.log, diff.log, ctest.log, unit.log, selftest.log, setup.out, jobs.txt (job, CPU,
wall time, data time) and times.txt (case seconds). tools/gcp/suite_status.sh OUT then gives the summary.
"""
import glob
import json
import os
import re
import sys

logs, plan, out = sys.argv[1:4]
os.makedirs(out, exist_ok=True)
jobs = json.load(open(os.path.join(plan, "matrix.json")))["include"]
expected = [x.strip() for x in open(os.path.join(plan, "expected.txt")) if x.strip()]
mode = open(os.path.join(plan, "mode.txt")).read().strip()


def read(p):
    return open(p, errors="replace").read() if os.path.exists(p) else ""


lines, setup, files, jobrows, times = [], [], [], [], []
other = {k: [] for k in ("idealfiles", "diff", "ctest", "unit", "selftest")}
for j in jobs:
    d = os.path.join(logs, f"logs-{j['name']}")
    s = read(os.path.join(d, "setup.out")).strip()
    if s:
        setup += [f"{j['name']}: {x}" for x in s.splitlines()]
    if not os.path.isdir(d):
        setup.append(f"{j['name']}: NO_LOGS (the job did not finish)")
    v = read(os.path.join(d, "versions.txt"))
    cpu = re.search(r"model name\s*:\s*(.*)", v)
    wall = read(os.path.join(d, "wall.txt")).split()
    dsec = sum(int(x.split()[3]) + int(x.split()[4]) for x in read(os.path.join(d, "data.txt")).splitlines()
               if x.startswith("TAR ") and len(x.split()) >= 5)
    jobrows.append(f"{j['name']:12s} {wall[1] if len(wall) > 1 else '-':>6s} s  data {dsec:5d} s  "
                   f"{cpu.group(1).strip() if cpu else '-'}")
    if j["kind"] == "suite":
        for x in read(os.path.join(d, "suite.log")).splitlines():
            if re.match(r"^(PASS|FAIL|SKIP|ERROR) ", x):
                lines.append(x)
                m = re.match(r"^PASS +(\S+) .*\((\d+) s\)$", x)
                if m:
                    times.append(f"{m.group(1)} {m.group(2)}")
    elif j["kind"] == "files":
        for c in j["cases"].split(","):
            t = read(os.path.join(d, f"files_{c}.log"))
            if not re.search(rf"^exit \d+ {re.escape(c)}$", t, re.M):
                t += f"FAIL {c} (no result: the job did not finish)\nexit 1 {c}\n"
            files.append(t)
    elif j["kind"] == "idealfiles":
        other["idealfiles"].append(read(os.path.join(d, "idealfiles.log")))
    elif j["kind"] == "diff":
        other["diff"].append(read(os.path.join(d, "diff.log")))
        other["ctest"].append(read(os.path.join(d, "ctest.log")))
    elif j["kind"] == "checks":
        other["unit"].append(read(os.path.join(d, "unit.log")))
        other["selftest"].append(read(os.path.join(d, "selftest.log")))

seen = {}
for x in lines:
    m = re.match(r"^(PASS|FAIL|SKIP) +(\S+)", x)
    if m:
        seen.setdefault(m.group(2), []).append(m.group(1))
for c in expected:
    if c not in seen:
        lines.append(f"FAIL  {c} (no result: missing from every job)")
count = {k: sum(1 for x in lines if x.startswith(k + " ")) for k in ("PASS", "FAIL", "SKIP")}
passed = {c for c, r in seen.items() if r == ["PASS"]}
ok = count["FAIL"] == 0 and count["SKIP"] == 0 and passed == set(expected) and len(lines) == len(expected)
with open(os.path.join(out, "suite.log"), "w") as f:
    f.write("".join(x + "\n" for x in lines))
    f.write(f"SUITE PASS {count['PASS']} FAIL {count['FAIL']} SKIP {count['SKIP']}\nexit {0 if ok else 1}\n")
if files:
    open(os.path.join(out, "files.log"), "w").write("".join(files))
for k, v in other.items():
    if v:
        open(os.path.join(out, f"{k}.log"), "w").write("".join(v))
open(os.path.join(out, "setup.out"), "w").write("".join(x + "\n" for x in setup))
open(os.path.join(out, "jobs.txt"), "w").write("".join(x + "\n" for x in jobrows))
open(os.path.join(out, "times.txt"), "w").write("".join(x + "\n" for x in sorted(times)))
open(os.path.join(out, "mode.txt"), "w").write(mode + "\n")
print("\n".join(jobrows))
