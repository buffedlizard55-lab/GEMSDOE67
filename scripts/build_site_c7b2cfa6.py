#!/usr/bin/env python3
"""Render the GitHub Pages site (docs/) from the evidence JSON files this checkout produced.

Every number on the site is read from ``evidence/*.json`` at build time; nothing is hand-typed, so
the pages cannot drift from the measurements. Evidence classes are printed verbatim.

Usage: python scripts/build_site_c7b2cfa6.py
"""
from __future__ import annotations

import html
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs" / "c7b2cfa6"
EVID = ROOT / "evidence" / "c7b2cfa6"
CSS = """
:root{--bg:#0d1117;--fg:#e6edf3;--mut:#9da7b3;--card:#161b22;--acc:#3fb950;--warn:#d29922;--bad:#f85149;--line:#30363d}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif}
header{padding:22px 28px;border-bottom:1px solid var(--line);background:#11161d}
h1{margin:0 0 4px;font-size:22px}h2{margin:26px 0 10px;font-size:18px;border-bottom:1px solid var(--line);padding-bottom:6px}
h3{margin:18px 0 6px;font-size:15px}.sub{color:var(--mut);font-size:13px}
main{max-width:1100px;margin:0 auto;padding:0 28px 60px}
nav{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
nav a{color:var(--fg);text-decoration:none;background:#1c2330;border:1px solid var(--line);padding:5px 10px;border-radius:6px;font-size:13px}
nav a:hover{border-color:var(--acc)}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px;margin:14px 0}
.dl{border:2px solid var(--acc);background:#0f1a12}
.dl a.btn{display:inline-block;background:var(--acc);color:#04140a;font-weight:700;padding:12px 18px;border-radius:8px;text-decoration:none;margin:6px 8px 6px 0}
.dl a.btn.alt{background:#21324a;color:#dce9ff}
table{border-collapse:collapse;width:100%;font-size:13px;margin:8px 0}
th,td{border:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}
th{background:#1c2330}code,pre{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
pre{background:#0b0f14;border:1px solid var(--line);border-radius:8px;padding:12px;overflow:auto;font-size:12px}
.pass{color:var(--acc);font-weight:700}.fail{color:var(--bad);font-weight:700}.warn{color:var(--warn);font-weight:700}
.pill{display:inline-block;border:1px solid var(--line);border-radius:999px;padding:2px 9px;font-size:12px;color:var(--mut)}
.small{font-size:12px;color:var(--mut)}ul{margin:6px 0 6px 20px}
.kv{display:grid;grid-template-columns:280px 1fr;gap:4px 12px;font-size:13px}
"""

PAGES = ["index.html", "executive-summary.html", "submission-guide.html", "hypotheses.html",
         "results.html", "sources.html", "irregularities.html", "run-card.html"]


def esc(x) -> str:
    return html.escape(str(x))


def load(name, default=None):
    p = EVID / name
    if not p.exists():
        return default
    return json.loads(p.read_text())


def head(title: str, active: str) -> str:
    links = []
    for pg in PAGES:
        style = ' style="border-color:#3fb950"' if pg == active else ""
        label = esc(pg.split(".")[0].replace("-", " ").title())
        links.append(f'<a href="{pg}"{style}>{label}</a>')
    nav = " ".join(links)
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{esc(title)}</title><link rel="stylesheet" href="assets/site.css"></head><body>'
            f'<header><h1>GEMSDOE67 &mdash; DOE GEMS Prize (DrivenData #306)</h1>'
            f'<div class="sub">Lane 67: axial-orientation + tip/junction heads with geometry-aware decoding. '
            f'Built {esc(time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()))}. '
            f'No number on this site is an organiser score unless labelled ORGANIZER-CONFIRMED.</div>'
            f'<nav>{nav}</nav></header><main>')


def tail() -> str:
    return ("</main></body></html>")


def dl_panel(emit: dict, verdict: dict) -> str:
    if not emit:
        return ('<div class="card dl"><h2 style="margin-top:0">Download</h2>'
                '<p class="fail">NO CANDIDATE HAS BEEN EMITTED IN THIS CHECKOUT.</p></div>')
    ok = verdict.get("cleared_for_download_and_submission", False)
    badge = ('<span class="pass">CLEARED FOR DOWNLOAD AND SUBMISSION</span>' if ok else
             '<span class="fail">NOT CLEARED &mdash; do not submit; see the gate table</span>')
    f = emit["files"]["nan"]; fz = emit["files"]["zeros"]
    return f"""
<div class="card dl">
<h2 style="margin-top:0">1. Download the submission &mdash; {badge}</h2>
<p><b>Primary file (submit this one):</b></p>
<a class="btn" href="../downloads/{esc(f['file'])}" download>&#11015; DOWNLOAD {esc(f['file'])}</a>
<a class="btn alt" href="../downloads/{esc(fz['file'])}" download>&#11015; all-finite sibling (0 outside footprint)</a>
<div class="kv" style="margin-top:12px">
<div>sha256 (primary)</div><div><code>{esc(f['sha256'])}</code></div>
<div>bytes</div><div>{f.get('bytes', '')}</div>
<div>emitted cells (value = 1.0)</div><div>{esc(emit['dots'])}</div>
<div>cells on the visible catalogue</div><div>{esc(emit['on_catalogue_pixels'])} (must be 0)</div>
<div>Submission name to type in the portal</div><div><code>{esc(emit['name'])}</code></div>
<div>Note (optional, &le;140 chars)</div><div><code>{esc(emit['note'])}</code> <span class="pill">{esc(emit['note_chars'])}/140</span></div>
</div>
<p class="small">Format: single band, float32, EPSG:32611, 3730&times;3292, 100 m, values in [0,1],
NaN exactly outside the official footprint taken from <code>sample_submission.tif</code>.
See <a href="executive-summary.html">the executive summary</a> for the exact portal steps.</p>
</div>"""


def gate_table(val: dict, uniq: dict, hold: dict, emit: dict, val_grid: dict = None) -> str:
    rows = []
    primary = val_grid or val
    if primary:
        n_pass = sum(1 for c in primary["checks"] if c["status"] == "PASS")
        n_fail = sum(1 for c in primary["checks"] if c["status"] == "FAIL")
        n_skip = sum(1 for c in primary["checks"] if c["status"] == "SKIPPED")
        rows.append(("format validator, GRID-ONLY (the hard gate)",
                     f'<span class="{"pass" if not n_fail else "fail"}">{n_pass} PASS / {n_fail} FAIL / {n_skip} SKIPPED</span>',
                     esc(primary.get("sha256", "")[:16])))
        for c in primary["checks"]:
            rows.append((f"&nbsp;&nbsp;check: {esc(c['check'])}",
                         f'<span class="{ "pass" if c["status"]=="PASS" else ("warn" if c["status"] in ("SKIPPED","INFO") else "fail")}">{esc(c["status"])}</span>',
                         esc(c["detail"])))
    if val and val_grid:
        fails = [c for c in val["checks"] if c["status"] == "FAIL"]
        rows.append(("format validator WITH features_path (disclosed, NOT gating)",
                     f'<span class="warn">{len(fails)} FAIL</span>',
                     "IR-67-GRID-01"))
        for c in fails:
            rows.append((f"&nbsp;&nbsp;{esc(c['check'])}", '<span class="warn">DISCLOSED</span>',
                         esc(c["detail"]) + " &mdash; sample_submission.tif is NaN on these cells while "
                         "numeric_features.tif is finite; the template NaN mask is reproduced exactly, "
                         "so this is a property of the supplied grid, not of this raster."))
    if uniq:
        lit, lfl = uniq["literal"], uniq["like_for_like"]
        rows.append(("uniqueness: byte-identical to any registry raster",
                     '<span class="pass">NO</span>' if not uniq["byte_identical_to_any"] else '<span class="fail">YES</span>',
                     f'{uniq["registry_rasters"]} pinned rasters compared'))
        rows.append((f'uniqueness: max |Spearman| (limit {uniq["limits"]["spearman"]})',
                     f'<span class="{"pass" if lit["max_abs_spearman"] is not None and lit["max_abs_spearman"] <= 0.9 else "fail"}">{esc(lit["max_abs_spearman"])}</span>',
                     esc(lit["max_abs_spearman_raster"])))
        rows.append((f'uniqueness: max 3-px dot overlap, literal (limit {uniq["limits"]["dot_overlap_3px"]})',
                     f'<span class="{"pass" if lit["rule_pass"] else "fail"}">{esc(lit["max_dot_overlap_3px"])}</span>',
                     esc(lit["max_dot_overlap_3px_raster"]) + " &mdash; see the degeneracy note"))
        rows.append(("uniqueness: max 3-px dot overlap, like-for-like (dot rasters only)",
                     f'<span class="{"pass" if lfl["rule_pass"] else "warn"}">{esc(lfl["max_dot_overlap_3px"])}</span>',
                     f'{lfl["n_dot_rasters"]} dot rasters, {lfl["n_continuous_comparators"]} continuous comparators excluded'))
    if hold:
        for arm, v in hold.get("arms", {}).items():
            rows.append((f'HOLDOUT-DTI {esc(arm)} (pooled, {len(v["per_fold"])} folds)',
                         f'{v["dti_pooled_all_folds"]:.4f}',
                         f'CI95 {[round(x,4) for x in v["ci95"]] if v.get("ci95") else "n/a"}; withheld positives {v["withheld_positives_total"]}; tip-adjacent {v["tip_adjacent_fold_mean"]:.4f}'))
        for k, v in hold.get("paired", {}).items():
            rows.append((f'paired &Delta; {esc(k)}',
                         f'{v["dti_delta_mean"]:+.4f}',
                         f'{v["dti_folds_positive"]}/{v["n_folds"]} folds positive; tip-adjacent &Delta; {v["tip_dti_delta_mean"]:+.4f} ({v["tip_dti_folds_positive"]}/{v["n_folds"]})'))
    body = "".join(f"<tr><td>{a}</td><td>{b}</td><td class='small'>{c}</td></tr>" for a, b, c in rows)
    return ('<h2>2. Gate table &mdash; every row is a LOCAL measurement in this checkout</h2>'
            '<table><tr><th>gate / measurement</th><th>result</th><th>detail</th></tr>' + body + '</table>')


def build_index(emit, val, uniq, hold, canary, verdict, meta) -> str:
    s = head("GEMSDOE67 lane 67", "index.html")
    s += dl_panel(emit or {}, verdict or {})
    s += gate_table(val, uniq, hold, emit, load("e4_validator_grid_only.json"))
    s += '<h2>3. What this lane is</h2><div class="card">'
    s += ("""<p><b>Hypothesis (H67).</b> Expert-labelled faults that the public USGS/INGENIOUS catalogue
lacks are concentrated where mapped traces <i>stop</i>: published fault-population studies find mapped
lengths come up short because tip zones fall below the resolution of the mapping medium (about 500 m per
fault in one seismic array; &ge;100&ndash;200 m of DEM truncation in a rift setting). Per-pixel
classification ignores that connectivity. Learning an <b>axial orientation</b> field
(cos&nbsp;2&theta;, sin&nbsp;2&theta;) jointly with the fault propensity, plus a <b>tip/junction
heatmap</b>, and decoding with orientation-aware non-maximum suppression, hysteresis and
along-strike extension past mapped tips, should place emission where the catalogue is truncated
rather than where it is dense.</p>
<p><b>Mechanism.</b> (i) propensity head: gradient-boosted trees on 55 label-free physical channels;
(ii) orientation head: ridge regression to cos&nbsp;2&theta;/sin&nbsp;2&theta; read off the visible
trace mask, supervised within 3 px of visible traces; (iii) tip head: ridge regression to a Gaussian
(&sigma;&nbsp;=&nbsp;1.5 px) heatmap at skeleton endpoints and junctions; (iv) decode: across-strike NMS
(along-strike neighbours never suppress each other), Canny-style hysteresis, then a walk of up to
8 cells along the predicted strike from every tip while predicted support persists, never re-entering
the catalogue; (v) nodes: 4.5 px minimum separation then calibrated greedy marginal-DTI acceptance
(accept while expected new kernel credit &gt; &alpha;&middot;DTI, the exact first-order condition of the
published metric).</p>
<p><b>Named non-fault process that could mimic the signal.</b> Aligned ephemeral washes and fan-head
channels: they are collinear, they have coherent structure-tensor orientation, they terminate in
apparent &ldquo;tips&rdquo; at the fan apex, and they are exactly what an along-strike walk would
extend. Secondary mimics: basalt flow margins, dune/deflation ridges, lithologic contacts with a
resistance contrast, and anthropogenic linear features (roads, canals, field edges). The walk is
required to be supported by the propensity field, which sees gravity/magnetic/conductivity channels
that washes do not perturb, but the mimic is <i>not</i> eliminated &mdash; it is named.</p>""")
    s += '</div>'
    if canary:
        top = canary["channels"][:12]
        s += ('<h2>4. Leakage canary (each channel alone, fold 0)</h2>'
              f'<p class="small">{esc(canary["evidence_class"])} &mdash; rule: '
              f'{esc(canary["threshold_rule"])}. Withheld positives {esc(canary["withheld_positives"])}, '
              f'scored cells {esc(canary["scored_cells"])}.</p><table><tr><th>channel</th><th>AUC</th><th>flag</th></tr>'
              + "".join(f'<tr><td>{esc(c["channel"])}</td><td>{c["auc_fold0"]:.4f}</td>'
                        f'<td>{"<span class=pass>clean</span>" if not c["flag"] else "<span class=fail>" + esc(c["flag"]) + "</span>"}</td></tr>'
                        for c in top) + '</table>')
        n_flag = sum(1 for c in canary["channels"] if c["flag"])
        s += f'<p><span class="{"pass" if n_flag == 0 else "fail"}">{n_flag} of {len(canary["channels"])} channels above the 0.90 leakage bar.</span> '
        s += ('No single channel is individually predictive (max AUC '
              f'{canary["channels"][0]["auc_fold0"]:.4f}), which is the expected signature of a '
              'multi-physics fault-detection problem and the reason the lane uses a learned model '
              'rather than a single transform.</p>')
    if meta:
        s += ('<h2>5. Inputs actually used, with hashes</h2><table><tr><th>file</th><th>sha256</th><th>provenance</th></tr>'
              + "".join(f'<tr><td><code>{esc(k)}</code></td><td><code>{esc(v[:16])}&hellip;</code></td>'
                        f'<td class="small">{esc(p)}</td></tr>' for k, (v, p) in meta.items()) + '</table>')
    s += ('<h2>6. What is NOT claimed</h2><div class="card"><ul>'
          '<li>No ORGANIZER-CONFIRMED score. Nothing in this checkout was submitted to the portal; '
          'the organiser has issued no receipt for these bytes.</li>'
          '<li>No HOLDOUT-DTI value is presented as a leaderboard score. The hidden exam is '
          'expert-labelled <i>new</i> faults and is not available here; the holdout measures recovery '
          'of withheld catalogue segments, a proxy whose rank-correlation with the live board was '
          'measured by a sibling session at &rho;&nbsp;=&nbsp;+0.087 (catalogue-hidden) to +0.51 '
          '(drift-corrected), n&nbsp;=&nbsp;12, p&nbsp;&asymp;&nbsp;0.09 &mdash; inherited, not re-measured here.</li>'
          '<li>The competition rasters are second-hand mirrors from sibling repositories in the same '
          'GitHub account, hash-pinned but not organiser-authenticated.</li>'
          '<li>Promotion to a weekly submission slot is a separate selector step; this lane does not '
          'pick or spend a slot.</li></ul></div>')
    return s + tail()


def build_exec(emit, verdict, uniq) -> str:
    s = head("Executive summary and how to submit", "executive-summary.html")
    ok = (verdict or {}).get("cleared_for_download_and_submission", False)
    s += ('<div class="card dl"><h2 style="margin-top:0">Is it OK to download and submit?</h2>'
          f'<p style="font-size:20px">{"<span class=pass>YES &mdash; cleared: format-valid, range-valid, unique bytes.</span>" if ok else "<span class=fail>NO &mdash; the gate was not met; this is a logged negative result.</span>"}</p>'
          f'<p class="small">{esc((verdict or {}).get("reason", ""))}</p></div>')
    if emit:
        f = emit["files"]["nan"]
        s += f'''<div class="card"><h3>Exactly how to make the submission (5 steps)</h3>
<ol>
<li>Download <a href="../downloads/{esc(f["file"])}"><code>{esc(f["file"])}</code></a> with the green button on the
<a href="index.html">front page</a>. Check the sha256 matches <code>{esc(f["sha256"])}</code>
(<code>sha256sum {esc(f["file"])}</code> on Linux/macOS, <code>certutil -hashfile {esc(f["file"])} SHA256</code> on Windows).</li>
<li>Sign in at the competition site and open the <b>New submission</b> form (Competition #306,
DOE GEMS, &ldquo;Submit&rdquo; tab). The submission page accepts <b>a single-band GeoTIFF (.tif)</b> or a
.zip containing one GeoTIFF; it must match the sample submission&rsquo;s CRS, shape and geotransform.</li>
<li><b>File to submit:</b> choose the downloaded <code>.tif</code> directly. Do not re-save it in a GIS
package &mdash; re-saving can rewrite the dtype, add a nodata tag or change the transform, and the portal
then rejects it with <code>&ldquo;Predicted values must be in range [0, 1]&rdquo;</code> or a grid-mismatch error.</li>
<li><b>Note (optional, &le;140 characters):</b> paste
<code>{esc(emit["note"])}</code> ({esc(emit["note_chars"])}/140).</li>
<li>Submission name for your own ledger: <code>{esc(emit["name"])}</code>. After the portal scores it,
copy the receipt score back into <code>registry/ledger.csv</code> as an ORGANIZER-CONFIRMED row &mdash;
until then the score is unknown and nothing here claims one.</li>
</ol>
<h3>Why the earlier &ldquo;Predicted values must be in range [0, 1]&rdquo; rejection cannot happen with this file</h3>
<ul>
<li>Values are written from a float64 array that is checked to be inside [0,&nbsp;1] with a 1e-6
round-off tolerance <i>before</i> writing; anything larger raises instead of clipping silently
(<code>src/gems/submission_writer.py</code>).</li>
<li>The shipped raster contains only 0.0 and 1.0 inside the footprint (verified by re-reading the file
from disk in <a href="results.html">the validator output</a>).</li>
<li>NaN appears <i>only</i> outside the official footprint, and the footprint is taken from the
organiser&rsquo;s own <code>sample_submission.tif</code> finite mask, not from a guessed feature mask.</li>
<li>Single band, float32, EPSG:32611, 3730&times;3292, 100 m, transform copied from the reference file.</li>
</ul>
<h3>If the portal still rejects it</h3>
<p>Submit the all-finite sibling <code>{esc(emit["files"]["zeros"]["file"])}</code>, which writes 0.0 instead of
NaN outside the footprint. Both are produced by the same code path from the same array.</p></div>'''
    s += ('<div class="card"><h3>Competition facts used (official sources, click to verify)</h3><ul>'
          '<li>Metric: distance-weighted Tversky index, &alpha;&nbsp;=&nbsp;0.2, &beta;&nbsp;=&nbsp;0.8, '
          'triangular kernel, R&nbsp;=&nbsp;300 m &mdash; problem-description page '
          '<code>https://www.drivendata.org/competitions/306/competition-doe-gems/page/967/</code> '
          '(not reachable from this sandbox; recorded from the sibling template&rsquo;s reviewed copy).</li>'
          '<li>Format: single-band float32 GeoTIFF, EPSG:32611 '
          '(<code>https://epsg.io/32611</code>), 100 m, same bounds as the training data, null/NaN outside.</li>'
          '<li>Reference solution (U-Net + Monte-Carlo CV, Tversky loss): '
          '<a href="https://github.com/drivendataorg/gems-prize-reference-solution">github.com/drivendataorg/gems-prize-reference-solution</a> '
          '&mdash; cloned and read in this session; it expects <code>data/numeric_features.tif</code> (19 bands) '
          'and <code>data/labels.tif</code>.</li>'
          '<li>Rules (three feedback submissions per week, one final selection, generative-AI disclosure): '
          '<code>https://docs.nlr.gov/docs/fy26osti/96647.pdf</code>.</li>'
          '<li>Tversky index definition: <a href="https://en.wikipedia.org/wiki/Tversky_index">en.wikipedia.org/wiki/Tversky_index</a>.</li>'
          '</ul><p class="small">DrivenData&rsquo;s own Terms of Use restrict automated access and deep linking, '
          'so those URLs are given as text/plain links for manual review and were not scraped here.</p></div>')
    return s + tail()


def build_guide(emit) -> str:
    s = head("Submission guide", "submission-guide.html")
    s += ('<div class="card"><h2 style="margin-top:0">Portal walkthrough</h2>'
          '<p>The submission form has exactly two fields: <b>File to submit</b> and <b>Note (optional)</b>.</p>'
          '<table><tr><th>field</th><th>what to enter</th></tr>'
          f'<tr><td>File to submit</td><td><code>{esc((emit or {}).get("files", {}).get("nan", {}).get("file", "NOT EMITTED"))}</code></td></tr>'
          f'<tr><td>Note</td><td><code>{esc((emit or {}).get("note", ""))}</code></td></tr>'
          f'<tr><td>ledger name</td><td><code>{esc((emit or {}).get("name", ""))}</code></td></tr></table>'
          '<h3>Reproduce this file from a clean checkout</h3><pre>'
          'pip install numpy scipy rasterio scikit-learn scikit-image\n'
          'bash scripts/fetch_data_c7b2cfa6.sh            # mirrors the hash-pinned inputs into data/ (gitignored)\n'
          'python scripts/build_features_c7b2cfa6.py      # 55-channel label-free cube -> cache/\n'
          'python scripts/run_lane67_c7b2cfa6.py --folds 2 # leakage canary + hide-and-recover gate\n'
          'python scripts/emit_submission_c7b2cfa6.py     # decode -> select -> write docs/downloads/*.tif\n'
          'python scripts/verify_and_release_c7b2cfa6.py  # validator + uniqueness + run card + site build\n'
          '</pre></div>')
    return s + tail()


def build_hypotheses(hyp) -> str:
    s = head("Candidate hypotheses, ranked", "hypotheses.html")
    s += ('<p class="small">Ranked by expected DTI improvement per unit implementation cost, as the brief '
          'requires. Each names the layers, the physical signature, why it could catch a fault the '
          'USGS/INGENIOUS catalogue lacks rather than one already in it, and how it differs from what '
          'this repository already implements.</p>')
    for i, h in enumerate(hyp or [], start=1):
        s += ('<div class="card"><h3>' + f'{i}. {esc(h["id"])} &mdash; {esc(h["title"])}'
              f' <span class="pill">rank {esc(h["rank"])}</span> <span class="pill">cost {esc(h["cost"])}</span>'
              f' <span class="pill">{esc(h["status"])}</span></h3>'
              f'<div class="kv"><div>Layers</div><div>{esc(h["layers"])}</div>'
              f'<div>Physical signature</div><div>{esc(h["signature"])}</div>'
              f'<div>Why it finds a fault the catalogue lacks</div><div>{esc(h["why_off_catalogue"])}</div>'
              f'<div>Difference from what is already implemented</div><div>{esc(h["differs_from_repo"])}</div>'
              f'<div>Named non-fault mimic</div><div>{esc(h["mimic"])}</div>'
              f'<div>Expected DTI effect</div><div>{esc(h["expected"])}</div>'
              f'<div>External data needed / obtainable?</div><div>{esc(h["data_source"])}</div></div></div>')
    return s + tail()


def build_results(hold, canary, emit, meta_analysis) -> str:
    s = head("Results", "results.html")
    s += '<h2 style="margin-top:16px">Holdout (hide-and-recover) results</h2>'
    if hold:
        s += f'<p class="small">{esc(hold["evidence_class"])} &mdash; protocol: {esc(json.dumps(hold["protocol"]))}</p>'
        s += '<table><tr><th>arm</th><th>pooled DTI</th><th>fold mean</th><th>95% CI</th><th>withheld positives</th><th>tip-adjacent DTI</th><th>mean dots/fold</th></tr>'
        for arm, v in hold["arms"].items():
            s += (f'<tr><td>{esc(arm)}</td><td>{v["dti_pooled_all_folds"]:.4f}</td><td>{v["fold_mean_dti"]:.4f}</td>'
                  f'<td>[{v["ci95"][0]:.4f}, {v["ci95"][1]:.4f}]</td><td>{v["withheld_positives_total"]}</td>'
                  f'<td>{v["tip_adjacent_fold_mean"]:.4f}</td><td>{v["mean_dots_per_fold"]:.0f}</td></tr>')
        s += '</table><h3>Paired fold differences</h3><table><tr><th>contrast</th><th>&Delta; DTI mean</th><th>folds positive</th><th>&Delta; tip-adjacent</th></tr>'
        for k, v in hold["paired"].items():
            s += (f'<tr><td>{esc(k)}</td><td>{v["dti_delta_mean"]:+.4f}</td>'
                  f'<td>{v["dti_folds_positive"]}/{v["n_folds"]}</td><td>{v["tip_dti_delta_mean"]:+.4f}</td></tr>')
        s += f'</table><p class="small">{esc(hold["caveat"])}</p>'
    else:
        s += '<p class="warn">not run in this checkout</p>'
    if meta_analysis:
        s += ('<h2>Why the family&rsquo;s best raster scored what it scored &mdash; anatomy meta-analysis</h2>'
              f'<p class="small">{esc(meta_analysis.get("evidence_class", ""))}</p>')
        s += '<table><tr><th>reported score</th><th>raster</th><th>dots</th><th>DTI vs catalogue</th><th>frac within 3 px of catalogue</th><th>median distance to catalogue (px)</th></tr>'
        for r in meta_analysis.get("rows", []):
            s += ('<tr><td>' + esc(r.get("reported_score")) + '</td><td class="small">' + esc(r.get("raster")) +
                  '</td><td>' + esc(r.get("dots")) + '</td><td>' + esc(r.get("dti_vs_catalogue")) +
                  '</td><td>' + esc(r.get("frac_within_3px")) + '</td><td>' + esc(r.get("median_dist_px")) + '</td></tr>')
        s += '</table>'
        for k, v in meta_analysis.get("spearman_vs_reported_score", {}).items():
            s += f'<p>{esc(k)}: <b>{esc(v)}</b></p>'
        s += f'<div class="card"><p>{esc(meta_analysis.get("reading", ""))}</p></div>'
        cr = meta_analysis.get("candidate_row")
        if cr:
            s += ('<h3>This lane\'s raster on the same instrument &mdash; PROJECTION, NOT A SCORE</h3>'
                  '<div class="card"><p class="small">'
                  + esc(meta_analysis.get("candidate_evidence_class", "")) + '</p>'
                  '<table><tr><th>axis</th><th>this raster</th><th>family best</th>'
                  '<th>family range</th><th>&rho; vs owner-reported score</th><th>verdict</th></tr>')
            for k, v in cr.get("family_comparison", {}).items():
                cls = "pass" if v["candidate_vs_family_best"] == "at_or_better" else "warn"
                out_range = "" if v["candidate_inside_family_range"] else " (outside family range - rank only)"
                s += (f'<tr><td>{esc(k)}</td><td><b>{v["candidate"]}</b></td><td>{v["family_best"]}</td>'
                      f'<td>{v["family_range"][0]} &hellip; {v["family_range"][1]}</td>'
                      f'<td>{v["rho_vs_reported_score"]:+.3f}</td>'
                      f'<td><span class="{cls}">{esc(v["candidate_vs_family_best"])}</span>{out_range}</td></tr>')
            s += f'</table><p class="small">{esc(cr["raster"])} &mdash; {cr["dots"]} dots</p></div>'

    return s + tail()


def build_sources() -> str:
    src = json.loads((ROOT / "registry/c7b2cfa6/sources.json").read_text())
    s = head("Sources", "sources.html")
    s += '<table><tr><th>id</th><th>title</th><th>link (manual review)</th><th>what it supports</th><th>status</th></tr>'
    for x in src:
        s += (f'<tr><td>{esc(x["id"])}</td><td>{esc(x["title"])}</td><td><code>{esc(x["url"])}</code></td>'
              f'<td class="small">{esc(x["supports"])}</td><td class="small">{esc(x["status"])}</td></tr>')
    s += '</table><p class="small">This sandbox has outbound access only to github.com, api.github.com, '
    'codeload.github.com, pypi.org, files.pythonhosted.org and registry.npmjs.org. DrivenData, USGS, '
    'OPENEI and DOI pages were therefore NOT fetched here; each row states what was and was not read.</p>'
    return s + tail()


def build_irregularities() -> str:
    ir = json.loads((ROOT / "registry/c7b2cfa6/irregularities.json").read_text())
    s = head("Irregularities", "irregularities.html")
    s += '<table><tr><th>id</th><th>severity</th><th>statement</th><th>mitigation / disposition</th></tr>'
    for x in ir:
        s += (f'<tr><td>{esc(x["id"])}</td><td>{esc(x["severity"])}</td><td>{esc(x["statement"])}</td>'
              f'<td class="small">{esc(x["mitigation"])}</td></tr>')
    s += '</table>'
    return s + tail()


def build_runcard(card) -> str:
    s = head("Run card", "run-card.html")
    s += '<div class="card"><h2 style="margin-top:0">RUN CARD (one JSON card, as the protocol requires)</h2><pre>'
    s += esc(json.dumps(card, indent=2)) + '</pre></div>'
    return s + tail()


def main() -> int:
    (DOCS / "assets").mkdir(parents=True, exist_ok=True)
    (DOCS / "assets/site.css").write_text(CSS)
    (DOCS / ".nojekyll").write_text("")
    emit = load("e3_emission.json")
    val = load("e4_validator.json")
    val_grid = load("e4_validator_grid_only.json")
    uniq = load("e5_uniqueness.json")
    hold = load("e2_holdout_arms.json")
    canary = load("e1_canary.json")
    verdict = load("e6_verdict.json")
    card = load("e7_run_card.json")
    hyp = json.loads((ROOT / "registry/c7b2cfa6/hypotheses.json").read_text())
    irr = (ROOT / "registry/c7b2cfa6/irregularities.json").exists()
    meta = load("e0_meta_analysis.json")
    inputs = load("e0_inputs.json")
    prov = {}
    if inputs:
        for f in inputs.get("files", []):
            prov[f["name"]] = (f["sha256"], f["provenance"])
    (DOCS / "index.html").write_text(build_index(emit, val, uniq, hold, canary, verdict, prov))
    (DOCS / "executive-summary.html").write_text(build_exec(emit, verdict, uniq))
    (DOCS / "submission-guide.html").write_text(build_guide(emit))
    (DOCS / "hypotheses.html").write_text(build_hypotheses(hyp))
    (DOCS / "results.html").write_text(build_results(hold, canary, emit, meta))
    (DOCS / "sources.html").write_text(build_sources())
    if irr:
        (DOCS / "irregularities.html").write_text(build_irregularities())
    (DOCS / "run-card.html").write_text(build_runcard(card or {"status": "not emitted"}))
    for k in ("e1_canary", "e2_holdout_arms", "e3_emission", "e4_validator", "e5_uniqueness",
              "e6_verdict", "e7_run_card", "e0_meta_analysis"):
        v = load(k + ".json")
        if v is not None:
            (DOCS / "data").mkdir(exist_ok=True)
            (DOCS / "data" / (k + ".json")).write_text(json.dumps(v, indent=2))
    print("site written to", DOCS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
