# Hypothesis register — five candidates, ranked, with what happened to each

Session: `arena/c331a9d8-gemsdoe67` · 2026-10-12 · Budget respected: **three experiments**
(E1 lane vs baselines, E2 greedy kernel-cover exposure sweep, E3 supervised head + public
USGS-derived layers), then the build.

Evidence classes used throughout: **[OFFICIAL]** read from an organizer/USGS/DrivenData page or
product, **[MEASURED]** computed in this checkout from hash-pinned bytes (command given),
**[BLOCKED]** could not be obtained here with the reason stated, **[NEGATIVE]** a measured
result that argues against the idea.

---

## H67-A — Multi-scale context-conditioned evidence on the 19 provided bands — rank 1, implemented

* **Layers:** all 19 bands of `training_features.tif`, grouped into six geological families
  (magnetic, gravity, topographic, subsurface, strain, seismic) exactly as named in the file's
  own `GDAL_METADATA`: see `data/registry.json → bands`.
* **Physical signature:** per-band gradient **structure tensor** at gradient scale σ₁ = 1 px,
  tensor smoothing σ₂ = 2 px; per-band lineament evidence
  `e = √λ₁ · (λ₁−λ₂)/(λ₁+λ₂)` (strong gradient whose *direction is consistent over a
  neighbourhood* — a lineament, not an isolated edge); family evidence = mean of members;
  **axial orientation** `(cos 2θ, sin 2θ)` and the multi-physics **axial order parameter**
  `R = |Σ_f w_f e^{2iθ_f}| / Σ_f w_f`. A supervised head (gradient-boosted trees) then combines
  the family evidences, coherence, order parameter, topographic curvature/rugosity and
  **multi-scale context** (Gaussian σ = 3 and 8 px of the aggregate evidence).
* **Why it should catch a fault the catalogue lacks:** the USGS/INGENIOUS catalogue grew by
  single-dataset mapping (topographic or previous state maps). A supervised head that requires
  evidence to be *simultaneously* present in several physics, and that is rewarded for regional
  context (four or more lineaments in the neighbourhood), selects exactly the multi-physics
  class that single-dataset mapping under-represents. **[OFFICIAL]** the organizers allow
  additional data sources and ask for "models and algorithms that provide accurate information
  about the presence of structures that are indicative of geothermal resources".
* **How it differs from prior work in this family of repositories:** the sibling GEMSDOE32
  repository thresholded hand-built transforms per pixel; here the evidence enters a
  supervised head with explicit multi-scale context, and the emission is a calibrated
  greedy kernel-cover rather than a per-pixel threshold.
* **Cost:** features 63 s; head 20-40 s per fold on 2 CPU cores. **[MEASURED]** AUC of the head
  on the withheld block: 0.652 / 0.722 / 0.627 / 0.676 (four folds) versus 0.596 / 0.649 /
  0.609 / 0.607 for the raw aggregate evidence alone — context is worth ≈ +0.05 AUC.
* **Result:** pooled HOLDOUT-DTI **0.2689** (4 folds, 60 594 withheld positives, 41 198
  emitted px/fold) versus 0.0014 for the incumbent "dots on the dilated visible catalogue"
  family. **Promoted; this is what the shipped file emits.**

## H67-A2 — Credit-weighted greedy emission with a calibrated stopping rule — rank 1b, derived, not yet measured

**Layer / instrument.** No new data: the same 23-channel head as H67-A, used as a *distribution*
rather than a threshold. **Physical signature transform.** The metric's own algebra,
`DTI = c / (0.8 + 0.2c + 0.2w)`: instead of covering the binary set `{q ≥ tau}` at 3 px spacing
(what ships today), add dots one at a time at the pixel that maximises *expected marginal credit*
under the model's calibrated probability, `Σ_u q(u)·max(0, k(d(u,x)) − credit(u))`, and stop when
that expected credit per unit mass falls to the marginal bar `0.2·DTI_hat`. This is weighted
maximum coverage — submodular, so lazy greedy is exact and needs no full-grid rescan.

**Why it should catch catalogue-missing faults.** It does not change *where* the model believes
faults are; it changes how the same belief is converted into mass. Today the tail of the field
(`0.3 ≤ q < 0.5`) consumes a large share of the emission and carries almost no credit (`T/S = 0.139`
at τ = 0.3 versus 0.209 at τ = 0.5, `evidence/ceiling.json`). A credit-weighted rule with a proper
stopping rule keeps the τ = 0.5-like efficiency while still pushing into the ridges that τ = 0.3
reaches — i.e. it walks along the ridge instead of up and down it.

**How it differs from prior work here and in the sibling repositories.** Those sweep a *threshold*
over a probability field or thin a *binary* mask; both treat every candidate pixel as equally
valuable and stop by fiat. This is the first rule in the family whose stopping condition is the
metric's own marginal condition, and the first that spends mass by expected credit rather than by
membership.

**Expected gain.** The shipped arm's own zero-waste ceiling is **0.4217** at its measured coverage
(0.3684); moving `w` from 2.48 to ≈1.0 at fixed coverage projects to ≈0.34 under the identity above
(MODEL projection — not a score). Realistically less, because a miscalibrated tail moves the real
`w` less than the belief-based rule assumes.

**Cost.** Low: one new emission function in `src/gems67/emit.py` (lazy-greedy heap, ~25 lookups per
accepted dot), plus one holdout run through `scripts/run_holdout_ml.py` to place it on the same
Pareto table. **Gate:** it must beat 0.2691 pooled *at equal or lower emitted mass*; otherwise it
is logged as a negative result.

## H67-B — Public USGS-derived LiDAR scarp composite and radiometric ratios — rank 2, implemented

* **Layers:** 12-band `lidar_scarp_features_u8.tif` (bands `ex_max`, `ex_mean`, `step_max`,
  `lapneg_max`, `lappos_max`, `downface_max`, `upface_max`, `cross_max`, `relief`, `coh100`,
  `strike`, `valid`), 4-band `geodawn_rad_u8.tif` (K, Th, U, TC) and 4-band
  `geodawn_extensions_u8.tif` (Th/K, U/K, U/Th, TMI upward-continued 150 m).
* **Provenance [OFFICIAL products, owner-derived rasters]:** LiDAR channels are derived from
  **USGS 3DEP 1 m lidar**; radiometrics are from the **USGS GeoDAWN data release,
  DOI 10.5066/P93LGLVQ**, ScienceBase item 657e1d85d34e23d3533209f7. Grid verified in this
  checkout: 3730 × 3292, EPSG:32611, tiepoint 243350 / 4508550 — identical to the competition
  grid. sha256 of each raster: `data/registry.json → external_layers`.
* **Physical signature:** the same structure-tensor lineament evidence applied to
  short-wavelength slope *excess* (a scarp, not a hill), fault-face asymmetry
  (`downface − upface`) and K/Th/U contrasts (hydrothermal alteration and lithology changes
  along a fault).
* **Why it should catch a fault the catalogue lacks:** the competition grid is 100 m; the
  published fault-population literature cited in the lane brief finds mapped fault lengths come
  up short because *tip zones fall below resolution* (~500 m per fault in one seismic array;
  ≥100-200 m DEM truncation in another rift). A 1 m-derived slope-excess composite measures
  exactly the sub-100 m signal that truncates a scarp at the grid scale.
* **How it differs:** the sibling repository used the LiDAR product as a *scalar weight*
  (`0.45·b1 + 0.35·b2 + 0.20·b5`); here each channel is skeletonised into lineament evidence
  and enters the supervised head as an independent family.
* **Status:** channels built (13 band → 3 families, 30 s). **[MEASURED]** the head with these
  channels reaches the same range of pooled DTI (see `evidence/holdout_ml_ext.json`); the gain
  over H67-A alone is small and is reported there rather than asserted here.
* **Caveat that must travel with this idea:** the LiDAR product covers only **3 893 184 of
  5 167 373** footprint pixels (`lidar_valid` band); the `valid` mask is passed to the head so
  that "no lidar" is not read as "no scarp".

## H67-C — Full-resolution 1 m DEM scarplet chain vote — rank 3, **BLOCKED here**, viable elsewhere

* **Layers needed:** the 1 m DEM tiles listed in the competition's `1m_DEM_links.csv`
  (USGS 3DEP / The National Map; free, official, no licence restriction).
* **Signature:** a scarplet detector (NMS ridge + face asymmetry at 2 m) chained by an
  N × 16-direction collinearity vote; en-echelon scarplets over hundreds of metres are what an
  expert accepts as a fault when a single scarplet is ambiguous.
* **Obtainability check performed here:** the link table itself is carried in this family of
  repositories (`GEMSDOE28` data/dem_links.json, sha256 `8804dbff8754…`), but the tiles
  themselves are served from USGS hosts that this sandbox cannot reach (egress is limited to
  the GitHub and PyPI hosts), and the full tile set is far larger than the 18 GB of free disk
  here. **Named source for an unrestricted machine:** <https://www.usgs.gov/3d-elevation-program>
  and the link table from <https://www.drivendata.org/competitions/306/competition-doe-gems/data/>.
* **Verdict:** not viable inside this sandbox; stated so that no one re-derives it.

## H67-D — Sub-kilometre seismicity lineaments from the raw ComCat catalogue — rank 4, **BLOCKED here**

* **Layers:** the provided `deq_n100a15` and `ieq_n100a15` bands are built on a 100 km radius
  (their own band names say so); they cannot resolve sub-kilometre lineaments. The raw
  USGS ANSS Comprehensive Earthquake Catalog (ComCat) is needed instead.
* **Signature:** epicentre-density ridges plus focal-mechanism nodal-plane strikes; a blind
  low-slip fault lights up seismically while leaving no scarp.
* **Obtainability check:** ComCat is free and official (<https://earthquake.usgs.gov/fdsnws/event/1/>),
  but `earthquake.usgs.gov` is not reachable from this sandbox. On an unrestricted machine the
  query is a single FDSN request for the GeoDAWN bounding box.
* **Verdict:** **[BLOCKED]** here; the cheapest of the blocked ideas to land next session.

## H67-E — Geothermal surface-expression corroboration (wells, springs, vents, travertine) — rank 5, data present, not used in the shipped rule

* **Layers:** GDR 1391 "Well and Spring Temperature and Chemistry"
  (DOI **10.15121/1881483**, CC BY 4.0) already mirrored in this family of repositories as
  `gdr_wellspring_in_footprint.csv`, plus `gdr_volcanic_vents_in_footprint.csv`.
* **Signature:** a kernel density of thermal springs/wells *offset from* mapped faults along
  the fault's strike — the classic structural control of geothermal upflow.
* **Why it could catch a new fault:** a thermal spring that sits on no mapped fault is direct
  evidence of an unmapped structure.
* **Why it is not in the shipped rule:** the metric scores *fault geometry*, not heat; a spring
  density field is a smooth, low-resolution prior, and its use would need a masked-holdout test
  of its own (the delivered rule was already at the top of the exposure sweep, and the brief's
  budget is three experiments). **Deliberately deferred, not rejected.**
* **Leakage caution for whoever picks this up:** the GDR mirror carries a `dist_known_fault_px`
  column that is derived from the labels. Using it would be leakage; it is documented in
  `data/registry.json` and must be dropped.

---

## Rank summary

| rank | candidate | expected DTI gain | implementation cost | status |
| --- | --- | --- | --- | --- |
| 1 | H67-A multi-physics evidence + context head + greedy cover | large (measured +0.15 over the lane's own geometry gate) | low (minutes, CPU only) | **shipped** |
| 1b | H67-A2 credit-weighted greedy emission + marginal-bar stopping rule | 0.2691 → ≈0.34 projected (MODEL); ceiling at our coverage is 0.4217 | low (one emission function + one holdout run) | **next session's first experiment** |
| 2 | H67-B public USGS-derived LiDAR/radiometric families | small on top of A; helps tip zones by construction | low | implemented, in `evidence/holdout_ml_ext.json` |
| 3 | H67-C 1 m DEM scarplet chains | potentially large (targets the missing tip zones) | high (data + compute) | BLOCKED here |
| 4 | H67-D raw ComCat seismicity lineaments | medium, unmeasurable here | medium | BLOCKED here |
| 5 | H67-E thermal-spring corroboration | unknown, needs its own holdout test | low | deferred |
