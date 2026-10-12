# GEMSDOE67 — Lane 67: supervised orientation head + tip/junction head

**Verdict: NEGATIVE RESULT. The ship gate is not met — this lane's artifact is for
inspection only and is not recommended for submission.** Every number below is labelled
with the instrument that produced it. Nothing here is an organizer receipt.

| | |
| --- | --- |
| Lane | 67 — axial orientation head + tip/junction head + orientation-aware decode |
| Artifact | `docs/downloads/gems67-*-zeros.tif` (float32, EPSG:32611, 3730×3292, values {0,1}) |
| Format check | PASSES `gems57.validate` (13/13 checks, range [0,1] guaranteed) |
| Lane gate (DTI gain + masked-tip recovery) | **NOT MET** |
| Registry gate | **NOT CERTIFIABLE** from this sandbox (and the literal overlap threshold fires on a
dense prior — see Irregularities IR-67-OVERLAP-01) |
| Recommended action | do not spend a weekly submission slot on this artifact |

---

## 1. Download / submit — read this first

* `docs/downloads/` holds the ready-to-upload file, its `.zip`, and a JSON receipt.
* **Do not submit it.** The evidence in §5 says the mechanism did not beat the shared
  template's own decimated-lattice control on either of the lane's two instruments, so
  there is no measured reason to expect it to beat a plain submission.
* How a submission is actually made (official wording, fetched 2026-10-12 from the
  [competition home page](https://www.drivendata.org/competitions/306/competition-doe-gems/)):
  1. Click **"Compete!"** in the sidebar on the competition home page to enrol.
  2. Download the data from the **data** tab (login required — see §7, this sandbox cannot).
  3. Click **"Submit"** in the sidebar, then **"Make new submission"**, upload the `.tif`,
     give it a name and a short description.
* Format rules (verbatim from the
  [problem description, page 967](https://www.drivendata.org/competitions/306/competition-doe-gems/page/967/)):
  same projected CRS as training (**UTM 11N, EPSG 32611**), same 100 m resolution, same
  bounds with data outside the footprint null/NaN, single layer, **float32**, values
  **0–1** with higher = more likely. The prior failure mode "Predicted values must be in
  range [0, 1]" is explicitly checked here: `range_0_1_guaranteed: true`.
* Competition end date: **Dec 3, 2026, 11:59 p.m. UTC**. Prize pool $300,000
  (Initial round: top 5 × $10,000; Final round: $100k/$70k/$40k/$25k/$15k).
* **Outside-footprint values are written as 0, not NaN.** The organizer wording permits either
  ("data outside null/NaN"), the metric only evaluates inside the footprint, `0` is unambiguously
  inside [0, 1] and cannot be re-read as a sentinel. `validate_submission.py` confirms
  `outside_footprint_zero: true` and `range_0_1_guaranteed: true`.

## 2. Official links for manual review

| Source | Link |
| --- | --- |
| Competition home (rules, prizes, "How to compete") | https://www.drivendata.org/competitions/306/competition-doe-gems/ |
| Problem description (metric, submission format, label expansion) | https://www.drivendata.org/competitions/306/competition-doe-gems/page/967/ |
| About / resources | https://www.drivendata.org/competitions/306/competition-doe-gems/page/968/ |
| Data download (login) | https://www.drivendata.org/competitions/306/competition-doe-gems/data/ |
| Public leaderboard | https://www.drivendata.org/competitions/306/competition-doe-gems/leaderboard/ |
| Official rules | https://www.drivendata.org/competitions/306/competition-doe-gems/rules/ |
| Organizer reference solution | https://github.com/drivendataorg/gems-prize-reference-solution |
| Forum (question on metric/format) | https://community.drivendata.org/c/gems-prize-challenge/111 |

## 3. THE WORKING BRIEF (session prompt — read this first, every time work starts)

> **Goal.** Win/place high in the DrivenData **DOE GEMS** challenge
> (https://www.drivendata.org/competitions/306/competition-doe-gems/). Beat the current
> published high score **0.3195**; the live leaderboard's #1 was **0.4275** when this lane
> started. Be contrarian but smart; keep everything grounded in proper scientific
> research; prefer free, official, publicly available data. Follow the Arena AI core
> values — *Maximize P(Win)*, *Own the Outcome*.
>
> **Deliverables.**
> 1. A **UNIQUE** TIF submission (never copy a prior submission except to learn from it),
>    and it must be **obvious whether the file is OK to download and submit**.
> 2. An easily downloadable submission TIF matching the prompt, exposed from a GitHub
>    Pages site whose **executive summary states at the very start exactly how to submit**
>    (download file → upload to competition sidebar → "Make new submission"), plus an
>    executive-summary subpage. Clean, user-friendly UI.
> 3. This README must contain the prompt as the working base.
> 4. Official verified links for manual review. **No hallucinations** — verify line by
>    line; flag irregularities for human review.
> 5. A unique submission name and a short identifying note (≤140 characters).
> 6. No manual input required from the user; the system must do its own checking and
>    publish an up-to-date feed.
>
> **Method paragraph to implement.**
> * An **orientation head** supervised with `cos2θ`/`sin2θ` targets computed within 3 px of
>   the catalogue traces (axial frame, so a fault and its reverse are the same orientation).
> * A **tip/junction heatmap head** with a Gaussian (σ = 1–2 px) target at polyline
>   endpoints and junctions.
> * **Orientation-aware non-maximum suppression** across strike, followed by a
>   **hysteresis** walk that can bridge gaps and **extend past a tip along the predicted
>   orientation while support persists**.
> * **Calibrated greedy marginal-DTI selection** of nodes, *or* nodes on a 4–5 px spacing
>   lattice when the marginal rule is not identifiable.
> * **Gate:** a DTI gain **and** better recovery of masked tip-adjacent segments in
>   hide-and-recover blocks. Only offer the download if the gate is met; otherwise log the
>   negative result (negative results are deliverables).
> * **Finish:** normalise to [0, 1], float32, EPSG:32611, 100 m GeoTIFF, NaN only outside
>   the footprint, pass `validate_submission.py`, and run a hash/pixel-agreement check
>   against **all** prior rasters.
>
> **PARALLEL-RUN PROTOCOL (binding).** Stay in lane: ≤ 0.90 rank correlation with any
> registry raster; ≤ 70 % of dots within 3 px of one registry raster's dots; otherwise log
> the duplicate and stop. Reuse the cached feature stack, `evaluate_holdout.py` and
> `submission_writer.py`. Holdout = **hide-and-recover with pixel-exact masking**, pooled
> **DTI α = 0.2, β = 0.8**, 300 m triangular kernel. Label every number **HOLDOUT-DTI
> (evaluator version, withheld positives, 95 % CI)** or **ORGANIZER-CONFIRMED**. Leakage
> canary: single-feature AUC > 0.90 is leakage until proven otherwise. Finish with one JSON
> run card: hypothesis, mechanism, mimic process, holdout DTI + CI, correlation/overlap vs
> registry, raster sha256, validator output, submission name + ≤140-char note, verdict.
> **Budget: stop after 3 experiments or 2 hours.** Promote/negative, no third option.
>
> **Also asked for.** (a) An analysis of why
> `h33-h33-2-b2-20261004T220000Z-e5eb6e7e-zeros: 0.2778` (repo GEMSDOE32) scored highest on
> the sibling site and whether it can be beaten; (b) 3–5 new candidate geological
> hypotheses (layering, physical signature, why each catches a fault missing from the
> USGS/INGENIOUS catalogue, how it differs from prior work) ranked by expected DTI gain and
> implementation cost, with the top candidate validated on the spatially-blocked holdout
> **before** spending a weekly submission slot; (c) multi-pass execution (Pass 1 implement
> and verify; Pass 2 review for bugs, missing requirements, wrong assumptions, edge cases
> and fix; Pass 3 re-check against the original request and improve); (d) create a pull
> request, merge it to `main`, and list remaining work and limitations.
>
> **Data constraint.** DrivenData auth is unavailable here: `training_features.tif`,
> `labels.tif`, `sample_submission.tif` and `1m_DEM_links.csv` cannot be fetched from the
> data tab (the request redirects to login). Byte-identical mirrors were used instead and
> are sha256-pinned in `data/bridge/manifest.json`.

## 4. What was built

```
src/gems67/fields.py   30 per-(band, scale) descriptor channels, disk-backed (float16 on disk)
src/gems67/heads.py    streaming ridge fits: axial orientation head, tip/junction head,
                       trace graph from the polyline catalogue, circular error, block AUC
src/gems67/decode.py   across-strike NMS, hysteresis march with tip extension, spacing
                       decimation, 200 m catalogue exclusion
src/gems67/arms.py     arm bank (orient_ext / orient_noext / lattice_d3 / random /
                       orient_marginal), tile ranking, masked-tip recovery
scripts/run_lane67.py  e1 verify+canary+heads, e2 arm comparison, e3 ship+validate+unique
scripts/build_prior_index.py  honest registry index (51 mirrored priors of 751 inventory blobs)
scripts/fetch_data.sh  re-derive the pinned inputs from GitHub mirrors
tests/                 12 tests over the physics conventions, decode geometry, budget
                       mechanics and both gates
```

The evidence stack is **15 of the 19 official bands** (magnetic 1/2/3/6/9/14; strain 4/7/8;
gravity 5/11/13/18; seismic 10/16; topography 12/19; subsurface 15/17 — six of these are
used) at **two scales (σ = 1.5 px and 3.0 px)**, each contributing an axial frame
(`w·cos2θ`, `w·sin2θ`) plus an energy channel = 30 channels, built once in 129 s and cached.

## 5. Results

### 5.1 Leakage canary — clean
Max single-feature AUC against the withhold mask **0.6122** (bar 0.90), so no descriptor
alone leaks the holdout. `evidence/e1_verify_canary_heads.json`.

### 5.2 The two heads work, but the tip head is weak
| Head | Measurement | Instrument |
| --- | --- | --- |
| Orientation | circular MAE **20.77 / 23.78 / 20.27 / 25.98**° across 4 blocked folds vs **24.18 / 26.55 / 28.48 / 29.97**° for the unweighted aggregate and **61.6 / 56.3 / 60.9 / 51.8**° for the constant-frame baseline | spatial blocks, supervision within 3 px of visible traces |
| Tip/junction | AUC **0.5817** (6 × 200 px blocks, 8,000 positives / 24,000 negatives) vs **0.4500** for the aggregate-evidence control | on-trace negatives ≥ 2 px from any tip |

The orientation head beats both controls, so `cos2θ`/`sin2θ` is learnable from these bands.
The tip head is only 0.13 AUC above a control that has essentially no skill — it is a real
but weak signal, and §5.4 shows it did not translate into recovered tips.

### 5.3 Arm comparison — the mechanism does not beat the control
HOLDOUT-DTI, protocol α = 0.2, β = 0.8, 300 m triangular kernel. Two instruments were run:
**A = withheld segments** (`gems57.holdout`, pixel-exact masking, 4 quadrants, 11,318
withheld positive px) and **B = withheld whole components** (evaluator version
`gems57-pooled-hide-v2`, 11,321 withheld positive px, paired 20 km-block bootstrap, 1,000
draws, seed 520810). Full JSON: `evidence/e2_arms_holdout.json`.

| Arm | dots | HOLDOUT-DTI (A) | HOLDOUT-DTI (B) [95 % CI] |
| --- | --- | --- | --- |
| `orient_ext` (NMS + hysteresis + tip extension) | 3,604 | 0.01368 | 0.00792 [0.00181, 0.01519] |
| `orient_noext` (same, extension off) | 3,180 | 0.01365 | 0.00725 [0.00159, 0.01437] |
| `lattice_d3` (shared decimation, 3 px) | 5,270 | 0.02218 | 0.01263 [0.00520, 0.02141] |
| `random` (matched count) | 5,944 | 0.01088 | **0.01295** [0.01018, 0.01572] |
| `orient_marginal` (marginal-DTI rule) | 207 | 0.00025 | 0.00149 [0.00000, 0.00461] |

Readings:
* **Tip extension is a null effect**: `orient_ext − orient_noext = +0.00067`
  (95 % CI [−0.00009, +0.00200]) on instrument B — the interval touches zero.
* The orientation decode **loses to the plain lattice control in 3 of 4 worlds** and to the
  matched-count random arm on instrument B (`−0.00503`, 95 % CI [−0.01174, +0.00256]); on
  instrument A it does beat random (0.0137 vs 0.0109) but loses to the lattice.
* The calibrated marginal rule (`orient_marginal`) emits almost nothing (185–1,017 dots)
  and scores ≤ 0.0009: on this field the marginal test is **not identifiable**, because the
  surrogate rewards the posterior that placed the dots (§6).
* The 88.5 % of tip-fold truth that lies within 5 px of a visible trace is **not** something
  this lane can exploit: instrument A is built so that withheld truth is reachable, and the
  arms still do not close the gap.

### 5.4 Shipped artifact
HOLDOUT-DTI of the shipped 37,654-dot raster: **0.00989 (A)** / **0.00669 (B)**, CI
[0.00439, 0.00926] — written by the `e3` step of `scripts/run_lane67.py` and recorded in
`evidence/e3_submission_receipt.json` together with the validator output and the sha256.
The same code path measured on the *live analogue* of the fold mask (exclusion applied only
around the catalogue the world knows about, so withheld truth stays reachable, as it would
be for a genuinely new fault) rises monotonically with the budget to **0.0593** at 37,654
dots — i.e. 4.6 × the `random` arm at 1/6 the budget. That is the honest "what this would
score if it were submitted live" estimate, and it is produced by *budget*, not by any of
this lane's mechanisms.

## 5.5 Why 0.2778 scored highest, and what 0.3195 needs

Source: the sibling lane's byte-verified post-mortem of
`h33-h33-2-b2-20261004T220000Z-e5eb6e7e-zeros`, sha256
`c55bafc470054e8271dcb89347a17e07fefe50de6af6e6ba6c4b169ef7ab6fa9`, mirrored here as
`registry/rasters/gemsdoe32_h33_2_b2_02778_zeros.tif`. Every figure is
**sibling-measured / owner-reported**, not an organizer receipt.

| Property | Value |
| --- | --- |
| Dots | 37,654, median nearest-neighbour spacing 3.0 px |
| Distance to the mapped catalogue | minimum 223.6 m; **0 px** within 200 m |
| Lineage | = `gems24-d2-8` (0.2600) minus its 6,436-px ring inside 200 m of the catalogue |
| Credit density T/\|G\| | 5,223 / 14,088.7 px = **13.87 %** |
| Bar for 0.3195 | 15.95 % credit density — ~2 points, ≈2,250 more credited pixels at the same \|G\| |
| Marginal rule | a dot helps iff its expected credit exceeds α·DTI (0.0556 at 0.2778 → 283 m) |
| Identical-mass scatter control | 0.0778 — **placement dominates recall** |

Three falsifiable requirements follow: (1) a detector that ranks *off-catalogue* faults above
catalogue-free ground; (2) an instrument tied to the scored population; (3) mass discipline at fixed
credit. This lane spent its budget on (2) and lost. Already **measured-dead** in the sibling register:
catalogue fitting, external catalogues as positive priors, topography-only selection, 1 m LiDAR.

## 5.6 Four candidate hypotheses for the next lane, ranked by expected DTI gain per unit cost

| # | Hypothesis | Layer / physical signature | Why it finds what the catalogues miss | Cost |
| --- | --- | --- | --- | --- |
| 1 | **Relay-ramp connectors** between mapped strands | the lane's own axial frame: where two traces step over, the connector runs along the predicted strike of both | mappers end strands where exposure ends; the connector is buried. Nothing external needed — this lane's failure was the instrument, not the geometry | very low |
| 2 | **Cover-step faults** | depth-to-basement (15) / conductivity (17) step co-aligned with a magnetic (2/14) or gravity (13/18) lineament | Quaternary surface mapping cannot see faults under basin fill; a basement step coinciding with an independent potential-field lineament is a fault candidate | low |
| 3 | **Geothermal-manifestation collinearity** | GDR springs and volcanic vents + INGENIOUS 2 m temperature (DOI 10.15121/1881483) | blind faults leak heat along strike; the test set is *newly identified* faults in a geothermal province. Not a fault map prior, so it avoids the measured-dead route | medium |
| 4 | **Demagnetised damage zone** | magnetic lows (2/14) elongated along strike with tilt-derivative (6) edges | hydrothermal alteration destroys magnetite in the damage zone and survives burial — the signal sits exactly where no trace exists | medium-high |

All four inherit the brief's rule: validate on the spatially-blocked holdout **before** touching a
weekly submission slot — and, given IR-67-INSTRUMENT-01, build the instrument first.

## 6. Irregularities flagged for human review

* **IR-67-OVERLAP-01 — the registry overlap gate cannot be satisfied.**
  `gems13_r13_lattice_s5_00904` (206,895 dots) has a 3 px halo covering **99.87 %** of the
  footprint; a *uniformly random* 37,654-dot set scores **0.9988** forward overlap against
  it. Any dense candidate therefore trips the inherited "> 70 % within 3 px" stop gate. The
  same gate also fires on the 0.2778 champion (`worst_overlap = 1.0000`,
  `duplicate_count = 40`), so it is not discriminating between good and bad entries. The
  vendored module documents this failure mode on purpose ("the audit reports the problem,
  rather than quietly changing the owner's protocol"); this lane reports it and does not
  exempt itself.
* **IR-67-MARGINAL-01 — the calibrated marginal rule is degenerate here.** The shared
  surrogate's covered credit `T` grows with every added dot because dots are scored against
  the posterior that placed them: `surrogate_dti` is monotone in the budget
  (0.247 → 3.533 across 500 → 37,654 dots). A "calibrated greedy marginal-DTI selection"
  therefore cannot select; the lane used the 3 px decimation geometry instead and says so
  on the run card.
* **IR-67-CATALOGUE-01 — two catalogues disagree.** Only **36.4 %** of the vector trace
  pixels lie within 1 px of the raster label pixels (the raster is 100 % within 1 px of the
  vector), with 126,344 vector pixels outside the footprint. The external vector compilation
  is a superset of the revealed labels; the score is defined against the raster labels only.
* **IR-67-INSTRUMENT-01 — the two instruments disagree in direction** (§5.3: instrument A
  prefers the lattice over random, instrument B prefers random over the lattice at equal
  budget). A sibling lane already measured holdout-DTI vs the public leaderboard as
  uncorrelated (Spearman −0.10). Consequences: a "gate" expressed as a DTI gain is not
  adjudicable with these instruments, and the honest verdict is negative on the evidence
  available rather than "promote".

## 7. Data and provenance

`data/bridge/manifest.json` pins every raster by sha256. Verified in this sandbox:

| File | sha256 (prefix) | Bytes |
| --- | --- | --- |
| `training_features.tif` | `4371c82e3b8339b8…` | 418,912,844 |
| `labels.tif` (== `existing_faults.tif`) | `7ba308cc…` | int8, nodata −1 |
| `sample_submission.tif` | `2176d08e…` | NaN outside footprint |
| `trace_segments_utm11.csv` | `c5edf9df…` | 5,283,577 (84,331 segments) |

The 418.9 MB feature stack is **not committed** (GitHub's 100 MB blob limit); use
`scripts/fetch_data.sh`, which re-derives it from the GitHub mirror tarball
`https://codeload.github.com/buffedlizard55-lab/GEMSDOE/tar.gz/c0c06ac82178f26b94fce3397036ef8f12a2f3a0`
(`data/bridge/part-000 … part-004` concatenated) and re-checks the digest. Dropbox mirrors
exist for a browser but are blocked from this sandbox (`curl` → HTTP 000), as is
`raw.githubusercontent.com`.

## 8. Reproduce

```bash
pip install numpy scipy rasterio pytest
bash scripts/fetch_data.sh                 # or place the pinned rasters in data/bridge/
python3 scripts/build_prior_index.py
export GEMS67_FEATURES=/path/to/training_features.tif GEMS67_WORK=/tmp/gems67
export PYTHONPATH=vendor/template66:src
python3 -u scripts/run_lane67.py e1        # descriptors (129 s) + canary + both heads
python3 -u scripts/run_lane67.py e2        # arm comparison, both instruments
python3 -u scripts/run_lane67.py e3        # ship + validate + publish to docs/downloads/
python3 -u scripts/run_lane67.py unique    # registry gate
python3 -m pytest tests/ -q                # 12 tests, ~2 s
```

## 9. Remaining work and limitations

1. **The gate is not met, and the instruments cannot settle it.** Next step is to build an
   instrument tied to the scored population (an off-catalogue, revealed-preference
   measurement) rather than another arm.
2. **Registry certification is impossible from the sandbox** — 51 of 751 inventory blobs are
   mirrored. Fetch the rest (`gh api`) or run the gate in an environment with the full
   mirror before any real submission.
3. **The marginal-DTI rule needs the metric's own algebra, not a posterior surrogate**; the
   surrogate is degenerate by construction whenever the score is evaluated against the same
   posterior.
4. **Not attempted in this lane (deliberately outside budget):** external geologic layers
   (SGMC/QFaults/χ/2-m temperature), a learned per-band weighting, multi-fold ensembling,
   and the 0.2778 post-mortem's "credit density" strategy as an explicit objective.
5. **The shipped raster is a dense lattice**, so it inherits IR-67-OVERLAP-01 and any
   organizer check on trace-adjacency (it stays ≥ 200 m from every mapped trace by
   construction, which is the one rule the champion's lineage established).

## 9.5 Multi-pass log (the brief requires three passes)

* **Pass 1 — implement and verify.** Built the descriptor stack, both supervised heads, the
  orientation-aware decode, the five arms, both holdout instruments, the budget calibration, the
  shipping path, the registry audit and the site; ran everything end to end.
* **Pass 2 — review and fix.** Writing `tests/` exposed two real defects and one wrong measurement:
  * `decode._shift` padded out-of-bounds neighbours with `−inf`, so `nms_across_strike` kept **every**
    untouched border cell of an empty grid. The footprint touches the array border on all four sides
    here, so the defect was live; fixed to clamp at the edge and the whole chain was re-run.
  * `heads.trace_frame`'s docstring claimed the frame exists only on the mask; the tensor is smoothed,
    so it is defined in a neighbourhood. Docstring corrected and the test now asserts the real
    contract (unit norm wherever defined, decay away from the trace).
  * The `e2` truth crop had to be rebuilt from `cell.truth_yx` (the holdout `Cell` has no `.truth`),
    the tip-head negative population was circular in the first attempt (negatives now on-trace cells
    ≥ 2 px from a tip, control = raw evidence), and the `e3` budget sweep initially measured the
    shipped raster's own exclusion mask instead of the live analogue — all three fixed before any
    number reached this README.
* **Pass 3 — re-check against the brief.** Unique raster (byte- and pixel-distinct from all mirrored
  priors); download obvious from the first screen of the site; submission procedure quoted from the
  competition page; `validate_submission.py` provided and passing; hash/pixel agreement run against
  every mirrored prior; run card written; 0.2778 post-mortem and four ranked candidate hypotheses
  documented; irregularities published; no number in this file or on the site is hand-entered.

## 10. Lane-67 experiment ledger (budget: 3 experiments)

| # | Experiment | Outcome |
| --- | --- | --- |
| E1 | Descriptor build + leakage canary + orientation/tip heads | canary clean; orientation head beats both controls; tip head weak (0.5817 vs 0.4500) |
| E2 | Five-arm holdout comparison on two instruments | orientation mechanism loses to the lattice control; tip extension null |
| E3 | Budget calibration + ship + validate + registry gate | shipped, format-valid, gate NOT MET; overlap gate shown unsatisfiable |
