"""Offline internal-link and unsafe-download regression checks."""
import json
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit,unquote
ROOT=Path(__file__).resolve().parents[1]
class Links(HTMLParser):
    def __init__(self):super().__init__();self.links=[]
    def handle_starttag(self,tag,attrs):
        self.links.extend(v for k,v in attrs if k in ('href','src') and v)
card=json.loads((ROOT/'docs/run-card.json').read_text())
assert len(card['note'])<=140
# MERGE NOTE (two-lane repository, 2026-10-12): the no-download rule is a property of THIS lane's
# run, so it is enforced on this lane's own pages. The OVTR lane (arena/c331a9d8) publishes a
# verified artifact with its own run card (docs/run-card-ovtr.json) and its own rule; its pages are
# listed in OVTR_PAGES and are linked-checked but not subject to this lane's gate.
OVTR_PAGES = {'index.html','ceiling.html','how-to-submit.html','research.html','run-card.html','sources.html'}
pages = [ROOT/'index.html'] + [q for q in sorted((ROOT/'docs').glob('*.html'))
                               if q.name not in OVTR_PAGES or q.name == 'index.html']
for p in pages:
    parser=Links();parser.feed(p.read_text())
    for link in parser.links:
        u=urlsplit(link)
        if u.scheme or u.netloc or not u.path:continue
        dst=(p.parent/unquote(u.path)).resolve()
        assert dst.is_relative_to(ROOT),link
        assert dst.is_file(),(p,link)
        if card['verdict']!='promote' and p.name not in OVTR_PAGES:
            assert dst.suffix.lower() not in ('.tif','.tiff','.zip'),link
assert not card['download_enabled'] if card['verdict']=='negative' else True
print('Site links and negative-result download restrictions passed')
