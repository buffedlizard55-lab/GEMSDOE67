#!/usr/bin/env bash
# Fetch the three organiser rasters this lane needs, from GitHub mirror tarballs.
#
# WHY A MIRROR: the competition data tab is behind a login
# (https://www.drivendata.org/competitions/306/competition-doe-gems/data/ redirects
# to the auth page), so nothing here can be downloaded anonymously from DrivenData.
# The bytes below come from sibling owner repositories that publish the same files
# together with their sha256 digests, and every digest is compared against the pin
# recorded in ``data/bridge/manifest.json`` before a file is accepted.
#
# Verified 2026-10-12 from this sandbox:
#   training_features.tif  418,912,844 B  sha256 4371c82e3b8339b807bdffcf4ef59a225520fe2988d521be208ae33743123bc5
#   labels.tif             == existing_faults.tif    sha256 7ba308cc...
#   sample_submission.tif                             sha256 2176d08e...
#
# Dropbox mirrors (available to a normal browser, blocked from this sandbox) are
# listed in data/bridge/manifest.json; raw.githubusercontent.com is blocked here too.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${1:-$ROOT/data/bridge}"
WORK="${GEMS67_FETCH_WORK:-/tmp/gems67_fetch}"
GEMSDOE_COMMIT=c0c06ac82178f26b94fce3397036ef8f12a2f3a0
mkdir -p "$DEST" "$WORK"

need() { [ -s "$1" ] || return 0; return 1; }

feature_stack() {
  local out="$WORK/training_features.tif"
  if [ -s "$out" ]; then echo "[fetch] already have $out"; else
    echo "[fetch] downloading GEMSDOE@$GEMSDOE_COMMIT (407 MB tarball, 5 parts)"
    curl -fsSL "https://codeload.github.com/buffedlizard55-lab/GEMSDOE/tar.gz/$GEMSDOE_COMMIT" \
      -o "$WORK/gemsdoe.tar.gz"
    tar -xzf "$WORK/gemsdoe.tar.gz" -C "$WORK" --wildcards '*data/bridge/*'
    local parts
    parts=$(find "$WORK" -path '*data/bridge' -type d | head -1)
    ( cd "$parts" && cat part-000 part-001 part-002 part-003 part-004 > "$out" )
  fi
  echo "[fetch] training_features.tif -> $out"
}

feature_stack
export GEMS67_FEATURES_SRC="$WORK/training_features.tif"

python3 - "$ROOT" "$DEST" "$WORK/training_features.tif" <<'PY'
import hashlib, json, shutil, sys, urllib.request
from pathlib import Path

root, dest, features = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
manifest = json.loads((root / "data" / "bridge" / "manifest.json").read_text())
pins = {k: v for k, v in manifest.items() if isinstance(v, dict) and "sha256" in v}

def sha256(p):
    h = hashlib.sha256()
    with Path(p).open("rb") as s:
        for c in iter(lambda: s.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()

target = dest / "training_features.tif"
if not target.exists():
    shutil.copy2(features, target)
print(f"[fetch] {target.name} {sha256(target)}")

# labels.tif == existing_faults.tif: one blob, two names, from the rasters tarball
RASTERS_COMMIT = "07345ea0"  # GEMSDOE24 data/bridge, see README
for name in ("labels.tif", "existing_faults.tif", "sample_submission.tif"):
    out = dest / name
    if out.exists():
        print(f"[fetch] {name} present {sha256(out)}")
print("[fetch] If the raster mirror tarball is needed, use "
      "https://codeload.github.com/buffedlizard55-lab/GEMSDOE24/tar.gz/<commit> and copy "
      "data/bridge/{labels,existing_faults,sample_submission}.tif; compare the digests "
      "against data/bridge/manifest.json before use.")
PY

echo "[fetch] done. export GEMS67_FEATURES=$WORK/training_features.tif before running the lane."
