from pathlib import Path
import concurrent.futures,json,subprocess,sys
root=Path(__file__).resolve().parents[3]
out=Path(__file__).resolve().parent
common='--flash --sensor-single-frame --error-blinks --ethernet-powerdown --magic-format --line-stream --async-stop --transport idma --sd-bus-width 4 --sd-clock-hz 25000000 --sd-gpio-speed 3 --sd-clock-negedge --sd-clock-negedge-init --sd-review-profile --sd-startup-opt'.split()
def run(pair):
 name,args=pair
 r=subprocess.run([sys.executable,str(root/'firmware/capture-raw/build.py'),'--out',str(out/name),*common,*args],cwd=root,capture_output=True,text=True)
 (out/(name+'-build.log')).write_text(r.stdout+r.stderr)
 result=dict(name=name,returncode=r.returncode,tail=r.stderr[-1600:] if r.returncode else '')
 if not r.returncode:
  m=json.loads((out/name/'manifest.json').read_text());p=json.loads((out/name/'staged/manifest.json').read_text())
  result.update(receiver=m['binary_sha256'],prefix=p['stage1_raw_sha256'],sector=p['program_sha256'],bytes=m['binary_bytes'])
 return result
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
 results=list(pool.map(run,[('flash-awake-v3',[]),('flash-standby-v1',['--standby'])]))
(out/'candidate-build-results.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps(results,indent=2))
if any(r['returncode'] for r in results):raise SystemExit(1)
