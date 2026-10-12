# Repository and scientific audit

## Scope and first-pass findings
The starting commit `8a64f734670f21139506c019ed1b1040b8e66464` contained only the README
heading. There were no previous-session tasks, scripts, cached feature stack, models, or
holdout best in this checkout. The prompt's claim that only data placement remained was
not true of this repository. The GitHub API inventory in `evidence/repository_inventory.json`
records related repositories, tree hashes, raster paths and candidate shared tooling. A
file-tree inventory does **not** verify each website, model, raster, score or receipt.

The owner's GitHub data bridges supplied the cached numerical feature stack, labels and
sample grid. They were restored successfully with SHA-256 checks. Raw data stay ignored,
out of the PR. No DrivenData login was used. Official-origin authenticity remains unverified.
The sample raster is used solely for its finite footprint and georeferencing; its nonzero
values are never model inputs. The labels mirror is the existing-fault raster, not private
competition ground truth.

## Why GEMSDOE32's leading example might have worked
The retrieved H33-2-B2 audit describes removal of all dots within two pixels of the
catalogue from an existing dotted base. It lists the resulting support, hashes and grid.
This is a change in **emission allocation**, not evidence of a new physical fault detector.
Its shared DTI arithmetic uses a maximum triangular credit per truth pixel. Closely spaced
predictions can have overlapping coverage while each prediction still contributes a
false-positive term. Deleting poorly placed dots can reduce that term more than it loses
coverage. Whether near-catalogue dots are poorly placed depends on actual withheld truth:
no universal catalogue buffer is justified, especially in the tip-recovery lane.

**Can we beat the user-reported result?** It is possible in principle, but neither those
historical scores nor the mechanism establishes that this candidate will do so. A useful
experiment must beat comparable buffered hide-and-recover controls and recover masked tips;
even then it is not an organizer score or leaderboard forecast. Optimizing against a
catalogue-biased proxy may select methods that fail on newly mapped faults.

## Irregularities requiring review
- The request contains conflicting current-leader figures. No organizer receipt was
  available. This repo makes no ORGANIZER-CONFIRMED performance claim.
- The H33 audit labels its candidate UNSCORED while containing a projected leaderboard
  number and a slot-eligibility declaration. Its reported pooled summaries do not agree
  with the scale of the listed quadrant values. They cannot be used as a comparable
  holdout best. Its long submission notes also exceed this lane's short-note contract.
- Several template lineages coexist. We use the commit and per-file SHA-256 values in
  `evidence/template_pin.json`, unchanged. No private evaluator fork was introduced.
- Original catalogue polylines are not supplied. Skeleton/PCA labels are approximate.
  Digital diagonal adjacency can produce false junctions. This limits geological claims.
- The restored feature bands include missing-value sentinels; they must not be treated as
  real extremes. Training-only median imputation and scaling are used by the prototype.
- A high feature AUC is a leakage alarm, not proof; a low one is not proof of no leakage.
- The inventory includes inputs, intermediates, quarantined outputs, duplicated mirrors
  and submissions. It is not a certified complete prior-submission registry. Hash/pixel,
  rank and dot-overlap clearance for a final candidate is therefore NOT asserted.
- The shared writer emits finite zeros outside the footprint. This satisfies “NaN only
  outside” as a restriction, without requiring any NaNs. The prior portal range error
  cannot be diagnosed from its message alone: negative sentinels, infinity, unnormalized
  output and NaN handling must each be checked. Do not blindly clip an invalid file.
- The official reference README supports CPU training. A GPU is useful but not logically
  required. The current small CPU model is not a spatial CNN and cannot validate Batra's
  full architecture.

## DTI labels and scientific restraint
Only measured experiment results from the pinned evaluator are labelled HOLDOUT-DTI,
with evaluator version, withheld positives and spatial-bootstrap confidence intervals.
AUC, kernel recall, sample counts and format diagnostics are not DTI scores. Historical
upstream evidence is stored verbatim as secondary evidence, including its problematic
projections; those numbers are not adopted as this project's results.

No direct observation of geothermal vents is inferred. Fault geometry can be relevant to
fluid flow, but neither permeability nor temperature is demonstrated by a line detector.
All proposed hypotheses and non-fault mimics are in `research/hypotheses.md`.
