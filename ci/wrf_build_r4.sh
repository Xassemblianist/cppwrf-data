#!/usr/bin/env bash
# wrf_build_r4.sh r4 DEST: WRF v4.8.0's default real*4 build (FLAVOR r4), as CPPWRF's FP32 references were made (the
# `WRF-4.8.0` sp build of docs/team/AGENTW_WRF480.md: `configure` option 32, serial gfortran / gcc, basic nesting 1,
# no -r8: PROMOTION empty, RWORDSIZE 4). The steps are wrf_build.sh's, run from a copy of it with `./configure -r8`
# replaced by `./configure`; a script of its own, so that the r8 / r8d8 build keys (wrf_build.sh's hash) stay valid
# (the r4 key hashes both scripts, .github/workflows/wrfref.yml).
set -euo pipefail
FLAVOR=$1 DEST=$2
[ "$FLAVOR" = r4 ] || { echo "wrf_build_r4.sh: flavor r4 only"; exit 1; }
S=$(mktemp)
sed 's#| ./configure -r8 >#| ./configure >#' "$(dirname "$0")/wrf_build.sh" > "$S"
grep -q "^printf '32\\\\n1\\\\n' | ./configure > configure.out" "$S" || { echo "wrf_build_r4.sh: no configure line"; exit 1; }
bash "$S" r4 "$DEST"
