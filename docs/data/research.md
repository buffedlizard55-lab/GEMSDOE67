GEMSDOE67 RESEARCH KNOWLEDGE BASE
==================================
Evidence classes used throughout: [OFFICIAL] organizer/publisher material,
[PEER-REVIEWED] journal/conference literature, [FAMILY] the group's own
measured receipts (never scores), [MODEL] our instruments' projections.

1. THE PROBLEM — blind geothermal systems in the Great Basin
------------------------------------------------------------
[OFFICIAL] DOE GEMS Prize (DrivenData #306): given the GeoDAWN airborne
magnetic/radiometric survey stack (19 layers: TMI, RTP, magnetic gradients,
isostatic gravity + gradients/slope, tilt angle, geodetic strain-rate trio,
earthquake proximity/density, detrended elevation + slope, depth to basement,
MT conductivity surface) over NW Nevada at 100 m, plus the USGS/INGENIOUS
mapped-fault catalogue (labels.tif / existing_faults.tif, 60,988 fault cells),
predict the location of geothermal-indicative FAULTS THAT ARE NOT IN THE
CATALOGUE. Scoring: distance-weighted Tversky index (DTI).

Why faults, not vents: in extensional Great Basin geothermal systems
(Steamboat Hills, Brady's Hot Springs, Desert Peak, Blue Mountain), permeability
is structurally controlled — faults and fault intersections are the upflow
conduits; the "discovery target" the prize encodes is the hidden fault network
that bounds and feeds the systems. Blind systems lack the surface hydrothermal
alteration/young-volcanism markers that easy targets have (classic literature:
fault-controlled flow in the Basin & Range; see the About page resources).

2. THE METRIC AS DECISION THEORY [OFFICIAL formula, FAMILY algebra]
------------------------------------------------------------------
DTI = TP_w / (TP_w + 0.2*FP_w + 0.8*FN_w), triangular kernel k(d)=max(1-d/300m,0).
Identity (verified against brute force in tests): DTI = T / (0.2(T+S-M) + 0.8|G|),
T = covered truth credit, S = total emitted mass, M = total dot self-credit.

Consequences (each one a design lever):
  a. A dot whose mass does not raise T costs 0.2 of denominator per unit mass.
  b. An uncovered truth cell costs 0.8 — recall is 4x more expensive than the
     mass of one misplaced cell, but coverage saturates at 1 per truth cell.
  c. Break-even for one non-redundant dot: k > alpha*DTI. At DTI ~ 0.28 that is
     credit > 0.056 — i.e. a dot more than ~283 m from its truth cell is a loss.
  d. Therefore: emit sparse DOT FIELDS on the highest-credit cells (thin the
     surface; do not emit thick ribbons), and stop when marginal credit < bar.

This is why the family's ladder thinned surfaces to dots (d2.8 spacing) and
pruned flank dots — allocation-side gains (FAMILY, ORGANIZER-CONFIRMED rungs).

3. WHY THE HIDDEN TRUTH IS NOT THE CATALOGUE SURFACE [FAMILY + PEER-REVIEWED]
----------------------------------------------------------------------------
- The organiser truth is unpublished. Our only instrument is hide-and-recover
  on the visible catalogue; it PROXIES discovery skill and cannot reward a
  genuinely new fault (IR-32-PROXY-01 in the family register).
- FAMILY live-mirror inference: hidden truth is scattered around evidential
  surfaces at ~1.85 px (185 m) scale — covering the mapped surface exactly is
  the wrong objective; covering the surface blurred by that scale is better
  (greedy_smoothfield +0.0140±0.0003, 16/16 paired draws in GEMSDOE32's
  truth-model MC [MODEL], not a score).
- PEER-REVIEWED tip under-mapping: mapped fault tips fall below resolution —
  ~500 m per fault in one seismic-array study (Southampton eprint 76146); DEM
  truncation of >= 100-200 m at tips in another rift (UCD Fault Analysis Group
  TSG-2008 abstract; exact URL pending manual verification — IR-67-SRC-01).
  Implication: the segments most likely to be MISSING from the catalogue are
  tip continuations and tip-adjacent splays — the exact target of the
  orientation/tip lane.

4. THE LANE — geometry-aware decoding (this repository)
------------------------------------------------------
[PEER-REVIEWED] Batra et al., CVPR 2019 (doi:10.1109/CVPR.2019.01063): stacked
multi-branch heads that learn orientation jointly with segmentation produce
better line-network topology than per-pixel classification alone.

Adaptation for undirected faults (this repo):
  * axial orientation head -> (cos 2t, sin 2t), supervised within 3 px of
    visible catalogue traces (strike is undirected; doubling the angle makes
    t == t + pi);
  * tip/junction head -> Gaussian heat (sigma = 1.5 px) on visible-trace
    endpoints and junctions;
  * decode: hysteresis grown only along orientation-consistent support
    (|dtheta| <= 45 deg to the nearest seed axis), orientation-aware NMS
    (thin along the predicted normal), then tip extension of <= 6 px (600 m)
    along the outward strike where segmentation support persists;
  * flank prune within 2 px of the mapped catalogue (h33 lesson), tip
    extensions protected;
  * nodes: shared greedy marginal-DTI allocation (k_truth prior 45,000 px,
    preregistered from the ORGANIZER-CONFIRMED mass regime 37.7k-46k).

Named non-fault processes that could mimic the signal (must stay in every
run card): fluvial terrace risers and channel-bank lines (scarp-like curvature
and orientation coherence), landslide headscarps, playa shorelines and
evaporite fronts (conductivity contrast), roads/canals/canals (linear, tip-like
endings), lithologic contacts (coherent magnetic edges without fault throw).

5. WHAT IS VERIFIED HERE, AND WHAT IS NOT
----------------------------------------
VERIFIED: data sha256 pins to the family bridge (byte-identical to the
Drivendata data-tab rasters per the bridge manifest); grid constants re-derived
from the rasters themselves; metric implementation vs official worked example
and vs O(n^2) brute force (tests/test_metric.py in the template); unit tests
for every decode primitive (tests/test_lane.py); on-disk submission format
receipts (scripts/validate_submission.py).
NOT VERIFIED: the organiser's private evaluator behaviour; whether round two
rescores G; the exact tip-study URL (IR-67-SRC-01); live leaderboard state
after 2026-10-04 (IR-67-LB-01); that any HOLDOUT-DTI predicts a leaderboard
score (it does not — different truth).

6. LIMITATIONS (read before acting on this page)
-----------------------------------------------
* HOLDOUT-DTI values here are conditional on catalogue truth and fixed budgets;
  the bootstrap CI is not a leaderboard interval.
* The heads are linear models on a single survey grid; "learning" = calibrating
  fabric->catalogue geometry, not deep training (no GPU, no hidden labels).
* The registry used for uniqueness is the accessible public family inventory,
  not an organiser-complete list.
* Absolute holdout DTI of this lane (order 0.03-0.04) is NOT comparable to the
  family's catalogue-proxy figures (order 0.16): different budgets and scoring
  domains. Only paired contrasts at matched pipeline settings are meaningful.
