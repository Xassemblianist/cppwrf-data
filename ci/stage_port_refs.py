#!/usr/bin/env python3
"""Turn portable wrfref assets into local data-v1 parts and updated release metadata."""
import argparse
import gzip
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

PORT_TARS = {
    "b04": ("port_b04_data.tar", "port_b04_files.tar"),
    "b13": ("port_b13_data.tar",),
    "b11": ("movenest_data.tar",),
}
PART_BYTES = 512 * 1024 * 1024


def inputs(folder, prefix):
    parts = sorted(folder.glob(f"{prefix}-refs.tar.part*"))
    expected = [f"{prefix}-refs.tar.part{i:03d}" for i in range(len(parts))]
    if not parts or [p.name for p in parts] != expected:
        raise ValueError(f"{prefix}: missing or noncontiguous reference parts")
    manifest = folder / f"{prefix}-refs_md5.txt"
    return parts, manifest


def unpack(parts, manifest, runs):
    with subprocess.Popen(["cat", *parts], stdout=subprocess.PIPE) as cat:
        with tarfile.open(fileobj=cat.stdout, mode="r|") as archive:
            # Track top-level names before extraction so two assets cannot replace one another's references.
            before = {p.name for p in runs.iterdir()}
            for member in archive:
                if Path(member.name).parts[0] in before:
                    raise ValueError(f"{manifest.name}: duplicate directory {member.name}")
                archive.extract(member, runs, filter="data")
        # tarfile stops at the archive's end marker. Consume tar's padding before waiting for cat.
        for padding in iter(lambda: cat.stdout.read(1024 * 1024), b""):
            if padding.strip(b"\0"):
                raise ValueError(f"{manifest.name}: extra data after tar")
        if cat.wait():
            raise ValueError(f"{manifest.name}: could not read parts")
    count = 0
    for line in manifest.read_text().splitlines():
        kind, name, md5 = line.split()
        p = (runs / name).resolve()
        if kind != "MD5" or not p.is_relative_to(runs) or not p.is_file():
            raise ValueError(f"{manifest.name}: invalid reference member {name}")
        with p.open("rb") as f:
            actual = hashlib.file_digest(f, "md5").hexdigest()
        if actual != md5:
            raise ValueError(f"{manifest.name}: MD5 mismatch for {name}")
        count += 1
    if not count:
        raise ValueError(f"{manifest.name}: empty reference manifest")


def pack(packer, filename, tmp, args, env):
    # Normalize ownership and index the exact members that go into data-v1.
    index = {}
    with subprocess.Popen([sys.executable, *packer, "-"], cwd=args.src, env=env, stdout=subprocess.PIPE) as src:
        split = subprocess.Popen(["split", "-b", str(PART_BYTES), "-d", "-a", "3", "-", tmp / (filename + ".part")],
                                 stdin=subprocess.PIPE)
        try:
            with tarfile.open(fileobj=src.stdout, mode="r|") as original, \
                 tarfile.open(fileobj=split.stdin, mode="w|", format=tarfile.GNU_FORMAT) as archive:
                for member in original:
                    member.uid = member.gid = 0
                    member.uname = member.gname = ""
                    archive.addfile(member, original.extractfile(member) if member.isfile() else None)
                    index[member.name] = (member.type.decode(), member.linkname)
            src.stdout.read()
        finally:
            split.stdin.close()
            split_rc = split.wait()
            src.stdout.close()
        if src.wait() or split_rc or not index:
            raise ValueError(f"failed to pack {filename}")

    parts = sorted(tmp.glob(filename + ".part*"))
    total = hashlib.sha256()
    size = 0
    sums = []
    for part in parts:
        piece = hashlib.sha256()
        with part.open("rb") as f:
            for data in iter(lambda: f.read(4 * 1024 * 1024), b""):
                piece.update(data)
                total.update(data)
                size += len(data)
        sums.append(f"{piece.hexdigest()}  {part.name}\n")
    return sums, f"{filename} {size} {total.hexdigest()} {len(parts)}\n", index


def check_files_test(runs):
    case = runs / "run_OB1_r8" / "steps"
    rst, rsm = runs / "rst_OB1_r8", runs / "rsm_OB1_r8"
    for directory, pattern in ((case, "OBS_DOMAIN101"), (case, "wrfout_d01_*"),
                               (rst, "wrfrst_d01_*_00:01:00"), (rsm, "wrfout_d01_*")):
        if not any(p.is_file() for p in directory.glob(pattern)):
            raise ValueError(f"ob1: missing {directory}/{pattern}")


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--port", choices=PORT_TARS, required=True)
    cli.add_argument("--src", type=Path, required=True, help="pinned CPPWRF port checkout or archive")
    cli.add_argument("--assets", type=Path, required=True, help="downloaded portable wrfref assets")
    cli.add_argument("--prefixes", required=True, help="comma-separated wrfref release asset prefixes")
    cli.add_argument("--metadata", type=Path, required=True, help="current data-v1 SHA256SUMS, TARS.txt and INDEX.tsv.gz")
    cli.add_argument("--out", type=Path, required=True, help="output directory for new parts and merged metadata")
    cli.add_argument("--dry-run", action="store_true", help="validate inputs and print the packing plan without writing")
    args = cli.parse_args()
    args.src = args.src.resolve()
    names = PORT_TARS[args.port]
    prefixes = args.prefixes.split(",")
    if len(prefixes) != len(set(prefixes)) or not all(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", p) for p in prefixes):
        cli.error("prefixes must be unique wrfref tags")
    checks = [inputs(args.assets, p) for p in prefixes]
    sums = (args.metadata / "SHA256SUMS").read_text().splitlines(keepends=True)
    tars = (args.metadata / "TARS.txt").read_text().splitlines(keepends=True)
    index = gzip.decompress((args.metadata / "INDEX.tsv.gz").read_bytes()).decode().splitlines(keepends=True)
    if any(row.split()[-1:] == ["LAYOUT"] for row in sums):
        cli.error("--metadata must be from a data-v1-style release")
    for name in names:
        registered = any(row.split()[:1] == [name] for row in tars)
        registered |= any(row.split()[-1].startswith(name + ".part") for row in sums if row.strip())
        if registered or any(args.out.glob(name + ".part*")):
            cli.error(f"{name} is already staged; use fresh output and baseline metadata")
    for parts, manifest in checks:
        if not manifest.is_file():
            cli.error(f"missing {manifest}")
        print(f"{manifest.name}: {len(parts)} parts")

    os.environ["CPPWRF_WRF_RUNS"] = str(args.out.resolve() / "wrf_runs")
    os.environ["CPPWRF_WRF_REF"] = str(args.out.resolve() / "wrf_ref")
    sys.path.insert(0, str(args.src / "tests/verify"))
    from case_data import derive, wrf_suite

    cases = sorted(name for name, data in wrf_suite.DATA.items() if data == names[0])
    if not cases:
        cli.error(f"{args.src}: no suite cases for {names[0]}")
    print(f"{names[0]}: {','.join(cases)}")
    if args.port == "b04":
        print(f"{names[1]}: files ob1")
    if args.dry_run:
        return

    args.out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".stage-port-refs-", dir=args.out) as temp:
        tmp = Path(temp).resolve()
        runs = tmp / "wrf_runs"
        runs.mkdir()
        for parts, manifest in checks:
            unpack(parts, manifest, runs)
        if args.port == "b04":
            check_files_test(runs)
        env = dict(os.environ, CPPWRF_WRF_RUNS=str(runs))
        packers = [["tools/colab/stage_data.py", "--whole", "--only", ",".join(cases)]]
        if args.port == "b04":
            packers.append(["tools/gcp/stage_files_data.py", "--cases", "ob1"])
        for name, packer in zip(names, packers):
            new_sums, whole, members = pack(packer, name, tmp, args, env)
            if name == names[0]:
                listing = {p: (0, "") for p in members}
                for case in cases:
                    _, problems = derive(case, {name: listing}, [name])
                    if problems:
                        raise ValueError(f"{case}: {'; '.join(problems)}")
            sums.extend(new_sums)
            tars.append(whole)
            index.extend(f"{name}\t{kind}\t{p}\t{link}\n" for p, (kind, link) in sorted(members.items()))
            print(whole.strip())

        (tmp / "SHA256SUMS").write_text("".join(sums))
        (tmp / "TARS.txt").write_text("".join(tars))
        (tmp / "INDEX.tsv.gz").write_bytes(gzip.compress("".join(index).encode(), mtime=0))
        for part in sorted(tmp.glob("*.part*")):
            shutil.move(part, args.out / part.name)
        for name in ("INDEX.tsv.gz", "TARS.txt", "SHA256SUMS"):
            (tmp / name).replace(args.out / name)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, tarfile.TarError) as exc:
        sys.exit(str(exc))
