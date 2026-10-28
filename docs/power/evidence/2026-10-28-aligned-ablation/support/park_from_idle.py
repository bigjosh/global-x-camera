import sys,json,importlib.util,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
build,prior,out=[Path(x).resolve() for x in sys.argv[1:4]];out.mkdir(exist_ok=False)
sys.path.insert(0,str(ROOT/'firmware/capture-raw'))
spec=importlib.util.spec_from_file_location('park_idle_bench',ROOT/'firmware/capture-raw/bench.py')
bmod=importlib.util.module_from_spec(spec);spec.loader.exec_module(bmod)
p=json.loads(prior.read_text());m,code=bmod.checked_build(build,p['binary_sha256'])
b=bmod.sd.Bench(out/'idle');bmod.terminal_gate(b,build,m,code,p,'fresh')
for label,args in [('recovery',[ROOT/'tmp/bringup/sd125-negedge-20261026/uart_recover.py',out/'recovery']),
    ('park',[ROOT/'firmware/capture-timing/recovery_gpio/check_park.py','--build',
      ROOT/'tmp/bringup/error-relocate-20261026/flash-normal-v2/staged','--out',out/'park'])]:
    with (out/(label+'.log')).open('wb') as log:
        subprocess.run([sys.executable,*map(str,args)],stdout=log,stderr=subprocess.STDOUT,
                       check=True,creationflags=subprocess.CREATE_NO_WINDOW)
print('FRESH_PARK_VERIFIED',out/'park/result.json')
