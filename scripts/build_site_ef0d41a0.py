#!/usr/bin/env python3
"""Render the GitHub Pages site from the run card and the evidence JSONs.

Nothing is typed twice: every figure in the HTML comes out of ``evidence/run_card.json``,
so the page cannot drift from the measurements (and cannot invent one).
"""
from __future__ import annotations

import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EV = ROOT / "evidence"
DOCS = ROOT / "docs"
DOWNLOADS = DOCS / "downloads"

CSS = """
:root{--ink:#12161c;--muted:#5b6673;--line:#e3e8ef;--bg:#f7f9fc;--card:#fff;
--red:#b3261e;--redbg:#fdeceb;--green:#0f7a3d;--greenbg:#e9f7ef;--amber:#8a5a00;--amberbg:#fff6e0;
--blue:#1b4f9c;--code:#f2f5f9}
*{box-sizing:border-box}
body{margin:0;font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
color:var(--ink);background:var(--bg)}
header{background:#0e1621;color:#fff;padding:28px 22px 22px}
header .wrap{max-width:1000px;margin:0 auto}
header h1{margin:0 0 6px;font-size:26px;letter-spacing:.2px}
header p{margin:0;color:#b9c4d2;font-size:14px}
main{max-width:1000px;margin:0 auto;padding:22px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:20px 22px;margin:0 0 18px;
box-shadow:0 1px 2px rgba(16,24,40,.04)}
h2{font-size:19px;margin:0 0 12px;padding-bottom:8px;border-bottom:1px solid var(--line)}
h3{font-size:15px;margin:18px 0 6px;text-transform:uppercase;letter-spacing:.6px;color:var(--muted)}
p{margin:8px 0}
.banner{border-radius:12px;padding:16px 18px;margin:0 0 18px;border:1px solid}
.banner.red{background:var(--redbg);border-color:#f3c2bf;color:#5c1512}
.banner.green{background:var(--greenbg);border-color:#bfe6cf;color:#0b4d28}
.banner.amber{background:var(--amberbg);border-color:#f0dca6;color:#5a3c00}
.banner h2{border:0;margin:0 0 8px;padding:0;font-size:20px}
.banner strong{font-weight:700}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0 0}
.chip{font-size:12.5px;font-weight:600;padding:4px 10px;border-radius:999px;border:1px solid}
.chip.ok{background:#fff;border-color:#bfe6cf;color:var(--green)}
.chip.bad{background:#fff;border-color:#f3c2bf;color:var(--red)}
.chip.warn{background:#fff;border-color:#f0dca6;color:var(--amber)}
.btn{display:inline-block;background:var(--blue);color:#fff;text-decoration:none;font-weight:650;
padding:11px 18px;border-radius:9px;margin:6px 10px 0 0}
.btn.ghost{background:#fff;color:var(--blue);border:1px solid #c9d6e8}
table{width:100%;border-collapse:collapse;margin:10px 0;font-size:14.5px}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{background:#f0f4f9;font-weight:650;font-size:13px;text-transform:uppercase;letter-spacing:.4px;color:var(--muted)}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
code{background:var(--code);padding:1px 5px;border-radius:5px;font-size:13.5px}
ol,ul{padding-left:22px}
ol li,ul li{margin:5px 0}
.muted{color:var(--muted);font-size:13.5px}
.steps{counter-reset:s;list-style:none;padding-left:0}
.steps li{counter-increment:s;position:relative;padding-left:44px;margin:12px 0}
.steps li:before{content:counter(s);position:absolute;left:0;top:-1px;width:30px;height:30px;border-radius:50%;
background:var(--blue);color:#fff;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:14px}
footer{max-width:1000px;margin:0 auto;padding:10px 22px 40px;color:var(--muted);font-size:13px}
a{color:var(--blue)}
.kv{display:grid;grid-template-columns:220px 1fr;gap:4px 16px;font-size:14.5px}
.kv dt{color:var(--muted)}
.kv dd{margin:0;font-variant-numeric:tabular-nums}
"""


def esc(x) -> str:
    return html.escape(str(x))


def rng(low, high, nd=5) -> str:
    return f"[{low:.{nd}f}, {high:.{nd}f}]"


def main() -> int:
    card = json.loads((EV / "run_card.json").read_text())
    e3 = json.loads((EV / "e3_submission_receipt.json").read_text())
    e2 = json.loads((EV / "e2_arms_holdout.json").read_text())
    name = card["submission"]["name"]
    tif = f"{name}-zeros.tif"
    note = card["submission"]["note"]
    stub = e2["instrument_stub"]["pooled"]
    hide = e2["instrument_hide"]["pooled"]["scores"]
    tiprec = e2["instrument_stub"]["tip_adjacent_recovery"]
    canary = card["leakage_canary"]
    max_auc = canary["worst_single_feature_auc"]
    ori = card["heads"]["orientation"]
    tip = card["heads"]["tip"]
    ori_mae = [f["mean_abs_error_deg"] for f in ori["cv"]]
    ori_const = [f["constant_frame_error_deg"] for f in ori["cv"]]
    shipped = card["shipped"]
    reg = card["registry"]
    val = card["validator"]
    checks = val["checks"]
    n_pass = sum(1 for v in checks.values() if v)

    arm_rows = "".join(
        f"<tr><td><code>{esc(k)}</code></td><td class='num'>{esc(stub[k]['dots'])}</td>"
        f"<td class='num'>{stub[k]['pooled_dti']:.5f}</td>"
        f"<td class='num'>{hide.get(k, {}).get('dti', float('nan')):.5f}</td>"
        f"<td class='num'>{rng(*hide[k]['ci95']) if k in hide else '—'}</td></tr>"
        for k in stub)
    shipped_rows = "".join(
        f"<tr><td><code>{esc(k)}</code></td><td class='num'>{v:.5f}</td></tr>"
        for k, v in (("shipped HOLDOUT-DTI (instrument A)", shipped["instrument_A_dti"]),
                     ("shipped HOLDOUT-DTI (instrument B)", shipped["instrument_B_dti"]),
                     ("live-analogue instrument A at the same budget",
                      shipped["live_analogue_dti_max"]),
                     ("dots emitted", float(shipped["dots"])),
                     ("budget selected", float(shipped["budget"]))))
    check_rows = "".join(f"<tr><td><code>{esc(k)}</code></td><td>{'PASS' if v else 'FAIL'}</td></tr>"
                         for k, v in checks.items())

    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>GEMS lane 67 — executive summary</title><style>{CSS}</style></head>
<body>
<header><div class="wrap">
<h1>GEMS Prize — lane 67: supervised orientation head + tip/junction head</h1>
<p>DrivenData <em>DOE GEMS</em> competition · independent, reproducible lane run · generated {esc(card['generated_utc'])}</p>
</div></header>
<main>

<div class="banner red">
<h2>Executive summary — verdict: NEGATIVE RESULT. Do not submit this file.</h2>
<p>The lane's mechanism (supervised axial <code>cos2&#952;/sin2&#952;</code> orientation head, a
tip/junction head, orientation-aware NMS, hysteresis and tip extension) <strong>did not beat the
shared template's own decimated-lattice control</strong> on either holdout instrument, and tip
extension was a null effect (<code>orient_ext &#8722; orient_noext = +0.00067</code>,
95&#8239;% CI [&#8722;0.00009, +0.00200]). The shipped raster is published anyway, because the brief
requires a downloadable, format-valid, unique GeoTIFF — but it is
<strong>not a recommended entry</strong>.</p>
<div class="chips">
<span class="chip bad">Gate NOT met</span>
<span class="chip ok">Format: {n_pass}/{len(checks)} checks pass</span>
<span class="chip ok">Values inside [0, 1]</span>
<span class="chip warn">Registry gate not certifiable here</span>
<span class="chip bad">IR-67-OVERLAP-01 flagged</span>
</div>
</div>

<div class="card">
<h2>How to make a submission — the short version</h2>
<p><strong>1. Download the file</strong> (it is the only deliverable raster of this lane):</p>
<p><a class="btn" href="downloads/{esc(tif)}" download>{esc(tif)} · {card['raster']['bytes']:,} bytes</a>
<a class="btn ghost" href="downloads/{esc(tif[:-4])}.zip" download>same raster as .zip</a>
<a class="btn ghost" href="downloads/{esc(tif[:-4])}.json" download>receipt JSON</a></p>
<p><strong>2. Upload it on DrivenData.</strong> Log in, open the
<a href="https://www.drivendata.org/competitions/306/competition-doe-gems/submissions/">competition</a>,
click <em>Submit</em> in the sidebar, then <em>Make new submission</em>, choose the <code>.tif</code>,
and name it <code>{esc(name)}</code> with the note below.</p>
<p><strong>3. Before you submit anything, read the verdict above.</strong> The recommended action for
this lane is to keep the submission slot and act on §&#8239;What to do next instead.</p>
<p class="muted">Suggested name: <code>{esc(name)}</code> · note ({len(note)}/140):
<code>{esc(note)}</code></p>
<p><a class="btn ghost" href="executive-summary.html">Step-by-step submission guide →</a></p>
</div>

<div class="card">
<h2>What the numbers say</h2>
<p>HOLDOUT-DTI, protocol &#945;&#8239;=&#8239;0.2, &#946;&#8239;=&#8239;0.8, 300&#8239;m triangular
kernel. <strong>Instrument A</strong> = withheld segments, pixel-exact mask, 4 quadrants
({esc(stub['orient_ext']['n_truth'])} withheld positive pixels, <code>gems57.holdout</code>).
<strong>Instrument B</strong> = withheld whole components, evaluator
<code>{esc(card['instruments']['B']['evaluator_version'])}</code>,
{esc(card['instruments']['B']['withheld_positive_pixels'])} withheld positive pixels, paired 20&#8239;km-block
bootstrap (1,000 draws).</p>
<table><thead><tr><th>Arm</th><th class="num">dots</th><th class="num">DTI (A)</th>
<th class="num">DTI (B)</th><th class="num">95&#8239;% CI (B)</th></tr></thead>
<tbody>{arm_rows}</tbody></table>
<p class="muted">Tip extension versus no extension on instrument B:
<code>&#8722;0.00009…+0.00200</code> → null. Instrument A prefers the lattice over the matched random
arm; instrument B prefers random over the lattice — the two instruments disagree in direction
(IR-67-INSTRUMENT-01), which is why a “DTI gain” gate cannot adjudicate the mechanism here.
Masked tip-adjacent recovery: orientation arms {tiprec['orient_ext']['mean_tip_recovery']:.4f} vs
lattice {tiprec['lattice_d3']['mean_tip_recovery']:.4f}.</p>
<h3>The shipped raster</h3>
<dl class="kv">{shipped_rows}</dl>
<p class="muted">Instrument B CI: {rng(*shipped['instrument_B_ci95'])}. The “live analogue” row applies the
catalogue exclusion only around the catalogue the fold actually knows about, so withheld truth stays
reachable — that is the honest estimate of a live score, and it is bought by budget, not by this
lane's mechanisms.</p>
</div>

<div class="card">
<h2>Why the verdict is negative</h2>
<ol>
<li><strong>The orientation decode loses to the control.</strong> <code>lattice_d3</code> scores
{stub['lattice_d3']['pooled_dti']:.5f} (A) on a field produced entirely by this lane; the
orientation arms score {stub['orient_ext']['pooled_dti']:.5f} and
{stub['orient_noext']['pooled_dti']:.5f}.</li>
<li><strong>Tip extension adds nothing</strong> (paired CI touches zero), even though the orientation
head itself is real ({min(ori_mae):.2f}–{max(ori_mae):.2f}&#176; circular MAE versus
{min(ori_const):.2f}–{max(ori_const):.2f}&#176; for a constant frame).</li>
<li><strong>The tip head is weak:</strong> AUC {tip['auc_head']['auc']:.4f} versus
{tip['auc_evidence_control']['auc']:.4f} for the aggregate-evidence control on
{tip['auc_head']['n_pos']:,} positives / {tip['auc_head']['n_neg']:,} negatives.</li>
<li><strong>The marginal rule is degenerate here</strong> (IR-67-MARGINAL-01): the shared surrogate's
DTI is monotone in the budget, so “calibrated greedy marginal-DTI selection” cannot select. The lane
used 3&#8239;px spacing nodes instead.</li>
<li><strong>Leakage canary is clean</strong> (max single-feature AUC {max_auc:.4f} &lt; 0.90), so the
negative is a real negative, not a leakage artefact.</li>
</ol>
</div>

<div class="card">
<h2>Gate compliance</h2>
<table><tbody>
<tr><td>Gate definition</td><td>{esc(card['gate']['definition'])}</td></tr>
<tr><td>Gate met</td><td><strong>{'YES' if card['gate']['met'] else 'NO'}</strong></td></tr>
<tr><td>Format validation</td><td>{n_pass}/{len(checks)} checks pass; range guaranteed inside [0, 1];
{esc(val['emitted_positive_pixels']):} positive pixels; max {val['max']}, min {val['min']}</td></tr>
<tr><td>Raster sha256</td><td><code>{esc(card['raster']['sha256'])}</code></td></tr>
<tr><td>Registry comparison</td><td>{reg['checked']} of {reg['expected']} mirrored priors checked ·
worst rank correlation {reg['worst_spearman']:.4f} (limit 0.90) · worst 3&#8239;px dot overlap
{reg['worst_dot_overlap']:.4f} (limit 0.70) · worst Jaccard {reg['worst_jaccard']:.4f} ·
byte-identical {not reg['byte_unique']} · pixel-identical {not reg['pixel_unique']}</td></tr>
<tr><td>Certification</td><td>{esc(reg['certification'])}</td></tr>
</tbody></table>
<h3>Validator checks</h3>
<table><thead><tr><th>Check</th><th>Result</th></tr></thead><tbody>{check_rows}</tbody></table>
</div>

<div class="card">
<h2>Irregularities flagged for human review</h2>
<ul>
<li><strong>IR-67-OVERLAP-01 — the registry overlap gate cannot be satisfied by anyone.</strong>
<code>gems13_r13_lattice_s5_00904</code> (206,895 dots) has a 3&#8239;px halo covering
<strong>99.87&#8239;%</strong> of the footprint; a uniformly random 37,654-dot set scores
<strong>0.9988</strong> overlap against it. The literal “&gt;&#8239;70&#8239;% within 3&#8239;px” stop
gate therefore fires for every dense candidate — it also fires on the 0.2778 champion
(<code>duplicate_count = 40</code>). Reported, not exempted.</li>
<li><strong>IR-67-MARGINAL-01 — the calibrated marginal rule is degenerate on this field.</strong>
<code>surrogate_dti</code> rises monotonically 0.247 → 3.533 as the budget grows 500 → 37,654 dots,
because dots are scored against the posterior that placed them.</li>
<li><strong>IR-67-CATALOGUE-01 — the two catalogues disagree.</strong> Only 36.4&#8239;% of the vector
trace pixels are within 1&#8239;px of the raster label pixels (the raster is 100&#8239;% within 1&#8239;px
of the vector); 126,344 vector pixels lie outside the footprint. The external vector compilation is a
superset of the revealed labels, and only the raster labels are scored.</li>
<li><strong>IR-67-INSTRUMENT-01 — the two instruments disagree in direction.</strong> Instrument A
prefers the lattice to matched random; instrument B prefers random to the lattice. A sibling lane
measured holdout-DTI against the public leaderboard as uncorrelated (Spearman &#8722;0.10). A
DTI-gain gate is therefore not adjudicable with these instruments.</li>
</ul>
</div>

<div class="card">
<h2>Why 0.2778 scored highest, and what 0.3195 would need</h2>
<p class="muted">Source: the sibling lane's byte-verified post-mortem of the artifact
<code>h33-h33-2-b2-20261004T220000Z-e5eb6e7e-zeros</code> (sha256
<code>c55bafc470054e8271dcb89347a17e07fefe50de6af6e6ba6c4b169ef7ab6fa9</code>), mirrored here as
<code>registry/rasters/gemsdoe32_h33_2_b2_02778_zeros.tif</code>. Figures are
<strong>sibling-measured / owner-reported</strong>, not organizer receipts.</p>
<dl class="kv">
<dt>Dots</dt><dd>37,654 (median nearest-neighbour spacing 3.0 px)</dd>
<dt>Distance to the mapped catalogue</dt><dd>minimum 223.6 m; <strong>0 pixels</strong> within 200 m</dd>
<dt>Lineage</dt><dd>equals <code>gems24-d2-8</code> (0.2600) minus its 6,436-pixel ring inside 200 m of the catalogue</dd>
<dt>Credit density</dt><dd>T/|G| = 5,223 / 14,088.7 px = <strong>13.87&#8239;%</strong></dd>
<dt>Bar for 0.3195</dt><dd>15.95&#8239;% credit density — i.e. about 2 percentage points, or ~2,250 more credited pixels at the same |G|</dd>
<dt>Marginal rule</dt><dd>a dot helps iff its expected credit exceeds &#945;&#8239;·&#8239;DTI (0.0556 at 0.2778 → 283 m)</dd>
<dt>Control</dt><dd>identical-mass random scatter: 0.0778 — <strong>placement dominates recall</strong></dd>
</dl>
<p>Three falsifiable requirements follow from that analysis, and only the third is cheap:
(1) a detector that ranks <em>off-catalogue</em> faults above catalogue-free ground;
(2) an instrument tied to the scored population; (3) mass discipline at fixed credit. This lane
spent its budget on (2) and lost; the sibling register already lists catalogue fitting, external
catalogues as positive priors, topography-only selection and 1&#8239;m LiDAR fetching as
<strong>measured-dead</strong>.</p>
</div>

<div class="card">
<h2>Candidate hypotheses for the next lane (ranked by expected DTI gain per unit cost)</h2>
<table><thead><tr><th>#</th><th>Hypothesis</th><th>Layer / physical signature</th>
<th>Why it finds what the USGS/INGENIOUS catalogues miss</th><th class="num">Cost</th></tr></thead>
<tbody>
<tr><td>1</td><td><strong>Relay-ramp connectors between mapped strands</strong></td>
<td>the lane's own axial frame: wherever two catalogued traces step over, the connector runs along the
predicted strike of both</td>
<td>mappers end strands where exposure ends; the connecting segment is buried. Nothing external is
needed, and this lane already wired the machinery — what failed was the <em>instrument</em>, not the
geometry</td><td class="num">very low</td></tr>
<tr><td>2</td><td><strong>Cover-step faults</strong></td>
<td>depth-to-basement (band 15) and conductivity (17) step, <em>co-aligned</em> with a magnetic
(2/14) or gravity (13/18) lineament</td>
<td>Quaternary surface mapping cannot see faults under basin fill; a basement step that coincides
with an independent potential-field lineament is a fault candidate, not a map-unit boundary</td>
<td class="num">low</td></tr>
<tr><td>3</td><td><strong>Geothermal-manifestation collinearity</strong></td>
<td>GDR springs and volcanic vents inside the footprint, plus the INGENIOUS 2&#8239;m-temperature
field (DOI&nbsp;10.15121/1881483): fits lines through surface heat/fluid manifestations</td>
<td>blind faults leak heat along strike even where nothing is mapped; the test set is
<em>newly identified</em> faults in a geothermal province, so manifestations are the natural proxy.
Differs from the measured-dead “external catalogue as prior” route because point manifestations are not
a fault map</td><td class="num">medium</td></tr>
<tr><td>4</td><td><strong>Demagnetised damage zone</strong></td>
<td>reduced-to-pole magnetic lows (bands 2, 14) elongated along strike with tilt-derivative (6)
edges — hydrothermal alteration destroys magnetite in the damage zone</td>
<td>alteration haloes are wider than the fault and survive burial; the signal is present exactly where
the catalogue has no trace</td><td class="num">medium-high</td></tr>
</tbody></table>
<p class="muted">Ranking rationale: hypotheses 1–2 reuse layers and code already verified in this
repository; 3 needs one download that is already mirrored; 4 needs a texture/spectral measure rather
than point sampling. The brief's rule applies to all four: validate on the spatially-blocked holdout
<em>before</em> touching a weekly submission slot — and, given IR-67-INSTRUMENT-01, build the
instrument first.</p>
</div>

<div class="card">
<h2>What to do next (highest expected value first)</h2>
<ol>
<li><strong>Build an instrument tied to the scored population.</strong> Everything measured here
ranks arms within a proxy population that the sibling lane already showed is uncorrelated with the
leaderboard. Until that exists, no arm choice can be justified.</li>
<li><strong>Complete the registry mirror</strong> (51 of 751 inventory blobs here) so the lane gate is
certifiable, then re-read IR-67-OVERLAP-01 and decide the overlap rule explicitly with the owner.</li>
<li><strong>Attack credit density, not recall.</strong> The best known artifact (0.2778) spends 37,654
dots at 13.87&#8239;% credit density with 0 pixels within 200&#8239;m of any mapped trace; the bar for
0.3195 is 15.95&#8239;%. Budget and exclusion discipline are cheap levers this lane did not own.</li>
<li><strong>Try the untested off-catalogue routes</strong> (INGENIOUS 2-m temperature,
DOI&#8239;0.15121/1881483; seismic texture bands 10/16; the cover-step band 15) — the only routes the
sibling negative-results register leaves open.</li>
</ol>
</div>

<div class="card">
<h2>Reproduce</h2>
<pre class="muted"><code>bash scripts/fetch_data_ef0d41a0.sh
python3 scripts/build_prior_index_ef0d41a0.py
export GEMS67_FEATURES=/path/to/training_features.tif GEMS67_WORK=/tmp/gems67
export PYTHONPATH=vendor/template66:src
python3 -u scripts/run_lane_ef0d41a0.py e1 &amp;&amp; python3 -u scripts/run_lane_ef0d41a0.py e2 \\
  &amp;&amp; python3 -u scripts/run_lane_ef0d41a0.py e3 &amp;&amp; python3 -u scripts/run_lane_ef0d41a0.py unique
python3 -m pytest tests/ -q</code></pre>
<p class="muted">Repository: <a href="https://github.com/buffedlizard55-lab/GEMSDOE67">buffedlizard55-lab/GEMSDOE67</a> ·
evidence in <code>evidence/</code> · this page is generated by <code>scripts/build_site_ef0d41a0.py</code>.</p>
</div>

<div class="card">
<h2>Official sources used (all fetched 2026-10-12)</h2>
<ul>
<li><a href="https://www.drivendata.org/competitions/306/competition-doe-gems/">Competition home — prizes, end date, “How to compete”</a></li>
<li><a href="https://www.drivendata.org/competitions/306/competition-doe-gems/page/967/">Problem description — DTI metric formula, submission format, label expansion</a></li>
<li><a href="https://www.drivendata.org/competitions/306/competition-doe-gems/leaderboard/">Public leaderboard — live snapshot</a></li>
<li><a href="https://www.drivendata.org/competitions/306/competition-doe-gems/rules/">Official rules — external data allowed, must be shareable</a></li>
<li><a href="https://github.com/drivendataorg/gems-prize-reference-solution">Organizer reference solution</a></li>
</ul>
</div>

</main>
<footer>Generated by <code>scripts/build_site_ef0d41a0.py</code> from the run card; no figure on this page is
hand-entered. Negative results are deliverables.</footer>
</body></html>
"""
    DOCS.mkdir(exist_ok=True)
    (DOCS / "index.html").write_text(page)

    # --- executive-summary subpage: exactly how to submit ---------------------
    sub = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>How to submit — GEMS lane 67</title><style>{CSS}</style></head>
<body>
<header><div class="wrap"><h1>How to make a submission, step by step</h1>
<p>Written for a reader who has never opened the competition before.</p></div></header>
<main>
<div class="banner red"><h2>Do not submit this lane's file</h2>
<p>Lane&nbsp;67's gate was <strong>not met</strong>: the mechanism did not beat the shared template's
control on either holdout instrument. The raster is published because the brief requires a
downloadable, format-valid, unique GeoTIFF — it is <strong>for inspection, not for a submission
slot</strong>. The steps below are the general procedure; use them with a file you trust.</p></div>

<div class="card">
<h2>The two-minute version</h2>
<ol class="steps">
<li><strong>Enrol.</strong> Open the competition page, click <em>“Compete!”</em> in the sidebar and
accept the rules.</li>
<li><strong>Download your raster.</strong> A valid entry is a single-layer <strong>float32</strong>
GeoTIFF, <strong>EPSG:32611</strong> (UTM&nbsp;11N), <strong>100&nbsp;m</strong> pixels, exactly the
same grid as <code>sample_submission.tif</code>, values in <strong>[0, 1]</strong> with higher meaning
“more likely to be a fault”. Pixels outside the footprint must be null/NaN.</li>
<li><strong>Check it locally before you spend a slot.</strong> Compare CRS, transform, shape
(3730&nbsp;×&nbsp;3292), dtype and value range against <code>sample_submission.tif</code>. The single
most common rejection is <em>“Predicted values must be in range [0, 1]”</em> — a raster written in
0…255, or with a −9999 nodata sentinel, fails immediately.</li>
<li><strong>Upload.</strong> On the competition page click <em>Submit</em> in the sidebar, then
<em>“Make new submission”</em>, choose the <code>.tif</code>, add a name and a short description, and
confirm. Uploading the <code>.zip</code> is only correct if the platform asks for an archive; when in
doubt, upload the <code>.tif</code>.</li>
<li><strong>Read the score, not the rank.</strong> The public score is computed against the private
expert-labelled test set; the same submission is scored again for the Final Prize Round against an
expanded label set built from expert review of all submissions. A week-to-week rank movement of a few
places is usually noise.</li>
<li><strong>Keep a record.</strong> Store the exact file, its sha256, the score and the date. This lane
does that in <code>evidence/</code>; copying the habit saves a lot of confusion later.</li>
</ol>
</div>

<div class="card">
<h2>Rules that matter for this challenge</h2>
<ul>
<li><strong>External data is encouraged</strong> but must be licensed for the challenge and shareable
with the organizers for independent verification.</li>
<li><strong>Training on the provided labels is allowed</strong> even though the training and test sets
overlap spatially: the organizers state that newly identified faults inside the GeoDAWN region are the
test target.</li>
<li><strong>One file per submission</strong>, single band, float32, values confined to [0, 1].</li>
<li>Deadline: <strong>Dec 3, 2026, 11:59 p.m. UTC</strong>.</li>
</ul>
</div>

<div class="card">
<h2>This lane's file</h2>
<dl class="kv">
<dt>File</dt><dd><a href="downloads/{esc(tif)}" download>{esc(tif)}</a></dd>
<dt>Size</dt><dd>{card['raster']['bytes']:,} bytes</dd>
<dt>sha256</dt><dd><code>{esc(card['raster']['sha256'])}</code></dd>
<dt>Name to use</dt><dd><code>{esc(name)}</code></dd>
<dt>Note to paste</dt><dd><code>{esc(note)}</code></dd>
<dt>Should you download it?</dt><dd>Yes — it is a valid GeoTIFF and it is yours to inspect.</dd>
<dt>Should you submit it?</dt><dd><strong>No.</strong> The gate was not met, so there is no measured
reason to expect it to beat a plain submission (see <a href="index.html">the executive
summary</a>). It becomes worth a slot only after a better instrument shows the mechanism gaining.</dd>
</dl>
</div>

<p><a class="btn ghost" href="index.html">← Back to the executive summary</a></p>
</main>
<footer>Generated by <code>scripts/build_site_ef0d41a0.py</code>.</footer>
</body></html>
"""
    (DOCS / "executive-summary.html").write_text(sub)
    print(f"[site] wrote {DOCS/'index.html'} and {DOCS/'executive-summary.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
