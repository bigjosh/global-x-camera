"""Freeze the qualified host runner with the currently installed recovery identity."""
from pathlib import Path
import hashlib,json
H=Path(__file__).resolve().parent;R=H.parents[2]
src=R/'tmp/bringup/power-ablation-20261028/run_aligned.py'
t=src.read_text()
old="str(Path(__file__).parent/'aligned_logger.py')"
assert t.count(old)==1
t=t.replace(old,"str(ROOT/'tmp/bringup/power-ablation-20261028/aligned_logger.py')")
old="recovery_build=ROOT/'tmp/bringup/error-relocate-20261026/flash-normal-v2/staged'"
assert t.count(old)==1
t=t.replace(old,"recovery_build=ROOT/'tmp/bringup/ethernet-normal-20261028/flash-candidate/staged'")
with (H/'run_aligned.py').open('x') as f:f.write(t)
(H/'runner-provenance.json').write_text(json.dumps(dict(source=str(src),source_sha256=hashlib.sha256(src.read_bytes()).hexdigest(),
    changes=['Bind currently installed Ethernet-normal recovery build','Keep original qualified JS logger absolute path'],
    target_sha256=hashlib.sha256((H/'run_aligned.py').read_bytes()).hexdigest()),indent=2)+'\n')
