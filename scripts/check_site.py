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
for p in [ROOT/'index.html',*(ROOT/'docs').glob('*.html')]:
    parser=Links();parser.feed(p.read_text())
    for link in parser.links:
        u=urlsplit(link)
        if u.scheme or u.netloc or not u.path:continue
        dst=(p.parent/unquote(u.path)).resolve()
        assert dst.is_relative_to(ROOT),link
        assert dst.is_file(),(p,link)
        if card['verdict']!='promote':assert dst.suffix.lower() not in ('.tif','.tiff','.zip'),link
assert not card['download_enabled'] if card['verdict']=='negative' else True
print('Site links and negative-result download restrictions passed')
