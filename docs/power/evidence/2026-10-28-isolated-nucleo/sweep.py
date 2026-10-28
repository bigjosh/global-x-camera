"""Sequential root-owned clock sweep. Stop on any failed measurement."""
from pathlib import Path
import subprocess,sys,json
HERE=Path(__file__).parent
prior=HERE/'cpu400b/operation/verified.json'
for name,divider in [('cpu200a',2),('cpu100a',4),('cpu50a',8),('cpu400c',1)]:
    assert json.loads(prior.read_text())['passed'] is True
    cmd=[sys.executable,str(HERE/'measure.py'),name,'--runner','run_v4.py','--build','probe-v4',
         '--flags','0','--divider',str(divider),'--prior',str(prior)]
    with (HERE/(name+'-host.log')).open('wb') as log:
        subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True,creationflags=subprocess.CREATE_NO_WINDOW)
    prior=HERE/name/'operation/verified.json'
    assert json.loads(prior.read_text())['passed'] is True
    print(json.dumps({'completed':name,'divider':divider,'verified':str(prior)}),flush=True)
