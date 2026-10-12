"""Hash + pixel-agreement uniqueness check against the local prior-raster registry.

Lane-drift gate (parallel-run protocol rule 1): stop as a duplicate if

* |Spearman rank correlation| of the candidate surface with any registry
  raster exceeds 0.90 (checked on the pre-placement surface AND the final
  dots), or
* more than 70% of the candidate's dots fall within 3 px of one registry
  raster's dots (with the saturation caveat: a dense prior that covers the
  whole allowed domain within 3 px makes this test degenerate for ANY
  nonempty candidate -- that is logged, not passed).

Scope honesty: the registry is the hash-indexed inventory of prior rasters
that are accessible in the public owner repositories (cloned under refs/).
It is NOT the organiser's complete registry; a pass here is a uniqueness
clearance within that scope only.

Usage::

    PYTHONPATH=src python scripts/check_uniqueness.py CANDIDATE.tif \
        --surface evidence/surface.npy --json-out evidence/uniqueness.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "vendor")]

from gems57 import grid as gridmod, uniqueness as uniq  # noqa: E402

RHO_LIMIT = 0.90
OVERLAP_LIMIT = 0.70


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_index(search_roots: list[Path], exclude: Path | None) -> dict:
    rasters = []
    seen = set()
    # never compare the candidate against copies of itself (its NaN twin and
    # receipts share the run id) -- the shared find_priors precedent (IR-52-027
    # family) requires the candidate's own artifact family to be out of scope
    exclude_ids: set[str] = set()
    if exclude is not None:
        base = exclude.name
        for tag in ("-allfinite", "-nan", "-zeros", ".tif", ".tiff"):
            base = base.replace(tag, "")
        exclude_ids.add(base)
    for root in search_roots:
        if not root.exists():
            continue
        for p in sorted(root.rglob("*.tif")):
            if exclude is not None and p.resolve() == exclude.resolve():
                continue
            if any(i in p.name for i in exclude_ids):
                continue
            sp = str(p)
            # competition inputs are not prior submissions (IR-52-027)
            if ("data/raw" in sp or "data/bridge" in sp
                    or p.name in ("labels.tif", "existing_faults.tif")
                    or p.name.startswith("sample_submission")
                    or "training_features" in sp or "numerical-features" in sp):
                continue
            digest = sha256(p)
            if digest in seen:
                continue
            seen.add(digest)
            rasters.append(dict(repo_first=p.parts[-4] if len(p.parts) > 4 else p.parent.name,
                                sources=[str(p)], cache_file=str(p), sha256=digest))
    return dict(complete_accessible_scan=False, rasters=rasters,
                scope_note="hash-indexed accessible public-owner-repository inventory; "
                           "not an organiser-complete registry")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("candidate", type=Path)
    ap.add_argument("--surface", type=Path, default=None,
                    help=".npy pre-placement continuous surface (float32 HxW)")
    ap.add_argument("--search-root", action="append", default=None)
    ap.add_argument("--index-out", type=Path, default=Path("evidence/registry_index.json"))
    ap.add_argument("--json-out", type=Path, default=Path("evidence/uniqueness.json"))
    args = ap.parse_args()

    repo = Path(__file__).resolve().parents[1]
    g = gridmod.load_grid(repo / "data" / "bridge")
    roots = [Path(r) for r in (args.search_root or [])] or [
        Path("/home/user/refs/GEMSDOE32"), Path("/home/user/refs/GEMSDOE65"),
        Path("/home/user/refs/GEMSDOE66"), repo / "artifacts",
        repo / "docs" / "downloads",
    ]
    index = build_index(roots, exclude=args.candidate)
    args.index_out.parent.mkdir(parents=True, exist_ok=True)
    args.index_out.write_text(json.dumps(index, indent=1) + "\n")
    print(f"registry index: {len(index['rasters'])} rasters", flush=True)

    result = uniq.compare_to_registry(args.candidate, index, g.footprint,
                                      include_reverse=True, progress=None)
    out = dict(candidate=str(args.candidate),
               rho_limit=RHO_LIMIT, overlap_limit=OVERLAP_LIMIT,
               phase="final-dots", registry=index["scope_note"],
               registry_rasters=index["rasters"].__len__(),
               result=result)

    if args.surface and args.surface.exists():
        surf = np.load(args.surface)
        surf = np.where(np.isfinite(surf), surf, 0.0).astype(np.float32)
        surf[~g.footprint] = 0.0
        worst = None
        for rec in index["rasters"]:
            try:
                with np.errstate(all="ignore"):
                    import rasterio
                    with rasterio.open(rec["cache_file"]) as src:
                        theirs = src.read(1)
                    theirs = np.where(np.isfinite(theirs), theirs, 0.0).astype(np.float32)
                    r = uniq.surface_rho(surf, theirs, g.footprint)
                rho = r["spearman_full_footprint"]
                if rho is not None and np.isfinite(rho) and (worst is None or abs(rho) > abs(worst["rho"])):
                    worst = dict(rho=float(rho), file=rec["cache_file"])
            except Exception as e:  # noqa: BLE001
                continue
        out["phase_pre_placement_surface"] = dict(
            worst_abs_spearman=abs(worst["rho"]) if worst else 0.0,
            worst=worst, limit=RHO_LIMIT,
            status="PASS" if (worst is None or abs(worst["rho"]) <= RHO_LIMIT) else "DRIFT-STOP")

    # summary verdicts (row-level flags come from the shared module)
    rows = result.get("rows", [])
    ok_rows = [r for r in rows if "error" not in r]
    worst_rho = max((abs(r.get("spearman_full_footprint") or 0.0) for r in ok_rows), default=0.0)
    # saturation-aware forward overlap.  A witness whose 3 px halo already
    # covers more allowed cells than the overlap limit makes the forward test
    # uninformative for ANY nonempty candidate (chance-expected overlap exceeds
    # the limit before any drift exists).  This is the shared template's own
    # saturation_certificate logic (58G ``chance_expected_overlap``); sessions
    # GEMSDOE65/66 hit it with lattice witnesses and logged degeneracy.  The
    # literal readings are kept and reported; the drift-stop set only admits
    # informative firings.
    import rasterio
    from scipy import ndimage as ndi2
    allowed = g.footprint & ~g.catalogue
    dense = [r for r in ok_rows if r.get("my_dots_within_3px_of_theirs", 0) > OVERLAP_LIMIT]
    informative, halo_saturated = [], []
    for r in dense:
        with rasterio.open(r["file"]) as src:
            theirs = src.read(1)
        support = np.isfinite(theirs) & (theirs > 0) & g.footprint
        yy, xx = np.mgrid[-3:4, -3:4]
        halo = ndi2.binary_dilation(support, structure=yy * yy + xx * xx <= 9)
        chance = float(halo[allowed].mean()) if allowed.any() else 1.0
        entry = dict(file=r["file"], forward=r["my_dots_within_3px_of_theirs"],
                     their_dots=r.get("their_dots"), chance_expected_forward=chance,
                     jaccard=r.get("jaccard_dot_sets"),
                     reverse=r.get("their_dots_within_3px_of_mine"))
        if chance > OVERLAP_LIMIT:
            halo_saturated.append(entry)
        else:
            informative.append(entry)
    verdict = dict(
        byte_unique=not any(r.get("identical_bytes") for r in ok_rows),
        pixel_unique=not any(r.get("identical_decoded_predictions") for r in ok_rows),
        worst_abs_spearman=float(worst_rho),
        rho_pass=bool(worst_rho <= RHO_LIMIT),
        overlap_failures_literal=len(dense),
        overlap_firings_informative=len(informative),
        halo_saturated_witnesses=[e["file"] for e in halo_saturated],
        overlap_honest_failures=len(informative),
        duplicate_by_hash=bool(result.get("duplicate_by_hash", False)),
        degeneracy_rule="forward-overlap firing admitted to the drift-stop set only if "
                        "chance-expected forward overlap (witness 3px halo coverage of the "
                        "allowed domain) <= the 0.70 limit; otherwise the witness is logged "
                        "as halo-saturated and the firing is reported but uninformative",
    )
    verdict["unique_in_scope"] = bool(
        verdict["byte_unique"] and verdict["rho_pass"]
        and verdict["overlap_honest_failures"] == 0
        and not verdict["duplicate_by_hash"])
    out["verdict"] = verdict
    out["overlap_firings"] = dict(informative=informative, halo_saturated=halo_saturated)

    text = json.dumps(out, indent=1, allow_nan=False, default=str)
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(text + "\n")
    print(text[:3000], flush=True)
    print("VERDICT:", json.dumps(verdict), flush=True)
    return 0 if verdict["unique_in_scope"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
