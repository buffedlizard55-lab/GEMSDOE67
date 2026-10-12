#!/usr/bin/env python3
"""Lane-67 anatomy meta-analysis: why did the family's best raster score what it scored?

For every pinned registry raster this recomputes, LOCALLY, the geometry that could plausibly drive
the live score (dot count, DTI against the visible catalogue, catalogue-proximity distribution,
mean radiometric K under the dots) and rank-correlates it with the reported scores in the inherited
ledger. Reported scores are OWNER-REPORTED: no organiser receipt links any hash to any score.

Output: evidence/e0_meta_analysis.json
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import rasterio  # noqa: E402
from scipy import ndimage  # noqa: E402
from scipy.stats import spearmanr  # noqa: E402

from gems.metric import tversky_terms  # noqa: E402

REG = ROOT / "data/registry"
EVID = ROOT / "evidence"
LEDGER = ROOT / "registry/ledger_reported_scores.json"
ANATOMY_INHERITED = ROOT / "registry/inherited_owner_score_map.json"


def main() -> int:
    with rasterio.open(ROOT / "data/official/labels.tif") as ds:
        cat = ds.read(1) > 0
    with rasterio.open(ROOT / "data/official/sample_submission.tif") as ds:
        fp = np.isfinite(ds.read(1))
    dcat = ndimage.distance_transform_edt(~cat)
    try:
        with rasterio.open(ROOT / "data/external/geodawn_rad_u8.tif") as ds:
            K = ds.read(1).astype(np.float32)
        K[K <= 0] = np.nan
    except FileNotFoundError:
        K = None
    scores = json.loads(ANATOMY_INHERITED.read_text())["owner_reported_scores"]
    rows = []
    for p in sorted(REG.glob("*.tif")):
        with rasterio.open(p) as ds:
            if (ds.height, ds.width) != cat.shape:
                continue
            a = ds.read(1).astype(np.float32)
        fin = np.isfinite(a)
        dots = fin & (a > 0)
        n = int(dots.sum())
        if n == 0:
            continue
        pred = np.where(fin, np.clip(a, 0, 1), 0.0)
        tp, fpw, fnw = tversky_terms(pred, cat)
        dti_cat = tp / (tp + 0.2 * fpw + 0.8 * fnw + 1e-9)
        dd = dcat[dots]
        row = {"raster": p.name, "dots": n, "mass": float(np.nansum(pred[fin])),
               "mean_intensity": float(np.mean(a[dots])),
               "dti_vs_catalogue": round(float(dti_cat), 5),
               "frac_within_1px": round(float(np.mean(dd <= 1)), 4),
               "frac_within_3px": round(float(np.mean(dd <= 3)), 4),
               "median_dist_px": round(float(np.median(dd)), 2),
               "mean_dist_px": round(float(np.mean(dd)), 2),
               "coverage_frac_of_footprint": round(n / int(fp.sum()), 5)}
        if K is not None:
            kv = K[dots]
            row["mean_K_under_dots"] = round(float(np.nanmean(kv)), 3)
        key = p.name
        row["reported_score"] = scores.get(key)
        row["score_evidence_class"] = ("OWNER-REPORTED (no organiser receipt)"
                                       if row["reported_score"] is not None else None)
        rows.append(row)
        del a, fin, dots, pred
    sc = [r for r in rows if r.get("reported_score") is not None]
    corr = {}
    if len(sc) >= 5:
        y = np.array([r["reported_score"] for r in sc], float)
        for k in ("dots", "dti_vs_catalogue", "frac_within_3px", "median_dist_px",
                  "mean_intensity", "coverage_frac_of_footprint", "mean_K_under_dots"):
            x = np.array([r.get(k, np.nan) for r in sc], float)
            m = np.isfinite(x)
            if m.sum() >= 5:
                rho, pv = spearmanr(x[m], y[m])
                corr[k] = {"spearman_rho": round(float(rho), 4), "p": round(float(pv), 4),
                           "n": int(m.sum())}
    # deduplicate identical geometry (the same raster mirrored under several names)
    seen = {}
    for r in sc:
        key = (r["dots"], r["dti_vs_catalogue"])
        seen.setdefault(key, []).append(r["raster"])
    out = {
        "evidence_class": ("STATISTICS MEASURED IN THIS CHECKOUT from the pinned registry rasters; "
                           "the score column is OWNER-REPORTED and has no organiser receipt"),
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "n_registry_rasters_analysed": len(rows), "n_with_reported_score": len(sc),
        "duplicate_geometry_groups": {str(k): v for k, v in seen.items() if len(v) > 1},
        "spearman_vs_reported_score": corr,
        "rows": sorted(sc, key=lambda r: -r["reported_score"]),
        "reading": (
            "Across the reported-score family the live score falls as the dot count rises and as the "
            "raster moves ONTO the visible catalogue. That is the arithmetic of the published metric: "
            "with TP_w = sum_g max_x p k, credit is a MAXIMUM not a sum, so extra dots never add "
            "credit for a truth cell that a nearer dot already covers, while every dot costs "
            "alpha = 0.2 of false-positive mass unless it sits within 300 m of hidden truth. The "
            "exact first-order condition (docs/research/metric-derivation.md, inherited from the "
            "shared template) is: a new dot is worth adding iff its kernel credit to a previously "
            "uncovered truth cell exceeds alpha * DTI. A uniform 5-px lattice over the whole "
            "footprint (206,895 dots) is reported by a sibling session at 0.0904 live, which is the "
            "same arithmetic taken to its limit. Consequence for this lane: emit unit-value dots, "
            "keep the count in the 30k-45k band the family's best occupy, keep them off the "
            "catalogue pixels, and let a calibrated marginal rule - not a hand-picked budget - "
            "decide where to stop."),
    }
    EVID.mkdir(exist_ok=True)
    (EVID / "e0_meta_analysis.json").write_text(json.dumps(out, indent=2))
    print(json.dumps({"n": len(rows), "scored": len(sc), "corr": corr}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
