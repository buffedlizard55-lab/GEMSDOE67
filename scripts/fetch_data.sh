#!/usr/bin/env bash
# Restore the mirrored inputs into data/ (gitignored). Nothing here contacts the organiser:
# www.drivendata.org requires a competition login and is not reachable from the sandbox, so the
# files are fetched from hash-pinned mirrors inside the same GitHub account and RE-HASHED on
# arrival against registry/data_manifest.json. See registry/irregularities.json IR-67-DATA-01.
#
# To replace these with first-hand copies, run on a machine with a competition login:
#   curl -L -b cookies.txt https://www.drivendata.org/competitions/306/competition-doe-gems/data/...
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
mkdir -p data/official data/cache data/external data/registry
ACC="https://github.com/buffedlizard55-lab"

echo "== official grid + labels (mirror: GEMSDOE63 data/official)"
for f in labels.tif existing_faults.tif sample_submission.tif; do
  [ -f "data/official/$f" ] || curl -sfL "$ACC/GEMSDOE63/raw/main/data/official/$f" -o "data/official/$f"
done

echo "== 19-band feature stack (mirror: 6GEMSDOE data/bridge, five split parts)"
if [ ! -f data/cache/numeric_features.tif ]; then
  for i in 000 001 002 003 004; do
    curl -sfL "$ACC/6GEMSDOE/raw/main/data/bridge/gems-geodawn-numerical-features.tif.part-$i" -o "/tmp/gf.part-$i"
  done
  cat /tmp/gf.part-00* > data/cache/numeric_features.tif
  rm -f /tmp/gf.part-00*
fi

echo "== external derived layers (mirror: 60GEMSDOE data/external)"
for f in geodawn_rad_u8.tif topo_10m_derived_100m_u8.tif derived_sgmc_faults_100m_u8.tif; do
  [ -f "data/external/$f" ] || curl -sfL "$ACC/60GEMSDOE/raw/main/data/external/$f" -o "data/external/$f"
done

echo "== pinned registry of prior rasters (mirror: GEMSDOE66 registry/rasters)"
if [ -z "$(ls -A data/registry 2>/dev/null)" ]; then
  curl -sfL "https://codeload.github.com/buffedlizard55-lab/GEMSDOE66/tar.gz/refs/heads/main" -o /tmp/s66.tgz
  tar -xzf /tmp/s66.tgz -C /tmp "GEMSDOE66-main/registry/rasters" && cp -r /tmp/GEMSDOE66-main/registry/rasters/. data/registry/
  rm -rf /tmp/s66.tgz /tmp/GEMSDOE66-main
fi

echo "== re-hash and compare with registry/data_manifest.json"
python3 - <<'PY'
import hashlib, json, pathlib
man = json.loads(pathlib.Path('registry/data_manifest.json').read_text())
want = {f['path']: f['sha256'] for f in man['files'] if not f['path'].startswith('data/registry/')}
bad = []
for p, h in sorted(want.items()):
    f = pathlib.Path(p)
    if not f.exists():
        bad.append((p, 'MISSING')); continue
    got = hashlib.sha256(f.read_bytes()).hexdigest()
    if got != h:
        bad.append((p, f'HASH MISMATCH got {got[:16]} want {h[:16]}'))
    else:
        print(f'  OK {got[:16]} {p}')
if bad:
    print('FAILED:'); [print('  ', *b) for b in bad]; raise SystemExit(2)
print('all mirrored inputs re-hashed clean')
PY
