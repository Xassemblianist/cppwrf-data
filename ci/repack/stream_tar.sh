#!/usr/bin/env bash
# stream_tar.sh TAR: a whole data tar of the release $TAG (default data-v1) of $DATA_REPO on stdout, from its parts
# (TAR.partNNN, or the single asset TAR, as SHA256SUMS lists them), each part checked against SHA256SUMS before it is
# written; up to 4 parts download ahead. $P: scratch directory for the parts (default parts).
set -uo pipefail
T=$1 P=${P:-parts}
URL=https://github.com/${DATA_REPO:-Xassemblianist/cppwrf-data}/releases/download/${TAG:-data-v1}
mkdir -p "$P"
get() {
  local i
  for i in 1 2 3 4 5; do
    curl -fsSL --retry 3 --connect-timeout 30 -o "$P/$1.tmp" "$URL/$1" && mv "$P/$1.tmp" "$P/$1" && return 0
    sleep $((10 * i))
  done
  return 1
}
[ -s "$P/SHA256SUMS" ] || get SHA256SUMS || { echo "stream_tar: no SHA256SUMS" >&2; exit 1; }
mapfile -t parts < <(awk '{print $2}' "$P/SHA256SUMS" | grep -E "^${T//./\\.}(\.part[0-9]+)?$" | sort)
n=${#parts[@]}
[ "$n" -gt 0 ] || { echo "stream_tar: $T not in SHA256SUMS" >&2; exit 1; }
declare -a pid
for ((i = 0; i < n && i < 4; i++)); do get "${parts[$i]}" & pid[$i]=$!; done
for ((i = 0; i < n; i++)); do
  wait "${pid[$i]}" || { echo "stream_tar: download of ${parts[$i]} failed" >&2; exit 1; }
  (cd "$P" && grep -E "  ${parts[$i]//./\\.}$" SHA256SUMS | sha256sum -c --quiet -) >&2 ||
    { echo "stream_tar: ${parts[$i]} sha256 differs" >&2; exit 1; }
  if [ $((i + 4)) -lt "$n" ]; then get "${parts[$((i + 4))]}" & pid[$((i + 4))]=$!; fi
  cat "$P/${parts[$i]}" || exit 1
  rm -f "$P/${parts[$i]}"
done
