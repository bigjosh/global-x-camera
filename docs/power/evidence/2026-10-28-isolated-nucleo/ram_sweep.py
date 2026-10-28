from pathlib import Path
import subprocess,sys,json
HERE=Path(__file__).parent
prior=HERE/'cpu400c/operation/verified.json'
for name,flags in [('ramcontrol01',0),('ramoff01',2),('ramcontrol02',0)]:
    assert json.loads(prior.read_text())['passed'] is True
    cmd=[sys.executable,str(HERE/'measure.py'),name,'--runner','run_v5.py','--build','probe-v5',
         '--flags',str(flags),'--divider','1','--prior',str(prior)]
    with (HERE/(name+'-host.log')).open('wb') as log:
        subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True,creationflags=subprocess.CREATE_NO_WINDOW)
    prior=HERE/name/'operation/verified.json';assert json.loads(prior.read_text())['passed'] is True
    print(json.dumps({'completed':name,'flags':flags,'verified':str(prior)}),flush=True)
