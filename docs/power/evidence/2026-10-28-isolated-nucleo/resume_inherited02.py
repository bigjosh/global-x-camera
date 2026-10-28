"""Resume prelaunch filename-collision failure; no reset or replacement code."""
import importlib.util,json,struct,sys,subprocess,time
from pathlib import Path
HERE=Path(__file__).parent
sp=importlib.util.spec_from_file_location('isolated_resume',HERE/'run.py')
p=importlib.util.module_from_spec(sp);sp.loader.exec_module(p)
out=HERE/'inherited02';old=out/'bootstrap'
# Retain probe request/clear under distinct names, then restore overwritten
# bridge input files from their independently captured original readbacks.
request=(old/'request.bin').read_bytes();clear=(old/'clear.bin').read_bytes()
assert len(request)==32 and clear==bytes(1024)
(old/'isolated-request.bin').write_bytes(request);(old/'isolated-clear.bin').write_bytes(clear)
(old/'request.bin').write_bytes((old/'request-readback.bin').read_bytes())
(old/'clear.bin').write_bytes((old/'cleared.bin').read_bytes())
m,code=p.checked(HERE/'probe-v1');b=p.raw.sd.Bench(out/'resume')
bridge=json.loads((old/'verified.json').read_text())
p.raw.sd.context_proof(b,{p.raw.bridge.BOOT_PARK},'fresh-bridge-context')
if b.upload(m['load'],len(code),'probe-readback.bin')!=code:raise ValueError('Probe differs')
if b.upload(m['request'],32,'request-readback.bin')!=request:raise ValueError('Request differs')
if b.upload(m['proof'],1024,'proof-clear-readback.bin')!=bytes(1024):raise ValueError('Proof not clear')
words=list(struct.unpack('<8I',request));assert words[0]==0x31514552 and words[2:]==[0,1,0,0,0,0]
s=dict(m,nonce=words[1],request_words=words,build=str((HERE/'probe-v1').resolve()))
p.raw.dump(b.output/'prepared.json',s)
armed=out/'logger-armed.json'
with (out/'logger.log').open('wb') as log:
    rec=subprocess.Popen([sys.executable,str(HERE/'aligned_logger.py'),'--out',str(out/'trace'),
       '--armed-file',str(armed),'--duration','6'],stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
    deadline=time.monotonic()+20
    while not armed.exists():
        if rec.poll() is not None or time.monotonic()>deadline:raise RuntimeError('Recorder did not arm')
        time.sleep(.05)
    p.launch(b,s);rec.wait(timeout=15)
    if rec.returncode:raise RuntimeError('Recording failed')
r=p.observe(b,s)
print(json.dumps({k:r[k] for k in ('passed','busy_nominal_ms','sleep_nominal_ms','qualified_timed_wfi_returns')},indent=2))
print(json.dumps(r['proof'],indent=2))
