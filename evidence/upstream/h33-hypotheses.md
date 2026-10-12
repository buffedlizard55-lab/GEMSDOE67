# H33 — five untried geological hypotheses, ranked, with the evidence for each

**Session:** Arena `arena/01a10714-gemsdoe32` · **Date:** 2026-10-04
**Question this file answers:** *what have we not tried, which of it can be validated locally, and
which of it needs new external data?*

Every claim carries an evidence class: **[OFFICIAL]** read from an organizer/USGS page or product,
**[MEASURED]** computed in this checkout from hash-pinned bytes (command given), **[OWNER-REPORT]**
the group's own unverified ledger, **[BLOCKED]** could not be obtained here, with the reason stated.

---

## 0. Why new hypotheses are needed at all

**[MEASURED, `evidence/instrument_calibration.json`]** Twelve artifacts with owner-reported live
scores (0.0107 … 0.2600) were re-scored on this repository's own holdout. The rank correlation with
the live board is:

| local instrument | Spearman ρ vs live (n=12) |
| --- | ---: |
| `catalogue_hidden` (the repo's historical headline proxy) | **+0.087** |
| `catalogue_hidden_strict` (no free mass on mapped faults) | +0.087 |
| `sgmc_prevalence_calibrated` | +0.498 |
| `drift_corrected_holdout_mean` (the repo's promotion instrument) | **+0.510** |

Within a single family the instrument is monotone against live (H19-5 121,131 px → 0.1922,
d1.5 60,069 px → 0.2477, d2.8 44,090 px → 0.2600, with `catalogue_hidden` 0.0697 < 0.0945 < 0.0983),
but **across families it is not a statistically significant ranker** (n=12, ρ=0.51, p≈0.09). Any
"we beat the holdout" claim is therefore a **screen**, never evidence of a leaderboard gain — which
is exactly why the three-slot identification experiment (`knowledge/02` §6) exists. This is the
"persistent gap between what the surrogate predicts and what the leaderboard returns" the brief
asks to be treated as *evidence the holdout has drifted*, and it is quantified here rather than
asserted.

**[MEASURED]** One instrument defect is now named and quantified: the historical
`catalogue_hidden` proxy removes *every visible catalogue pixel* from the scored domain
(`holdout.py`: `active = valid & ~known`), so a dot placed on a mapped fault is never charged the
`α = 0.2` false-positive penalty, even though the live scorer only ever sees *new* faults as truth.
Placing mass on the catalogue is therefore **free in the proxy and expensive live**. The strict
variant charges it; the two differ by up to 0.056 of DTI (8GEMSDOE `Hedge-v2`: 0.28159 → 0.22550)
and the strict variant ranks live no better (ρ = +0.087 versus +0.087).

---

## 1. The five candidates

Ranked by *expected DTI gain per unit of implementation cost*, with the local-validatability and
data-dependency of each stated honestly.

### H33-A — Multi-physics oriented-lineament consensus — **rank 1, implementable now**

* **Layers [OFFICIAL band names, read from `training_features.tif` band descriptions]:**
  `rtp` (2), `tmi` (14), `mag_anom` (1), `iso_grav_anom` (13), `det_elev` (12), `cond_surf` (17),
  `depth_to_base_surf` (15); GeoDAWN radiometrics (`geodawn_rad_u8.tif` bands K, Th, TC) and the
  1 m LiDAR scarp composite (`lidar_scarp_features_u8.tif` bands `ex_max`, `step_max`,
  `downface_max`).
* **Physical signature:** per physics, a scale-normalised **Hessian line response**
  (Frangi/Sato, *both* polarities — a magnetic low and a magnetic high are equally good contact
  markers) at σ = 1.2 and 2.5 px, times a **second-order orientation order parameter**
  `R = |Σ_p w_p e^{2iθ_p}| / Σ_p w_p` — i.e. a pixel scores only if independent physics agree that
  *a line exists* and *which way it runs*.
* **Why it should catch a fault the catalogue lacks:** an expert who can only add a fault to the
  catalogue by eye accepts it when *several* fields agree. The USGS/INGENIOUS catalogue is
  dominated by faults that were mappable in one dataset (topography, or the previous state map).
  Requiring multi-physics strike agreement selects exactly the class that single-dataset mapping
  under-represents, and does so without ever looking at the catalogue.
* **How it differs from everything in this repo:** `features.py`'s 35 channels contain per-band
  ridge responses and gradient magnitudes, and H32-A/B/C contain *pixel-wise products* of band
  transforms; **no existing channel or surface requires independent physics to agree on an
  orientation.** The order parameter is the new object.
* **Cost:** ~40 s CPU, no new data. **Validatable locally: yes.**

### H33-B — Aligned drainage-valley chains — **rank 2, implementable now**

* **Layers:** `det_elev` (12), `det_elev_slope` (19).
* **Physical signature:** a valley skeleton (NMS ridge of **−`det_elev`**) multiplied by a
  9-pixel, 16-direction **collinearity vote** (the mean skeleton occupancy along every straight
  line through the pixel), de-emphasised where `det_elev_slope` is high.
* **Why it should catch a fault the catalogue lacks:** faults with no preserved scarp still
  deflect and align drainage. A single straight valley is a stream; **a chain of collinear valley
  segments across several drainages is a structure**, and that is precisely the evidence that a
  scarp-height map cannot see. **[OFFICIAL]** the provided `det_elev` is *detrended* elevation —
  the correct input for channel-network extraction (band description: *"Detrended elevation -
  topography with regional trends removed"*).
* **Novelty:** every DEM-derived channel in this repo is *local* (curvature, ridge response at 3
  scales, 5-px relief, 5×5 top-hat); nothing aggregates evidence **along** a candidate line.
* **Cost:** ~25 s CPU, no new data. **Validatable locally: yes.**

### H33-C — En-echelon scarplet chain vote (1 m LiDAR) — **rank 3, implementable now**

* **Layers:** `lidar_scarp_features_u8` (`ex_max`, `step_max`, `downface_max`).
* **Physical signature:** scarplet skeleton (NMS ridge **and** contrast against the local minimum,
  i.e. a scarp rather than a slope break) × an 11-pixel collinearity vote.
* **Why it should catch a fault the catalogue lacks:** the competition grid is 100 m; a < 1 m throw
  produces no 100 m-averaged signal. Expert mappers accept a fault when *en-echelon* scarplets are
  collinear over hundreds of metres — a criterion that is invisible at 100 m and that the current
  repo uses only as a per-pixel corroboration weight.
* **Novelty:** the LiDAR product enters H32-A/B/C only as a scalar weight `0.45·b1 + 0.35·b2 +
  0.20·b5`; here it is skeletonised and *chained*.
* **Cost:** ~20 s CPU, no new data (the product is already hash-pinned). **Validatable locally: yes.**

### H33-D — Long-straight conductive / basement structural boundary — **rank 4, implementable now**

* **Layers:** `cond_surf` (17), `depth_to_base_surf` (15).
* **Physical signature:** gradient magnitude × **directional coherence of the gradient direction**
  over a 3×3 window — a *straight boundary*, not a blobby anomaly.
* **Why it should catch a fault the catalogue lacks:** magnetotelluric conductivity and basement
  depth image the *subsurface*; a straight conductivity step locates a fault under cover, where a
  surface-expression catalogue has nothing to record.
* **Novelty:** both bands enter `features.py` as scalars or plain gradient magnitudes.
* **Cost:** ~15 s CPU, no new data. **Validatable locally: yes.**

### H33-E — Sub-kilometre seismicity lineaments from the raw catalogue — **rank 5, DATA-BLOCKED here**

* **Layers:** would replace/augment `ieq_n100a15` (16) and `deq_n100a15` (10).
* **Physical signature:** epicentre density + **focal-mechanism nodal-plane strikes**; a fault that
  is unmapped but active carries earthquakes whose preferred nodal plane is the fault plane.
* **Why it should catch a fault the catalogue lacks:** instrumental seismicity is a *dynamic*
  inventory — blind, low-slip faults light up seismically while leaving no scarp.
* **Measured justification [MEASURED, this checkout]:** the supplied seismic bands are computed on a
  100 km radius and carry no fault-scale information:

  | band | ρ(lag = 0.5 km) | ρ(1 km) | ρ(3 km) | ρ(10 km) |
  | --- | ---: | ---: | ---: | ---: |
  | `ieq_n100a15` (16) | 0.9994 | 0.9986 | 0.9935 | 0.9534 |
  | `deq_n100a15` (10) | 0.9777 | 0.9447 | 0.8408 | 0.5813 |
  | `tmi_hg` (3) | 0.6680 | 0.5471 | 0.3457 | 0.1346 |
  | `det_elev` (12) | 0.9781 | 0.9416 | 0.7344 | 0.0096 |

  At the metric's own resolution (300 m) `ieq` is **constant by construction**: two pixels 3 km
  apart are 0.9935-correlated. The information the fault-scale question needs is simply not in the
  band.
* **Source, named and checked [OFFICIAL]:** USGS earthquake catalogues are free and public
  (FDSN event web service, `https://earthquake.usgs.gov/fdsnws/event/1/query`, and the ComCat UI
  `https://earthquake.usgs.gov/earthquakes/search/`; products include moment tensors/nodal planes).
  **Obtainability check performed here:** `curl` from this sandbox returns HTTP 000 for
  `earthquake.usgs.gov` (the sandbox egress allow-list admits only `api.github.com`, `pypi.org` and
  a few others), and the browsing path returned HTTP 500 for the FDSN query URL. The source is
  therefore **named but NOT verified obtainable from this sandbox**; per the brief it is ranked and
  **not proposed as ready**. A ready-to-run fetcher is provided
  (`scripts/fetch_earthquake_catalog.sh`) for an unrestricted machine; until it runs, no earthquake
  surface is fabricated.

---

## 2. Ranked decision table

| rank | hypothesis | layers | signature | off-catalogue reason | novelty vs this repo | cost | local validation | data |
| ---: | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | **H33-A** | 8 official bands + radiometrics + LiDAR | Hessian line response × orientation order parameter | multi-physics strike agreement selects what single-dataset mapping misses | no channel requires *independent* physics to agree on an orientation | 40 s | yes | none |
| 2 | **H33-B** | `det_elev`, `det_elev_slope` | valley skeleton × 16-direction collinearity vote | scarp-less faults still align drainage | DEM channels are all local; none aggregates along a line | 25 s | yes | none |
| 3 | **H33-C** | LiDAR scarp product | scarplet skeleton × 11-px chain vote | sub-100 m en-echelon scarplets are invisible at 100 m | LiDAR is used only as a per-pixel weight | 20 s | yes | none |
| 4 | **H33-D** | `cond_surf`, `depth_to_base_surf` | gradient × directional coherence | subsurface boundary under cover | both bands are used as scalars | 15 s | yes | none |
| 5 | **H33-E** | earthquake catalogue | epicentre lineaments + nodal planes | active blind faults are seismic | supplied bands are 100 km-radius | n/a | **no** | USGS FDSN — **blocked here**, named + fetcher provided |

## 3. Measurements

Hypotheses H33-A…D are implemented label-free in [`src/gems32/h33.py`](../../src/gems32/h33.py)
(no surface reads `labels.tif`, `existing_faults.tif` or any scored artifact) and measured by
`PYTHONPATH=src python3 scripts/run_h33.py --budgets 44090`; the receipts are
[`evidence/h33_holdout.json`](../../evidence/h33_holdout.json). Results and the promotion decision
are recorded in the session README and in `registry/observations.jsonl` (every evaluation, promoted
or not, is an observation for the GP surrogate).

## 4. How to reproduce

```bash
bash scripts/fetch_mirrors.sh                     # 23/23 sha256-verified (no DrivenData auth)
PYTHONPATH=src python3 scripts/prepare_data.py    # 19 bands -> .cache/gems_work/bands
PYTHONPATH=src python3 scripts/calibrate_instrument.py   # the 12-artifact rank calibration
PYTHONPATH=src python3 scripts/run_h33.py --budgets 44090
PYTHONPATH=src python3 scripts/run_h34.py --sigmas 0,0.75,1.25 --budget 44090
```
