#!/usr/bin/env python3
"""One-off / idempotent: create Posts_jpeg/<stem>.jpg for every non-JPEG image in Posts/.

    python3 automation/make_jpegs.py            # convert what is missing
    python3 automation/make_jpegs.py --check    # report only
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jpeg_util as J

def main():
    check = "--check" in sys.argv
    made = skipped = bad = 0
    for fn in sorted(os.listdir(J.POSTS)):
        p = os.path.join(J.POSTS, fn)
        if not os.path.isfile(p) or fn.startswith(".") or J.is_jpeg(fn):
            continue
        if not fn.lower().endswith((".png", ".webp", ".gif", ".bmp", ".tif", ".tiff")):
            continue
        dst = J.jpeg_path(fn)
        if os.path.exists(dst) and os.path.getmtime(dst) >= os.path.getmtime(p):
            skipped += 1; continue
        if check:
            print("missing:", fn); bad += 1; continue
        try:
            J.to_jpeg(p, dst); made += 1
        except Exception as e:
            print(f"FAILED {fn}: {e}"); bad += 1
    print(f"created {made}, up to date {skipped}, problems {bad}")

if __name__ == "__main__":
    main()
