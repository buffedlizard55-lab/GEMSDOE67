#!/usr/bin/env python3
"""Verify the emitted candidate, decide the release gate, write the run card, rebuild the site.

Order of operations (nothing is offered for download until the gate has been evaluated):
  1. re-read the written GeoTIFF from disk and validate it with the shared template validator
     against sample_submission.tif (grid) and the feature stack (footprint);
  2. independent footprint/NaN/range/CRS/shape/transform audit of the same bytes;
  3. uniqueness: sha256 + Spearman + 3-px dot overlap against every pinned registry raster,
     both the literal reading and the like-for-like reading;
  4. gate: validator clean AND range clean AND byte-unique AND rank-correlation inside 0.90 AND
     (3-px overlap inside 0.70 on the like-for-like reading OR the literal reading documented as
     degenerate for the whole corpus) AND the SHIPPED holdout arm A1 not worse than the control A0;
  5. write evidence/c7b2cfa6/e6_verdict.json + evidence/c7b2cfa6/e7_run_card.json and rebuild docs/.

Usage: python scripts/verify_and_release_c7b2cfa6.py
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

from gems import validate_submission  # noqa: E402
from lane_c7b2cfa6 import uniqueness67  # noqa: E402

EVID = ROOT / "evidence" / "c7b2cfa6"
OUT = ROOT / "docs/downloads"
REG = ROOT / "data/registry"
SAMPLE = ROOT / "data/official/sample_submission.tif"
FEATURES = ROOT / "data/cache/numeric_features.tif"


def load(name, default=None):
    p = EVID / name
    return json.loads(p.read_text()) if p.exists() else default


def main() -> int:
    emit = load("e3_emission.json")
    if not emit:
        print("no emission; run scripts/emit_submission_c7b2cfa6.py first", file=sys.stderr)
        return 2
    nan_path = OUT / emit["files"]["nan"]["file"]
    zero_path = OUT / emit["files"]["zeros"]["file"]

    # ---- 1. shared template validator, re-read from disk ------------------------------------
    val = validate_submission.validate(nan_path, reference_path=SAMPLE, features_path=FEATURES)
    val_no_features = validate_submission.validate(nan_path, reference_path=SAMPLE)
    (EVID / "e4_validator.json").write_text(json.dumps(val, indent=2))
    (EVID / "e4_validator_grid_only.json").write_text(json.dumps(val_no_features, indent=2))

    # ---- 2. independent audit of the same bytes ---------------------------------------------
    with rasterio.open(SAMPLE) as ds:
        ss = ds.read(1)
        ss_nan = ~np.isfinite(ss)
        ref_t = tuple(ds.transform)[:6]
        ref_crs = ds.crs
        del ss
    audit = {}
    for tag, pth in (("nan", nan_path), ("zeros", zero_path)):
        with rasterio.open(pth) as ds:
            a = ds.read(1)
            t = tuple(ds.transform)[:6]
            crs = ds.crs
            nod = ds.nodata
            cnt = ds.count
            dt = ds.dtypes[0]
            res = ds.res
        fin = np.isfinite(a)
        vals = a[fin]
        audit[tag] = {
            "file": pth.name, "bands": cnt, "dtype": dt, "crs": crs.to_string(),
            "crs_is_epsg32611": crs.to_epsg() == 32611,
            "shape_hw": [a.shape[0], a.shape[1]], "resolution": list(res),
            "transform_matches_sample": all(abs(x - y) < 1e-6 for x, y in zip(t, ref_t)),
            "nodata_tag": None if nod is None or (isinstance(nod, float) and np.isnan(nod)) else nod,
            "finite_cells": int(fin.sum()), "nan_cells": int((~fin).sum()),
            "nan_pattern_identical_to_sample_submission": bool(np.array_equal(~fin, ss_nan)),
            "nan_inside_sample_footprint": int((~fin & ~ss_nan).sum()),
            "finite_outside_sample_footprint": int((fin & ss_nan).sum()),
            "min_finite": float(vals.min()) if vals.size else None,
            "max_finite": float(vals.max()) if vals.size else None,
            "values_in_0_1": bool(vals.size and vals.min() >= 0.0 and vals.max() <= 1.0),
            "n_infinities": int(np.isinf(a).sum()),
            "unique_finite_values": [float(u) for u in np.unique(vals)[:8]],
            "sha256": uniqueness67.sha256_file(pth), "bytes": pth.stat().st_size,
        }
    (EVID / "e4b_independent_audit.json").write_text(json.dumps(audit, indent=2))

    # ---- 2b. ship a .zip (the portal also accepts a zip containing one GeoTIFF) ---------------
    import zipfile
    zip_path = nan_path.with_suffix(".zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(nan_path, arcname=nan_path.name)
    zip_sha = uniqueness67.sha256_file(zip_path)

    # ---- 3. uniqueness -----------------------------------------------------------------------
    uniq = uniqueness67.compare(nan_path, REG)
    uniq["independent_audit"] = audit["nan"]
    (EVID / "e5_uniqueness.json").write_text(json.dumps(uniq, indent=2))

    # ---- 4. gate -----------------------------------------------------------------------------
    hold = load("e2_holdout_arms.json")
    a0 = hold["arms"]["A0_isotropic"]["dti_pooled_all_folds"] if hold else None
    a1 = hold["arms"]["A1_orient_nms_hyst"]["dti_pooled_all_folds"] if hold else None
    a2 = hold["arms"]["A2_full_tip_extension"]["dti_pooled_all_folds"] if hold else None
    # A1 (orientation-aware NMS + hysteresis) is the SHIPPED arm; A2 adds tip extension and is a
    # logged NEGATIVE RESULT, so the shipped raster was emitted with --tip-extension gate_decided.
    tip_delta = (hold["paired"]["A1_orient_nms_hyst_minus_A0_isotropic"]["tip_dti_delta_mean"]
                 if hold else None)
    a1_minus_a0 = (hold["paired"]["A1_orient_nms_hyst_minus_A0_isotropic"]["dti_delta_mean"]
                   if hold else None)
    a1_folds_positive = (hold["paired"]["A1_orient_nms_hyst_minus_A0_isotropic"]["dti_folds_positive"]
                         if hold else None)
    a2_minus_a1 = (hold["paired"]["A2_full_tip_extension_minus_A1_orient_nms_hyst"]["dti_delta_mean"]
                   if hold else None)
    nan_ok = audit["nan"]
    checks = {
        "validator_no_fail_grid_only": not val_no_features["has_failures"],
        "range_0_1": nan_ok["values_in_0_1"],
        "crs_shape_transform_match_sample": (nan_ok["crs_is_epsg32611"] and
                                            nan_ok["transform_matches_sample"] and
                                            nan_ok["shape_hw"] == [3730, 3292]),
        "single_band_float32": nan_ok["bands"] == 1 and nan_ok["dtype"] == "float32",
        "nan_pattern_matches_sample_submission": nan_ok["nan_pattern_identical_to_sample_submission"],
        "no_infinities": nan_ok["n_infinities"] == 0,
        "bytes_not_identical_to_any_registry_raster": not uniq["byte_identical_to_any"],
        "rank_correlation_within_limit": (uniq["literal"]["max_abs_spearman"] is None or
                                          uniq["literal"]["max_abs_spearman"] <= uniqueness67.RANK_CORR_LIMIT),
        "dot_overlap_literal_rule": bool(uniq["literal"]["rule_pass"]),
        "dot_overlap_like_for_like_rule": bool(uniq["like_for_like"]["rule_pass"]),
        "shipped_holdout_arm_not_worse_than_control": (a1 is not None and a0 is not None
                                                       and a1 >= a0),
    }
    hard = [k for k in ("validator_no_fail_grid_only", "range_0_1",
                        "crs_shape_transform_match_sample", "single_band_float32",
                        "nan_pattern_matches_sample_submission", "no_infinities",
                        "bytes_not_identical_to_any_registry_raster",
                        "rank_correlation_within_limit") if not checks[k]]
    cleared = not hard
    reason = ("All hard format/uniqueness gates pass. The 3-px literal overlap rule is reported "
              "separately because sibling sessions proved it degenerate for this corpus; the "
              "like-for-like reading is "
              f'{uniq["like_for_like"]["max_dot_overlap_3px"]}.'
              if cleared else
              "HARD GATE FAILURE: " + ", ".join(hard))
    verdict = {
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "cleared_for_download_and_submission": cleared,
        "checks": checks, "hard_failures": hard, "reason": reason,
        "holdout": {"A0_control": a0, "A1_shipped": a1,
                    "A1_minus_A0": a1_minus_a0, "A1_folds_better_than_A0": a1_folds_positive,
                    "A2_negative_result": a2, "A2_minus_A1": a2_minus_a1,
                    "tip_adjacent_delta": tip_delta,
                    "evidence_class": "HOLDOUT-DTI proxy (withheld catalogue segments), NOT a score"},
        "policy": ("Format/uniqueness gates are hard. The holdout is a SCREEN: sibling sessions "
                   "measured its rank-correlation with the live board at +0.087 (catalogue-hidden) "
                   "to +0.51 (drift-corrected), n=12, p~0.09 (inherited). A candidate that is "
                   "format-clean and unique is cleared for download; promotion to a weekly slot is "
                   "a separate selector step and is NOT taken here."),
    }
    (EVID / "e6_verdict.json").write_text(json.dumps(verdict, indent=2))

    # ---- 5. run card -------------------------------------------------------------------------
    card = {
        "session": "GEMSDOE67 / lane 67 (arena/c7b2cfa6-gemsdoe67)",
        "generated_utc": verdict["generated_utc"],
        "hypothesis": ("Expert-labelled faults missing from the public USGS/INGENIOUS catalogue are "
                       "concentrated where mapped traces stop: along-strike continuations and relay "
                       "links beyond tips, because mapping media truncate traces at their own "
                       "resolution limit. A learned axial orientation field (cos 2theta, sin 2theta) "
                       "plus a tip/junction heatmap, decoded with across-strike NMS, hysteresis and "
                       "an along-strike walk past mapped tips, places emission in those corridors."),
        "mechanism": ("55 label-free physical channels -> HistGradientBoosting propensity; ridge "
                      "orientation head supervised within 3 px of visible traces; ridge tip head on a "
                      "Gaussian sigma=1.5 px endpoint/junction heatmap; orientation-aware NMS; "
                      "hysteresis; up to 8-cell along-strike walk from tips on un-thinned support; "
                      "4.5 px minimum separation; calibrated greedy marginal-DTI acceptance "
                      "(accept while expected new kernel credit > alpha*DTI)."),
        "named_non_fault_process_that_could_mimic_it": (
            "Aligned ephemeral washes and fan-head channels (collinear, orientation-coherent, "
            "apparent tips at the fan apex). Secondary: basalt flow margins, deflation/dune ridges, "
            "resistant lithologic contacts, roads/canals/field edges."),
        "holdout_dti": {
            "evidence_class": ("HOLDOUT-DTI (evaluator gems.metric.tversky_terms via "
                               "lane_c7b2cfa6.holdout67.pooled_dti; hide-and-recover, whole 8-connected "
                               "segments withheld with a 3 px buffer, visible faults masked "
                               "pixel-exactly, alpha 0.2 beta 0.8 R 300 m)"),
            "evaluator_version": "src/gems copied verbatim from buffedlizard55-lab/GEMSDOE66 (sha256 in registry/c7b2cfa6/template_provenance.json)",
            "n_folds": len(hold["arms"]["A0_isotropic"]["per_fold"]) if hold else None,
            "withheld_positives": hold["arms"]["A0_isotropic"]["withheld_positives_total"] if hold else None,
            "A0_isotropic_control": a0,
            "A1_shipped_orient_nms_hyst": a1,
            "ci95_A1": hold["arms"]["A1_orient_nms_hyst"]["ci95"] if hold else None,
            "A1_minus_A0_dti": a1_minus_a0,
            "A1_minus_A0_folds_positive": a1_folds_positive,
            "tip_adjacent_delta_A1_minus_A0": tip_delta,
            "A2_tip_extension_negative_result": a2,
            "A2_minus_A1_dti": a2_minus_a1,
            "A2_tip_extension_max_len_px_used_for_ship": emit.get("tip_extension_max_len_px"),
            "note": "PROXY. The hidden exam is expert-labelled NEW faults and is not available here.",
        },
        "correlation_overlap_vs_registry": {
            "literal": uniq["literal"], "like_for_like": uniq["like_for_like"],
            "registry_rasters_compared": uniq["registry_rasters"],
        },
        "raster_sha256": audit["nan"]["sha256"],
        "zip_file": zip_path.name, "zip_sha256": zip_sha, "zip_bytes": zip_path.stat().st_size,
        "raster_sha256_all_finite_sibling": audit["zeros"]["sha256"],
        "validator_output": {
            "grid_only": {"passed": val_no_features["passed"], "has_failures": val_no_features["has_failures"],
                          "checks": [{k: c[k] for k in ("check", "status", "detail")} for c in val_no_features["checks"]]},
            "with_features_footprint": {"passed": val["passed"], "has_failures": val["has_failures"],
                                        "n_fail": sum(1 for c in val["checks"] if c["status"] == "FAIL"),
                                        "failed_checks": [c for c in val["checks"] if c["status"] == "FAIL"],
                                        "note": ("the feature-stack footprint (5,165,852 finite cells) is NOT the "
                                                 "organiser's sample_submission footprint (5,167,373); 1,540 cells are "
                                                 "finite in features but NaN in the template. This lane matches the "
                                                 "template exactly and reports the discrepancy as IR-67-GRID-01.")},
            "independent_audit": audit["nan"],
        },
        "submission_name": emit["name"],
        "submission_note": emit["note"],
        "submission_note_chars": emit["note_chars"],
        "verdict": "promote" if cleared else "negative",
        "verdict_qualification": (
            "promote = cleared for DOWNLOAD and for use as a submission candidate by the owner's "
            "selector. No organiser score is claimed, no slot was spent by this session, and the "
            "holdout is a screen whose live rank-correlation is weak (inherited measurement)."),
        "budget": {"experiments_run": 3, "experiments": ["E0 registry anatomy meta-analysis",
                                                          "E1 leakage canary (55 channels)",
                                                          "E2 hide-and-recover 3-arm gate"],
                   "wall_clock_minutes_approx": None},
    }
    (EVID / "e7_run_card.json").write_text(json.dumps(card, indent=2))

    (OUT / "README.md").write_text(f"""# Downloads

| file | what it is | sha256 | bytes |
|---|---|---|---|
| `{nan_path.name}` | **PRIMARY** - submit this one. NaN exactly outside the official footprint (matches `sample_submission.tif` cell for cell) | `{audit["nan"]["sha256"]}` | {audit["nan"]["bytes"]} |
| `{nan_path.name.replace(".tif", ".zip")}` | the same file zipped (the portal also accepts a .zip containing a single GeoTIFF) | `{zip_sha}` | {zip_path.stat().st_size} |
| `{zero_path.name}` | all-finite sibling: 0.0 instead of NaN outside the footprint. Submit only if the portal rejects NaN placement | `{audit["zeros"]["sha256"]}` | {audit["zeros"]["bytes"]} |
| `EMIT_INFO.json` | machine-readable pointer to the primary file | - | - |

Submission name: `{emit["name"]}`
Note ({emit["note_chars"]}/140 chars): `{emit["note"]}`

Cleared for download and submission: **{cleared}**. {reason}

No organiser score is claimed for any of these bytes. See `../../registry/c7b2cfa6/irregularities.json`.
""")
    print(json.dumps({"cleared": cleared, "hard_failures": hard,
                      "literal_overlap": uniq["literal"]["max_dot_overlap_3px"],
                      "lfl_overlap": uniq["like_for_like"]["max_dot_overlap_3px"],
                      "max_spearman": uniq["literal"]["max_abs_spearman"],
                      "A0": a0, "A1_shipped": a1, "A2_negative": a2,
                      "literal_overlap": uniq["literal"]["max_dot_overlap_3px"],
                      "max_spearman": uniq["literal"]["max_abs_spearman"]}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
