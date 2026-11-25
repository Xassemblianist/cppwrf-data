#!/usr/bin/env bash
# Prepare an Actions workspace and launch the WRF reference or N3 reproduction job.
set -euo pipefail
mode=$1
mkdir -p wrf out
printf '%s\n' "${PREP:-}" > prep.sh
printf '%s\n' "${RERUN:-}" > rerun.txt
printf '%s\n' "${REFS:-}" | python3 ci/ci/wrfref_refs.py - --flavors "$FLS" \
  --restart-refs "${RESTART_REFS:-}" --plan . > refs.txt
git clone -q https://github.com/Xassemblianist/CPPWRF src
if [ -n "$BUNDLE" ]; then
  gh release download jobs -R "$CI_REPO" -p "$BUNDLE" -O job.bundle
  git -C src bundle verify ../job.bundle
  git -C src fetch -q ../job.bundle refs/heads/ci:refs/heads/ci-under-test
  test "$SRC" = "$(git -C src rev-parse refs/heads/ci-under-test)"
fi
git -C src checkout -q --detach "$SRC"
git -C src log -1 --format='%H %s' | tee out/source.txt

builds=$FLS
# the reproduction job: r8dm and the -r8 build of each moving kind requested (wrfref_refs.py's plan)
if [ "$mode" = repro ]; then builds="r8dm $(sed -n 's/^repro=//p' outputs)"; fi
for fl in $builds; do
  asset=$(bash ci/ci/wrf_build_asset.sh "$fl")
  gh release download wrf-build -R "$CI_REPO" -p "${asset%% *}" -O - | zstd -dq | tar xf - -C wrf
done
# Keep runner logs readable even after a failed container command.
trap 'sudo chown -R "$(id -u):$(id -g)" out fetch 2>/dev/null || true' EXIT
docker run --rm -v "$GITHUB_WORKSPACE:/w" -e DATA -e DATA_TAG -e DATA_REPO -e PORTABLE -e RESUMED_RESTART_INTERVAL \
  -e "BUILDS=$builds" debian:13 bash /w/ci/ci/wrfref_run.sh "$mode"
