#!/usr/bin/env bash
# Apply the dmpar configuration to the serial recipe without changing the existing serial cache keys.
set -euo pipefail
flavor=$1 dest=$2
case $flavor in
  r8dm) nesting=1; promotion=-r8; word=8 ;;
  r8dmmove) nesting=2; promotion=-r8; word=8 ;;
  r4dmmove) nesting=2; promotion=; word=4 ;;
  r8dmvortex) nesting=3; promotion=-r8; word=8 ;;
  r4dmvortex) nesting=3; promotion=; word=4 ;;
  *) echo "unknown dmpar flavor: $flavor" >&2; exit 2 ;;
esac
recipe=$(mktemp)
trap 'rm -f "$recipe"' EXIT
sed -e 's/libnetcdff-dev /libnetcdff-dev mpich libmpich-dev /' \
    -e "s/^printf .* | \.\/configure -r8 >/printf '%s\\\\n%s\\\\n' 34 $nesting | .\/configure $promotion >/" \
    "$(dirname "$0")/wrf_build.sh" > "$recipe"
grep -Fq "34 $nesting | ./configure $promotion >" "$recipe"
grep -Fq 'mpich libmpich-dev' "$recipe"
bash "$recipe" "$flavor" "$dest"
config=$dest/configure.wrf
grep -q -- '-DDM_PARALLEL' "$config"
if grep -q -- '-DSTUBMPI' "$config"; then exit 1; fi
grep -Eq "^RWORDSIZE[[:space:]]*=[[:space:]]*$word([[:space:]]|$)" "$config"
# nesting 2 (preset moves): -DMOVE_NESTS; 3 (vortex following): -DMOVE_NESTS -DVORTEX_CENTER
if [ "$nesting" -ge 2 ]; then
  grep -q -- '-DMOVE_NESTS' "$config"
elif grep -q -- '-DMOVE_NESTS' "$config"; then
  exit 1
fi
if [ "$nesting" = 3 ]; then
  grep -q -- '-DVORTEX_CENTER' "$config"
elif grep -q -- '-DVORTEX_CENTER' "$config"; then
  exit 1
fi
