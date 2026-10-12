"""Unit tests for the GEMSDOE67 orientation/tip lane (CPU, synthetic grids)."""

from __future__ import annotations

import numpy as np
import pytest

from gems57 import metric
from lane_5dc3ab34 import decode as dec, heads as headsmod, lane as lanemod, nodes as nodesmod


def _ridge_grid(H=60, W=60, t0=10, t1=48):
    yy, xx = np.mgrid[0:H, 0:W]
    seg = (yy >= t0) & (yy <= t1) & (np.abs(yy - xx) <= 3)
    p = (np.exp(-((yy - xx) ** 2) / 8.0) * seg).astype(np.float32)
    theta = np.full((H, W), np.pi / 4)
    cos2 = np.cos(2 * theta).astype(np.float32)
    sin2 = np.sin(2 * theta).astype(np.float32)
    return p, cos2, sin2


class TestDecode:
    def test_hysteresis_and_nms_thin(self):
        p, cos2, sin2 = _ridge_grid()
        sup = dec.oriented_hysteresis(p, cos2, sin2, 0.55, 0.25, orient_gate=True)
        thin = dec.oriented_nms(p, cos2, sin2, sup, halfwidth=2)
        assert sup.sum() > thin.sum() > 0
        ty, _ = dec.tip_points(thin)
        assert len(ty) == 2

    def test_tips_extend_along_support(self):
        # p support persists well past the traced segment -> extension must fire
        p, cos2, sin2 = _ridge_grid(t1=48)
        sup = dec.oriented_hysteresis(p, cos2, sin2, 0.55, 0.25, orient_gate=True)
        thin = dec.oriented_nms(p, cos2, sin2, sup, halfwidth=2)
        thin[31:] = False
        res = dec.extend_tips(thin, p, cos2, sin2,
                              np.zeros(p.shape, np.float32),
                              max_len=6, tau_ext=0.25, tau_tip=0.99)
        assert res.n_extension_px >= 3
        assert res.extended.sum() == res.n_extension_px

    def test_orientation_gate_blocks_cross_ridge(self):
        p, cos2, sin2 = _ridge_grid()
        # constant-orientation field: every pixel agrees with the seeds
        gated = dec.orientation_consistent(cos2, sin2, p >= 0.55, 45.0)
        assert gated[p >= 0.55].all()
        # spatially varying field: seeds strike 0 deg, far side strikes 90 deg
        # (axial +90 flips the doubled vector) -> a 45-deg gate must block it
        c2 = np.where(np.arange(60)[None, :] < 30, 1.0, -1.0).astype(np.float32)
        c2 = np.repeat(c2, 60, axis=0)
        s2 = np.zeros((60, 60), np.float32)
        seeds = np.zeros((60, 60), bool)
        seeds[20:25, 5:10] = True
        gated2 = dec.orientation_consistent(c2, s2, seeds, 45.0)
        assert gated2[22, 7]
        assert not gated2[22, 50]

    def test_flank_prune_protects_extensions(self):
        cand = np.zeros((20, 20), bool)
        cand[10, 10] = True
        cand[10, 14] = True
        vis = np.zeros((20, 20), bool)
        vis[10, 12] = True
        prot = np.zeros((20, 20), bool)
        prot[10, 14] = True
        kept = dec.flank_prune(cand, vis, protect=prot, flank_px=2.0)
        assert not kept[10, 10]
        assert kept[10, 14]


class TestHeads:
    def test_axial_targets_match_trace(self):
        mask = np.zeros((60, 60), bool)
        for i in range(10, 50):
            mask[i, i] = True
        c2, s2, coh, near = headsmod.axial_targets(mask)
        ang = dec.axial_angle_deg(float(c2[30, 30]), float(s2[30, 30]))
        assert abs(ang - 45.0) < 5.0
        assert near[30, 30]
        assert not near[30, 10]

    def test_tips_endpoints_and_junctions(self):
        mask = np.zeros((30, 30), bool)
        mask[5, 5:20] = True           # horizontal bar
        mask[5:15, 12] = True          # vertical bar -> junction at (5,12)
        tips = headsmod.endpoint_tips(mask)
        junc = headsmod.junction_pixels(mask)
        # endpoints: (5,5), (5,19), (14,12) -- exactly 3
        assert tips.sum() == 3
        assert junc.sum() >= 1
        heat = headsmod.tip_heatmap(mask)
        assert 0.0 < heat.max() <= 1.0


class TestMetricBridge:
    def test_spacing_nodes_honour_exclusion(self):
        cand = np.ones((40, 40), bool)
        prio = np.zeros((40, 40), np.float32)
        prio[20, 20] = 1.0
        out = nodesmod.spacing_nodes(cand, prio, spacing=3.0)
        assert out[20, 20]
        ys, xs = np.nonzero(out)
        d = np.hypot(ys - 20, xs - 20)
        assert (d[d > 0] > 2.9).all()

    def test_tip_adjacent_truth_subset(self):
        truth = np.zeros((30, 30), bool)
        truth[10, 5:25] = True         # 20 px bar: middle is >3 px from both tips
        sub = lanemod.tip_adjacent_truth(truth, radius_px=3.0)
        assert sub[10, 5] and sub[10, 24]
        assert not sub[10, 15]
        assert sub.sum() < truth.sum()

    def test_dti_matches_bruteforce_on_toy(self):
        rng = np.random.default_rng(0)
        truth = np.zeros((25, 25), bool)
        truth[5, 5] = True
        truth[10, 18] = True
        pred = np.zeros((25, 25))
        pred[5, 6] = 1.0
        pred[12, 18] = 1.0
        a = metric.dti_exact(pred, truth)
        b = metric.dti_bruteforce(pred, truth)
        assert a["dti"] == pytest.approx(b["dti"], rel=1e-9)
