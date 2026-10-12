"""Build the unique GEMSDOE67 submission raster (orientation + tip lane).

Pipeline (live, all faults visible):

1. fit the three heads on the full mapped catalogue;
2. predict segmentation / axial orientation / tip heat;
3. decode with orientation-gated hysteresis + orientation-aware NMS;
4. extend traces past mapped tips along predicted orientation where support
   persists (lane brief; tip under-mapping: ~500 m per fault in published
   seismic-array studies, 100-200 m DEM truncation in rift studies);
5. flank-prune candidates within 2 px of the mapped catalogue (h33 lesson),
   protecting tip-extension pixels;
6. select nodes by calibrated greedy marginal-DTI allocation (shared
   ``gems57.emit.greedy_allocate``);
7. write with the shared ``gems57.submission_writer`` (fail-closed, all-finite
   float32, EPSG:32611, 100 m, zeros outside footprint, no nodata tag).

The output name and note are deterministic from the arm and dot count.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gems57 import grid as gridmod, submission_writer  # noqa: E402
from gems67 import features as featmod, heads as headsmod, lane as lanemod  # noqa: E402

NOTE_MAX = 140


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", default="data/raw/gems-geodawn-numerical-features.tif")
    ap.add_argument("--arm", default="lane", choices=["lane", "lane_blur"])
    ap.add_argument("--emission", default="greedy", choices=["greedy", "spacing"])
    ap.add_argument("--out-dir", default="artifacts/h67a-orientip")
    ap.add_argument("--k-truth", type=float, default=None)
    ap.add_argument("--tag", default=None)
    args = ap.parse_args()

    t0 = time.time()
    repo = Path(__file__).resolve().parents[1]
    g = gridmod.load_grid(repo / "data" / "bridge")
    cache = featmod.build_cache(Path(args.features), repo / "data" / "cache" / "features67.f32",
                                g.footprint)
    print(f"grid {g.shape}; catalogue {int(g.catalogue.sum())} px; "
          f"footprint {int(g.footprint.sum())} px", flush=True)

    heads = headsmod.fit_heads(cache, g.catalogue)
    print("heads fitted:", heads.fit_receipt, flush=True)
    preds = headsmod.predict_full(cache, heads)

    params = {}
    if args.k_truth is not None:
        params["k_truth"] = args.k_truth
    res = lanemod.run_arm(args.arm, cache, g.catalogue, g.footprint, heads=heads,
                          preds=preds, params=params, emission=args.emission)
    print(f"arm {args.arm}: dots={res.n_dots} support={int(res.support.sum())} "
          f"extensions={int(res.extended.sum())}", flush=True)

    # final raster: 1.0 at selected nodes, 0.0 elsewhere inside the footprint
    pred = np.zeros(g.shape, np.float32)
    pred[res.emitted] = 1.0

    tag = args.tag or time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    stem = f"gems67-h67a-orientip-{args.arm}-{res.n_dots}dots-{tag}"
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    tif_path = out_dir / f"{stem}-allfinite.tif"

    name = f"GEMSDOE67-H67A-ORIENTIP-{args.arm.upper()}"
    note = (f"GEMSDOE67 orientation+tip lane {args.arm}: {res.n_dots} dots, "
            f"{int(res.extended.sum())} tip-extension px; greedy DTI-gated; "
            f"HOLDOUT-GATED; UNSCORED")
    if len(note) > NOTE_MAX:
        note = note[:NOTE_MAX - 3] + "..."
    assert len(name) <= 140 and len(note) <= NOTE_MAX

    receipt = submission_writer.write_submission(
        tif_path, pred, repo / "data" / "bridge" / "sample_submission.tif",
        g.footprint, note=note, name=name, catalogue=g.catalogue,
        metadata=dict(lane="orientation+tip heads (Batra et al. 2019 adaptation)",
                      arm=args.arm, emission=args.emission,
                      params=lanemod.PARAMS | params,
                      support_px=int(res.support.sum()),
                      extension_px=int(res.extended.sum()),
                      fit_receipt=heads.fit_receipt,
                      built_utc=tag, elapsed_s=round(time.time() - t0, 1)),
    )
    meta = dict(file=tif_path.name, sha256=receipt["sha256"],
                zip_file=receipt["zip_file"], zip_sha256=receipt["zip_sha256"],
                name=name, note=note, n_dots=res.n_dots, arm=args.arm,
                emission=args.emission, built_utc=tag)
    (out_dir / f"{stem}-meta.json").write_text(json.dumps(meta, indent=1) + "\n")
    print(json.dumps(meta, indent=1), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
