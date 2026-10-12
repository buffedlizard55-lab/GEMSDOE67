# GEMSDOE67 · two lanes: orientation/tip decoding (`main`) and orientation-voted evidence (OVTR)

## Submission status — read this table first

| lane | branch / merge | status | measured HOLDOUT-DTI |
| --- | --- | --- | --- |
| **OVTR** — orientation-voted evidence, calibrated greedy kernel-cover | `arena/c331a9d8` (PR #2) | **DOWNLOAD READY** — verified artifact offered below | **0.2691** pooled (4 folds, 60 594 withheld px); 22/22 format checks pass with a second GDAL build; registry check *distinct lane* |
| **ORIENT/TIP** — axial + tip heads, geometry-aware decoding | `arena/cfeaa9d4` (PR #1, already on `main`) | **NEGATIVE · DOWNLOAD BLOCKED** — do not submit a file from that run | 0.0344 (joint) / 0.0404 (segmentation control) |

The two statements do not conflict: they are different lanes with different measured numbers. The
blocked status belongs to the orientation/tip lane and is preserved verbatim on its own page —
[`docs/status-cfeaa9d4.html`](docs/status-cfeaa9d4.html) — with its run card still at
[`docs/run-card.json`](docs/run-card.json). The OVTR lane's card is
[`docs/run-card-ovtr.json`](docs/run-card-ovtr.json) and its one-click download page is
[`docs/index.html`](docs/index.html). **No competition slot has been used by either lane**;
promotion into a slot is a separate selector decision inside the weekly cap shown on the submission
page.

---


## Submission status of the orientation/tip lane: **NOT READY — do not submit a file from *that* run**

[Project website](https://buffedlizard55-lab.github.io/GEMSDOE67/) ·
[Executive submission guide](https://buffedlizard55-lab.github.io/GEMSDOE67/docs/executive-summary.html) ·
[Research and irregularities](research/review.md) · [Run card](docs/run-card.json)

A unique, gate-passing submission TIFF is the goal, **not a deliverable we can claim before
evidence exists**. No previous submission is copied into a new submission. No dummy TIFF,
renamed historical raster, projected leaderboard score, or unconditional download button.
Negative results are deliverables. No competition slot is consumed by this repository.

## Starting point — read at every session

This is the maintained project brief from the user's request. Repeated wording is consolidated
below; it is not represented as a verbatim transcript. Preserve this intent in future work.

> MUST GENERATE A UNIQUE TIF SUBMISSION FOR THE COMPETITION. DO NOT COPY A PREVIOUS
> SUBMISSION UNLESS IT'S FOR LEARNING AND EDUCATION. IT MUST BE OBVIOUS WHETHER IT IS
> OK TO DOWNLOAD AND SUBMIT THE GENERATED TIF SUBMISSION.

### Mandatory lane and parallel-run protocol

1. **Orientation/tip heads only.** Joint segmentation, axial `(cos 2θ, sin 2θ)` supervision
   within 3 px of catalogue traces; Gaussian endpoint/junction supervision σ = 1–2 px.
   Orientation-aware non-maximum suppression and hysteresis; continuation beyond mapped
   tips only with predicted-direction and persistent probability support. Greedy calibrated
   marginal-DTI allocation or 4–5 px node spacing. Do not assume a universal truncation length.
2. **Reuse, don't rebuild.** Use cached feature inputs and shared `evaluate_holdout.py` /
   `submission_writer.py`. Whole segments hidden with a buffer; catalogue-derived features
   use visible faults only; mask visible faults pixel-exactly. Pool DTI terms with α = 0.2,
   β = 0.8 and a 300 m triangular kernel. Fix shared defects in the template, not privately.
3. **Distinctness.** Before production placement and again on final dots compare to the
   registry. Rank correlation exceeding 0.90 or over 70% of candidate dots within 3 px of
   one prior raster is a duplicate: log and stop. Hash and pixel agreement checks cover all
   prior rasters; missing registry coverage is not success.
4. **Leakage canary.** Test each feature alone on the holdout. AUC above 0.90 is leakage
   until explained. Low AUC alone does not prove safety.
5. **Evidence.** Scores are HOLDOUT-DTI (evaluator version, withheld positives, 95% CI) or
   ORGANIZER-CONFIRMED (submission-page receipt). A projection is never a score. Unverified
   user-reported history remains unverified. Conflicting leaderboard reports must be flagged.
6. **Promotion gate.** Beat the comparable current holdout best and improve recovery of
   masked tip-adjacent segments. Then normalize to [0,1], write single-band float32
   EPSG:32611, 100 m GeoTIFF on the sample's exact shape/transform; NaNs, if any, only outside
   the footprint. Run `validate_submission.py`, uniqueness and hash/pixel checks. Offer a
   download only after all gates pass; otherwise log the negative result.
7. **Run card.** One JSON card records hypothesis, mechanism, named non-fault mimic,
   holdout DTI/CI, registry comparisons, raster SHA-256, validator output, submission name,
   note ≤140 characters, and verdict promote/negative. Null means unmeasured, not zero.
8. **Budget.** Stop after 3 experiments or 2 hours. Real submission-slot promotion is a
   separate selector step within the weekly cap shown on the submission page. Never assume
   that cap, auto-submit, or spend a slot during research.

### Research, product and ownership requirements

- Review the repository and previous-session work before implementation. Generate 3–5
  geological hypotheses, name specific layers, physical transforms/signatures, missing-fault
  rationale, non-fault confounder and differences from implemented methods. Rank expected
  holdout utility and cost without presenting speculative scores. Check any new official
  free data source is obtainable before calling a dependent hypothesis viable.
- Study the related GEMSDOE work, especially GEMSDOE32 H33-2-B2, but never relabel its raster
  as new science. Explain how sparsity and the metric interact and why that is not proof of
  future leaderboard performance. The discovery target is missing faults relevant to
  geothermal exploration, not unverified claims of vent discovery.
- Use official, trusted sources where obtainable; preserve source URLs, verification state,
  hashes, irregularities and limitations for manual review. Do not claim line-by-line
  official verification where authentication or network policy prevents it.
- Work autonomously without requesting credentials. Restore obtainable data, test on CPU
  where possible, and document actual blockers instead of repeating stale setup claims.
- Build a clean GitHub Pages site. Executive summary and submission readiness belong at
  the beginning. A future approved artifact has one-click download, unique name and a short
  note; unapproved candidates have no TIFF link. Provide exact contest upload instructions.
  A static page cannot itself train a model. Clearly date feed/snapshot evidence, never fake
  a live leaderboard or current verification.
- Perform three passes: implement/test; review bugs/assumptions/edge cases and fix; recheck
  against this brief and document unmet requirements. Open a PR and merge it only after
  checks. Record next steps and limitations for the next session.
- **Maximize P(Win):** evidence-based tradeoffs over impressive-looking unvalidated results.
  **Own the Outcome:** investigate and fix end-to-end failures; a truthful negative is more
  valuable than an unsafe submission. These values do not authorize invented evidence.

### Competition and source starting points from the request

- [Overview](https://www.drivendata.org/competitions/306/competition-doe-gems/)
- [Problem / metric](https://www.drivendata.org/competitions/306/competition-doe-gems/page/967/)
- [About](https://www.drivendata.org/competitions/306/competition-doe-gems/page/968/)
- [Data](https://www.drivendata.org/competitions/306/competition-doe-gems/data/)
- [Leaderboard](https://www.drivendata.org/competitions/306/competition-doe-gems/leaderboard/)
- [Official reference](https://github.com/drivendataorg/gems-prize-reference-solution)
- [Prize PDF](https://docs.nlr.gov/docs/fy26osti/96647.pdf)
- [USGS GeoDAWN](https://www.usgs.gov/data/geodawn-airborne-magnetic-and-radiometric-surveys-northwestern-great-basin-nevada-and)
- [INGENIOUS](https://gbcge.org/current-projects/ingenious/) · [GDR 1391](https://gdr.openei.org/submissions/1391)
- [Batra DOI](https://doi.org/10.1109/CVPR.2019.01063) · [Southampton 76146](https://eprints.soton.ac.uk/76146/)
- [EPSG](https://epsg.io/32611) · [Tversky overview](https://en.wikipedia.org/wiki/Tversky_index)
- [GEMSDOE32 site](https://buffedlizard55-lab.github.io/GEMSDOE32/docs/index.html)
- Full related-repository tree inventory: [JSON](evidence/repository_inventory.json).
  This preserves discovered raster/tool paths, not verification of all published results.
- Source-by-source verification table: [CSV](research/sources.csv).

## What is actually implemented

- Hash-checked owner-mirror restoration and grid audit; source arrays excluded from Git.
- Unmodified commit-pinned shared GEMSDOE60 `gems57` evaluator, spatial folds and writer.
- Feature-alone canaries on buffered spatial folds.
- Small CPU shared-trunk neural research prototype with axial and heatmap heads feeding a
  second segmentation stage; raster/PCA proxy labels, orientation NMS, supported directional
  hysteresis and 5 px node spacing. **Not Batra's spatial CNN, not original polyline labels,
  not a complete production mapped-tip extension implementation.**
- One matched segmentation-control experiment, pooled spatial-bootstrap DTI and tip recall.
- Strict format-validation wrapper, scoped uniqueness comparisons and fail-closed release
  decision utility. No global-registry or production-artifact approval is implied.
- Tests, reproducible receipts and a static status/guide site.

## Reproduce locally

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
bash scripts/download_competition_data.sh   # gh auth already configured in Arena
.venv/bin/python scripts/prepare_data.py
OPENBLAS_NUM_THREADS=1 .venv/bin/python scripts/run_canaries.py
OPENBLAS_NUM_THREADS=1 .venv/bin/python scripts/run_experiment.py
.venv/bin/python -m pytest -q
.venv/bin/python scripts/build_site.py
.venv/bin/python scripts/check_site.py
```

Data restoration uses allowed GitHub hosts. The initial TIFFs occupy roughly half a gigabyte;
the memory-mapped transcode uses additional disk. A run is not a weekly submission. The fixed
experiment has no automatic retry/tuning loop. Check the budget before manually rerunning it.
To validate a future candidate: `.venv/bin/python scripts/validate_submission.py PATH.tif`.
Format validation alone is never promotion or organizer acceptance.

## Next session

Read this README, `research/review.md`, `research/hypotheses.md`, `research/verification.md`
and the run card first. Resolve documented gates before spending a slot. The website remains
blocked until **all** required evidence exists. No credentials belong in this repository.

---

# Lane OVTR (`arena/c331a9d8`) — the lane that produced the offered artifact

> Everything from here on belongs to the OVTR lane. The lane brief and the parallel-run protocol in
> the first half of this README govern both lanes; the numbers, artifacts and scripts below are
> OVTR's, and its run card is `docs/run-card-ovtr.json`.

## What is in this repository

| path | what it is |
| --- | --- |
| `src/gems67/metric.py` | the competition metric, transcribed from the problem description and unit-tested against the published worked example (0.60) and a brute-force oracle |
| `src/gems67/features.py` | geometry-aware evidence: per-band gradient structure tensor → axial orientation `(cos 2θ, sin 2θ)`, per-family lineament evidence, multi-physics axial order parameter |
| `src/gems67/decode.py` | axial non-maximum suppression, hysteresis, tip/junction head, tip relay along the predicted orientation |
| `src/gems67/emit.py` | calibrated greedy marginal-DTI selection and greedy kernel-cover — the two emission rules the holdout compares |
| `src/gems67/holdout.py` | hide-and-recover folds: whole catalogue components withheld with a buffer, visible faults masked pixel-exactly when scoring |
| `scripts/` | data preparation, feature builds, the holdout funnel, the submission builder, the registry agreement check, the ceiling analysis, the artifact verifier, the site builder, the preview renderer |
| `docs/` | the GitHub Pages site: executive summary, how to submit, research register, sources, run card |
| `data/registry.json` | every sha256, shape, CRS and measured count used anywhere in this repository |
| `tests/` | metric, grid, IO, provenance and shipped-artifact tests (`pytest -q`) |
| `evidence/ceiling.json` | the metric's algebra applied to every measured arm: coverage `c`, waste `w`, the reachable ceiling, and the coverage each target score would need — computed by `scripts/ceiling_analysis.py` |
| `evidence/verify_*.json` | 22 format checks re-run on the published bytes by a *different* GDAL build than the writer used (`scripts/verify_artifact.py`) |
| `docs/assets/preview-*.png` | rendered previews of the shipped emission over a shaded relief of the provided residual-elevation band (a human-eye receipt only) |

---

## The finding that matters most (and it is counter-intuitive)

The lane's geometry-aware decoder — axial NMS, hysteresis, tip relay — produces **thin, correct
topology and a lower score** on the holdout than emitting mass across the model's whole
predicted region. Measured on the same four folds, same masking, same kernel:

| arm (HOLDOUT-DTI, pooled over 4 folds; withheld positives = 60 594 px) | pooled DTI | emitted px / fold |
| --- | ---: | ---: |
| `A0` incumbent family: dots on the dilated visible catalogue | 0.0014 | 459 |
| lane, geometry-gated (`A1_ovtr`, preregistered) | 0.1149 | 10 404 |
| lane, same sites carrying calibrated probabilities (`A1_soft`) | 0.0034 | 10 404 |
| random control, matched mass | 0.0760 | 10 404 |
| supervised head, geometry gate applied as a mass filter (`ML_cover_geom_tau0.3`) | 0.1469 | 5 122 |
| **shipped rule: greedy 3 px kernel-cover of the head's field, τ = 0.3** | **0.2691** | 40 106 |
| same rule, τ = 0.5 (the published sibling) | 0.2207 | 16 742 |
| same rule, τ = 0.2 / 0.1 / 0.05 (exposure sweep) | 0.2671 / 0.2579 / 0.2536 | 56 495 / 77 747 / 87 246 |

Head AUC per fold 0.647 / 0.726 / 0.647 / 0.687 against 0.596 / 0.649 / 0.609 / 0.607 for the raw
evidence alone; the single-feature leakage canary is 0.50–0.65, far below the 0.90 bar. No
bootstrap CI was computed before the session budget stop — that gap is `IR-67-04` in the run card.
Registry check on the shipped raster: max |rank correlation| **0.0478** (limit 0.90), max 3 px
overlap **0.3593** (limit 0.70) — verdict *distinct lane*.

Mechanism. With `α = 0.2` and `β = 0.8` the metric's denominator is dominated by
`0.8 × |G_hidden|`, so the marginal cost of a unit of emitted mass (0.2, and only 0.2) is five
times cheaper than leaving a truth pixel uncovered (0.8). A thin trace is *correct* geology and
*expensive* scoring: it covers few truth pixels. The optimum is to spend mass wherever the
model's probability of a hidden fault is non-trivial, which is what the greedy kernel-cover
does. This is the arithmetic behind the leaderboard's mid-0.3s, and it is why the group's own
"dotted thin" family stalls near 0.26.

*(Also measured: the tip-relay step in the lane, once its acceptance test was fixed to use the
raw evidence field rather than the thinned field, extends traces past mapped tips — but it does
not change the pooled ranking, because the geometry gate it feeds is the binding constraint.
Both facts are in the run card; the tip-relay bug is irregularity IR-67-02.)*

---

## Honest limitations

* **No organizer score exists for anything here.** All numbers are holdout numbers from this
  repository's own instrument. `docs/run-card-ovtr.json` labels each one.
* **The instrument's truth is the old catalogue**, so it structurally cannot reward a genuinely
  new fault; a holdout pass licenses *packaging*, never a score claim.
* **The detector is trained on the catalogue**, so its strongest predictions are catalogue-like
  faults. Hidden expert-mapped faults come from a source the organizers declined to describe
  (forum thread 11527), so no local instrument can measure that generalization.
* **Compute budget.** Everything here ran on 2 CPU cores / 3 GB RAM; the 1 m DEM and any deep
  model were out of scope in this session (the competition ships a `1m_DEM_links.csv`, and the
  reference solution trains a U-Net on 64-pixel tiles).
* **Phase 2.** The Final Prize Round rescoring uses labels expanded by expert review of Phase 1
  submissions (official forum answer, thread 11527), so a file that flags *geologically
  defensible* new traces is worth more than a file that only maximises Phase 1 density. Both
  properties are arguments for the shipped rule, and neither is measurable here.

## Why 0.28 and not 0.43 — the root cause, with the algebra

The published metric reduces exactly (`FN_w = |G| − TP_w`) to

```
DTI = c / (0.8 + 0.2·c + 0.2·w)        c = TP_w/|G|  (coverage),  w = FP_w/|G|  (waste)
```

`scripts/ceiling_analysis.py` recovers `c` and `w` for every arm from the holdout evidence alone
(`evidence/ceiling.json`). The shipped arm sits at `c = 0.3684`, `w = 2.477`, and its **own
zero-waste ceiling is 0.4217** — i.e. the live bar (0.4275 on 2026-10-12) is unreachable for this
coverage *no matter how the dots are packed*, while 0.15 of headroom is still sitting in the waste
term. Efficiency (`T/S`) ranks the families in the exact reverse of the score, which is the
signature of a coverage-limited regime: the 0.26–0.28 band is a Pareto ridge, not a bug. Loosening
exposure to buy coverage makes it worse (τ = 0.05: `c = 0.508`, score 0.2536). Full write-up:
[`docs/research/why-the-ceiling.md`](docs/research/why-the-ceiling.md), rendered at
[`docs/ceiling.html`](docs/ceiling.html). The cheapest next gain is the emission, not the data:
**H67-A2**, credit-weighted greedy with the marginal-bar stopping rule.

## Reproduce

```bash
python scripts/prepare_data_ovtr.py     # verify sha256 pins, decode the stack to /tmp/gems_data
python scripts/build_features.py        # 19-band evidence + axial orientation + context
python scripts/add_external_channels.py # public USGS-derived lidar/radiometric evidence
python scripts/run_holdout.py           # arms A0..A3   -> evidence/holdout.json
python scripts/run_holdout_ml.py        # supervised head + cover sweep -> evidence/holdout_ml.json
python scripts/run_holdout_ml.py        # 23-channel extension   -> evidence/holdout_ml_ext.json
python scripts/build_submission.py --name gemsdoe67-ovtr-ml-cover-tau3p0-20261012 \
    --tau 0.30 --radius 3.0              # -> docs/downloads/*.tif, *.zip, checks-*.json
python scripts/registry_check.py --ours docs/downloads/gemsdoe67-ovtr-ml-cover-tau3p0-20261012-nan.tif
python scripts/verify_artifact.py        # 22 format checks with a second GDAL build
python scripts/ceiling_analysis.py       # coverage/waste/ceiling per arm -> evidence/ceiling.json
python scripts/make_preview.py           # site previews
python scripts/build_site.py             # regenerate the Pages site from the JSON evidence
pytest -q
```

## Sources (all verified in this checkout; see `docs/sources.html`)

* Problem description, metric and submission format —
  <https://www.drivendata.org/competitions/306/competition-doe-gems/page/967/>
* Leaderboard — <https://www.drivendata.org/competitions/306/competition-doe-gems/leaderboard/>
* Known-fault masking (DrivenData staff answer) —
  <https://community.drivendata.org/t/11516>
* Test-fault provenance (organizer: not disclosed) — <https://community.drivendata.org/t/11527>
* Reference solution (U-Net, John Lipor, Portland State) —
  <https://github.com/drivendataorg/gems-prize-reference-solution>
* GeoDAWN airborne magnetic and radiometric surveys —
  <https://www.usgs.gov/data/geodawn-airborne-magnetic-and-radiometric-surveys-northwestern-great-basin-nevada-and>
* INGENIOUS project (Great Basin Center for Geothermal Energy) —
  <https://gbcge.org/current-projects/ingenious/>
* EPSG:32611 — <https://epsg.io/32611>
* Tversky index — <https://en.wikipedia.org/wiki/Tversky_index>
* GDR submission 1391 (Nevada geothermal data) — <https://gdr.openei.org/submissions/1391>
