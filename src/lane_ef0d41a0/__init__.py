"""GEMSDOE67 lane: axial orientation head + tip/junction head with geometry-aware decoding.

Lane paragraph (from the session brief, reproduced in ``PROMPT.md``):

    Add an axial orientation head (cos 2theta, sin 2theta, the adaptation for
    undirected faults, supervised within 3 px of catalogue traces).  Add a
    tip/junction heatmap head (Gaussian sigma = 1-2 px at polyline endpoints and
    junctions).  Decode with orientation-aware non-maximum suppression and
    hysteresis.  Extend traces past mapped tips only along predicted orientation
    where probability support persists.  Select nodes by calibrated greedy
    marginal-DTI selection or 4-5 px spacing.

Nothing in this package writes a score.  Every measured number is produced by
``gems57.evaluate_holdout`` / ``gems57.metric`` (the shared template pinned in
``vendor/gems57``) and is labelled HOLDOUT-DTI with its evaluator version and
withheld-positive count.
"""
from __future__ import annotations

__all__ = ["fields", "heads", "decode", "arms"]
