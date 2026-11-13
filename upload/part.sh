#!/usr/bin/env bash
# split --filter: one part on stdin, NAME = $1. Skips a part already uploaded (asset of the recorded size; the stream's
# sha256 must equal the recorded one), else writes it to ci3_up/, waits for the previous upload and uploads it in the
# background (bin/upload.sh holds up/upload.lock while it runs: at most two parts on disk).
set -uo pipefail
D=$HOME/cppwrf_scratch/ci3 U=$HOME/cppwrf_scratch/ci3_up NAME=$1
rec=$(awk -v n="$NAME" '$1 == n {print $2, $3}' "$D/sums/parts.txt" 2>/dev/null | tail -1)
have=$(awk -v n="$NAME" '$1 == n {print $2}' "$D/up/assets.txt" 2>/dev/null | tail -1)
if [ -n "$rec" ] && [ -n "$have" ] && [ "${rec#* }" = "$have" ]; then
  sha=$(sha256sum | cut -d' ' -f1)
  [ "$sha" = "${rec%% *}" ] && { echo "SKIP $NAME" >> "$D/up/log.txt"; exit 0; }
  echo "MISMATCH $NAME stream $sha recorded ${rec%% *}" >> "$D/up/FAILED"; exit 1
fi
# free disk >= 12 GB + this part at every moment
while [ $(( $(df -B1 --output=avail "$U" | tail -1) )) -lt $(( 12000000000 + 560000000 )) ]; do sleep 20; done
cat > "$U/$NAME" || { echo "WRITE $NAME" >> "$D/up/FAILED"; exit 1; }
flock -x "$D/up/upload.lock" true   # the previous part's upload has ended
[ -e "$D/up/FAILED" ] && exit 1
setsid flock -x "$D/up/upload.lock" bash "$D/bin/upload.sh" "$NAME" > /dev/null 2>&1 < /dev/null &
sleep 2
exit 0
