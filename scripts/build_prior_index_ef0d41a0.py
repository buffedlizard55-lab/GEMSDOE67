#!/usr/bin/env python3
"""Build ``registry/prior_index.json`` -- the input to the vendored uniqueness gate.

The vendored ``gems57.uniqueness.records_from_index`` consumes a *full inventory*
whose records carry ``repo_first`` / ``sources`` / ``cache_file`` / ``sha256``.
This lane only mirrors part of the sibling-repository registry, so two classes of
record are written and they are never conflated:

* ``provenance: "upstream-sha256"``  -- the file came from a sibling registry's
  cache manifest that publishes the sha256 of the bytes it downloaded from the
  owner repository, and the local copy still matches that digest.  These hashes
  are evidence about the upstream artifact, not about our copy.
* ``provenance: "local-mirror-sha256"``  -- no upstream digest was published for
  this blob; the recorded hash is the digest of the local mirror copy and only
  proves the file has not changed since the index was written.

``complete_accessible_scan`` is deliberately **false**: the sibling inventory
lists 751 prior rasters and this lane mirrors 51 of them, so the literal stop gate
cannot be closed from inside the sandbox.  The comparison is still worth running,
because byte-identity and pixel-identity findings stand on their own and a large
worst-case rank correlation would be a real duplicate finding.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RASTERS = ROOT / "registry" / "rasters"
# Sibling registry cache manifest copied into this lane (GEMSDOE63 @ main,
# registry/cache.json).  It lists the 21 hash-verified prior artifacts that carry
# owner-reported leaderboard scores.
CACHE_MANIFEST = ROOT / "registry" / "cache.json"
UPSTREAM_TOTAL = 751  # union inventory size published by the sibling registry


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    upstream = {}
    if CACHE_MANIFEST.exists():
        cache = json.loads(CACHE_MANIFEST.read_text())
        for entry in cache.get("entries", []):
            name = Path(entry["local_path"]).name
            upstream[name] = dict(repo_first=entry["repo"], sources=[entry["path"]],
                                  sha256=entry["sha256"],
                                  owner_reported_score=entry.get("owner_reported_score"))
    records, mismatched = [], []
    for path in sorted(RASTERS.glob("*.tif")):
        digest = _sha256(path)
        up = upstream.get(path.name)
        if up is None:
            records.append(dict(repo_first="buffedlizard55-lab/<sibling>",
                                sources=[f"local mirror: registry/rasters/{path.name}"],
                                cache_file=f"registry/rasters/{path.name}",
                                sha256=digest, provenance="local-mirror-sha256",
                                bytes=path.stat().st_size))
        else:
            if digest != up["sha256"]:
                mismatched.append(path.name)
            records.append(dict(repo_first=up["repo_first"], sources=up["sources"],
                                cache_file=f"registry/rasters/{path.name}",
                                sha256=up["sha256"], provenance="upstream-sha256",
                                owner_reported_score=up.get("owner_reported_score"),
                                bytes=path.stat().st_size))
    index = dict(
        schema="lane67-prior-index-v1",
        built_utc=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        scope=("Every prior raster mirrored into this lane from the sibling owner-repository "
               "registry. NOT a complete organizer registry."),
        upstream_inventory_size=UPSTREAM_TOTAL,
        mirrored=len(records),
        upstream_hashed=sum(1 for r in records if r["provenance"] == "upstream-sha256"),
        local_only_hashed=sum(1 for r in records if r["provenance"] == "local-mirror-sha256"),
        hash_mismatches=mismatched,
        complete_accessible_scan=False,
        completeness_note=(
            f"{len(records)} of {UPSTREAM_TOTAL} inventory blobs are mirrored here, so the "
            "vendored stop gate cannot certify uniqueness from inside this sandbox; it can "
            "only detect a duplicate among the mirrored priors."),
        errors=[],
        rasters=records,
    )
    out = ROOT / "registry" / "prior_index.json"
    out.write_text(json.dumps(index, indent=1) + "\n")
    print(f"[prior-index] {len(records)} records ({index['upstream_hashed']} upstream-sha256, "
          f"{index['local_only_hashed']} local-mirror) -> {out.relative_to(ROOT)}")
    if mismatched:
        print(f"[prior-index] WARNING upstream hash mismatch: {mismatched}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
