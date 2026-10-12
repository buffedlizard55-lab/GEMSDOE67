"""Tests for the shared template metric and for lane-67 modules. Run: python -m pytest -q"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gems.metric import dti, dti_from_terms, marginal_credit_bar, tversky_terms, tversky_terms_bruteforce  # noqa: E402
from lane_c7b2cfa6 import decode67, emit67, heads67  # noqa: E402


def test_official_worked_example():
    # the problem page's worked example: TP_w 3.00, FP_w 1.89, FN_w 2.00 -> 0.60
    assert abs(dti_from_terms(3.00, 1.89, 2.00) - 0.6027) < 5e-4


def test_identity_tp_plus_fn_equals_truth_count():
    rng = np.random.default_rng(0)
    p = rng.random((17, 19))
    g = rng.random((17, 19)) < 0.2
    tp, fp, fn = tversky_terms(p, g)
    assert abs(tp + fn - g.sum()) < 1e-6
    assert fp >= 0.0


def test_bruteforce_matches_vectorised():
    rng = np.random.default_rng(1)
    p = (rng.random((9, 11)) > 0.6).astype(float)
    g = rng.random((9, 11)) < 0.15
    a = tversky_terms(p, g)
    b = tversky_terms_bruteforce(p, g)
    assert np.allclose(a, b, atol=1e-9)


def test_marginal_break_even_rule():
    # one of two truth cells covered at credit 1 -> DTI 0.5556, break-even credit 0.1111
    p = np.zeros((1, 5)); p[0, 0] = 1.0
    g = np.zeros((1, 5), bool); g[0, 0] = True; g[0, 4] = True
    d = dti(p, g)
    assert abs(d - 1.0 / 1.8) < 1e-9
    assert abs(marginal_credit_bar(d) - 0.2 * d) < 1e-12
    # a dot 2 cells (200 m) from the uncovered truth cell has credit 1/3 > bar -> DTI must rise
    p2 = p.copy(); p2[0, 2] = 1.0
    assert dti(p2, g) > d


def test_nan_predictions_are_zero_and_out_of_range_raises():
    p = np.array([[np.nan, 0.5], [0.0, 1.0]])
    g = np.array([[True, False], [False, True]])
    assert tversky_terms(p, g)[0] == pytest.approx(tversky_terms(np.nan_to_num(p), g)[0])
    with pytest.raises(ValueError):
        tversky_terms(np.array([[1.5, 0.0], [0.0, 0.0]]), g)


def test_orientation_targets_are_axial_and_normalised():
    m = np.zeros((40, 40), bool)
    m[20, 5:35] = True          # a horizontal trace
    ot = heads67.trace_orientation_targets(m)
    assert ot["valid"].any()
    v = ot["valid"]
    assert np.all(np.abs(ot["cos2t"]) <= 1.0001) and np.all(np.abs(ot["sin2t"]) <= 1.0001)
    # a horizontal trace has its gradient along the row axis: cos2theta should be near -1
    core = m & v
    assert np.mean(ot["cos2t"][core]) < -0.5


def test_tip_targets_find_the_ends_of_a_trace():
    m = np.zeros((40, 40), bool)
    m[20, 5:35] = True
    tt = heads67.tip_targets(m)
    assert tt["tips"].sum() >= 2                       # both ends
    assert tt["heat"].max() == pytest.approx(1.0)
    ys, xs = np.nonzero(tt["tips"])
    assert xs.min() <= 6 and xs.max() >= 33


def test_tip_extension_walks_along_strike_past_a_blocked_tip():
    rng = np.random.default_rng(0)
    p = rng.random((60, 60)).astype(np.float32) * 0.1
    p[30, 10:40] = 0.9
    p[31, 10:40] = 0.95
    p[30, 41:50] = 0.5                                 # support continuing past the tip
    c2 = np.zeros((60, 60), np.float32) - 1.0          # theta = pi/2 -> strike along the row
    s2 = np.zeros((60, 60), np.float32)
    tips = np.zeros((60, 60), bool); tips[30, 40] = True
    blocked = np.zeros((60, 60), bool); blocked[30, 10:41] = True
    d = decode67.decode(p, c2, s2, tips, t_hi=0.85, t_lo=0.5, max_len=8, t_ext=0.2,
                        blocked=blocked, tip_weight=0.25)
    assert int(d["extension"].sum()) == 8              # exactly the supported along-strike run
    ys, xs = np.nonzero(d["extension"])
    assert list(xs) == list(range(41, 49)) and set(ys) == {30}
    assert d["score"][ys, xs].min() > 0.0


def test_tip_extension_stops_when_support_fails():
    p = np.zeros((30, 30), np.float32); p[15, :] = 0.9
    c2 = np.zeros((30, 30), np.float32) - 1.0
    s2 = np.zeros((30, 30), np.float32)
    tips = np.zeros((30, 30), bool); tips[15, 15] = True
    d = decode67.decode(p, c2, s2, tips, t_hi=0.95, t_lo=0.9, max_len=8, t_ext=0.95,
                        blocked=np.zeros((30, 30), bool))
    assert int(d["extension"].sum()) == 0


def test_orientation_aware_nms_keeps_along_strike_and_removes_across_strike():
    p = np.zeros((21, 21), np.float32)
    p[10, 3:18] = 0.9      # a horizontal ridge, one cell thick
    p[11, 3:18] = 0.5      # a weaker parallel neighbour across strike
    c2 = np.zeros_like(p) - 1.0
    s2 = np.zeros_like(p)
    out = decode67.orientation_aware_nms(p, c2, s2, reach=1)
    assert out[10, 10] > 0                 # ridge survives
    assert out[11, 10] == 0                # across-strike weaker neighbour suppressed
    iso = np.zeros_like(p); iso[10, 10] = 0.9
    assert decode67.orientation_aware_nms(iso, c2, s2)[10, 10] > 0


def test_min_separation_enforces_the_disk():
    sc = np.zeros((40, 40), np.float32)
    sc[10, 10] = 1.0; sc[10, 12] = 0.9; sc[10, 20] = 0.8
    cand = sc > 0
    keep = emit67.min_separation_select(sc, cand, min_sep_px=4.5)
    assert keep[10, 10] and keep[10, 20] and not keep[10, 12]


def test_greedy_marginal_dti_stops_at_the_alpha_bar():
    q = np.zeros((30, 30), np.float64)
    q[15, 5] = 5.0        # one strong, isolated pocket of assumed truth probability
    cand = q > 0
    res = emit67.greedy_marginal_dti(q, cand, dti_target=0.28)
    assert res["n_accepted"] == 1 and res["dots"][15, 5]
    # a field whose total assumed probability is below the bar accepts nothing
    res0 = emit67.greedy_marginal_dti(q * 1e-6, cand, dti_target=0.28)
    assert res0["n_accepted"] == 0


def test_calibrate_matches_the_requested_prevalence():
    q = emit67.calibrate(np.ones((5, 5)), np.ones((5, 5), bool), prevalence_cells=10.0)
    assert q.sum() == pytest.approx(10.0)
