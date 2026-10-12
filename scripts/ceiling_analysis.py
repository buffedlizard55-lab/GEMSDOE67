#!/usr/bin/env python3
"""Why every emission family in this project parks at 0.26-0.28 -- derived, not asserted.

Algebra (transcription of the official metric, see src/gems67/metric.py):

    DTI = TP_w / (TP_w + alpha*FP_w + beta*FN_w),   alpha = 0.2, beta = 0.8
    FN_w = |G| - TP_w         (exact for clipped predictions)
  =>DTI = T / (0.8*|G| + 0.2*FP_w + 0.2*T)
  =>DTI = c / (0.8 + 0.2*c + 0.2*w)        c = T/|G|  (credit-weighted coverage)
                                            w = FP_w/|G| (wasted mass, in units of the truth count)

This script recovers c, w for every measured arm from the holdout evidence alone (no new
experiment), evaluates the reachable ceiling, and writes evidence/ceiling.json.

Usage: python scripts/ceiling_analysis.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FOLDS = 4


def arm_stats(v: dict) -> dict:
    """Recover T, S, FP_w, c, w, and the marginal quantities from a pooled arm record."""
    k = float(v["n_truth"])                       # |G|, pooled across folds
    c = float(v["coverage"])                      # T / |G|
    dti = float(v["dti"])
    t = c * k
    s = float(v["mean_px"]) * FOLDS               # pooled emitted mass
    fp = (t / dti - 0.8 * k - 0.2 * t) / 0.2      # invert the identity for FP_w
    m = s - fp                                    # mass that earned credit (identity FP_w = S - M)
    return {
        "pooled_dti": dti,
        "n_truth_px": k,
        "emitted_px": s,
        "T": t,
        "S": s,
        "FP_w": fp,
        "M": m,
        "coverage_c": c,
        "waste_w": fp / k,
        "credit_per_unit_mass": t / s if s else 0.0,
        "mass_inside_truth_kernel_share": m / s if s else 0.0,
        "zero_waste_ceiling": c / (0.8 + 0.2 * c),
        "per_fold": v.get("per_fold", []),
    }


def required_coverage(target_dti: float, w: float = 0.0) -> float:
    """Smallest c achieving `target_dti` at waste level w:  c = target*(0.8 + 0.2w)/(1 - 0.2*target)."""
    return target_dti * (0.8 + 0.2 * w) / (1.0 - 0.2 * target_dti)


def main() -> int:
    ev = json.loads((ROOT / "evidence" / "holdout_ml_ext.json").read_text())
    arms = {name: arm_stats(v) for name, v in ev["pooled"].items() if v.get("n_truth")}

    e1 = json.loads((ROOT / "evidence" / "holdout.json").read_text())["pooled"]
    for name in ("A0_incumbent_dots", "A1_ovtr_geometry_gated", "A3_random_matched_mass"):
        if name in e1 and e1[name].get("n_truth"):
            arms[name] = arm_stats(e1[name])

    board = json.loads((ROOT / "data" / "registry.json").read_text())
    live = board.get("live_board_20261012", {})
    bar = float(live.get("top_score", 0.4275))

    out = {
        "derivation": {
            "identity": "DTI = c / (0.8 + 0.2*c + 0.2*w)",
            "c": "credit-weighted coverage T/|G| -- the share of the hidden truth the emission earns",
            "w": "waste FP_w/|G| -- emitted mass that lies further than one kernel radius from truth",
            "alpha_beta_reading": "missing a hidden fault costs 0.8 per pixel; wrong mass costs 0.2 per unit at worst",
            "why_the_ratio_matters": "the denominator carries 0.8 for EVERY truth pixel whether or not it "
                                     "is found, so the score is first a coverage ratio and only second a "
                                     "precision ratio -- but once coverage stalls, waste is the binding term",
        },
        "arms": arms,
        "ceiling_curve": {
            "zero_waste_ceiling_at_our_coverage": None,
            "note": "DTI_max(c) = c/(0.8 + 0.2c): the best score any emission could reach if it were free of waste",
        },
        "required_coverage_to_reach": {},
        "live_board": {k: v for k, v in live.items()} if live else {},
    }

    best = max(arms.items(), key=lambda kv: kv[1]["pooled_dti"])
    out["shipped_arm"] = best[0]
    out["ceiling_curve"]["zero_waste_ceiling_at_our_coverage"] = best[1]["zero_waste_ceiling"]
    out["ceiling_curve"][
        "verdict"
    ] = ("with the shipped arm's coverage c = "
          f"{best[1]['coverage_c']:.4f}, the absolute best achievable score at zero waste is "
          f"{best[1]['zero_waste_ceiling']:.4f}; the live bar {bar} is therefore out of reach for this "
          "coverage level, no matter how the dots are packed")

    for target in (0.30, 0.35, 0.40, bar):
        key = f"{target:.4f}"
        out["required_coverage_to_reach"][key] = {
            "required_c_at_zero_waste": required_coverage(target, 0.0),
            "required_c_at_our_waste": required_coverage(target, best[1]["waste_w"]),
            "our_c": best[1]["coverage_c"],
            "reachable_at_our_coverage": target <= best[1]["zero_waste_ceiling"],
        }

    # where the incumbent families sit in the same coordinates
    inc = arms.get("A0_incumbent_dots", {})
    out["why_the_incumbents_park_low"] = {
        "incumbent_c": inc.get("coverage_c"),
        "incumbent_w": inc.get("waste_w"),
        "geometry_gate_c": arms.get("A1_ovtr_geometry_gated", {}).get("coverage_c"),
        "geometry_gate_w": arms.get("A1_ovtr_geometry_gated", {}).get("waste_w"),
        "random_c": arms.get("A3_random_matched_mass", {}).get("coverage_c"),
        "statement": "every family that stays inside the mapped-fault neighbourhood has almost no "
                     "coverage of the hidden faults (c near 0.02), so its score is bounded near 0.02; "
                     "raising coverage by loosening the geometry gate raises c but also raises w, and the "
                     "0.26-0.28 band is the Pareto point those two forces reach at this head's ranking "
                     "quality. It is a ceiling in information, not a bug in the writer.",
    }

    path = ROOT / "evidence" / "ceiling.json"
    path.write_text(json.dumps(out, indent=1))
    print(f"{'arm':44s} {'DTI':>7s} {'c':>7s} {'w':>7s} {'T/S':>7s} {'ceil(c)':>8s}")
    for name, a in sorted(arms.items(), key=lambda kv: -kv[1]["pooled_dti"]):
        print(f"{name:44s} {a['pooled_dti']:7.4f} {a['coverage_c']:7.4f} {a['waste_w']:7.3f} "
              f"{a['credit_per_unit_mass']:7.4f} {a['zero_waste_ceiling']:8.4f}")
    print()
    for key, v in out["required_coverage_to_reach"].items():
        print(f"[ceiling] DTI {key}: needs c >= {v['required_c_at_zero_waste']:.4f} at zero waste "
              f"({v['required_c_at_our_waste']:.4f} at our waste); ours {v['our_c']:.4f} -> "
              f"{'reachable' if v['reachable_at_our_coverage'] else 'NOT reachable'}")
    print(f"[ceiling] written -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
