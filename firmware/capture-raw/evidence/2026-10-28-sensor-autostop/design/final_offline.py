from pathlib import Path
import concurrent.futures
import hashlib
import json
import subprocess
import sys

root=Path(__file__).resolve().parents[4]
out=Path(__file__).resolve().parent
common='--error-blinks --ethernet-powerdown --magic-format --line-stream --async-stop --transport idma --sd-bus-width 4 --sd-clock-hz 25000000 --sd-gpio-speed 3 --sd-clock-negedge --sd-clock-negedge-init --sd-review-profile --sd-startup-opt'.split()
profiles={'ram-auto-final':['--sensor-autostop'],'ram-default-final':[],
          'flash-default-final':['--flash','--standby']}
def build(pair):
 name,extra=pair
 r=subprocess.run([sys.executable,str(root/'firmware/capture-raw/build.py'),'--out',str(out/name),*common,*extra],cwd=root,capture_output=True,text=True)
 (out/(name+'-build.log')).write_text(r.stdout+r.stderr)
 return {'name':name,'returncode':r.returncode,'tail':r.stderr[-1600:] if r.returncode else ''}
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
 results=list(pool.map(build,profiles.items()))
comparisons=[('ram-auto-final/capture.bin',out/'ram-auto-v2/capture.bin'),
 ('ram-default-final/capture.bin',root/'tmp/bringup/ethernet-normal-20261028/ram-candidate/capture.bin')]
for name in ('capture.bin','staged/stage1.bin','staged/capture_sector_0.bin'):
 comparisons.append(('flash-default-final/'+name,root/'tmp/bringup/ethernet-normal-20261028/flash-candidate'/name))
for name,reference in comparisons:
 path=out/name
 if path.exists():
  data=path.read_bytes()
  results.append({'comparison':name,'reference':str(reference),'equal':data==reference.read_bytes(),
                  'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
(out/'final-build-results.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps(results,indent=2))
if any(r.get('returncode',0) for r in results) or any(r.get('equal') is False for r in results):raise SystemExit(1)
