#!/usr/bin/env python3
"""Render a small preview of the shipped emission for the competition site.

Background: the provided detrended-elevation band (band 11, `det_elev`) turned into a
shaded relief.  Overlays: the public training labels (+1 pixels, cyan) and the shipped
emission (red).  Nothing here is used to score anything; it is a visual receipt that the
artifact looks like a lineament map rather than noise.

Usage: python scripts/make_preview.py --artifact gemsdoe67-ovtr-ml-cover-tau3p0-20261012
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gems67 import dataio  # noqa: E402

DATA = Path("/tmp/gems_data")
OUT = ROOT / "docs" / "assets"


def relief(band: np.ndarray, footprint: np.ndarray, step: int) -> np.ndarray:
    """Shaded relief of a residual-elevation band, normalised to uint8."""
    z = band.astype(np.float64)
    z[~footprint] = np.nan
    # fill NaN with the column median so the gradient stays finite at the edge
    med = np.nanmedian(z)
    z = np.where(np.isfinite(z), z, med)
    gy, gx = np.gradient(z)
    az, alt = np.deg2rad(315.0), np.deg2rad(45.0)
    slope = np.pi / 2.0 - np.arctan(np.hypot(gx, gy) * 8.0)
    aspect = np.arctan2(-gx, gy)
    shade = np.sin(alt) * np.sin(slope) + np.cos(alt) * np.cos(slope) * np.cos(az - aspect)
    shade = np.clip(shade, 0, 1)
    shade[~footprint] = 0.0
    # box-downsample by `step` with the mean
    h, w = shade.shape
    h2, w2 = (h // step) * step, (w // step) * step
    s = shade[:h2, :w2].reshape(h2 // step, step, w2 // step, step).mean(axis=(1, 3))
    lo, hi = np.percentile(s[s > 0], [2, 98]) if (s > 0).any() else (0, 1)
    return np.clip((s - lo) / max(hi - lo, 1e-9), 0, 1)


def downsample_bool(mask: np.ndarray, step: int) -> np.ndarray:
    h, w = mask.shape
    h2, w2 = (h // step) * step, (w // step) * step
    return mask[:h2, :w2].reshape(h2 // step, step, w2 // step, step).any(axis=(1, 3))


def overlay(base: np.ndarray, truth: np.ndarray, dots: np.ndarray) -> Image.Image:
    rgb = np.repeat((base * 255).astype(np.uint8)[:, :, None], 3, axis=2)
    rgb[dots] = (255, 60, 40)
    rgb[truth] = (40, 220, 255)
    both = dots & truth
    rgb[both] = (255, 255, 0)
    return Image.fromarray(rgb)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact", default="gemsdoe67-ovtr-ml-cover-tau3p0-20261012")
    ap.add_argument("--step", type=int, default=4)
    args = ap.parse_args()

    labels = dataio.read_labels(DATA / "labels.tif")
    footprint = labels != -1
    truth = labels == 1

    import tifffile

    emission = tifffile.TiffFile(ROOT / "docs" / "downloads" / f"{args.artifact}-nan.tif")
    dots = emission.pages[0].asarray() > 0.5

    with tifffile.TiffFile(DATA / "training_features.tif") as t:
        det_elev = t.pages[0].asarray()[:, :, 11]

    OUT.mkdir(parents=True, exist_ok=True)
    step = args.step
    base = relief(det_elev, footprint, step)
    img = overlay(base, downsample_bool(truth, step), downsample_bool(dots, step))
    img.save(OUT / "preview-overview.png")

    # zoom on the busiest truth quadrant (4 x finer sampling, still an integer factor of `step`)
    zs = 2
    dens = {
        "NW": truth[: truth.shape[0] // 2, : truth.shape[1] // 2].mean(),
        "NE": truth[: truth.shape[0] // 2, truth.shape[1] // 2 :].mean(),
        "SW": truth[truth.shape[0] // 2 :, : truth.shape[1] // 2].mean(),
        "SE": truth[truth.shape[0] // 2 :, truth.shape[1] // 2 :].mean(),
    }
    quad = max(dens, key=dens.get)
    r0 = 0 if quad[0] == "N" else truth.shape[0] // 2
    c0 = 0 if quad[1] == "W" else truth.shape[1] // 2
    # window: 1/8 of each side, centred on the densest 1/8 block inside the quadrant
    ph, pw = truth.shape[0] // 16, truth.shape[1] // 16
    best, best_at = -1.0, (r0, c0)
    for r in range(r0, r0 + truth.shape[0] // 2 - ph + 1, ph):
        for c in range(c0, c0 + truth.shape[1] // 2 - pw + 1, pw):
            d = truth[r : r + ph, c : c + pw].mean()
            if d > best:
                best, best_at = d, (r, c)
    r, c = best_at
    win = (slice(r, r + ph * (step // zs)), slice(c, c + pw * (step // zs)))
    zb = relief(det_elev[win], footprint[win], zs)
    zimg = overlay(zb, downsample_bool(truth[win], zs), downsample_bool(dots[win], zs))
    zimg = zimg.resize((zimg.width * 2, zimg.height * 2), Image.NEAREST)
    zimg.save(OUT / "preview-zoom.png")
    print(f"[preview] overview {img.size}, zoom {zimg.size} at {quad} rows {win[0].start}:{win[0].stop} "
          f"cols {win[1].start}:{win[1].stop} (truth density {best:.4f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
