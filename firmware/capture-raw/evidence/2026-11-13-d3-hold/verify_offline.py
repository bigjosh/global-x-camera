"""Verify the archived D3 package and exact bytes; never access hardware."""
from pathlib import Path
import hashlib
import json
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT/'firmware/capture-raw'))
import inspect_flash

for line in (HERE/'SHA256SUMS').read_text().splitlines():
    digest, name = line.split('  ', 1)
    if hashlib.sha256((HERE/name).read_bytes()).hexdigest() != digest:
        raise SystemExit('Changed archive file: ' + name)
folder = HERE/'hold-standby'
manifest = json.loads((folder/'manifest.json').read_text())
staged = json.loads((folder/'staged/manifest.json').read_text())
result = inspect_flash.gpio_hold_artifacts(folder, manifest, staged)
assert result == json.loads((HERE/'capture-audit.json').read_text())
assert result['prefix']['pin'] == 'PE9'
assert manifest['gpio_hold_contract']['schema'] == 4
for relative in ('capture.bin', 'staged/stage1.bin', 'staged/capture_sector_0.bin'):
    old = ROOT/'firmware/capture-raw/evidence/2026-10-28-sensor-single-frame/flash-standby-v1'/relative
    assert (HERE/'no-hold-control'/relative).read_bytes() == old.read_bytes()
print('Exact D3 package, no-HOLD baseline and archive hashes passed; no instruments accessed.')
