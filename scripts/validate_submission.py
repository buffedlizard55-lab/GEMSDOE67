"""CLI wrapper for the unchanged shared format validator; does not clear promotion."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'vendor'))
import numpy as np
import rasterio
from gems57.gates import format_report

def main():
    p=argparse.ArgumentParser();p.add_argument('raster');p.add_argument('--sample',default=str(ROOT/'data/sample_submission.tif'));a=p.parse_args()
    with rasterio.open(a.sample) as s: footprint=np.isfinite(s.read(1))
    result=format_report(a.raster,a.sample,footprint=footprint)
    print(json.dumps(result,indent=2,allow_nan=False));return 0 if result['ok'] else 1
if __name__=='__main__':raise SystemExit(main())
