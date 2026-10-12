#!/usr/bin/env python3
"""Build the deliverable GeoTIFFs, their receipts and the registry agreement check.

Rule (frozen before the numbers were read; see docs/run-card.json):

  q_ml  = gradient-boosted head on the evidence channels, trained on the *full* visible
          catalogue (positives = catalogue pixels, negatives = pixels >= 5 px from any
          catalogue pixel)
  dots  = greedy kernel-cover of {q_ml >= tau} with radius 3 px (one dot per covered cluster)
  raster= 1.0 on dots, 0.0 elsewhere inside the footprint, NaN outside (primary) or all-finite
          (twin)

Usage:  python scripts/build_submission.py --name gemsdoe67-... --tau 0.3
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import zipfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gems67 import emit, head, submission  # noqa: E402
from gems67.dataio import validate_submission, write_json, write_submission  # noqa: E402


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for blk in iter(lambda: fh.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--tau", type=float, default=0.30)
    ap.add_argument("--radius", type=float, default=3.0)
    ap.add_argument("--iters", type=int, default=200)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--max-pos", type=int, default=60000)
    ap.add_argument("--neg-per-pos", type=float, default=2.0)
    ap.add_argument("--no-external", action="store_true",
                    help="restrict the head to the 19-band-stack channels")
    ap.add_argument("--outdir", default=str(ROOT / "docs" / "downloads"))
    args = ap.parse_args()

    t0 = time.time()
    labels, footprint = head.load_labels_and_footprint()
    catalogue = labels == 1

    channels = head.available(head.BASE_CHANNELS if args.no_external
                              else head.BASE_CHANNELS + head.EXTERNAL_CHANNELS)
    print(f"[build] {len(channels)} channels: {', '.join(channels)}")

    rng = np.random.default_rng(args.seed)
    rows, cols, y = head.sample_training_pixels(footprint, catalogue,
                                                exclude=np.zeros(labels.shape, bool), rng=rng,
                                                max_pos=args.max_pos,
                                                neg_per_pos=args.neg_per_pos)
    print(f"[build] training pixels: {rows.size} positives={int(y.sum())}")
    clf = head.fit(channels, rows, cols, y, iters=args.iters, seed=args.seed)
    del rows, cols, y

    q = head.predict_full(clf, channels, footprint)
    print(f"[build] q_ml predicted; above tau={args.tau}: {int((q >= args.tau).sum())} px "
          f"({time.time() - t0:.0f}s)")

    dots = emit.cover_greedy(q, tau=args.tau, candidate_mask=footprint, radius=args.radius)
    n_dots = int(dots.sum())
    print(f"[build] cover-greedy dots={n_dots}")
    if n_dots == 0:
        write_json(ROOT / "evidence" / "build_negative.json",
                   {"tau": args.tau, "channels": list(channels),
                    "verdict": "NEGATIVE — no dot cleared the exposure threshold"})
        print("[build] NEGATIVE RESULT: no dots; not writing a submission")
        return 2

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    receipts = {
        "name": args.name,
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "rule": {
            "lane": "OVTR — orientation-voted tip relay, decoded, then greedy kernel-covered",
            "head": "HistGradientBoostingClassifier (max_iter=%d, lr=0.08, leaves=31, l2=1.0)"
                    % args.iters,
            "channels": list(channels),
            "training_pixels": int(args.max_pos),
            "negatives_per_positive": args.neg_per_pos,
            "exposure_tau": args.tau,
            "cover_radius_px": args.radius,
            "n_dots": n_dots,
            "binary_values": True,
            "catalogue_pixels_in_emission_domain": True,
            "assumption": ("known USGS/INGENIOUS fault pixels are masked out of every metric "
                           "term, so mass placed on them is free — DrivenData staff answer, "
                           "forum thread 11516"),
        },
        "files": {},
    }
    for mode in ("nan", "zero"):
        arr = submission.to_submission(dots, footprint, outside=mode)
        p = outdir / f"{args.name}-{mode}.tif"
        write_submission(p, arr, nodata=np.nan if mode == "nan" else None)
        rep = validate_submission(p)
        rep["sha256"] = sha256(p)
        receipts["files"][mode] = rep
        print(f"[build] {p.name}: sha256={rep['sha256'][:16]}… min={rep['min']} max={rep['max']} "
              f"nan={rep['nan_cells']} positives={rep['positive_cells']}")
        np.save(outdir / f"{args.name}-{mode}.npy", arr)

    zp = outdir / f"{args.name}.zip"
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(outdir / f"{args.name}-nan.tif", arcname=f"{args.name}-nan.tif")
    receipts["zip"] = {"path": zp.name, "sha256": sha256(zp), "bytes": zp.stat().st_size}

    write_json(outdir / f"checks-{args.name}.json", receipts)
    print(f"[build] wrote {outdir / f'checks-{args.name}.json'} in {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
