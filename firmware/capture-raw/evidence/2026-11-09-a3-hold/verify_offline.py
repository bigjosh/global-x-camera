"""Verify archived A3 builds with current strict auditors; no hardware access."""
from pathlib import Path
import hashlib
import json
import sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT/'firmware/capture-raw'))
import inspect_flash
for line in (HERE/'SHA256SUMS').read_text().splitlines():
    digest,name=line.split('  ',1)
    if hashlib.sha256((HERE/name).read_bytes()).hexdigest()!=digest:
        raise SystemExit('Changed archive file: '+name)
for name in ('hold-standby','hold-awake'):
    folder=HERE/name
    m=json.loads((folder/'manifest.json').read_text())
    p=json.loads((folder/'staged/manifest.json').read_text())
    result=inspect_flash.gpio_hold_artifacts(folder,m,p)
    assert result['prefix']['pin']=='PA2'
    print(name+': exact A3 package passed')
print('Archive hashes passed; no instruments accessed.')
