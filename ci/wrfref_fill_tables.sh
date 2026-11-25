#!/usr/bin/env bash
# Restore WRF stock runtime tables omitted from suite data. Keep files supplied by the case.
set -euo pipefail
tables=$1
shift
for base in "$@"; do
  test -f "$base/namelist.input"
  for table in "$tables"/*; do
    name=${table##*/}
    case $name in namelist.*|*.exe|wrfinput*|wrfbdy*|wrfout*|wrfrst*) continue ;; esac
    if [ -f "$table" ] && [ ! -e "$base/$name" ]; then ln -sfn "$table" "$base/$name"; fi
  done
done
