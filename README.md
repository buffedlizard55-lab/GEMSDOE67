# GEMSDOE67 · orientation and tip decoding

## Submission status: **NOT READY — do not submit a file from this run**

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
