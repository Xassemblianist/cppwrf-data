#!/usr/bin/env bash
# Print the release asset and its build recipe. Keep existing serial cache keys.
set -euo pipefail
cd "$(dirname "$0")"
case $1 in
  r8|r8d8) recipe=wrf_build.sh; key=$(sha256sum "$recipe") ;;
  r4) recipe=wrf_build_r4.sh; key=$(cat wrf_build.sh "$recipe" | sha256sum) ;;
  r8dm|r8dmmove|r4dmmove) recipe=wrf_build_dm.sh; key=$(cat wrf_build.sh "$recipe" | sha256sum) ;;
  *) echo "unknown WRF flavor: $1" >&2; exit 2 ;;
esac
printf 'wrf-4.8.0-%s-%s.tar.zst %s\n' "$1" "${key:0:12}" "$recipe"
