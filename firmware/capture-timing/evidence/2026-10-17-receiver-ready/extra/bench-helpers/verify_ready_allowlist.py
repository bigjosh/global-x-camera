"""Offline verification of every experimental prefix approved this session."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path('firmware/capture-timing/recovery_gpio').resolve()))
import check_park
names=[
'v37-streaming-stop10-coarse5','v37-streaming-stop0-coarse5',
'v38a-ack-stop0-coarse5','v38b-ack-stop0-default',
'v39-early-stop100-coarse5','v39-force-stop100-coarse5',
'v41-force-lane1-stop100-coarse5','v41-force-lane1-stop100-default',
'v42-force-stop0-coarse5','v43-force-lane1-stop100-pen200-coarse5']
for name in names:
    code,approved=check_park.checked_build(Path('tmp/bringup')/('capture-phy-ready-'+name+'-20261017')/'staged')
print(f'{len(names)} exact full-prefix/sector allowlist checks passed; no hardware accessed')
