"""Root-owned RAM capture with native JS markers and no mid-cycle debugger polling.

No reset/power/NOR command. Existing RAW bench gates perform all target actions.
"""
import sys,importlib.util,json,subprocess,time,hashlib
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[3]
build=Path(sys.argv[1]).resolve();out=Path(sys.argv[2]).resolve()
out.relative_to(ROOT/'tmp');out.mkdir(exist_ok=False)
m=json.loads((build/'manifest.json').read_text())
sys.path.insert(0,str(ROOT/'firmware/capture-raw'))
spec=importlib.util.spec_from_file_location('aligned_raw_bench',ROOT/'firmware/capture-raw/bench.py')
bench=importlib.util.module_from_spec(spec);spec.loader.exec_module(bench)
original=bench.sd.Bench.call;started=[]
def call(self,*args,**kwargs):
    if '-run' not in args or f"PC={hex(m['entry'])}" not in args:
        return original(self,*args,**kwargs)
    if started:raise RuntimeError('Unexpected second RAW launch')
    started.append(True);armed=out/'logger-armed.json'
    with (out/'logger.log').open('wb') as log:
        p=subprocess.Popen([sys.executable,str(Path(__file__).parent/'aligned_logger.py'),
            '--out',str(out/'trace'),'--armed-file',str(armed),'--duration','6'],
            stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
        deadline=time.monotonic()+20
        while not armed.exists():
            if p.poll() is not None:raise RuntimeError('Logger exited before arming; target not launched')
            if time.monotonic()>deadline:
                raise RuntimeError('Logger arm timeout; target not launched; inspect process before retry')
            time.sleep(.05)
        answer=original(self,*args,**kwargs)
        # Target runs autonomously; no debugger calls until the recorder closes.
        p.wait(timeout=15)
        if p.returncode:raise RuntimeError('Logger failed; leave target state for diagnosis')
    return answer
bench.sd.Bench.call=call
a=SimpleNamespace(build=build,expected_sha=m['binary_sha256'],out=out/'capture',
    prior=None,bridge_proof=None,recovery_build=ROOT/'tmp/bringup/error-relocate-20261026/flash-normal-v2/staged',
    execute=True,operation='capture',generation=None,slot_limit=0,lba=0,count=1,download_frame=True)
bench.run(a)
if len(started)!=1:raise RuntimeError('No synchronized RAW launch')
print('ALIGNED_CAPTURE_VERIFIED',flush=True)
