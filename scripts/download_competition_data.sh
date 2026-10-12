#!/usr/bin/env bash
# Fetch the official DOE GEMS competition rasters into data/raw/ on a machine
# with unrestricted egress, then run scripts/prepare_data.py.
#
# Official source (login required):
#   https://www.drivendata.org/competitions/306/competition-doe-gems/data/
# Verified public mirrors of the same bytes (sha256-pinned in
# data/bridge/manifest.json and 6GEMSDOE/data/evidence/):
#   https://www.dropbox.com/scl/fi/3vz9o0wwavi26xaeoxlwr/gems-geodawn-numerical-features.tif
#   https://www.dropbox.com/scl/fi/t7fyt03qdh9egyme0itwo/existing_faults.tif
#   https://www.dropbox.com/scl/fi/6rgvnuady818ol8yqgis4/example_submission.tif
#
# In an egress-restricted sandbox, use the git data bridge instead:
#   git clone --depth 1 https://github.com/buffedlizard55-lab/6GEMSDOE.git
#   cat 6GEMSDOE/data/bridge/gems-geodawn-numerical-features.tif.part-0* \
#       > data/raw/gems-geodawn-numerical-features.tif
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p data/raw

echo "== trying DrivenData (requires prior login in this browser/session) =="
if curl -fsSL --max-time 60 -o data/raw/features.download \
    "https://www.dropbox.com/scl/fi/3vz9o0wwavi26xaeoxlwr/gems-geodawn-numerical-features.tif?rlkey=je8d8fepqfbst9lnwsq9rkplu&dl=1"; then
  mv data/raw/features.download data/raw/gems-geodawn-numerical-features.tif
  curl -fsSL -o data/raw/existing_faults.tif \
    "https://www.dropbox.com/scl/fi/t7fyt03qdh9egyme0itwo/existing_faults.tif?rlkey=yiao96uluqdkipf0h5vju71jf&dl=1"
  curl -fsSL -o data/raw/example_submission.tif \
    "https://www.dropbox.com/scl/fi/6rgvnuady818ol8yqgis4/example_submission.tif?rlkey=kbykilvau066xuogoosbf4cq8&dl=1"
else
  echo "dropbox unreachable; trying the git data bridge (6GEMSDOE) ..."
  rm -f data/raw/features.download
  [ -d /tmp/6GEMSDOE ] || git clone --depth 1 https://github.com/buffedlizard55-lab/6GEMSDOE.git /tmp/6GEMSDOE
  cat /tmp/6GEMSDOE/data/bridge/gems-geodawn-numerical-features.tif.part-00* \
      > data/raw/gems-geodawn-numerical-features.tif
  cp /tmp/6GEMSDOE/data/bridge/existing_faults.tif data/raw/
  cp /tmp/6GEMSDOE/data/bridge/example_submission.tif data/raw/
fi

python3 scripts/prepare_data.py
