# Preregistered lane hypotheses — 2026-10-12

These are hypotheses, not discoveries or projected scores. Rank is qualitative expected
**incremental hide-and-recover utility**, not a numerical leaderboard forecast. The starting
GEMSDOE67 repository had no methods at all. Novelty across all related repositories is NOT
established: the inventory is a file-tree audit, not exhaustive scientific code review.

| Rank | Candidate and layers | Physical signature / missing-fault rationale | Named non-fault mimic | Cost / distinction |
|---|---|---|---|---|
| 1 | H67-A: axial continuation; cached magnetic, gravity, detrended-elevation and other supplied numerical bands | Jointly learn segmentation, undirected strike (cos 2θ, sin 2θ), and endpoint/junction likelihood; thin across strike and connect along it. Weak but directionally coherent signal may recover unresolved continuations rather than simply copy mapped lines. | Lithologic contacts and aligned erosional channels | Medium; new trainable multi-head decoder, not B2 pruning of a prior raster. Test first. |
| 2 | H67-B: cross-physics orientation agreement; RTP/TMI, gravity anomaly, detrended elevation | Separate magnetic/gravity/topographic orientation heads and permit continuation only under agreement. Potential-field edges may persist where surface expression fades. | Aligned volcanic contacts | Higher; within the same orientation lane. Cross-physics orientation agreement already appears in GEMSDOE32 H33-A; novelty would be *learned, fold-isolated heads*, NOT the agreement concept. Not run. |
| 3 | H67-C: tip uncertainty; same supplied layers plus endpoint supervision from visible trace geometry | High tip likelihood with coherent orientation but weak segmentation triggers support-bounded continuation. Explicitly model truncation uncertainty, not a universal length correction. | Alluvial fan margins | Medium; new uncertainty-aware termination rule here. Existing GEMSDOE33 and GEMSDOE53 tip concepts make global novelty unproven. Not run. |
| 4 | H67-D: junction-safe decoding; supplied magnetic/gravity/elevation layers plus visible junction labels | Retain multiple locally supported orientations at likely junctions instead of suppressing the weaker branch. Could recover small splays overlooked by a single-line mapper. | Drainage confluences | High; mixture orientation head is an extension of this lane, not a new prior-raster ensemble. Not run. |

## Data and scientific limits
No additional external data proposed as currently viable. Restored cached numerical layers
are from the owner mirror, not independently authenticated official downloads. Catalogue
polylines are absent; raster-derived skeleton endpoints and local PCA strike are **proxy
supervision**, not authentic mapped polyline endpoints. Raster junction labels are sensitive
to digitization. Physical faults and geothermal permeability/vents are not interchangeable.

Batra et al. DOI supplied by user: https://doi.org/10.1109/CVPR.2019.01063 . The transfer
from road topology to faults and axial rather than directed angles is a hypothesis. Full
paper and Southampton eprint 76146 / UCD TSG-2008 claims cannot be independently checked
through this environment's permitted network hosts. No fixed metre-scale extension is
inferred from those unverified summaries.

## Experiment preregistration
One controlled experiment: small CPU joint neural heads vs the same architecture with
auxiliary losses disabled; fixed random seed, fixed training steps, fixed decoding thresholds,
5 px node separation. This is NOT a reproduction of Batra's stacked CNN. Shared hidden trunk,
axial and heatmap heads feed a second segmentation stage. Raw cached bands only; no catalogue
input feature. Skeleton geometry is used only as fold-visible training targets. Train only
outside the shared fold exclusion buffer. Evaluate through unchanged `gems57.evaluate_holdout`.
Report pooled paired physical-block bootstrap CIs and tip-adjacent recovery. No test-set tuning.

Promotion requires a positive paired DTI-gain CI, improved tip-adjacent recovery, comparison
with a reproducible current holdout best, feature canaries, surface/final uniqueness against
all registry rasters, and on-disk validation. Missing evidence fails closed. No weekly slot
is used, even if a local diagnostic succeeds. Maximum three experiments / two hours.
