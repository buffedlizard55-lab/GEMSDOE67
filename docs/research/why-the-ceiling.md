# Why every emission family in this project parks at 0.26–0.28

*Forensic note, 2026-10-12. All numbers below are recomputed from `evidence/*.json` by
`scripts/ceiling_analysis.py`; run it and you get the same table. Nothing here is a score —
the only organizer scores that exist are on the leaderboard.*

## 1. What the score actually is

The organizers publish the metric (problem description, *Performance metric*):

```
k(d)  = max(1 − d/300 m, 0)          triangular kernel, R = 300 m = 3 px at 100 m
TP_w  = Σ_{g∈G} max_{x} p(x)·k(d(x,g))
FP_w  = Σ_{x: p(x)>0} p(x)·(1 − max_g k(d(x,g)))
FN_w  = Σ_{g∈G} (1 − max_x p(x)·k(d(x,g)))
DTI   = TP_w / (TP_w + 0.2·FP_w + 0.8·FN_w)
```

Two algebraic identities matter (both unit-tested in `tests/test_metric.py`):

1. `FN_w = |G| − TP_w` exactly, for any prediction clipped to [0, 1].
2. therefore `DTI = T / (0.8·|G| + 0.2·FP_w + 0.2·T)`.

Divide through by `|G|` and write `c = T/|G|` (credit-weighted coverage: the share of hidden
truth that earns credit) and `w = FP_w/|G|` (waste expressed in units of the hidden truth count):

```
DTI = c / (0.8 + 0.2·c + 0.2·w)
```

That is the whole story. `0.8` sits in the denominator for *every* hidden pixel whether or not
you find it, so:

* **coverage is what pays** — a single hidden pixel found at zero distance adds 1.0 to `T` and 0.2·0.8
  to the denominator through the `0.2·c` term,
* **waste is a slow tax** — 0.2 per unit of mass that lands further than 3 px from truth (at most;
  fractionally less as it approaches),
* and the marginal bar that decides whether one more dot helps is `k > 0.2·DTI`, where `k` is its
  best kernel weight to a hidden pixel. Verified numerically, not just derived.

## 2. The measured coordinates of every family

Recovered from the pooled holdout evidence (`evidence/holdout.json`,
`evidence/holdout_ml_ext.json`); `T/S` is credit earned per unit of emitted mass, i.e. efficiency.

| arm | pooled DTI | coverage `c` | waste `w` | `T/S` | ceiling at its own `c` |
| --- | ---: | ---: | ---: | ---: | ---: |
| `ML_cover_allpix_tau0.3` (shipped) | **0.2691** | 0.3684 | 2.477 | 0.139 | **0.4217** |
| `ML_cover_allpix_tau0.2` | 0.2671 | 0.4248 | 3.529 | 0.114 | 0.4800 |
| `ML_cover_allpix_tau0.1` | 0.2579 | 0.4840 | 4.900 | 0.094 | 0.5397 |
| `ML_cover_allpix_tau0.05` | 0.2536 | 0.5082 | 5.513 | 0.088 | 0.5637 |
| `ML_cover_allpix_tau0.5` (sibling) | 0.2207 | 0.2311 | 1.004 | 0.209 | 0.2731 |
| `ML_cover_geom_tau0.3` (geometry gate as mass filter) | 0.0966 | 0.0847 | 0.300 | 0.254 | 0.1037 |
| `A0_incumbent_dots` | 0.0014 | 0.0012 | 0.029 | 0.038 | 0.0014 |

Read the last two columns together: the *efficiency* ranking is the exact reverse of the *score*
ranking (`geom` is the most efficient and scores worst; `tau0.05` is the least efficient and is
second-worst). That is the signature of a **coverage-limited regime**: at this ranking quality,
buying coverage costs waste roughly in proportion, so the score runs along a Pareto ridge instead
of climbing. The ridge is where 0.26–0.28 comes from — it is not a writer bug, not a format
problem, and not a calibration problem.

## 3. What would have to change

`scripts/ceiling_analysis.py` also inverts the identity: the coverage needed to reach a target
score at the shipped arm's own waste level.

| target DTI | needed `c` at zero waste | needed `c` at our waste (2.477) | our `c` |
| ---: | ---: | ---: | ---: |
| 0.30 | 0.2553 | 0.4134 | 0.3684 |
| 0.35 | 0.3011 | 0.4875 | 0.3684 |
| 0.40 | 0.3478 | 0.5632 | 0.3684 |
| 0.4275 (live #1 on 2026-10-12) | 0.3740 | 0.6056 | 0.3684 |

Two consequences, both hard:

* **The current #1 score is 0.029 above the best possible score our shipped arm could reach even
  with zero waste** (0.4217). No repacking of the same dots reaches 0.4275 — that requires more
  coverage, i.e. a ranking improvement, and only then better packing.
* **Within our arm's own coverage, there is 0.15 of unused headroom** (0.2691 measured against its
  own 0.4217 ceiling) sitting entirely in the waste term. Cutting `w` from 2.48 to ~1.0 at fixed
  `c` would give `0.3684/(0.8 + 0.0737 + 0.2) ≈ 0.34` — a projection (MODEL), not a score.

## 4. Why the project's own history sits in the same band

Sibling repositories in this family emit dots on dilated mapped faults, or topologically thinned
traces with a geometry gate, or kernel-covers with exposure thresholds swept over the same head.
In the coordinates above all of those are *one line*: they differ in how much mass they spend, not
in how much of the hidden truth they find. `A0_incumbent_dots` has `c = 0.0012` — the neighbourhood
of the mapped catalogue contains essentially none of the withheld faults, which is exactly what a
competition built on *catalogue-missing* faults is designed to measure. Every family that then buys
coverage by loosening its geometry gate slides up the same ridge and stops at the same 0.26–0.28.

The live board is consistent with this: entries at 0.28–0.34 differ from the 0.26–0.28 band mostly
in coverage under the same precision regime, and the 0.4275 leader differs by having a better
*ranking* on the region the catalogue never mapped.

## 5. The two honest caveats

1. **`w` is an upper bound.** The holdout's truth is the withheld *catalogue*. A dot on a real,
   geologically coherent scarp that the catalogue does not record is scored as pure waste by this
   instrument. The DrivenData staff answer in forum thread 11527 says the Phase-2 label set is
   produced by expert review of Phase-1 submissions, so part of that "waste" is exactly the signal
   the final round rewards. The holdout therefore ranks *emission families* correctly but reads low
   in absolute terms for coverage-heavy families.
2. **`c` cannot be forced.** Buying the `c` in the table above by loosening the exposure threshold
   (`tau0.05`) *lowers* the score, because `w` grows faster than `c` (measured: 0.2536 at
   `c = 0.508`). Only a better ranking — or an emission rule that spends mass where the model's own
   calibrated probability is highest, with a stopping rule from the marginal bar — moves the ridge
   outward. That is H67-A2 in the hypothesis register, and it is the first thing to test next.
