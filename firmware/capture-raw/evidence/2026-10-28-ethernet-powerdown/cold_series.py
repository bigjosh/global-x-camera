"""Root-owned bounded cold comparisons; stop on any recording/marker/park failure."""
from pathlib import Path
import hashlib,importlib.util,json,subprocess,sys
H=Path(__file__).resolve().parent;R=H.parents[2]
group,build,prior=sys.argv[1:4];build=Path(build).resolve();prior=Path(prior).resolve()
spec=importlib.util.spec_from_file_location('analysis',H/'analysis/analyze_cycles.py')
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
prefix=hashlib.sha256((build/'staged/stage1.bin').read_bytes()).hexdigest()
def run(log,*args):
    with log.open('xb') as f:
        subprocess.run([sys.executable,*map(str,args)],cwd=R,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
records=[]
for i in range(1,4):
    name=f'{group}{i:02d}';out=H/name;out.mkdir(exist_ok=False)
    run(out/'capture.log',H/'cold_logger.py','--out',out/'trace','--cycle','--park-proof',prior,'--expected-prefix-sha',prefix)
    item=dict(run=name,group=group,trace=str(out/'trace'),evidence=dict(build=str(build),prefix_sha256=prefix))
    v=a.analyze(item)
    assert v['unique_marker_train'] and v['marker_precedence_pass']
    assert 6<v['low_plateau_100ms']['current_mean_mA']<12
    # All ten normal markers + the low plateau precede the warm recovery.
    # No power switch follows until exact prefix/park is verified again.
    run(out/'recovery.log',R/'tmp/bringup/sd125-negedge-20261026/uart_recover.py',out/'recovery')
    run(out/'park.log',R/'firmware/capture-timing/recovery_gpio/check_park.py','--build',build/'staged','--out',out/'park')
    prior=out/'park/result.json';records.append(item)
    (H/(group+'-runs.json')).write_text(json.dumps(records,indent=2))
    print(json.dumps(dict(run=name,energy_post5ms_mJ=v['post5ms_to_plateau']['energy_mJ'],last_park=str(prior))),flush=True)
a.summarize([json.loads((H/'analysis'/(x['run']+'-analysis.json')).read_text()) for x in records])
