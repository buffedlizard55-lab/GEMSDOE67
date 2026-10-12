"""Lane-67 uniqueness / duplicate check against every pinned registry raster.

The parallel-run protocol prescribes two duplicate statistics, checked on the surface *before*
placement and again on the final dots:

* rank correlation (Spearman) with any registry raster above 0.90  -> duplicate, stop;
* more than 70 % of my dots within 3 px of one registry raster's dots -> duplicate, stop.

Both are computed here on the official footprint. Two readings of the 3-px rule are reported,
because sibling sessions proved the literal rule is degenerate in this corpus: several registry
rasters are *continuous* fields that are positive on essentially every footprint cell, so every
non-empty dot field is within 3 px of 100 % of their dots (including the live-scored incumbent).
``literal`` uses every raster; ``like_for_like`` restricts to rasterised *dot* families
(<= 50 % of footprint cells positive), which is the informative comparison.

Definitions used: ``dot`` = cell with value > 0 among finite cells; Spearman is computed on a
systematic subsample of the common finite domain (disclosed in the output) for tractability.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from scipy import ndimage
from scipy.stats import rankdata

DOT_OVERLAP_LIMIT = 0.70
RANK_CORR_LIMIT = 0.90
NEIGH_PX = 3
CONTINUOUS_FRAC = 0.50


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    if a.size < 3:
        return float("nan")
    ra, rb = rankdata(a), rankdata(b)
    ra -= ra.mean(); rb -= rb.mean()
    da = float(np.sqrt((ra * ra).sum())); db = float(np.sqrt((rb * rb).sum()))
    if da == 0 or db == 0:
        return float("nan")
    return float((ra * rb).sum() / (da * db))


def compare(candidate_path: Path, registry_dir: Path, subsample: int = 400_000,
            seed: int = 67) -> dict:
    """Compare one candidate GeoTIFF against every ``*.tif`` in ``registry_dir``."""
    import rasterio

    with rasterio.open(candidate_path) as ds:
        cand = ds.read(1).astype(np.float32)
        cand_shape = (ds.height, ds.width)
    cand_fin = np.isfinite(cand)
    cand_dots = cand_fin & (cand > 0)
    n_cand_dots = int(cand_dots.sum())
    cand_sha = sha256_file(Path(candidate_path))
    rng = np.random.default_rng(seed)
    idx = np.flatnonzero(cand_fin.ravel())
    if idx.size > subsample:
        idx = np.sort(rng.choice(idx, subsample, replace=False))
    rows = []
    for p in sorted(Path(registry_dir).glob("*.tif")):
        psha = sha256_file(p)
        with rasterio.open(p) as ds:
            if (ds.height, ds.width) != cand_shape:
                rows.append({"raster": p.name, "status": "SKIPPED-shape", "shape": [ds.height, ds.width]})
                continue
            other = ds.read(1).astype(np.float32)
        o_fin = np.isfinite(other)
        o_dots = o_fin & (other > 0)
        n_o = int(o_dots.sum())
        common = cand_fin & o_fin
        cf = np.flatnonzero(common.ravel())
        if cf.size > subsample:
            cf = np.sort(rng.choice(cf, subsample, replace=False))
        cy, cx = np.unravel_index(cf, common.shape)
        rho = _spearman(cand[cy, cx].astype(np.float64), other[cy, cx].astype(np.float64))
        # 3-px overlap of MY dots against THEIR dots
        if n_o:
            d = ndimage.distance_transform_edt(~o_dots, sampling=(1.0, 1.0))
            ov3 = float(np.mean(d[cand_dots] <= NEIGH_PX)) if n_cand_dots else float("nan")
        else:
            ov3 = float("nan")
        inter = int((cand_dots & o_dots).sum())
        union = int((cand_dots | o_dots).sum())
        rows.append({
            "raster": p.name, "sha256": psha, "bytes": p.stat().st_size,
            "byte_identical": psha == cand_sha,
            "their_dots": n_o, "their_positive_frac_of_footprint": round(n_o / max(int(cand_fin.sum()), 1), 4),
            "spearman_common_finite": None if not np.isfinite(rho) else round(float(rho), 4),
            "dot_overlap_3px_of_mine": None if not np.isfinite(ov3) else round(ov3, 4),
            "exact_cell_jaccard": round(inter / union, 6) if union else None,
            "shared_cells": inter,
            "continuous_comparator": bool(n_o > CONTINUOUS_FRAC * int(cand_fin.sum())),
        })
        del other, o_dots, o_fin
    scored = [r for r in rows if "spearman_common_finite" in r]
    lfl = [r for r in scored if not r.get("continuous_comparator")]
    def _mx(rs, key):
        vals = [(abs(r[key]), r["raster"]) for r in rs if isinstance(r.get(key), float)]
        return max(vals) if vals else (None, None)
    max_rho = _mx(scored, "spearman_common_finite")
    max_rho_lfl = _mx(lfl, "spearman_common_finite")
    max_ov = _mx(scored, "dot_overlap_3px_of_mine")
    max_ov_lfl = _mx(lfl, "dot_overlap_3px_of_mine")
    return {
        "candidate": str(candidate_path), "candidate_sha256": cand_sha,
        "candidate_dots": n_cand_dots, "candidate_finite_cells": int(cand_fin.sum()),
        "registry_dir": str(registry_dir), "registry_rasters": len(rows),
        "subsample_cells_for_spearman": subsample,
        "limits": {"spearman": RANK_CORR_LIMIT, "dot_overlap_3px": DOT_OVERLAP_LIMIT, "neighbourhood_px": NEIGH_PX},
        "literal": {
            "max_abs_spearman": max_rho[0], "max_abs_spearman_raster": max_rho[1],
            "max_dot_overlap_3px": max_ov[0], "max_dot_overlap_3px_raster": max_ov[1],
            "rule_pass": bool((max_rho[0] is None or max_rho[0] <= RANK_CORR_LIMIT) and
                              (max_ov[0] is None or max_ov[0] <= DOT_OVERLAP_LIMIT)),
        },
        "like_for_like": {
            "n_dot_rasters": len(lfl), "n_continuous_comparators": len(scored) - len(lfl),
            "max_abs_spearman": max_rho_lfl[0], "max_abs_spearman_raster": max_rho_lfl[1],
            "max_dot_overlap_3px": max_ov[0] if not lfl else max_ov_lfl[0],
            "max_dot_overlap_3px_raster": max_ov[1] if not lfl else max_ov_lfl[1],
            "rule_pass": bool((max_rho_lfl[0] is None or max_rho_lfl[0] <= RANK_CORR_LIMIT) and
                              (max_ov_lfl[0] is None or max_ov_lfl[0] <= DOT_OVERLAP_LIMIT)),
        },
        "byte_identical_to_any": any(r.get("byte_identical") for r in rows),
        "per_raster": rows,
        "note": "literal reading is reported alongside like_for_like because the corpus contains "
                "continuous rasters that make the literal 3-px clause unsatisfiable for any "
                "non-empty candidate (documented by sibling sessions; re-measured here).",
    }


if __name__ == "__main__":
    import sys
    out = compare(Path(sys.argv[1]), Path(sys.argv[2]))
    print(json.dumps({k: v for k, v in out.items() if k != "per_raster"}, indent=2))
    Path(sys.argv[3]).write_text(json.dumps(out, indent=2)) if len(sys.argv) > 3 else None
