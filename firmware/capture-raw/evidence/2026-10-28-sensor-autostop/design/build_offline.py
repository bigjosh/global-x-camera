from pathlib import Path
import concurrent.futures
import hashlib
import json
import subprocess
import sys

root=Path(__file__).resolve().parents[4]
out=Path(__file__).resolve().parent
common='--ethernet-powerdown --magic-format --line-stream --async-stop --transport idma --sd-bus-width 4 --sd-clock-hz 25000000 --sd-gpio-speed 3 --sd-clock-negedge --sd-clock-negedge-init --sd-review-profile --sd-startup-opt'.split()
profiles={
 'ram-auto':['--sensor-autostop'],
 'ram-default':[],
 'flash-auto':['--flash','--standby','--error-blinks','--sensor-autostop'],
 'flash-default':['--flash','--standby','--error-blinks'],
}
def build(pair):
 name,extra=pair
 result=subprocess.run([sys.executable,str(root/'firmware/capture-raw/build.py'),'--out',str(out/name),*common,*extra],cwd=root,capture_output=True,text=True)
 (out/(name+'-build.log')).write_text(result.stdout+result.stderr)
 return {'name':name,'returncode':result.returncode,'tail':result.stderr[-2400:] if result.returncode else ''}
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
 results=list(pool.map(build,profiles.items()))
for r in results:
 if r['returncode']==0:
  m=json.loads((out/r['name']/'manifest.json').read_text())
  r.update(binary_sha256=m['binary_sha256'],binary_bytes=m['binary_bytes'],proof=m.get('sensor_autostop_proof'),late=m.get('late_load',{}).get('early_bytes'))
normal=root/'tmp/bringup/ethernet-normal-20261028/flash-candidate'
rebuilt=out/'flash-default'
if (rebuilt/'capture.bin').exists():
 for name in ('capture.bin','staged/stage1.bin','staged/capture_sector_0.bin'):
  a=(normal/name).read_bytes();b=(rebuilt/name).read_bytes()
  results.append({'comparison':name,'equal':a==b,'sha256':hashlib.sha256(b).hexdigest()})
(out/'build-results.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps(results,indent=2))
if any(r.get('returncode',0) for r in results) or any(r.get('equal') is False for r in results):raise SystemExit(1)
