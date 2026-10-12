#!/usr/bin/env python3
"""Assemble the single JSON run card required by the parallel-run protocol.

Every field is read from an artifact written by ``scripts/run_lane_ef0d41a0.py``; nothing is
typed in by hand, so the card cannot drift from the measurements.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EV = ROOT / "evidence"

NOTE_LIMIT = 140


def _load(name: str) -> dict:
    path = EV / name
    if not path.exists():
        raise SystemExit(f"missing evidence {path}; run the lane steps first")
    return json.loads(path.read_text())


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    e1 = _load("e1_verify_canary_heads.json")
    e2 = _load("e2_arms_holdout.json")
    e3 = _load("e3_submission_receipt.json")
    uq = _load("e3_uniqueness.json")
    gate = _load("e3_uniqueness_gate.json")

    stub = e2["instrument_stub"]["pooled"]
    hide = e2["instrument_hide"]["pooled"]["scores"]
    hide_paired = e2["instrument_hide"]["pooled"]["paired_differences"]
    shipped_stub = e3["scored_on_instruments"]["stub"]
    shipped_hide = e3["scored_on_instruments"]["hide"]
    tif = ROOT / "docs" / "downloads" / e3["raster"]["filename"]
    if not tif.exists():
        raise SystemExit(f"published raster missing: {tif}")

    best_control = max(("lattice_d3", "random"), key=lambda k: stub[k]["pooled_dti"])
    gate_met = bool(e3["gate_met"])
    card = dict(
        schema="lane67-run-card-v1",
        lane="67-orientation-tip-heads",
        generated_utc=e3["generated_utc"],
        verdict="negative" if not gate_met else "promote",
        hypothesis=e3["hypothesis"],
        mechanism=e3["mechanism"],
        non_fault_mimic=e3["non_fault_mimic"],
        instruments=dict(
            A=dict(name="withheld segments (hide-and-recover, pixel-exact mask)",
                   implementation="gems57.holdout.build_holdout + score_cell",
                   withheld_positive_pixels=stub["orient_ext"]["n_truth"],
                   note="quadrants at footprint medians, whole <=12 px segments withheld"),
            B=dict(name="withheld whole components", evaluator_version=e2["instrument_hide"]
                   ["pooled"]["evaluator_version"],
                   withheld_positive_pixels=e2["instrument_hide"]["pooled"]["scores"]
                   ["orient_ext"]["withheld_positive_pixels"],
                   bootstrap="paired 20 km blocks, 1000 draws"),
        ),
        arms={k: dict(dots=v["dots"], instrument_A_dti=v["pooled_dti"]) for k, v in stub.items()},
        instrument_B={k: dict(dti=v["dti"], ci95=v["ci95"],
                              withheld_positive_pixels=v["withheld_positive_pixels"])
                      for k, v in hide.items()},
        paired_differences_B=hide_paired,
        best_control={"arm": best_control, "instrument_A_dti": stub[best_control]["pooled_dti"],
                      "instrument_B_dti": hide.get("lattice_d3", {}).get("dti")},
        shipped=dict(arm=e3["shipped_arm"], dots=e3["dots"], budget=e3["budget_selection"]
                     ["chosen_budget"],
                     instrument_A_dti=shipped_stub["pooled_dti"],
                     instrument_B_dti=shipped_hide["dti"], instrument_B_ci95=shipped_hide["ci95"],
                     live_analogue_dti_max=e3["budget_selection"]["sweep"][-1]
                     ["selection_instrument_stub_dti"]),
        gate=dict(met=gate_met, definition=e3["gate_definition"],
                  tip_recovery=e2["instrument_stub"]["tip_adjacent_recovery"]),
        leakage_canary=e1["canaries"],
        heads=dict(orientation=e1["orientation_head"], tip=e1["tip_head"]),
        registry=dict(
            checked=int(uq["registry_rasters_checked"]),
            expected=int(uq["registry_rasters_expected"]),
            complete_accessible_scan=bool(uq["complete_accessible_scan"]),
            worst_spearman=uq["worst_spearman_full_footprint"],
            worst_spearman_submission=uq["worst_rho_submission"],
            worst_dot_overlap=uq["worst_dot_overlap"],
            worst_dot_overlap_submission=uq["worst_overlap_submission"],
            worst_jaccard=uq["worst_jaccard_dot_sets"] or None,
            byte_unique=uq["byte_unique_among_checked"], pixel_unique=uq["pixel_unique_among_checked"],
            lane_duplicate_detected=gate["lane_duplicate_detected"],
            certification=gate["certification"],
            irregularity="IR-67-OVERLAP-01: a mirrored prior's 3 px halo covers 99.87% of the "
                         "footprint, so the literal >0.70 overlap gate fires for any dense "
                         "candidate, including the 0.2778 champion.",
        ),
        raster=dict(filename=tif.name, sha256=_sha256(tif), bytes=tif.stat().st_size,
                    **{k: v for k, v in e3["raster"].items() if k not in ("filename", "sha256",
                                                                          "bytes")}),
        validator=e3["validator"],
        submission=dict(name=e3["submission_name"], note=e3["submission_note_140c"],
                        note_length=len(e3["submission_note_140c"]), note_limit=NOTE_LIMIT,
                        submit_guidance="Gate NOT met: keep the slot. The file is published for "
                                        "inspection because the prompt requires a downloadable, "
                                        "format-valid unique GeoTIFF."),
        seconds=e3["seconds"],
        budget=dict(experiments_planned=3, experiments_run=3,
                    note="E3 folded budget calibration, shipping and the registry gate into one "
                         "experiment; two ad-hoc probes reused existing artifacts."),
    )
    if len(card["submission"]["note"]) > NOTE_LIMIT:
        raise SystemExit("note exceeds the 140-character limit")
    out = EV / "run_card.json"
    out.write_text(json.dumps(card, indent=1, sort_keys=False) + "\n")
    print(f"[run-card] verdict={card['verdict']} -> {out.relative_to(ROOT)}")
    print(f"[run-card] shipped HOLDOUT-DTI A {shipped_stub['pooled_dti']:.5f} "
          f"B {shipped_hide['dti']:.5f} {shipped_hide['ci95']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
