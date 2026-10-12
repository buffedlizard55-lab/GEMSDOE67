#!/usr/bin/env python3
"""Decode the pinned competition rasters into memmappable form and record their hashes.

Usage:  python scripts/prepare_data.py [--data /tmp/gems_data]

The competition rasters are hash-pinned (see data/registry.json).  When they are absent this
script prints the exact retrieval route and exits non-zero rather than guessing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import tifffile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

PINNED = {
    "training_features.tif": "4371c82e3b8339b807bdffcf4ef59a225520fe2988d521be208ae33743123bc5",
    "labels.tif": "7ba308ccdc4418b31a178f4f1ef21aaa6e152e4028f2f6f64b01f7eb25ae4093",
    "sample_submission.tif": "2176d08e485aa2cd2860ce8df539db4faf4d76163b38a4dd8c30a40454d35cbc",
}

RETRIEVAL = """\
Competition data is login-walled at
  https://www.drivendata.org/competitions/306/competition-doe-gems/data/
The two files used here are also carried byte-identically in public GitHub mirrors that this
sandbox can reach (owner-supplied mirrors, integrity-pinned; NOT organizer-authenticated):

  training_features.tif  -> github.com/buffedlizard55-lab/GEMSDOE  data/bridge/
                            gems-geodawn-numerical-features.tif.part-000 .. part-004
                            (concatenate in order -> 418 912 844 bytes)
  labels.tif             -> github.com/buffedlizard55-lab/GEMSDOE24 data/bridge/labels.tif
  sample_submission.tif  -> github.com/buffedlizard55-lab/GEMSDOE24 data/bridge/sample_submission.tif

Verify each file against data/registry.json before use.
"""


def sha256(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while blk := fh.read(chunk):
            h.update(blk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="/tmp/gems_data")
    args = ap.parse_args()
    data = Path(args.data)

    report: dict[str, object] = {"data_dir": str(data), "files": {}, "ok": True}
    for name, want in PINNED.items():
        p = data / name
        if not p.exists():
            print(f"ERROR: missing {p}\n\n{RETRIEVAL}")
            report["ok"] = False
            report["files"][name] = {"present": False, "expected_sha256": want}
            continue
        got = sha256(p)
        ok = got == want
        report["files"][name] = {"present": True, "sha256": got, "matches_pin": ok}
        print(f"{name:24s} sha256={got[:16]}… pin_match={ok}")
        report["ok"] = report["ok"] and ok

    stack = data / "stack.npy"
    if report["ok"] and not stack.exists():
        with tifffile.TiffFile(data / "training_features.tif") as t:
            arr = t.pages[0].asarray()
        np.save(stack, arr)
        print(f"wrote {stack} shape={arr.shape} dtype={arr.dtype}")
    elif stack.exists():
        print(f"{stack} already present")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
