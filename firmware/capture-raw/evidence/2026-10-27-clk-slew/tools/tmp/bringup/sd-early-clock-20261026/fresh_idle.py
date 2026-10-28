"""Read-only fresh verification of the last exact RAM terminal."""
import sys,json,importlib.util
from pathlib import Path
root=Path.cwd()
spec=importlib.util.spec_from_file_location('raw_bench',root/'firmware/capture-raw/bench.py')
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
build,prior,out=map(Path,sys.argv[1:4]);out.mkdir(parents=True,exist_ok=False)
p=json.loads(prior.read_text());m,code=mod.checked_build(build,p['binary_sha256'])
b=mod.sd.Bench(out/'reads')
context=mod.terminal_gate(b,build,m,code,p,'fresh-idle')
(out/'verified.json').write_text(json.dumps(dict(prior=str(prior),build=str(build),binary_sha256=p['binary_sha256'],context=context),indent=2)+'\n')
print('Fresh exact idle/code/context proof passed',flush=True)
