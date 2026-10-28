import sys,importlib.util,subprocess,time,json
from pathlib import Path
HERE=Path(__file__).parent;ROOT=HERE.parents[2]
spec=importlib.util.spec_from_file_location('power_sleep_runner',HERE/'sleep-probe/run.py')
probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)
out=HERE/'sleep01'
b,m=probe.prepare(HERE/'ram-normal',HERE/'normal04/capture/verified.json',out)
armed=out/'logger-armed.json'
with (out/'logger.log').open('wb') as log:
    p=subprocess.Popen([sys.executable,str(HERE/'aligned_logger.py'),'--out',str(out/'trace'),
        '--armed-file',str(armed),'--duration','6'],stdout=log,stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW)
    deadline=time.monotonic()+20
    while not armed.exists():
        if p.poll() is not None:raise RuntimeError('Logger ended before arming; CPU probe not launched')
        if time.monotonic()>deadline:raise RuntimeError('Logger arm timeout; inspect owner before recovery')
        time.sleep(.05)
    probe.launch(b,m)
    p.wait(timeout=15)
    if p.returncode:raise RuntimeError('Logger failed; CPU state left for diagnosis')
result=probe.observe(b,m)
print(json.dumps(result,indent=2))
