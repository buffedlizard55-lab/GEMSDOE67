# GEMSDOE67 — orientation + tip heads with geometry-aware decoding

**DOE GEMS Prize (DrivenData #306) fault-discovery lane.** Find geothermal-indicative
faults *missing* from the USGS/INGENIOUS catalogue in the GeoDAWN survey area
(NW Nevada, EPSG:32611) and ship them as a legal GeoTIFF.

> **Read the master prompt at the bottom of this README before every work session.**
> It is the standing brief for this project. Core values: **Maximize P(Win)** and
> **Own the Outcome**.

---

## ⬇ One-click submission file

See **[the site's executive summary](docs/index.html)** — the download button, the
OK-TO-SUBMIT gate, and the exact name/note to paste are at the very top. The page
makes it obvious whether the current file is cleared to download and submit.

- Format contract (verified byte-level by `scripts/validate_submission.py`):
  single-band float32 GeoTIFF · EPSG:32611 · 100 m · 3292×3730 · every cell finite ·
  every value in [0, 1] · zeros outside the footprint · no nodata tag ·
  **this convention cannot trigger the portal error
  "Predicted values must be in range [0, 1]"** (the two mechanisms that cause it
  are documented on the site).
- A sample-faithful twin (NaN outside the footprint, NaN nodata) is also generated.

## What this repository is

1. **A lane, not a fork.** The shared template `gems57` (metric, buffered
   hide-and-recover holdout, pooled evaluator, fail-closed submission writer,
   uniqueness audit) is vendored **byte-identical** to the family's 60GEMSDOE pin.
   This repo adds one lane: stacked **segmentation / axial-orientation / tip heads**
   (Batra et al., CVPR 2019, doi:10.1109/CVPR.2019.01063, adapted to undirected
   faults with cos 2θ / sin 2θ), decoded with orientation-gated hysteresis,
   orientation-aware NMS, and tip extension past mapped tips along predicted
   strike where probability support persists.
2. **An evidence-first experiment record.** Every number is labelled
   **HOLDOUT-DTI** (evaluator `gems57-pooled-hide-v2`, withheld-pixel counts, 95% CI)
   or **ORGANIZER-CONFIRMED** (copied from a submission-page receipt). Projections
   are labelled MODEL and are never written as scores.
3. **A submission factory.** `scripts/build_submission.py` → shared writer →
   `scripts/validate_submission.py` → `scripts/check_uniqueness.py` → site.
   The download is offered only when the gate passes; negative results are logged
   as deliverables.

## Pipeline (no manual steps)

```bash
bash scripts/download_competition_data.sh     # or the git data bridge (see script)
python scripts/prepare_data.py                # sha256-pin verify + stage to data/bridge
PYTHONPATH=src python scripts/run_experiments.py   # E1 ablation / E2 lane / E3 blur + canary
PYTHONPATH=src python scripts/build_submission.py  # live raster, fail-closed writer
PYTHONPATH=src python scripts/validate_submission.py artifacts/h67a-orientip/*.tif
PYTHONPATH=src python scripts/check_uniqueness.py artifacts/h67a-orientip/*.tif
PYTHONPATH=src python scripts/build_site.py        # regenerate docs/
```

## Status of the current candidate

| item | value | class |
|---|---|---|
| pooled HOLDOUT-DTI (lane) | 0.03757 [0.02456, 0.04962] | HOLDOUT-DTI, evaluator `gems57-pooled-hide-v2`, 22,893 withheld + px |
| paired Δ vs per-pixel ablation | +0.00964 [+0.00394, +0.01543] | HOLDOUT-DTI, paired physical-block bootstrap |
| tip-adjacent coverage (lane vs iso) | 0.04257 vs 0.02725 (+56% rel., 7,854 tip-adjacent px) | HOLDOUT-DTI |
| leakage canary (feature-alone AUC) | worst = dist_to_visible 0.894 / 0.865 (bar 0.90) — pass, monitored (IR-67-CANARY-01) | HOLDOUT-DTI |
| format preflight | PASS on all checks (receipt: `evidence/validate_primary.json`) | local |
| uniqueness vs local registry | byte-unique · pixel-unique · \|ρ\|≤0.036 (dots) / 0.112 (surface) · honest forward overlap max 0.54 < 0.70 · one halo-saturated witness disclosed (IR-67-DUP-01) | local scope (78 rasters) |
| raster | `gems67-h67a-orientip-lane-29447dots-20261012T021226Z-allfinite.tif` sha256 `9088ee17…` · 29,447 dots · 38,758 tip-extension px | local |
| leaderboard | no score claimed here | ORGANIZER-CONFIRMED values live only on the DrivenData page |

**Honesty note.** Absolute HOLDOUT-DTI of this instrument is *not* comparable to
leaderboard scores or to the family's catalogue-proxy figures (different truth,
different budgets). Only paired contrasts at matched settings are meaningful.

## Known irregularities (flagged for review)

- **IR-67-LB-01** — the session brief quotes 0.3195 as the current leaderboard
  high; the family's stored read (2026-10-04) shows #1 nchuzhoy **0.3262** and
  #2 DARD 0.3195. Re-check the live page before quoting either number.
- **IR-67-SRC-01** — the UCD Fault Analysis Group TSG-2008 abstract URL (DEM
  truncation of fault tips) is cited in the lane brief but could not be
  machine-verified from this sandbox; the claims using it are marked pending.
- **IR-67-TPL-01** — the older 58GEMSDOE `submission_writer` wrote NaN-outside
  while the pinned gates/validate enforce all-finite; the 60GEMSDOE pin (used
  here) already resolved this. Anyone still on the 58G writer should upgrade.

---

## Master prompt (read before every session)

<details>
<summary>Click to expand the standing brief</summary>

Review the repo.

**THE FOLLOWING IS THE HIGHEST URGENCY AND MUST BE FOLLOWED!**

MUST GENERATE A UNIQUE TIF SUBMISSION FOR THE COMPETITION. DO NOT COPY A PREVIOUS
SUBMISSION UNLESS IT'S FOR LEARNING AND EDUCATION. BUT WE MUST GENERATE A UNIQUE TIF
SUBMISSION. IT MUST BE OBVIOUS WHETHER IT IS OK TO DOWNLOAD AND SUBMIT THE GENERATED
TIF SUBMISSION.

There should be an easy to download submission tif file as described by the prompt.
Read the entire prompt.

Orientation and tip heads with geometry-aware decoding. Per-pixel classification
ignores connectivity. Batra et al. (CVPR 2019, doi:10.1109/CVPR.2019.01063) show that
learning orientation jointly with segmentation in stacked multi-branch heads improves
the topology of extracted line networks. Add an axial orientation head (cos 2θ, sin 2θ,
my adaptation for undirected faults, supervised within 3 px of catalogue traces). Add a
tip/junction heatmap head (Gaussian σ = 1–2 px at polyline endpoints and junctions).
Decode with orientation-aware non-maximum suppression and hysteresis. Extend traces past
mapped tips only along predicted orientation where probability support persists.
Published fault-population studies find mapped lengths come up short because tip zones
fall below resolution (about 500 m per fault in one seismic array; ≥100–200 m DEM
truncation in another rift: Southampton eprint 76146 and a UCD Fault Analysis Group
TSG-2008 abstract). Select nodes by calibrated greedy marginal-DTI selection or 4–5 px
spacing. Gate: DTI gain and better recovery of masked tip-adjacent segments in
hide-and-recover blocks. Finish: normalize to [0,1]; write a float32 EPSG:32611 100 m
GeoTIFF (NaN only outside the footprint); pass validate_submission.py; run a
hash/pixel-agreement check against all prior rasters; offer the download only if the
gate is met, else log the negative result.

PARALLEL-RUN PROTOCOL — read first. This session is one of several running from this
same prompt.

1. LANE. Your lane is the single method paragraph above. Stay inside it. If your
raster's rank-correlation with any registry raster exceeds [0.90], or more than [70%]
of your dots fall within 3 px of one registry raster's dots, you have drifted into
another lane: log it as a duplicate and stop. Check this on the surface before
placement AND on the final dots.
2. REUSE, DON'T REBUILD. Use the template's cached feature stack, evaluate_holdout.py
and submission_writer.py. Holdout = hide-and-recover: withhold whole fault segments
with a buffer, derive every catalogue-based feature only from the visible faults, mask
visible faults pixel-exactly, score pooled DTI (alpha 0.2, beta 0.8, 300 m triangular
kernel). If a shared tool is wrong, fix it once in the template and report it; never
keep a private fork.
3. LABEL EVERY NUMBER as HOLDOUT-DTI (evaluator version, number of withheld positives,
95% CI) or ORGANIZER-CONFIRMED (copied from a submission-page receipt). A projection is
never written as a score.
4. LEAKAGE CANARY. Test each feature alone on the holdout before trusting any result.
AUC above [0.90] means leakage until proven otherwise.
5. RUN CARD. End with one JSON card: hypothesis; mechanism; the named non-fault process
that could mimic it; holdout DTI + CI; correlation/overlap vs registry; raster sha256;
validator output (no NaN inside the footprint, values in [0,1], CRS/shape/transform
match); submission name + note of at most 140 characters; verdict promote / negative.
Negative results are deliverables.
6. BUDGET. Stop after [3] experiments or [2] hours. Do not pick submissions: promotion
to a real slot is a separate selector step, within the weekly cap shown on the
submission page.

We need to generate a unique TIF submission into the competition. It must be unique —
unlike any within the GEMSDOE sites. Verify working line by line, no hallucinations.

Answer the question using PhD-level experience, knowledge, and judgement: Why and how
did `h33-h33-2-b2-20261004T220000Z-e5eb6e7e-zeros` (0.2778) get the highest score among
the GEMSDOE family sites, and are we able to generate a submission that scores higher?

Before implementing, generate 3–5 candidate geological hypotheses we haven't tried yet,
each naming: the specific layer(s) involved, the physical signature being targeted, why
it should catch a fault missing from the USGS/INGENIOUS catalogue rather than one
already in it, and how it differs from anything already implemented in this repo. Rank
them by expected DTI improvement and implementation cost. Validate the top candidate on
our spatially-blocked holdout set before touching a weekly submission slot.

The goal of this project is to place top of the leaderboard in this competition
(https://www.drivendata.org/competitions/306/competition-doe-gems/). Collect all data
and organize it into a clean, easily auditable table with official verified links.
Create a GitHub page with clean UI: executive summary at the very beginning explaining
exactly how to make a submission, an easy download of the submission TIF, a unique name
and a short note (≤140 characters) to tell submissions apart.

"Predicted values must be in range [0, 1]" — the downloaded file must not trip this
portal error. No manual input required; work autonomously; flag irregularities; no
hallucinations; verify line by line from official verified trusted sources and provide
links for manual review. Run every task through multiple passes (implement → review →
re-check against the original request). Create a pull request and merge to main; make
suggestions for remaining work and limitations.

Core values (Arena): **Maximize P(Win)** — weigh tradeoffs and choose the path that
maximizes the probability of winning. **Own the Outcome** — own results end to end;
problems are acted on without waiting for permission; failure and success are signals
to improve.

The single blocker to training on an unrestricted machine is data placement: run
`bash scripts/download_competition_data.sh` into `data/`, then
`python scripts/prepare_data.py` — after that the full train→inference→validate
pipeline runs (CPU is sufficient for this lane's linear heads).

</details>

## Sources (manual-review links)

Full auditable table: [docs/sources.html](docs/sources.html). Key official links:

- Competition: https://www.drivendata.org/competitions/306/competition-doe-gems/
- Problem/metric: https://www.drivendata.org/competitions/306/competition-doe-gems/page/967/
- Data (login): https://www.drivendata.org/competitions/306/competition-doe-gems/data/
- Leaderboard: https://www.drivendata.org/competitions/306/competition-doe-gems/leaderboard/
- Reference solution: https://github.com/drivendataorg/gems-prize-reference-solution
- GeoDAWN survey: https://www.usgs.gov/data/geodawn-airborne-magnetic-and-radiometric-surveys-northwestern-great-basin-nevada-and
- INGENIOUS: https://gbcge.org/current-projects/ingenious/
- EPSG:32611: https://epsg.io/32611
- Tversky index: https://en.wikipedia.org/wiki/Tversky_index
- Batra et al. 2019: https://doi.org/10.1109/CVPR.2019.01063
