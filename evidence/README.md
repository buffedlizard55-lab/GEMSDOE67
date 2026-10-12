# Evidence conventions

- `data_restore.json`: measured hashes of owner-mirrored input bytes, not organizer authentication.
- `data_audit.json`: measured restored grid and band metadata.
- `feature_canaries.json`: AUC diagnostics on shared buffered folds; **not DTI**.
- `experiment.json`: one measured CPU research experiment, including pooled HOLDOUT-DTI,
  paired conditional confidence intervals and tip-recovery diagnostics.
- `template_pin.json`: exact shared-template commit and local per-file hashes. Tests enforce
  byte identity. Unused shared-template modules are retained for provenance, not run as methods.
- `repository_inventory.json`: GitHub tree listing, not exhaustive website/score verification,
  artifact retrieval, scientific code review or global-uniqueness clearance.
- `upstream/`: secondary source snapshots retained for review only. Historical scores,
  projections, claims of official verification, slot declarations and old receipts inside
  these snapshots are **not adopted as GEMSDOE67 results**. Do not run snapshot scripts as
  this project's pipeline. The official training notebook excerpt is training code, not an
  organizer DTI-scoring implementation. Source links are in `research/sources.csv`.

No organizer receipt or submission TIFF exists for this run. The canonical final run card
is `docs/run-card.json`. Null fields intentionally indicate missing measurements.
