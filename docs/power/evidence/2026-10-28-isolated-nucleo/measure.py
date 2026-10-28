"""Root-owned isolated RAM probe with JS recording and no debugger polling."""
import argparse,importlib.util,json,subprocess,sys,time
from pathlib import Path
HERE=Path(__file__).parent
ap=argparse.ArgumentParser();ap.add_argument('name');ap.add_argument('--flags',type=int,default=0)
ap.add_argument('--build',default='probe-v1');ap.add_argument('--runner',default='run.py')
ap.add_argument('--prior');ap.add_argument('--divider',type=int,default=1);ap.add_argument('--refusal')
a=ap.parse_args();out=HERE/a.name
spec=importlib.util.spec_from_file_location('isolated_probe_runner',HERE/a.runner)
probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)
kwargs=dict(flags=a.flags,prior=Path(a.prior) if a.prior else None)
if a.runner!='run.py':kwargs['divider']=a.divider
if a.refusal:kwargs['refusal']=Path(a.refusal)
b,s=probe.prepare(HERE/a.build,out,**kwargs)
armed=out/'logger-armed.json'
with (out/'logger.log').open('wb') as log:
    p=subprocess.Popen([sys.executable,str(HERE/'aligned_logger.py'),'--out',str(out/'trace'),
       '--armed-file',str(armed),'--duration','6'],stdout=log,stderr=subprocess.STDOUT,
       creationflags=subprocess.CREATE_NO_WINDOW)
    deadline=time.monotonic()+20
    while not armed.exists():
        if p.poll() is not None:raise RuntimeError('Recorder ended before arming; no probe launch')
        if time.monotonic()>deadline:raise RuntimeError('Recorder arm timeout; inspect owner')
        time.sleep(.05)
    probe.launch(b,s)
    p.wait(timeout=15)
    if p.returncode:raise RuntimeError('Recorder failed; leave target for diagnosis')
r=probe.observe(b,s)
print(json.dumps({k:r[k] for k in ('passed','busy_nominal_ms','sleep_nominal_ms','qualified_timed_wfi_returns')},indent=2))
print(json.dumps({k:r['proof'][k] for k in ('FLAGS','DIVIDER','DBG_BEFORE','DBG_ACTIVE','DBG_AFTER','BUSY_ITERATIONS','WFI_RETURNS','ERROR')},indent=2))
