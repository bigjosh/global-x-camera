"""One explicitly requested matched RAM trial, with fresh predecessor idle proof."""
import sys,subprocess,importlib.util,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).parent
oldbuild=Path(sys.argv[1]).resolve();prior=Path(sys.argv[2]).resolve()
build=Path(sys.argv[3]).resolve();name=sys.argv[4]
out=HERE/name;transition=HERE/(name+'-transition');transition.mkdir(exist_ok=False)
sys.path.insert(0,str(ROOT/'firmware/capture-raw'))
spec=importlib.util.spec_from_file_location('transition_bench',ROOT/'firmware/capture-raw/bench.py')
bmod=importlib.util.module_from_spec(spec);spec.loader.exec_module(bmod)
p=json.loads(prior.read_text());m,code=bmod.checked_build(oldbuild,p['binary_sha256'])
b=bmod.sd.Bench(transition/'idle');bmod.terminal_gate(b,oldbuild,m,code,p,'fresh')
def run(label,*args):
    with (transition/(label+'.log')).open('wb') as log:
        subprocess.run([sys.executable,*map(str,args)],cwd=ROOT,stdout=log,
            stderr=subprocess.STDOUT,check=True,creationflags=subprocess.CREATE_NO_WINDOW)
run('recovery',ROOT/'tmp/bringup/sd125-negedge-20261026/uart_recover.py',transition/'recovery')
run('park',ROOT/'firmware/capture-timing/recovery_gpio/check_park.py','--build',
    ROOT/'tmp/bringup/error-relocate-20261026/flash-normal-v2/staged','--out',transition/'park')
run('capture',HERE/'run_aligned.py',build,out)
run('counters',ROOT/'tmp/bringup/sd50-reviewed-20261026/read_trace.py',build,out/'capture/verified.json',out/'counters')
print('COMPLETE',name,flush=True)
