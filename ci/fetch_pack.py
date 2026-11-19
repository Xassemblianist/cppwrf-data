#!/usr/bin/env python3
"""fetch_pack.py URL STAT PART SHA256 [PART SHA256 ...]: the parts of one pack of a data release (packs layout) on
stdout, in order, each streamed from URL/PART (a broken download resumes where it stopped, up to 8 tries) and
checked against its sha256; exits 1 at the first failure. STAT gets "bytes seconds"."""
import hashlib
import sys
import time
import urllib.request

url, stat, args = sys.argv[1], sys.argv[2], sys.argv[3:]
out = sys.stdout.buffer
t0, total = time.time(), 0
for part, want in zip(args[0::2], args[1::2]):
    h, got, tries = hashlib.sha256(), 0, 0
    while True:
        try:
            req = urllib.request.Request(f"{url}/{part}", headers={"Range": f"bytes={got}-"} if got else {})
            with urllib.request.urlopen(req, timeout=60) as r:
                if got and r.status != 206:  # the server sent the whole asset: skip what is written
                    skip = got
                    while skip:
                        b = r.read(min(skip, 8 << 20))
                        if not b:
                            raise OSError("short read")
                        skip -= len(b)
                while True:
                    b = r.read(8 << 20)
                    if not b:
                        break
                    h.update(b)
                    out.write(b)
                    got += len(b)
            break
        except Exception as e:  # noqa: BLE001
            tries += 1
            if tries >= 8:
                print(f"fetch_pack: {part}: {e}", file=sys.stderr)
                sys.exit(1)
            time.sleep(5 * tries)
    if h.hexdigest() != want:
        print(f"fetch_pack: {part}: sha256 differs", file=sys.stderr)
        sys.exit(1)
    total += got
out.flush()
open(stat, "w").write(f"{total} {int(time.time() - t0)}\n")
