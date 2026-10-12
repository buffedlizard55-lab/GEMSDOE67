# Irregularities flagged for human review — lane 67

Each entry states the measurement, the artifact that carries it, and what decision it blocks.
Nothing here is a request to loosen a gate: the gates stay as the owner wrote them, and this
lane reports itself as non-compliant where it is.

## IR-67-OVERLAP-01 — the literal registry overlap gate cannot be satisfied

* **Measurement.** `gems13_r13_lattice_s5_00904.tif` (206,895 positive pixels) has a 3 px
  dilation covering **99.87 %** of the 5,167,373-pixel footprint. A uniformly random
  37,654-dot set scores **0.9988** forward overlap against it.
* **Consequence.** The inherited stop condition “> 70 % of our dots within 3 px of one prior's
  dots” fires for *any* dense candidate. The 0.2778 champion also fires it
  (`worst_overlap = 1.0000`, `duplicate_count = 40`), so the criterion does not separate good
  submissions from duplicates.
* **Artifacts.** `evidence/e3_uniqueness.json` (`worst_overlap`, per-prior rows),
  `evidence/e3_uniqueness_gate.json`.
* **Blocked decision.** Lane promotion cannot be decided by this gate. The vendored module
  documents the failure mode deliberately (“no density exemption … the audit reports the
  problem, rather than quietly changing the owner's protocol”); the owner should decide
  whether dense lattices are inside the lane definition at all.
* **Substantive distinctness, for the record.** Worst rank correlation over the 51 mirrored
  priors 0.0289 (limit 0.90), worst Jaccard 0.019, and versus the 0.2778 champion: 25.9 % of
  our dots within 3 px of its dots, 12.3 % the other way, Jaccard 0.0083, no shared rays.

## IR-67-MARGINAL-01 — the calibrated marginal-DTI rule is degenerate on this field

* **Measurement.** The shared surrogate's covered credit grows with every added dot, because
  dots are scored against the posterior that placed them: `emit.surrogate_terms(...)`
  `surrogate_dti` rises monotonically 0.247 → 3.533 as the budget grows 500 → 37,654 dots.
* **Consequence.** “Calibrated greedy marginal-DTI selection” cannot select a budget from the
  surrogate; the lane therefore selected on instrument A (withheld segments) and confirmed on
  instrument B, and says so on the run card
  (`evidence/e3_submission_receipt.json` → `budget_selection`).
* **Owner action.** The marginal test needs the metric's own algebra
  (`gems57.metric.marginal_inclusion_threshold`) rather than a posterior surrogate.

## IR-67-CATALOGUE-01 — the two catalogues disagree by more than half

* **Measurement.** `vector_in_raster_1px = 0.3639` (only 36 % of the vector trace pixels have a
  raster label pixel within 1 px), while `raster_in_vector_1px = 1.0000`; exact intersection
  32,052 of 198,450 vector pixels; 126,344 vector pixels lie outside the footprint.
* **Consequence.** The external vector compilation is a superset of the revealed raster labels.
  Anything supervised on the raster labels (this lane's heads, its 200 m exclusion) is
  supervised on a subset; the score is defined against the raster labels only.
* **Artifact.** `evidence/e1_verify_canary_heads.json` → `vector_raster_agreement`.

## IR-67-INSTRUMENT-01 — the two holdout instruments disagree in direction

* **Measurement.** Instrument A prefers `lattice_d3` (0.02218) to matched `random` (0.01088);
  instrument B prefers `random` (0.01295) to `lattice_d3` (0.01263). A sibling lane measured
  holdout-DTI against the public leaderboard as uncorrelated (Spearman −0.10).
* **Consequence.** A gate expressed as “a DTI gain” is not adjudicable with these instruments,
  which is why this lane's verdict is *negative on the evidence available* rather than
  *promote* — the same code could be promoted later on a better instrument.
* **Artifact.** `evidence/e2_arms_holdout.json`.
