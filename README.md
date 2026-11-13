# cppwrf-data

Reference data for the WRF comparison suite of [CPPWRF](https://github.com/Xassemblianist/CPPWRF): WRF v4.8.0
runs (inputs from public GFS 0.25 degree data through WPS and real.exe) and their outputs, published as release
assets, and the continuous integration that uses them on free GitHub-hosted runners.

## Data

Release `data-v1`: the tars of CPPWRF's `tests/verify/vm_data.txt` (unpacked in that file's order, a later tar
replacing an earlier one's files), each split into parts of 512 MiB (`NAME.tar.part000`, ...; `cat` the parts in
order into `tar x`). `SHA256SUMS` lists every part, `TARS.txt` every whole tar (`NAME bytes sha256 parts`),
`INDEX.tsv.gz` every member (`tar type name link-target`). The release notes give the provenance.
The tars were re-packed on the way (owner 0, links into the reference machine's home left out; `upload/`):
`diff_data.tar` is not published (its WRF build trees name that machine's paths): `diff_runs.tar` holds its WRF run
files, and the differential tests use the WRF builds of the `wrf-build` release; `NAME.tar.links` (small tars of
relative links) restore the links between reference directories that the re-pack left out and are unpacked after
all of a job's tars.

## Continuous integration

- `.github/workflows/suite.yml`: the CPU FP64 suite of one CPPWRF commit. `prep` takes the source (the public
  repository, or a git bundle of an unpushed commit from this repository's `jobs` release) and plans the jobs
  (`ci/plan.py`); `build` compiles the CPU FP64 binary once; the `work` matrix runs the suite cases (packed by their
  recorded times, `ci/times.txt`, each job downloading only its tars: `ci/fetch_data.sh`), the output files tests,
  the ideal files test, the differential and ctest tests, the translator tests and the comparators' self-test
  (`ci/job.sh`); `gate` merges the logs (`ci/gate.py`) and fails unless every job passed and every expected case
  PASSed. Every job runs in a Debian 13 container (gcc 14, gfortran 14, glibc 2.41, NetCDF 4.9) as the machines
  that made the references.
- `.github/workflows/wrfref.yml`: WRF v4.8.0 built as the references were (`ci/wrf_build.sh`: `configure` option
  32, serial gfortran / gcc, basic nesting, `-r8`, and `-r8` with `-fdefault-double-8`; each build is kept as an
  asset of the `wrf-build` release), WRF reference runs of variant namelists on given data (CPPWRF's
  `tools/gcp/wrf_ref_run.py`; the run directories come back as assets of the `wrfref` release) and re-runs of
  existing references compared byte for byte (`ci/wrf_rerun.sh`; a different file variable by variable,
  `ci/nc_same.py`). wrf.exe runs with CPPWRF's Intel vector log / log10 (`tests/phys/libmvec_intel.cpp`) preloaded:
  the references are Intel-made, and glibc's vector log differs on AMD CPUs.

Start a suite run with CPPWRF's `tools/ci/ci_submit.sh` (see its header and CPPWRF's docs/USER_GUIDE.md); pushes to
CPPWRF's main run the full suite through CPPWRF's `.github/workflows/wrf_suite.yml`, which calls `suite.yml`.
`probe/` holds the 2026-11-02 check of the runners (CPU, free disk, glibc's vector math functions).

The scripts are GPL-3.0-or-later as CPPWRF. WRF is developed by UCAR/NCAR and is in the public domain per its
LICENSE.txt; RRTM / RRTMG data files are AER's, distributed with WRF under AER's notice.
