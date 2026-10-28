"""Read all six measured cold-cycle images after exact normal recovery.
No reset/power/erase or card write. Original RAM does not survive Standby.
"""
from pathlib import Path
import json,subprocess,sys
H=Path(__file__).resolve().parent;R=H.parents[2]
def run(name,*args):
    with (H/(name+'.log')).open('xb') as log:
        subprocess.run([sys.executable,*map(str,args)],cwd=R,stdout=log,stderr=subprocess.STDOUT,
                       check=True,creationflags=subprocess.CREATE_NO_WINDOW)
run('candidate-standby-flags',R/'firmware/capture-sd/low_power/read_standby_flag.py',
    '--build',H/'flash-candidate/staged','--park-result',H/'candidate03/park/result.json',
    '--out',H/'candidate-standby-flags')
run('cold-read-entry',R/'firmware/capture-raw/bench.py','read',
    '--build',H/'ram-candidate','--expected-sha','ef85e7106b3cb0cb253fe4a174e926a1bd227c006b7bfa46ab0433a1496ae000',
    '--out',H/'cold-read-entry','--recovery-build',H/'flash-candidate/staged',
    '--lba',123*3730,'--count',1,'--execute')
run('cold-images-readback',R/'tmp/bringup/sd-fourbit-20261024/magic_readback.py','read-slots',
    '--build',H/'ram-candidate','--prior',H/'cold-read-entry/verified.json',
    '--scr-proof',H/'candidate-reobserved/verified.json',
    '--slot',123,'--slot',124,'--slot',125,'--slot',127,'--slot',128,'--slot',129,
    '--out',H/'cold-images-readback','--execute')
v=json.loads((H/'cold-images-readback/summary.json').read_text());assert v['passed'] and len(v['slots'])==6
print('ALL_SIX_COLD_IMAGES_VERIFIED',flush=True)
