"""Verification of the metric implementation against the published equations.

Source of truth: https://www.drivendata.org/competitions/306/competition-doe-gems/page/967/
(published worked example: TP_w = 3.00, FP_w = 1.89, FN_w = 2.00 -> 0.60).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gems67 import metric  # noqa: E402
from gems67.grid import ALPHA, BETA  # noqa: E402


def test_published_worked_example():
    """The exact arithmetic printed on the problem description page."""
    v = 3.00 / (3.00 + 0.2 * 1.89 + 0.8 * 2.00)
    assert round(v, 2) == 0.60
    assert round(metric.dti_from_components(3.00, 1.89, 2.00), 2) == 0.60


def test_kernel_values_on_the_100m_lattice():
    """Kernel weights used everywhere else: only 25 offsets are inside the 300 m support.

    Values from the kernel definition itself, not copied from anywhere:
    k(1,1) = 1 - sqrt(2)/3, k(2,2) = 1 - 2*sqrt(2)/3, and the (3,0) offset is exactly 0.
    """
    import math

    offs = {(o[0], o[1]): o[2] for o in metric.kernel_offsets()}
    assert len(offs) == 25
    assert (3, 0) not in offs                      # k(3) = 0 is excluded by construction
    assert offs[(2, 0)] == pytest.approx(1.0 - 2.0 / 3.0, abs=1e-12)
    assert offs[(1, 1)] == pytest.approx(1.0 - math.sqrt(2.0) / 3.0, abs=1e-12)
    assert offs[(2, 2)] == pytest.approx(1.0 - 2.0 * math.sqrt(2.0) / 3.0, abs=1e-12)
    assert round(offs[(1, 1)], 6) == 0.528595
    assert round(offs[(2, 2)], 6) == 0.057191


def _random_case(seed: int, shape=(40, 40), n_truth=12, n_pred=15, soft=True):
    rng = np.random.default_rng(seed)
    truth = np.zeros(shape, bool)
    ti = rng.choice(shape[0] * shape[1], n_truth, replace=False)
    truth.ravel()[ti] = True
    pred = np.zeros(shape, np.float32)
    pi = rng.choice(shape[0] * shape[1], n_pred, replace=False)
    pred.ravel()[pi] = rng.uniform(0.2, 1.0, n_pred).astype(np.float32) if soft else 1.0
    return pred, truth


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_exact_matches_bruteforce(seed):
    pred, truth = _random_case(seed)
    a = metric.dti_exact(pred, truth)
    b = metric.dti_bruteforce(pred, truth)
    assert a["dti"] == pytest.approx(b["dti"], rel=1e-9, abs=1e-9)
    assert a["tp"] == pytest.approx(b["tp"], rel=1e-9, abs=1e-9)
    assert a["fp"] == pytest.approx(b["fp"], rel=1e-9, abs=1e-9)


@pytest.mark.parametrize("seed", [4, 5])
def test_identity_fn_equals_k_minus_tp(seed):
    pred, truth = _random_case(seed)
    c = metric.dti_exact(pred, truth)
    assert c["fn"] == pytest.approx(c["n_truth"] - c["tp"], abs=1e-9)
    k = metric.components(pred, truth)
    assert k["marginal_bar"] == pytest.approx(ALPHA * k["dti"], abs=1e-12)


def test_masked_pixels_leave_every_term():
    """Known-fault masking (forum thread 11516) removes pixels from TP, FP and FN alike."""
    pred, truth = _random_case(6)
    known = np.zeros_like(truth)
    known[5:15, 5:15] = True
    c = metric.dti_exact(pred, truth, known=known)
    p2 = pred.copy()
    p2[known] = 0.0
    t2 = truth.copy()
    t2[known] = False
    c2 = metric.dti_exact(p2, t2)
    assert c["dti"] == pytest.approx(c2["dti"], abs=1e-12)
    assert c["n_truth"] == c2["n_truth"]


def test_marginal_inclusion_bar():
    """A *new* unit of mass raises DTI iff its kernel weight exceeds alpha * DTI.

    Construction: two truth pixels 20 px apart (no kernel overlap).  The base solution covers
    the first one exactly, so it scores DTI0 = 1/(1 + 0.8) = 0.5556 and the second truth pixel
    is uncovered.  A candidate pixel is then placed at distance d from the second truth pixel;
    its marginal credit is exactly k = max(1 - d/3, 0), and the score must rise iff k > alpha*DTI0
    (here 0.1111), which happens between d = 2 (k = 0.333) and d = 3 (k = 0).
    """
    shape = (30, 40)
    truth = np.zeros(shape, bool)
    truth[5, 5] = True
    truth[5, 25] = True
    base = np.zeros(shape, np.float32)
    base[5, 5] = 1.0
    dti0 = metric.dti_exact(base, truth)["dti"]
    assert dti0 == pytest.approx(1.0 / 1.8, abs=1e-9)
    bar = ALPHA * dti0
    seen = []
    for d in range(0, 5):
        p = base.copy()
        p[5, 25 + d] = 1.0                       # never closer than 25+d to the first truth pixel
        k = max(1.0 - d / 3.0, 0.0)
        gain = metric.dti_exact(p, truth)["dti"] - dti0
        seen.append((d, round(k, 4), round(gain, 4)))
        if k > bar:
            assert gain > 0, (d, k, bar, gain)
        elif k < bar:
            assert gain < 0, (d, k, bar, gain)
    assert seen[0][0] == 0 and seen[-1][0] == 4
    assert [s[1] for s in seen] == [1.0, 0.6667, 0.3333, 0.0, 0.0]


def test_credit_audit_flags_redundant_mass():
    m = np.zeros((20, 20), np.float32)
    m[10, 5:15] = 1.0
    a = metric.credit_audit(m)
    assert a.n_emitted == 10
    assert a.mean_self_kernel > 0.4  # neighbours inside the support
