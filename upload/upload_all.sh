#!/usr/bin/env bash
# Stream every scanned-clean tar of tars.txt from Drive, re-packed (bin/repack.py), in 512 MiB parts to the release.
set -uo pipefail
D=$HOME/cppwrf_scratch/ci3 U=$HOME/cppwrf_scratch/ci3_up
R=Xassemblianist/cppwrf-data TAG=${CI3_TAG:-data-v1}
cd "$D" || exit 1
mkdir -p up "$U"; touch sums/parts.txt up/excluded.txt
gh api "repos/$R/releases/tags/$TAG" --jq .id > up/release_id || exit 1
assets() { gh api --paginate "repos/$R/releases/$(cat up/release_id)/assets?per_page=100" --jq '.[] | select(.state == "uploaded") | "\(.name) \(.size)"'; }
publish_sums() {  # SHA256SUMS (parts) and TARS.txt (whole re-packed tars) from the records
  awk '{print $2 "  " $1}' sums/parts.txt | sort -k2 -u > up/SHA256SUMS
  cat sums/tars.txt 2>/dev/null | sort -u > up/TARS.txt
  for f in SHA256SUMS TARS.txt; do
    for try in 1 2 3; do gh release upload "$TAG" "up/$f" -R "$R" --clobber >> up/gh.log 2>&1 && break; sleep 30; done
  done
}
drop_short() {  # a stream that broke off left a short last part: forget it (record and asset), the retry makes it again
  local n id
  for n in $(awk -v t="$1" 'index($1, t ".part") == 1 && $3 < 536870912 {print $1}' sums/parts.txt); do
    grep -v "^$n " sums/parts.txt > sums/parts.tmp; mv sums/parts.tmp sums/parts.txt
    for id in $(gh api --paginate "repos/$R/releases/$(cat up/release_id)/assets?per_page=100" --jq ".[] | select(.name == \"$n\") | .id"); do
      gh api -X DELETE "repos/$R/releases/assets/$id" > /dev/null
    done
    echo "DROPPED short part $n" >> up/log.txt
  done
}
for t in $(cat tars.txt); do
  grep -q "^$t " sums/tars.txt 2>/dev/null && continue
  while [ ! -e "scan/$t.done" ]; do sleep 30; done
  if grep '^SUMMARY' "scan/$t.txt" | grep -qE 'hits_(text|binary|netcdf|name)=[1-9]'; then
    grep -q "^$t$" up/excluded.txt || echo "$t" >> up/excluded.txt
    echo "EXCLUDED $t (scan/$t.txt)" >> up/log.txt; continue
  fi
  for try in 1 2 3; do
    [ -e up/FAILED ] && { echo "STOP: up/FAILED"; cat up/FAILED; exit 1; }
    assets > up/assets.txt || { sleep 60; continue; }
    t0=$SECONDS; rm -f "up/$t.sha" "up/$t.size"
    rclone cat --low-level-retries 20 "cppwrf-drive:cppwrf-data/$t" | python3 -I bin/repack.py 2>> "up/repack_$t.log" |
      tee >(sha256sum | cut -d' ' -f1 > "up/$t.sha") >(wc -c > "up/$t.size") |
      split -b 512M -d -a 3 --filter='bash "$HOME/cppwrf_scratch/ci3/bin/part.sh" "$FILE"' - "$t.part"
    st=("${PIPESTATUS[@]}")
    flock -x up/upload.lock true
    for i in $(seq 60); do [ -s "up/$t.sha" ] && [ -s "up/$t.size" ] && break; sleep 1; done
    if [ "${st[*]}" = "0 0 0 0" ] && [ ! -e up/FAILED ]; then
      n=$(grep -c "^$t\.part" <(awk '{print $1}' sums/parts.txt | sort -u))
      echo "$t $(cat "up/$t.size") $(cat "up/$t.sha") $n" >> sums/tars.txt
      echo "TAR $t $(cat "up/$t.size") bytes, $n parts, $((SECONDS - t0)) s" >> up/log.txt
      publish_sums; break
    fi
    echo "TAR $t try $try failed (${st[*]})" >> up/log.txt; [ -e up/FAILED ] && break
    drop_short "$t"; sleep 60
  done
done
echo "UPLOAD_ALL_END" >> up/log.txt
