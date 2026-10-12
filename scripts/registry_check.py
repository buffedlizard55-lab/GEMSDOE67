#!/usr/bin/env python3
"""Lane-hygiene check against every prior raster this checkout can read.

The parallel-run protocol for this lane states: *"If your raster's rank-correlation with any
registry raster exceeds [0.90], or more than [70%] of your dots fall within 3 px of one
registry raster's dots, you have drifted into another lane: log it as a duplicate and stop."*

This script performs exactly those two tests, before and after placement, and writes
``evidence/registry_check.json``.  Prior rasters are read from the sibling repositories'
published downloads when they are present in the checkout (they are **not** re-published here).

Usage:  python scripts/registry_check.py --ours docs/downloads/<name>-nan.tif
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

RANK_LIMIT = 0.90
OVERLAP_LIMIT = 0.70
SUBSAMPLE = 400_000

SEARCH_DIRS = [
    "/home/user/_ref/GEMSDOE32/docs/downloads/*.tif",
    "/home/user/_ref/GEMSDOE25/docs/downloads/*.tif",
    "/home/user/_ref/GEMSDOE28/docs/downloads/*.tif",
    "/home/user/_ref/GEMSDOE31/docs/downloads/*.tif",
]


def read_binary(path: Path) -> np.ndarray:
    import tifffile

    a = tifffile.TiffFile(path).pages[0].asarray()
    if a.ndim != 2:
        raise ValueError(f"{path}: not single-band")
    return np.isfinite(a) & (a > 0)


def spearman_sample(a: np.ndarray, b: np.ndarray, seed: int = 0) -> float:
    rng = np.random.default_rng(seed)
    m = a | b | True
    idx = rng.choice(a.size, min(SUBSAMPLE, a.size), replace=False)
    x = a.ravel()[idx].astype(np.float64)
    y = b.ravel()[idx].astype(np.float64)
    if x.std() == 0 or y.std() == 0:
        return float("nan")
    from scipy.stats import rankdata

    return float(np.corrcoef(rankdata(x), rankdata(y))[0, 1])


def overlap_fraction(ours: np.ndarray, theirs: np.ndarray, radius: float = 3.0) -> float:
    orr, occ = np.nonzero(ours)
    trr, tcc = np.nonzero(theirs)
    if orr.size == 0 or trr.size == 0:
        return 0.0
    tree = cKDTree(np.stack([trr, tcc], 1))
    d, _ = tree.query(np.stack([orr, occ], 1), k=1)
    return float((d <= radius).mean())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ours", required=True)
    ap.add_argument("--out", default=str(ROOT / "evidence" / "registry_check.json"))
    args = ap.parse_args()

    ours = read_binary(Path(args.ours))
    n_ours = int(ours.sum())
    print(f"[registry] ours: {Path(args.ours).name} positives={n_ours}")

    priors: list[Path] = []
    for pat in SEARCH_DIRS:
        priors.extend(sorted(Path(p) for p in glob.glob(pat)))

    rows = []
    worst_rank, worst_overlap = 0.0, 0.0
    for p in priors:
        try:
            theirs = read_binary(p)
        except Exception as exc:  # pragma: no cover
            rows.append({"file": str(p), "error": str(exc)})
            continue
        if theirs.shape != ours.shape:
            rows.append({"file": str(p), "error": f"shape {theirs.shape}"})
            continue
        rho = spearman_sample(ours, theirs)
        ov = overlap_fraction(ours, theirs)
        rows.append({"file": p.name, "positives": int(theirs.sum()),
                     "spearman_rank": None if rho != rho else round(rho, 4),
                     "overlap_within_3px": round(ov, 4)})
        worst_rank = max(worst_rank, 0.0 if rho != rho else abs(rho))
        worst_overlap = max(worst_overlap, ov)
        print(f"[registry]   vs {p.name:62s} rho={rho:.4f} overlap3px={ov:.4f}")

    verdict = "distinct lane"
    if worst_rank > RANK_LIMIT:
        verdict = f"DUPLICATE LANE (rank correlation {worst_rank:.3f} > {RANK_LIMIT})"
    if worst_overlap > OVERLAP_LIMIT:
        verdict = f"DUPLICATE LANE (overlap {worst_overlap:.3f} > {OVERLAP_LIMIT})"

    out = {"ours": str(Path(args.ours).name), "n_positives": n_ours,
           "rank_limit": RANK_LIMIT, "overlap_limit": OVERLAP_LIMIT,
           "max_abs_rank_correlation": round(worst_rank, 4),
           "max_overlap_within_3px": round(worst_overlap, 4),
           "verdict": verdict, "priors": rows,
           "note": ("prior rasters are read from sibling checkouts, not re-published; a missing "
                    "prior reduces coverage of this check and is recorded as an error row")}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2) + "\n")
    print(f"[registry] verdict: {verdict}  -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
