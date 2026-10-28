"""Read both diagnostic cold-cycle slots; no writes or erases."""
from pathlib import Path
import json,subprocess,sys
H=Path(__file__).resolve().parent;R=H.parents[2]
assert json.loads((H/'cold-gap02-park/result.json').read_text())['passed']
def run(name,*args):
    with (H/(name+'.log')).open('xb') as log:
        subprocess.run([sys.executable,*map(str,args)],cwd=R,stdout=log,stderr=subprocess.STDOUT,
                       check=True,creationflags=subprocess.CREATE_NO_WINDOW)
run('gap-standby-flags',R/'firmware/capture-sd/low_power/read_standby_flag.py',
    '--build',H/'design/flash-gap/staged','--park-result',H/'cold-gap02-park/result.json',
    '--out',H/'gap-standby-flags')
run('cold-read-entry',R/'firmware/capture-raw/bench.py','read',
    '--build',H/'design/ram-gap','--expected-sha','b106972b4973e0a46c25754ca417f347001b540c76fa2c0c43a3c54edaabb133',
    '--out',H/'cold-read-entry','--recovery-build',H/'design/flash-gap/staged',
    '--lba',133*3730,'--count',1,'--execute')
run('cold-images-readback',R/'tmp/bringup/sd-fourbit-20261024/magic_readback.py','read-slots',
    '--build',H/'design/ram-gap','--prior',H/'cold-read-entry/verified.json',
    '--scr-proof',H/'ram-gap01/capture/verified.json',
    '--slot',133,'--slot',134,'--out',H/'cold-images-readback','--execute')
v=json.loads((H/'cold-images-readback/summary.json').read_text());assert v['passed'] and len(v['slots'])==2
print('BOTH_COLD_IMAGES_VERIFIED',flush=True)
