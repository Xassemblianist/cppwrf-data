#!/usr/bin/env python3
"""Validate, normalize and select reference lines for wrfref.yml."""
import argparse
import json
import re
import sys
from pathlib import Path

FLAVORS = ("r8", "r8d8", "r4", "r8dm", "r8dmmove", "r4dmmove")
ALIASES = {f"wrf_{fl}.exe": fl for fl in FLAVORS}
ALIASES.update({"wrf_r8_basic.exe": "r8dm", "wrf_r8_move.exe": "r8dmmove", "wrf_r4_move.exe": "r4dmmove"})
MOVING = {"r8dmmove", "r4dmmove"}


def rows(text):
    seen = set()
    source = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    for line in source.replace(";", "\n").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        if len(fields) < 3:
            raise ValueError(f"expected NAME BASE FLAVOR: {line}")
        name, base, flavor, *sets = fields
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name) or name in seen:
            raise ValueError(f"invalid or duplicate reference name: {name}")
        if base.startswith("../wrf_runs/"):
            base = base[3:]
        if not re.fullmatch(r"[A-Za-z0-9_./-]+", base) or ".." in Path(base).parts:
            raise ValueError(f"{name}: invalid base directory {base}")
        flavor = ALIASES.get(flavor, flavor)
        if flavor not in FLAVORS:
            raise ValueError(f"{name}: unknown WRF flavor {flavor}")
        for setting in sets:
            if not re.fullmatch(r"[A-Za-z0-9_]+\.[A-Za-z0-9_]+=\S+", setting):
                raise ValueError(f"{name}: invalid setting {setting}")
        seen.add(name)
        yield name, base, flavor, *sets


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("refs", type=Path, help="reference lines file (use - for stdin)")
    cli.add_argument("--select", help="comma-separated subset of names")
    cli.add_argument("--flavors", help="space-separated requested builds")
    cli.add_argument("--restart-refs", default="", help="comma-separated names, none, or empty for all with steps")
    cli.add_argument("--plan", type=Path, help="write restart names and Actions job outputs here")
    args = cli.parse_args()
    refs = list(rows(sys.stdin.read() if args.refs == Path("-") else args.refs.read_text()))
    if args.select:
        selected = set(args.select.split(","))
        if selected - {r[0] for r in refs}:
            cli.error(f"unknown --select names: {sorted(selected - {r[0] for r in refs})}")
        refs = [r for r in refs if r[0] in selected]
    flavors = list(dict.fromkeys(args.flavors.split())) if args.flavors is not None else None
    if flavors is not None and (not flavors or set(flavors) - set(FLAVORS)):
        cli.error(f"invalid flavors: {args.flavors}")
    if flavors is not None and {r[2] for r in refs} - set(flavors):
        cli.error("reference flavor missing from --flavors")
    moving = bool(set(flavors or ()) & MOVING)
    if moving and not {"r8dm", "r8dmmove"}.issubset(flavors):
        cli.error("moving builds require r8dm and r8dmmove for the N3 reproduction check")
    restartable = [r[0] for r in refs if "run.steps=0" not in r[3:] and not r[2].endswith("dm")
                   and r[2] not in MOVING]
    restarts = {"": restartable, "none": []}.get(args.restart_refs, args.restart_refs.split(","))
    if set(restarts) - set(restartable) or len(restarts) != len(set(restarts)):
        cli.error(f"invalid --restart-refs names: {args.restart_refs}")
    if args.plan:
        args.plan.mkdir(exist_ok=True)
        (args.plan / "restarts.txt").write_text("".join(f"{n}\n" for n in restarts))
        (args.plan / "outputs").write_text(
            f"flavors={json.dumps(flavors)}\nmoving={str(moving).lower()}\n")
    for ref in refs:
        print(" ".join(ref))


if __name__ == "__main__":
    try:
        main()
    except ValueError as exc:
        sys.exit(str(exc))
