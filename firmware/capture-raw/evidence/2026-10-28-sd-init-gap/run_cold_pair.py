"""Two measured diagnostic cold cycles, with exact UART park between runs."""
from pathlib import Path
import json, subprocess, sys
H=Path(__file__).resolve().parent; R=H.parents[2]
sys.path.insert(0,str(H/'analysis'))
from analyze_gap import analyze
build=H/'design/flash-gap'
prefix=json.loads((build/'staged/manifest.json').read_text())['binary_sha256'] if False else 'cedb4d9e7c38b90f805dbf24c1bad5cc8af8c1597f3cd9e58fd5e9b9c86cc6c6'
def run(label,args):
    with (H/(label+'.log')).open('xb') as f:
        subprocess.run([sys.executable,*map(str,args)],stdout=f,stderr=subprocess.STDOUT,check=True,creationflags=subprocess.CREATE_NO_WINDOW)
def park(label):
    run(label+'-recovery',[R/'tmp/bringup/sd125-negedge-20261026/uart_recover.py',H/(label+'-recovery')])
    out=H/(label+'-park')
    run(label+'-park',[R/'firmware/capture-timing/recovery_gpio/check_park.py','--build',build/'staged','--out',out])
    return out/'result.json'
proof=park('gap-installed')
for n in (1,2):
    label=f'cold-gap{n:02d}'
    run(label,[R/'tmp/bringup/ethernet-normal-20261028/cold_logger.py','--out',H/label/'trace','--cycle','--park-proof',proof,'--expected-prefix-sha',prefix])
    result=analyze(dict(run=label,group='gap',trace=str(H/label/'trace'),evidence=dict(build=str(build))))
    print(label,'ANALYSIS_PASSED',flush=True)
    proof=park(label)
print('COLD_PAIR_COMPLETE',proof,flush=True)
