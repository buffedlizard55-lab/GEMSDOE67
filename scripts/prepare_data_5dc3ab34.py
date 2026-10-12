"""Verify and stage the official competition rasters (data bridge).

Checks every file against the sha256 pins published in
``data/bridge/manifest.json`` (generated from the official DrivenData data tab
via the 6GEMSDOE transport bridge) and stages the two grid-defining files into
``data/bridge/`` where the shared template's ``gems57.grid`` loader expects
them.

A pin match means: byte-identical to the rasters the competition distributes.
It does NOT authenticate the organiser's own origin (see the manifest's
``source`` block for the chain of custody).
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

PINS = {
    "gems-geodawn-numerical-features.tif":
        "4371c82e3b8339b807bdffcf4ef59a225520fe2988d521be208ae33743123bc5",
    "existing_faults.tif":
        "7ba308ccdc4418b31a178f4f1ef21aaa6e152e4028f2f6f64b01f7eb25ae4093",
    "example_submission.tif":
        "2176d08e485aa2cd2860ce8df539db4faf4d76163b38a4dd8c30a40454d35cbc",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    raw = repo / "data" / "raw"
    bridge = repo / "data" / "bridge"
    bridge.mkdir(parents=True, exist_ok=True)
    receipt = {"files": {}, "ok": True}

    for name, pin in PINS.items():
        p = raw / name
        if not p.is_file():
            # accept the already-staged bridge copy
            p2 = bridge / name
            if p2.is_file():
                p = p2
            else:
                receipt["files"][name] = {"status": "MISSING", "expected_sha256": pin}
                receipt["ok"] = False
                continue
        digest = sha256(p)
        status = "PIN-MATCH" if digest == pin else "MISMATCH"
        receipt["files"][name] = {"status": status, "sha256": digest,
                                  "expected_sha256": pin, "path": str(p)}
        if status != "PIN-MATCH":
            receipt["ok"] = False
            continue
        # stage into the template's expected layout
        dest = bridge / name
        if not dest.is_file():
            shutil.copy2(p, dest)
        if name == "example_submission.tif":
            alias = bridge / "sample_submission.tif"
            if not alias.is_file():
                shutil.copy2(p, alias)

    out = repo / "evidence" / "data_receipt.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(receipt, indent=1) + "\n")
    print(json.dumps(receipt, indent=1))
    return 0 if receipt["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
