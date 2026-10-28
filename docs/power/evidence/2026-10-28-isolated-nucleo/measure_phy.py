"""Root-owned PHY baseline / power-down / restored-baseline measurement."""
import importlib.util,json,subprocess,sys,time
from pathlib import Path
HERE=Path(__file__).parent;out=HERE/sys.argv[1]
spec=importlib.util.spec_from_file_location('phy_aba_runner',HERE/'mdio/power_aba/run.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
b,m=p.prepare(out,HERE/'ramcontrol02/operation/verified.json')
armed=out/'logger-armed.json'
with (out/'logger.log').open('wb') as log:
    rec=subprocess.Popen([sys.executable,str(HERE/'aligned_logger.py'),'--out',str(out/'trace'),
        '--armed-file',str(armed),'--duration','6'],stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
    deadline=time.monotonic()+20
    while not armed.exists():
        if rec.poll() is not None or time.monotonic()>deadline:raise RuntimeError('Recorder failed to arm')
        time.sleep(.05)
    p.launch(b,m);rec.wait(timeout=15)
    if rec.returncode:raise RuntimeError('Recording failed; inspect before any reset')
r=p.observe(b,m)
print(json.dumps({k:r[k] for k in ('completed_and_restored','phy_restored_verified','window_ms','cfsr','hfsr')},indent=2))
if not r['completed_and_restored']:raise RuntimeError('PHY result not qualified; leave for diagnosis')
b.call('-halt','-coreReg','PC=0x343003AA','XPSR=0x01000000','-run',success='Core run')
(b.output/'return-to-main.json').write_text(json.dumps({'pc':'0x343003AA','reason':'PHY BMCR, GPIO and clocks independently verified restored; main v5 code/proof untouched. Next operation performs its own fresh gate.'},indent=2))
