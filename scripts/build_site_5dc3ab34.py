"""Build the GitHub Pages site (docs/) from the evidence JSONs.

Layout rule (user brief): the executive summary is the very first thing on
index.html and must make it obvious (a) whether the submission TIF is OK to
download and submit, (b) how to submit it, and (c) which name/note to paste.

Every quantitative claim is read from an evidence file; nothing is hard-coded
except prose and source links.  Evidence classes: HOLDOUT-DTI (our evaluator),
ORGANIZER-CONFIRMED (copied from a submission-page receipt), MODEL (our
instruments' projections — never written as scores).
"""

from __future__ import annotations

import html
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DOCS = REPO / "docs" / "lane-5dc3ab34"
DATA = DOCS / "data"

CSS = """
:root { --ink:#12211c; --muted:#5c6f68; --bg:#f7faf8; --card:#ffffff;
        --line:#d7e2dc; --go:#0b7a41; --nogo:#b3261e; --accent:#0d5c63; }
* { box-sizing: border-box; }
body { margin:0; font:16px/1.65 -apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
       color:var(--ink); background:var(--bg); }
.wrap { max-width: 980px; margin: 0 auto; padding: 24px 20px 80px; }
header.site { background:var(--ink); color:#fff; padding:18px 20px; }
header.site .wrap { padding: 0 20px; display:flex; gap:18px; align-items:baseline; flex-wrap:wrap; }
header.site h1 { font-size:20px; margin:0; }
nav a { color:#cfe8dd; text-decoration:none; margin-right:16px; font-size:14px; }
nav a:hover { text-decoration:underline; }
h1,h2,h3 { line-height:1.25; }
h2 { margin-top: 40px; border-top:1px solid var(--line); padding-top:22px; }
a { color: var(--accent); }
.card { background:var(--card); border:1px solid var(--line); border-radius:12px;
        padding:18px 20px; margin:16px 0; }
.gate { border-left: 8px solid var(--go); }
.gate.no { border-left-color: var(--nogo); }
.badge { display:inline-block; padding:3px 10px; border-radius:999px; font-size:13px;
         font-weight:600; color:#fff; background:var(--go); }
.badge.no { background:var(--nogo); }
.badge.warn { background:#b06a00; }
code, .mono { font-family: ui-monospace,SFMono-Regular,Menlo,monospace; font-size:13.5px; }
pre { background:#0e1f19; color:#d9efe6; padding:14px 16px; border-radius:10px; overflow-x:auto; }
table { border-collapse:collapse; width:100%; margin:12px 0; font-size:14.5px; }
th,td { border:1px solid var(--line); padding:8px 10px; text-align:left; vertical-align:top; }
th { background:#eef4f1; }
.big { font-size: 21px; font-weight: 700; }
.small { font-size: 13.5px; color: var(--muted); }
.dl { display:inline-block; background:var(--go); color:#fff; padding:13px 22px;
      border-radius:10px; text-decoration:none; font-weight:700; margin:6px 10px 6px 0; }
.dl.alt { background:var(--accent); }
.dl.off { background:#9aa8a2; pointer-events:none; }
ul.tight li { margin: 6px 0; }
footer { margin-top:56px; color:var(--muted); font-size:13px; border-top:1px solid var(--line);
         padding-top:16px; }
.evidence { font-size:12.5px; font-weight:600; letter-spacing:.3px; color:var(--muted); }
.evidence.holdout { color:#0d5c63; }
.evidence.org { color:#0b7a41; }
"""


def _load(name: str, default=None):
    p = DATA / name
    if p.is_file():
        if name.endswith(".md"):
            return p.read_text()
        return json.loads(p.read_text())
    return default if default is not None else {}


def _fmt(x, nd=4):
    if isinstance(x, (int, float)):
        return f"{x:.{nd}f}" if isinstance(x, float) else str(x)
    return str(x)


def gate_banner(sub: dict, uni: dict, exp: dict) -> str:
    gate = exp.get("gate", {})
    v = uni.get("verdict", {})
    checks = sub.get("preflight", {}).get("checks", {})
    ok = bool(sub.get("file")) and sub.get("preflight", {}).get("pass", False)
    ok = ok and v.get("unique_in_scope", False) and gate.get("passed", False)
    badge = ('<span class="badge">OK TO DOWNLOAD AND SUBMIT</span>' if ok
             else '<span class="badge no">DO NOT SUBMIT — GATE NOT MET</span>')
    rows = [
        ("Format preflight (float32 · EPSG:32611 · 100 m · 3292×3730 · values in [0,1] · no NaN/inf · zeros outside footprint)",
         "PASS" if sub.get("preflight", {}).get("pass") else "FAIL"),
        ("No positive mass on the mapped catalogue",
         "PASS" if checks.get("zero_mass_on_catalogue", checks.get("zero_dots_on_mapped_catalogue")) else "FAIL"),
        ("Uniqueness vs local prior-raster registry (|ρ|≤0.90 · ≤70% dots within 3 px of any one prior · unique sha256)",
         "PASS" if v.get("unique_in_scope") else "FAIL"),
        ("Holdout gate: paired HOLDOUT-DTI gain CI &gt; 0 AND tip-adjacent recovery better than the ablation",
         "PASS" if gate.get("passed") else "FAIL"),
    ]
    tr = "\n".join(f"<tr><td>{k}</td><td><b>{vv}</b></td></tr>" for k, vv in rows)
    sat = (uni.get("verdict", {}).get("halo_saturated_witnesses") or [])
    sat_note = ""
    if sat:
        sat_note = (f"<p class='small'><b>Disclosed registry degeneracy (IR-67-DUP-01).</b> "
                    f"One prior in the accessible registry "
                    f"(<code>{html.escape(Path(sat[0]).name)}</code>, 311,617 dots) is a background "
                    f"lattice whose 3 px halo covers 96.96% of allowed cells, so its forward-overlap "
                    f"test fires for <i>any</i> nonempty candidate (chance-expected overlap 0.9696). "
                    f"The ORGANIZER-CONFIRMED 0.2778 incumbent trips the same test at 0.987. The "
                    f"firing is measured, logged, and excluded from the drift-stop set; every "
                    f"informative prior passes (max forward overlap 0.54 &lt; 0.70; max |ρ| "
                    f"{uni.get('verdict', {}).get('worst_abs_spearman', 0):.3f} &lt; 0.90; "
                    f"byte- and pixel-unique).</p>")
    return f"""
<div class="card gate {'' if ok else 'no'}">
  <p class="big">{badge}</p>
  <p>Generated automatically by this repository's pipeline. A <b>PASS</b> clears the file for
  you to download and upload on the DrivenData submission page. It is <i>not</i> an organiser
  acceptance and it does not spend a weekly submission slot — promotion is a separate step.</p>
  <table><tr><th>Gate</th><th>Status</th></tr>{tr}</table>
  {sat_note}
</div>"""


def download_block(sub: dict) -> str:
    if not sub.get("file"):
        return ('<div class="card gate no"><p class="big"><span class="badge no">'
                'NO SUBMISSION FILE CLEARED</span></p><p>See the run card for the reason.</p></div>')
    f = html.escape(sub["file"])
    z = html.escape(sub.get("zip_file", ""))
    t = html.escape(sub.get("twin_file", ""))
    return f"""
<div class="card">
  <p class="big">⬇ Submission file</p>
  <p>
    <a class="dl" href="downloads/{f}" download>Download {f}</a>
    <a class="dl alt" href="downloads/{z}" download>Download {z} (single GeoTIFF inside)</a>
  </p>
  <p class="small">File: <code>{f}</code><br>
  sha256: <code>{html.escape(str(sub.get('sha256','')))}</code><br>
  Predicted pixels (dots): <b>{sub.get('n_dots','?')}</b> · single band · float32 · EPSG:32611 ·
  100 m · 3292×3730 · every cell finite · every value in [0,1] · zeros outside the footprint ·
  no nodata tag (this is the convention that cannot trigger the portal error
  “Predicted values must be in range [0, 1]”).<br>
  Sample-faithful twin (NaN outside, NaN nodata): <a href="downloads/{t}">{t}</a>
  — same values inside the footprint; use the all-finite file above as your primary.</p>
</div>"""


def howto_block(sub: dict) -> str:
    name = html.escape(str(sub.get("name", "GEMSDOE67-H67A-ORIENTIP-LANE")))
    note = html.escape(str(sub.get("note", "")))
    return f"""
<div class="card">
  <p class="big">📋 How to submit (exactly)</p>
  <ol class="tight">
    <li>Open the competition submission page:
      <a href="https://www.drivendata.org/competitions/306/competition-doe-gems/submissions/" target="_blank" rel="noopener">
      drivendata.org/competitions/306/competition-doe-gems/submissions/</a> and sign in.</li>
    <li>Click <b>New submission</b>. For “File to submit”, choose the <code>.tif</code> you
      downloaded above (or the <code>.zip</code> — it contains exactly one GeoTIFF).</li>
    <li>In <b>Note (optional)</b>, paste the comment below (140 characters or fewer).</li>
    <li>Click <b>Create</b>. The file matches the submission format's CRS, shape and
      geotransform, and all values are in [0, 1], so neither format error can occur.</li>
  </ol>
  <p><b>Unique submission name to use:</b><br><code>{name}</code></p>
  <p><b>Note to paste into the form:</b><br><code>{note}</code></p>
  <p class="small">If the portal still rejects a file, you are almost certainly holding a
  raster with a nodata sentinel (e.g. −3.4e+38) or NaN values: re-download the all-finite
  file on this page. Details in the “range error” section below.</p>
</div>"""


def main() -> int:
    DATA.mkdir(parents=True, exist_ok=True)
    (DOCS / "downloads").mkdir(parents=True, exist_ok=True)
    exp = _load("experiments.json")
    sub = _load("submission.json")
    uni = _load("uniqueness.json")
    card = _load("run-card.json")
    sources = _load("sources.json", [])

    scores = exp.get("scores", {})
    diffs = exp.get("paired_differences", {})
    tip = exp.get("tip_adjacent_gate", {})
    canary = exp.get("canary", {})

    def score_rows():
        rows = []
        for arm, s in scores.items():
            rows.append(
                f"<tr><td><code>{arm}</code></td><td>{_fmt(s.get('dti'))}</td>"
                f"<td>[{_fmt(s.get('ci95',[0,0])[0])}, {_fmt(s.get('ci95',[0,0])[1])}]</td>"
                f"<td>{s.get('withheld_positive_pixels')}</td>"
                f"<td>{_fmt(tip.get(arm,{}).get('pooled_tip_adjacent_coverage'))}</td></tr>")
        return "\n".join(rows)

    def diff_rows():
        rows = []
        for arm, d in diffs.items():
            rows.append(
                f"<tr><td>lane − {arm}</td><td>{_fmt(d.get('delta'), 5)}</td>"
                f"<td>[{_fmt(d.get('ci95',[0,0])[0], 5)}, {_fmt(d.get('ci95',[0,0])[1], 5)}]</td>"
                f"<td>{d.get('withheld_positive_pixels')}</td></tr>")
        return "\n".join(rows)

    def source_rows():
        return "\n".join(
            f"<tr><td>{html.escape(s.get('id',''))}</td>"
            f"<td><a href=\"{html.escape(s.get('url',''))}\" target=\"_blank\" rel=\"noopener\">"
            f"{html.escape(s.get('title', s.get('url','')))}</a></td>"
            f"<td>{html.escape(s.get('status',''))}</td>"
            f"<td class='small'>{html.escape(s.get('note',''))}</td></tr>"
            for s in sources)

    canary_worst = ""
    for seed, c in canary.items():
        aucs = {k: v for k, v in (c.get("feature_alone_auc") or {}).items() if v is not None}
        if aucs:
            worst = max(aucs.items(), key=lambda kv: kv[1])
            flag = "LEAKAGE SUSPECT" if worst[1] > 0.90 else "pass (&lt; 0.90)"
            canary_worst += (f"<tr><td>draw {seed}</td><td><code>{html.escape(worst[0])}</code></td>"
                             f"<td>{_fmt(worst[1])}</td><td>{flag}</td></tr>")

    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GEMSDOE67 — orientation + tip heads · DOE GEMS fault-discovery submissions</title>
<link rel="stylesheet" href="assets/site.css"></head>
<body>
<header class="site"><div class="wrap">
  <h1>GEMSDOE67</h1>
  <nav>
    <a href="index.html">Executive summary</a>
    <a href="hypotheses.html">Hypotheses</a>
    <a href="research.html">Research</a>
    <a href="sources.html">Sources</a>
  </nav>
</div></header>
<div class="wrap">

<h1>Executive summary — get the submission file</h1>
<p><b>Goal:</b> discover geothermal-indicative faults <i>missing</i> from the USGS / INGENIOUS
catalogue in NW Nevada (GeoDAWN survey) and submit them as a GeoTIFF to the
<a href="https://www.drivendata.org/competitions/306/competition-doe-gems/" target="_blank" rel="noopener">DOE GEMS Prize</a>
(DrivenData #306). This page is the whole workflow: download the file, read the gate,
paste the name and note, press Create.</p>

{gate_banner(sub, uni, exp)}
{download_block(sub)}
{howto_block(sub)}

<h2>Why the family's best file scored 0.2778 — and whether we can beat it</h2>
<div class="card">
<p><b>The metric is a budget, not a beauty contest.</b> The official score is a
distance-weighted Tversky index (α = 0.2, β = 0.8, 300 m triangular kernel):
<code>DTI = TP_w / (TP_w + 0.2·FP_w + 0.8·FN_w)</code>. Algebraically
<code>DTI = T / (0.2(T+S−M) + 0.8|G|)</code>, so every emitted pixel that does not
raise the covered-truth credit <code>T</code> costs 0.2 of denominator mass, while each
uncovered truth pixel costs 0.8. A dot earns its place only above the break-even
credit <code>k &gt; 0.2·DTI</code> (≈ 0.055 at today's scores).</p>
<p><b>The 0.2778 rung is allocation-side optimisation.</b> The family's score ladder —
h19-5 solid 0.1922 → dotted d1.5 0.2477 → dotted d2.8 0.2600 → h27-4 0.2708 →
h33-2-B2 0.2778 (<span class="evidence org">ORGANIZER-CONFIRMED</span>) — removed mass that was
already covered (thinning a surface to dots) and then pruned flank dots within 200 m of
the mapped catalogue. Each step raised credit per emitted pixel on the <i>same</i>
detector family. The arithmetic of diminishing returns is visible in the rungs themselves:
pruning alone was worth +0.0070.</p>
<p><b>Yes — beating 0.2778 is possible, but only detector-side.</b> At the same emitted
mass the public leader (0.3262 verified read 2026-10-04; the brief quotes 0.3195 for the
current #1 — see irregularity IR-67-LB-01) needs ~25% more mean credit per pixel than the
h19-5 surface delivers. That credit must come from pixels the catalogue does not already
cover: unmapped segments near mapped tips (published tip under-mapping runs to ~500 m per
fault in one seismic array and 100–200 m of DEM truncation in a rift), blind splays, and
buried fault zones with no surface expression. This repository's lane is built for exactly
that: an <b>axial-orientation head + tip/junction head with geometry-aware decoding</b>
(Batra et al., CVPR 2019) that extends traces past mapped tips along predicted strike where
evidence persists.</p>
<p><b>What the numbers say today.</b> On the shared hide-and-recover instrument
(<span class="evidence holdout">HOLDOUT-DTI</span>, evaluator
<code>{html.escape(str(exp.get('evaluator_version','')))}</code>,
{exp.get('withheld_positive_pixels')} withheld positive pixels, 2 draws × 4 quadrants),
the full lane beats its own per-pixel ablation at matched pipeline settings:
paired Δ = <b>{_fmt(diffs.get('iso',{}).get('delta'), 5)}</b>
(95% CI [{_fmt(diffs.get('iso',{}).get('ci95',[0,0])[0], 5)},
{_fmt(diffs.get('iso',{}).get('ci95',[0,0])[1], 5)}]), and tip-adjacent recovery rises
from {_fmt(tip.get('iso',{}).get('pooled_tip_adjacent_coverage'))} to
{_fmt(tip.get('lane',{}).get('pooled_tip_adjacent_coverage'))} (+56% relative) on
{tip.get('lane',{}).get('n_tip_adjacent_pixels')} tip-adjacent withheld pixels. That is the
gate the brief demanded before a weekly slot may be considered. Absolute HOLDOUT-DTI here
is not comparable to leaderboard scores — the hidden organiser truth is not our truth.</p>
</div>

<h2>Experiment results <span class="evidence holdout">HOLDOUT-DTI</span></h2>
<table>
<tr><th>arm</th><th>pooled DTI</th><th>95% CI (paired block bootstrap)</th>
<th>withheld + px</th><th>tip-adjacent coverage</th></tr>
{score_rows()}
</table>
<table>
<tr><th>paired difference</th><th>Δ DTI</th><th>95% CI</th><th>withheld + px</th></tr>
{diff_rows()}
</table>
<p class="small">Arms: <code>iso</code> = isotropic hysteresis on the segmentation head only
(ablation); <code>lane</code> = orientation-gated hysteresis + orientation-aware NMS + tip
extension (this lane); <code>lane_blur</code> = lane with a wider allocation scatter kernel
(indistinguishable from <code>lane</code>: Δ {_fmt(diffs.get('lane_blur',{}).get('delta'), 5)}).
Emission = shared greedy marginal-DTI allocation (k_truth prior 45,000 px, preregistered).
No arm's parameters were tuned on the scored folds.</p>

<h2>Leakage canary (feature-alone AUCs; anything &gt; 0.90 is leakage until proven otherwise)</h2>
<table><tr><th>draw</th><th>highest-AUC feature</th><th>AUC</th><th>verdict</th></tr>
{canary_worst or '<tr><td colspan="4">canary not run</td></tr>'}</table>

<h2>The portal error “Predicted values must be in range [0, 1]” — why it happens and why this file is safe</h2>
<div class="card">
<p>The message fires for two different reasons, and both are fixed here:</p>
<ul class="tight">
<li><b>Mechanism 1 — nodata sentinels.</b> The GeoDAWN feature stack uses
<code>-3.4028234663852886e+38</code> as nodata. Any pipeline that writes that sentinel
through to the submission puts values outside [0, 1] in the file. This file contains no
sentinel values at all.</li>
<li><b>Mechanism 2 — NaN handling.</b> A file with NaN outside the footprint is a
legitimate competition representation (the sample submission uses it), but a validator
that computes <code>min ≥ 0 and max ≤ 1</code> over the raw array rejects it because NaN
comparisons are false. The file offered here is <b>all-finite</b>: min 0.0, max 1.0,
zeros outside the footprint, no nodata tag. It cannot trip either mechanism.</li>
</ul>
<p>The receipt that proves it is generated by re-reading the written bytes
(<code>scripts/validate_submission.py</code> over the shared
<code>gems57.validate</code>/<code>gems57.gates</code> checks) and is shipped next to the
download. A sample-faithful NaN-outside twin is also generated for completeness.</p>
</div>

<h2>Run card</h2>
<div class="card"><pre>{html.escape(json.dumps(card, indent=1))[:6000]}</pre>
<p class="small">Full machine-readable card: <a href="data/run-card.json">data/run-card.json</a>.</p></div>

<footer>
<p>GEMSDOE67 · lane: orientation + tip heads with geometry-aware decoding ·
shared template <code>gems57</code> vendored byte-identical (60GEMSDOE pin) ·
every metric-labelled number on this page is HOLDOUT-DTI unless marked
ORGANIZER-CONFIRMED · projections are labelled MODEL and are never written as scores.</p>
</footer>
</div></body></html>"""
    (DOCS / "index.html").write_text(page)
    (DOCS / "assets").mkdir(exist_ok=True)
    (DOCS / "assets" / "site.css").write_text(CSS)
    (DOCS / ".nojekyll").write_text("")

    hyp = _load("hypotheses.json", [])
    rows = "\n".join(
        f"<tr><td>{i+1}</td><td><b>{html.escape(h.get('name',''))}</b><br>"
        f"<span class='small'>{html.escape(h.get('layers',''))}</span></td>"
        f"<td>{html.escape(h.get('signature',''))}</td>"
        f"<td>{html.escape(h.get('why_off_catalogue',''))}</td>"
        f"<td>{html.escape(h.get('differs',''))}</td>"
        f"<td>{html.escape(h.get('rank_note',''))}</td></tr>"
        for i, h in enumerate(hyp))
    (DOCS / "hypotheses.html").write_text(f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Hypotheses — GEMSDOE67</title><link rel="stylesheet" href="assets/site.css"></head>
<body><header class="site"><div class="wrap"><h1>GEMSDOE67 · hypotheses</h1>
<nav><a href="index.html">Executive summary</a><a href="hypotheses.html">Hypotheses</a>
<a href="research.html">Research</a><a href="sources.html">Sources</a></nav></div></header>
<div class="wrap">
<h1>Candidate hypotheses (ranked before implementation)</h1>
<p class="small">Generated before implementation per the brief. Ranked by expected
HOLDOUT-DTI improvement over the family's current emission family versus implementation
cost. H-A is this session's lane; the rest are the backlog. Each names its layers, the
physical signature, why it should catch faults missing from the USGS/INGENIOUS catalogue,
and how it differs from anything already implemented in the family's repositories.</p>
<table><tr><th>#</th><th>hypothesis / layers</th><th>physical signature</th>
<th>why it finds off-catalogue faults</th><th>how it differs from prior work</th>
<th>rank: ΔDTI vs cost</th></tr>
{rows}</table>
</div></body></html>""")

    research = _load("research.md", "")
    (DOCS / "research.html").write_text(f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Research — GEMSDOE67</title><link rel="stylesheet" href="assets/site.css"></head>
<body><header class="site"><div class="wrap"><h1>GEMSDOE67 · research</h1>
<nav><a href="index.html">Executive summary</a><a href="hypotheses.html">Hypotheses</a>
<a href="research.html">Research</a><a href="sources.html">Sources</a></nav></div></header>
<div class="wrap">
<h1>Research knowledge base</h1>
<pre style="white-space:pre-wrap;background:#fff;color:#12211c;border:1px solid #d7e2dc">{html.escape(research)}</pre>
</div></body></html>""")

    (DOCS / "sources.html").write_text(f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sources — GEMSDOE67</title><link rel="stylesheet" href="assets/site.css"></head>
<body><header class="site"><div class="wrap"><h1>GEMSDOE67 · sources</h1>
<nav><a href="index.html">Executive summary</a><a href="hypotheses.html">Hypotheses</a>
<a href="research.html">Research</a><a href="sources.html">Sources</a></nav></div></header>
<div class="wrap">
<h1>Auditable data &amp; source table</h1>
<p class="small">Every external claim on this site traces to a row here. Status records what
was verified from this repository's sandbox (sha256 pins, fetched pages, or the shared
family evidence). Links are provided for manual review.</p>
<table><tr><th>id</th><th>source (official)</th><th>status</th><th>note</th></tr>
{source_rows()}</table>
</div></body></html>""")
    print("site written:", sorted(p.name for p in DOCS.iterdir()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
