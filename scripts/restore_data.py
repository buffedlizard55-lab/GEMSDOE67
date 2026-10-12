"""Restore owner-mirrored data with upstream hash checks; not organizer authentication."""
import hashlib, json, subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1048576), b''): h.update(b)
    return h.hexdigest()
def main():
    target = ROOT / 'data'; target.mkdir(exist_ok=True)
    manifest = json.loads((ROOT/'evidence/upstream/data_manifest.json').read_text())
    receipts=[]
    for e in manifest['files']:
        if e['group'] != 'core' or e['id']=='existing_faults': continue
        dst=target/e['dest']; tmp=dst.with_suffix('.partial')
        if not dst.exists() or digest(dst)!=e['sha256']:
            try:
                with tmp.open('wb') as out:
                    for p in e.get('parts', [e.get('path')]):
                        print('Restoring',p,flush=True)
                        subprocess.run(['gh','api',f"repos/{e['repo']}/contents/{p}?ref={e['ref']}",'-H','Accept: application/vnd.github.raw'],stdout=out,check=True,timeout=300)
                if digest(tmp)!=e['sha256']: raise ValueError('SHA256 mismatch: '+e['id'])
                tmp.replace(dst)
            finally: tmp.unlink(missing_ok=True)
        receipts.append({'file':e['dest'],'bytes':dst.stat().st_size,'sha256':digest(dst),'provenance':e['provenance']})
    (ROOT/'evidence/data_restore.json').write_text(json.dumps(receipts,indent=2)+'\n')
if __name__=='__main__':main()
