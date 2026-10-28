"""Read-only trace after exact successful RAM terminal/live-code gate."""
import sys,json,importlib.util,subprocess
from pathlib import Path
root=Path.cwd();spec=importlib.util.spec_from_file_location('raw_bench',root/'firmware/capture-raw/bench.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
build,prior,out=map(Path,sys.argv[1:4]);out.mkdir()
p=json.loads(prior.read_text());m,code=mod.checked_build(build,p['binary_sha256'])
assert m.get('cycle_trace'), 'No enabled cycle trace'
b=mod.sd.Bench(out/'reads');mod.terminal_gate(b,build,m,code,p,'before')
b.upload(0x343FB000,1024,'cycle-trace.bin')
subprocess.run([sys.executable,str(root/'firmware/capture-raw/cycle_trace.py'),str(out/'reads/cycle-trace.bin'),'--header',str(build/'cycle_trace_events.h'),'--header',str(build/'cycle_trace_sd.h'),'--require-complete','--out',str(out/'cycle-trace.json')],check=True)
