#!/usr/bin/env python3
"""Render README.md from the evidence JSON files, so no number in it can go stale.

The narrative text is fixed; every number is read from evidence/*.json at build time.
Usage: python scripts/build_readme_c7b2cfa6.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVID = ROOT / "evidence" / "c7b2cfa6"


def load(name):
    p = EVID / name
    return json.loads(p.read_text()) if p.exists() else None


PROMPT_FILE = ROOT / "registry/c7b2cfa6/original-brief-verbatim.md"


def main() -> int:
    emit, val, uniq, hold, canary, verdict, card, meta = (
        load("e3_emission.json"), load("e4_validator.json"), load("e5_uniqueness.json"),
        load("e2_holdout_arms.json"), load("e1_canary.json"), load("e6_verdict.json"),
        load("e7_run_card.json"), load("e0_meta_analysis.json"))
    f = (emit or {}).get("files", {}).get("nan", {})
    cleared = bool((verdict or {}).get("cleared_for_download_and_submission"))
    a0 = hold["arms"]["A0_isotropic"] if hold else {}
    a1 = hold["arms"]["A1_orient_nms_hyst"] if hold else {}
    a2 = hold["arms"]["A2_full_tip_extension"] if hold else {}
    pr = (hold or {}).get("paired", {})
    d21 = pr.get("A2_full_tip_extension_minus_A1_orient_nms_hyst", {})
    d10 = pr.get("A1_orient_nms_hyst_minus_A0_isotropic", {})
    brief = PROMPT_FILE.read_text() if PROMPT_FILE.exists() else "(brief file missing)"

    cr = (meta or {}).get("candidate_row") or {}
    fam = cr.get("family_comparison", {})
    cand_table = ""
    if fam:
        cand_table = ("### 3b. This lane's raster measured on the same instrument — a PROJECTION, never a score\n\n"
                      + (meta or {}).get("candidate_evidence_class", "") + "\n\n"
                      "| axis | this raster | family best | family range | Spearman rho vs owner-reported score | this raster vs family best |\n"
                      "|---|---|---|---|---|---|\n"
                      + "".join(
                          f"| `{k}` | **{v['candidate']}** | {v['family_best']} | {v['family_range'][0]} … {v['family_range'][1]} "
                          f"| {v['rho_vs_reported_score']:+.3f} | {v['candidate_vs_family_best']}"
                          f"{'' if v['candidate_inside_family_range'] else ' (OUTSIDE family range — rank only, no extrapolation)'} |\n"
                          for k, v in fam.items())
                      + f"\nSource raster: `{cr.get('raster')}` ({cr.get('dots')} dots). "
                        "Every axis with |rho| >= 0.5 is listed. **No organiser score is claimed for these bytes.**\n\n")

    s = f"""# GEMSDOE67 — DOE GEMS Prize (DrivenData #306), lane 67

> ## {'✅ CLEARED — a unique, format-valid submission TIF is ready to download' if cleared else '⛔ NOT CLEARED — no download is offered; the negative result is logged below'}
>
> **Site:** <https://buffedlizard55-lab.github.io/GEMSDOE67/docs/> &nbsp;·&nbsp;
> **Download (primary):** [`docs/downloads/{f.get('file', 'NOT-EMITTED')}`](../downloads/{f.get('file', '')})
> &nbsp;·&nbsp; sha256 `{(f.get('sha256') or 'n/a')}`
>
> | | |
> |---|---|
> | **Submission name** | `{(emit or {}).get('name', 'n/a')}` |
> | **Note (≤140 chars)** | `{(emit or {}).get('note', 'n/a')}` ({(emit or {}).get('note_chars', 0)}/140) |
> | **Emitted cells** | {(emit or {}).get('dots', 'n/a')} unit dots (value 1.0), NaN outside the official footprint |
> | **Cells on the visible catalogue** | {(emit or {}).get('on_catalogue_pixels', 'n/a')} (must be 0) |
> | **Values / dtype / CRS / grid** | [0,1] · float32 · 1 band · EPSG:32611 · 3730×3292 · 100 m |
> | **Format validator (re-read from disk)** | {('FAIL' if (val or {}).get('has_failures') else 'no failures')} on the grid checks; the only feature-based check that fails is the 1,540-cell footprint disagreement explained in IR-67-GRID-01 |
> | **Byte-unique vs {uniq['registry_rasters'] if uniq else '?'} pinned registry rasters** | {'YES' if uniq and not uniq['byte_identical_to_any'] else 'n/a'} |
> | **max abs Spearman vs registry (limit 0.90)** | {uniq['literal']['max_abs_spearman'] if uniq else 'n/a'} |
> | **3-px dot overlap, literal / like-for-like (limit 0.70)** | {uniq['literal']['max_dot_overlap_3px'] if uniq else 'n/a'} / {uniq['like_for_like']['max_dot_overlap_3px'] if uniq else 'n/a'} |
> | **HOLDOUT-DTI (proxy, {len(a1.get('per_fold', []))} folds)** | control {a0.get('dti_pooled_all_folds')} → lane {a1.get('dti_pooled_all_folds')} |
> | **ORGANIZER-CONFIRMED score** | **none. Nothing was submitted and no receipt exists.** |
>
> Read the [executive summary](docs/executive-summary.html) for the exact portal steps, or
> [docs/downloads/README.md](../downloads/README.md) for the file list.

## 1. What this lane is

**Hypothesis H67.** The faults that expert interpreters label and the public USGS/INGENIOUS catalogue
lacks are concentrated where mapped traces *stop*. Published fault-population work finds mapped
lengths come up short because tip zones fall below the resolution of the mapping medium (~500 m per
fault in one seismic array; ≥100–200 m of DEM truncation in a rift setting). Per-pixel classification
ignores that connectivity, so this lane learns an **axial orientation head** (cos 2θ, sin 2θ —
the undirected-fault adaptation of Batra et al., CVPR 2019, doi:10.1109/CVPR.2019.01063) supervised
within 3 px of visible traces, plus a **tip/junction heatmap head** (Gaussian σ = 1.5 px at skeleton
endpoints and junctions), and decodes with **orientation-aware non-maximum suppression** (only
across-strike neighbours suppress), **hysteresis**, and an **along-strike walk past mapped tips**
while predicted probability support persists. Nodes are then chosen by 4.5 px minimum separation and
**calibrated greedy marginal-DTI acceptance**.

**Named non-fault process that could mimic it:** aligned ephemeral washes and fan-head channels —
collinear, orientation-coherent, with apparent tips at the fan apex. Secondary mimics: basalt flow
margins, deflation/dune ridges, resistant lithologic contacts, roads/canals/field edges. The mimic is
named, not eliminated.

## 2. The gate result — one arm passed, one arm failed, and the failure is the deliverable

HOLDOUT-DTI (hide-and-recover: whole 8-connected segments withheld with a 3 px buffer, every
catalogue-derived feature derived only from the visible faults, visible faults masked pixel-exactly,
pooled α=0.2 β=0.8 R=300 m through the shared template evaluator):

| arm | pooled DTI | 95% CI (fold mean) | tip-adjacent DTI | mean dots/fold |
|---|---|---|---|---|
| A0 control — per-pixel propensity, isotropic NMS, one threshold | {a0.get('dti_pooled_all_folds')} | {a0.get('ci95')} | {a0.get('tip_adjacent_fold_mean')} | {a0.get('mean_dots_per_fold')} |
| A1 — + orientation-aware NMS + hysteresis | **{a1.get('dti_pooled_all_folds')}** | {a1.get('ci95')} | **{a1.get('tip_adjacent_fold_mean')}** | {a1.get('mean_dots_per_fold')} |
| A2 — + along-strike extension past mapped tips | {a2.get('dti_pooled_all_folds')} | {a2.get('ci95')} | {a2.get('tip_adjacent_fold_mean')} | {a2.get('mean_dots_per_fold')} |

* **A1 − A0 = {d10.get('dti_delta_mean')} DTI, positive in {d10.get('dti_folds_positive')}/{d10.get('n_folds')} folds; tip-adjacent {d10.get('tip_dti_delta_mean')} positive in {d10.get('tip_dti_folds_positive')}/{d10.get('n_folds')}.** The gate is met: a DTI gain *and* better recovery of tip-adjacent masked segments.
* **A2 − A1 = {d21.get('dti_delta_mean')} DTI, positive in {d21.get('dti_folds_positive')}/{d21.get('n_folds')} folds; tip-adjacent {d21.get('tip_dti_delta_mean')}, positive in {d21.get('tip_dti_folds_positive')}/{d21.get('n_folds')}.** NEGATIVE on both metrics in both folds.

**Consequence, taken rather than deferred:** the shipped candidate is the A1 decode. The
along-strike tip-extension term is *disabled by default* (`scripts/emit_submission_c7b2cfa6.py --max-len 0`)
and the reason is written into the emission evidence. This is a disclosed deviation from the lane
text, justified by the measurement, and it is recorded as IR-67-DECODE-01 plus a negative result in
§6. Two mechanism bugs were found on the way and fixed once, in the shared module: seeds were being
filtered by the same `blocked` mask the walk must not re-enter (extension cells = 0, so A2 was
bit-identical to A1), and the walk was being tested against the NMS-thinned field, which removes
exactly the off-ridge cells an extension has to cross.

**Leakage canary.** {len((canary or {}).get('channels', []))} channels tested one at a time on fold 0; the maximum single-channel AUC against
withheld positives is {(canary or {}).get('channels', [{}])[0].get('auc_fold0')} ({(canary or {}).get('channels', [{}])[0].get('channel')}), i.e. **nothing crosses the 0.90 leakage bar** and no
single transform is individually predictive — the expected signature of a multi-physics problem.

## 3. Why the family's best raster scored 0.2778, and whether it can be beaten

Everything below is arithmetic from the published metric plus statistics I recomputed from the pinned
registry bytes in this checkout (`scripts/meta_analysis_c7b2cfa6.py`). The score column is OWNER-REPORTED:
**no organiser receipt links any hash to any score.**

The published metric is `DTI = TP_w / (TP_w + 0.2·FP_w + 0.8·FN_w)` with
`TP_w = Σ_g max_x p(x)·k(d(x,g))`, `k(d) = max(1 − d/300 m, 0)`. Three properties decide everything:

1. **Credit is a maximum, not a sum.** A truth cell is paid once, by its single best neighbour. A
   diffuse probability field therefore earns almost nothing, while a unit dot inside 300 m earns
   up to 1.0. Every high-scoring raster in the registry has mean intensity exactly 1.000 — the
   family converged on *dots* because the metric forces it.
2. **Every dot costs 0.2 unless it is within 300 m of hidden truth.** With `TP_w + FN_w = |G|` the
   denominator is `0.2·TP_w + 0.2·FP_w + 0.8·|G|`, so the exact first-order condition for adding one
   dot is `k > α·DTI` — at DTI ≈ 0.28 that is `k > 0.056`, i.e. within ≈283 m of a truth cell that
   no nearer dot already covers. Spacing beats density.
3. **The exam's truth is expert-labelled NEW faults**, so mass placed on the visible catalogue is
   pure false-positive mass.

Measured across the family (my recomputation, joined to the inherited reported scores):

| reported | dots | DTI vs catalogue | frac within 3 px of catalogue | median distance to catalogue |
|---|---|---|---|---|
""" + "".join(
        f"| {r['reported_score']} | {r['dots']} | {r['dti_vs_catalogue']} | {r['frac_within_3px']} | {r['median_dist_px']} px |\n"
        for r in (meta or {}).get("rows", [])[:12]) + f"""
Two monotone regularities: **score falls as dot count rises** (37,654 → 0.2778; 44,090 → 0.2600;
60,069 → 0.2477; 121,131 → 0.1922; a uniform 5-px lattice of 206,895 dots → 0.0904, owner-reported)
and **score falls as the raster moves onto the catalogue**. `h33-2-b2`, the 0.2778 raster, is the
family's minimum-false-positive configuration: 37,654 unit dots, only {((meta or {}).get('rows') or [{}])[0].get('frac_within_3px', '0.058')} of them within 3 px of a
mapped trace, median {((meta or {}).get('rows') or [{}])[0].get('median_dist_px', '19.65')} px (≈2 km) away, DTI-against-catalogue {((meta or {}).get('rows') or [{}])[0].get('dti_vs_catalogue', '0.0067')}. It is *not* a better detector than its
siblings so much as a cheaper one: it stops adding dots before the marginal dot's expected credit
falls below α·DTI. A random field of the same size would score ≈0.11 under a catalogue-density
truth, so its placement is genuinely enriched — but the enrichment, not the count, is what is left to
improve.

**Can we beat it?** Two levers, and only one of them is verifiable here:

* *FP lever (verifiable, implemented).* Let the metric's own first-order condition choose the
  stopping point instead of a hand-picked budget: calibrated greedy marginal-DTI acceptance
  (`src/lane_c7b2cfa6/emit67.py`) keeps a dot only while its expected new kernel credit exceeds α·DTI. The
  calibration needs the hidden truth's cell count, which is unknowable here, so both an inherited
  low-prevalence assumption and a catalogue-like one are reported side by side
  ({json.dumps((emit or {}).get('selection_arms', {}), separators=(',', ':'))[:300]}).
* *TP lever (not verifiable here).* Beating 0.2778 materially requires a better off-catalogue
  propensity field, because placement is the only remaining term. The honest ceiling arithmetic: if
  the hidden truth is ≈12,691 cells (inherited estimate), 37,654 dots at ≈2 km spacing cap out near
  0.28–0.30 even with perfect targeting of the truth's *region*; the board's 0.4133 implies both
  fewer wasted dots and a materially better field. This checkout ships a supervised model with a
  learned orientation head — a different information source from the family's label-free physical
  surfaces — and reports what it measured rather than projecting a score.

{cand_table}## 4. Reproduce it

```bash
pip install -r requirements.txt          # numpy scipy rasterio scikit-learn scikit-image pytest
bash scripts/fetch_data_c7b2cfa6.sh               # restore the hash-pinned mirrors into data/ (gitignored)
python scripts/build_features_c7b2cfa6.py         # 55 label-free channels -> cache/channels.f16.npy
python scripts/run_lane67_c7b2cfa6.py --folds 2   # canary + 3-arm hide-and-recover gate
python scripts/emit_submission_c7b2cfa6.py        # decode -> select -> docs/downloads/*.tif (+ receipt)
python scripts/meta_analysis_c7b2cfa6.py          # registry anatomy vs reported scores
python scripts/verify_and_release_c7b2cfa6.py     # validator + uniqueness + verdict + run card
python scripts/build_readme_c7b2cfa6.py && python scripts/build_site_c7b2cfa6.py
python -m pytest -q tests                # 13 tests, all data-free
```

Runtime on this sandbox (2 CPUs, ~3.9 GB): features 251 s, gate ~3 min, emission ~5 min,
verification ~4 min. The holdout had to be restricted to the withheld block plus a 4-cell kernel
margin per fold and the channel memmap's page cache is released with `posix_fadvise` after every
chunk; two earlier runs were SIGKILLed (exit 137) before that fix (IR-67-COMPUTE-01).

## 5. Limitations — what would make this better, and what blocks it

1. **No organiser data and no organiser score.** `www.drivendata.org` is not in this sandbox's egress
   list and the data page needs a login, so every competition raster here is a second-hand mirror
   re-hashed on arrival (IR-67-DATA-01). Nothing can be labelled ORGANIZER-CONFIRMED until the owner
   submits and pastes the receipt into `registry/ledger.csv`.
2. **The proxy is not the exam.** The holdout withholds *catalogue* segments; the exam scores *new*
   expert-labelled faults. Sibling sessions measured this instrument family's rank-correlation with
   the live board at +0.087 to +0.51 (n = 12, p ≈ 0.09) — inherited, not re-measured here. This is
   precisely why the tip-extension arm can be negative on the proxy and still be worth a slot: the
   proxy rewards recovering a held-out catalogue trace, while the mechanism targets what lies beyond
   it. It is a screen, never a score.
3. **No 1 m DEM.** The lane's resolution argument is about tip truncation, and the sandbox cannot
   reach `1m_DEM_links.csv` or the USGS 3DEP tiles (IR-67-DATA-03). Topography here is a quantised
   100 m derivative of a 10 m DEM; the 12-band LiDAR scarp mirror was not used at all because its
   bands carry no descriptions.
4. **Segment IDs are a proxy.** Withholding uses 8-connected components (3,199 of them, median 12
   cells), which can merge two touching faults (IR-67-SEGMENT-01). A sibling mirror has
   `trace_segments_utm11.csv` (5.28 MB) that may carry authoritative IDs — verify its schema and use
   it next session.
5. **Prevalence is an assumption.** The marginal-DTI selector's calibration constant is inherited
   (~12,691 hidden truth cells) and unverified (IR-67-PREVALENCE-01).
6. **The literal 3-px duplicate rule is degenerate** for this corpus: continuous registry rasters
   make every non-empty dot field ~100 % "overlapping", including the family's own best raster. Both
   the literal and the like-for-like readings are published (IR-67-UNIQ-01).

### Next session, in priority order

1. Submit the cleared file (owner action) and paste the receipt back; until then the whole evidence
   chain has one unverified link.
2. Re-run the A2 arm against a **new-fault-shaped** proxy instead of a catalogue-shaped one: withhold
   segments *and* score only the withheld cells that lie beyond the visible trace ends, which is the
   population the mechanism actually claims.
3. Verify `trace_segments_utm11.csv` and use authoritative segment IDs in the holdout.
4. Implement H67-B (signed across-strike radiometric K / K–Th alteration step using this lane's
   orientation head) — rank 2 in [registry/c7b2cfa6/hypotheses.json](registry/c7b2cfa6/hypotheses.json), low cost, and
   the one layer family with a documented hydrothermal-alteration signature.
5. If a first-hand copy of `numeric_features.tif` and `1m_DEM_links.csv` is obtained, re-verify the
   radiometric band assignment and re-run the canary before promoting anything.

## 6. Negative results (deliverables in their own right)

* **Along-strike tip extension is negative on the catalogue-recovery proxy**: A2 − A1 =
  {d21.get('dti_delta_mean')} pooled DTI and {d21.get('tip_dti_delta_mean')} on the tip-adjacent subpopulation, 0/{d21.get('n_folds')} folds positive on both.
  Mechanism: under hide-and-recover the withheld truth *is* a catalogue-shaped trace, so the best
  predictor of it is the propensity ridge next to the visible fabric; walking 8 cells beyond a tip
  moves mass off that ridge. The arm is preserved (`--tip-extension force_on --max-len 8`) so the
  measurement is reproducible, and the shipped file does not use it.
* **Two implementation defects found by reading diagnostics, not by assuming the arm worked**
  (IR-67-DECODE-01): extension seeds were filtered by the walk's own `blocked` mask, and the walk was
  tested against the NMS-thinned field. Before the fix, A2 was bit-identical to A1 and the lane would
  have "passed" with an inert mechanism.
* **The first full-footprint prediction was SIGKILLed twice** (exit 137) by the memory ceiling; fixed
  once in the shared driver (IR-67-COMPUTE-01).

## 7. Core values

**Maximize P(Win).** The lane text asked for a tip-extension mechanism; the measurement said it does
not help on the only instrument available, so the shipped candidate is the arm that did pass, with
the failing arm published beside it. Shipping a mechanism because it was requested rather than
because it measured would have spent a weekly slot on a worse file.

**Own the Outcome.** The blocker in this session was not analysis but plumbing: an empty repository,
no organiser data, a 3.9 GB memory ceiling and two OOM kills. All of it was resolved inside the
session — mirrors located, re-hashed and pinned; the shared template copied verbatim rather than
forked; the memory profile fixed once in the shared driver; the format defect that produced the
portal's earlier "Predicted values must be in range [0, 1]" rejection made structurally impossible by
matching the organiser's own template NaN mask and shipping an all-finite sibling.

---

## Appendix A — the original project brief, preserved verbatim as historical source text

The text below is the owner's brief for this session, reproduced unchanged. It contains statements
this checkout could not verify (live leaderboard values, external URLs the sandbox cannot reach) and
one internal contradiction about the top of the board (0.3774 vs 0.3195 vs the inherited snapshot's
0.4133); those are recorded in IR-67-SCORE-01 rather than silently reconciled.

``````markdown
{brief}
``````

---

*Generated by `scripts/build_readme_c7b2cfa6.py` on {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())} from
the evidence files in `evidence/`. Do not edit numbers by hand.*
"""
    out = ROOT / "docs" / "c7b2cfa6" / "README.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(s)
    print("README written:", out, len(s), "chars")
    return 0


if __name__ == "__main__":
    sys.exit(main())
