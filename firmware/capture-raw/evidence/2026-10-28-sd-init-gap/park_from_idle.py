"""Fresh successful RAM-terminal gate, then exact selected UART recovery."""
from pathlib import Path
import importlib.util,json,subprocess,sys
H=Path(__file__).resolve().parent;R=H.parents[2]
build,prior,recovery,out=[Path(x).resolve() for x in sys.argv[1:5]]
out.mkdir(exist_ok=False)
s=importlib.util.spec_from_file_location('gap_idle_bench',R/'firmware/capture-raw/bench.py')
bmod=importlib.util.module_from_spec(s);s.loader.exec_module(bmod)
p=json.loads(prior.read_text());m,code=bmod.checked_build(build,p['binary_sha256'])
b=bmod.sd.Bench(out/'idle');bmod.terminal_gate(b,build,m,code,p,'fresh')
for label,args in [('recovery',[R/'tmp/bringup/sd125-negedge-20261026/uart_recover.py',out/'recovery']),
    ('park',[R/'firmware/capture-timing/recovery_gpio/check_park.py','--build',recovery,'--out',out/'park'])]:
    with (out/(label+'.log')).open('xb') as log:
        subprocess.run([sys.executable,*map(str,args)],stdout=log,stderr=subprocess.STDOUT,
                       check=True,creationflags=subprocess.CREATE_NO_WINDOW)
print('FRESH_PARK_VERIFIED',out/'park/result.json')
