"""Read selected experiment images using the normal RAM helper, no writes/reset."""
import json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];BASE=Path(__file__).parent
prior=BASE/'normal03/capture/verified.json'
scr=prior
records=[]
for name in ('receiver02','long01'):
    capture=BASE/name/'capture';v=json.loads((capture/'verified.json').read_text())
    out=BASE/('readback-'+name)
    with (BASE/('readback-'+name+'.log')).open('wb') as log:
        subprocess.run([sys.executable,str(ROOT/'tmp/bringup/sd-fourbit-20261024/magic_readback.py'),
            'read-slots','--build',str(BASE/'ram-normal'),'--prior',str(prior),
            '--scr-proof',str(scr),'--slot',str(v['proof']['slot']),
            '--reference',str(capture/'frame.bin'),'--reference-kind','sensor-ram',
            '--out',str(out),'--execute'],stdout=log,stderr=subprocess.STDOUT,check=True,
            creationflags=subprocess.CREATE_NO_WINDOW)
    report=json.loads((out/'readback-validation.json').read_text())
    assert report['passed'] and report['original_sensor_frame_comparison']
    assert report['source_reference_comparison']['bytes_equal'] and report['png_samples_match_read_raw']
    prior=Path(json.loads((out/'summary.json').read_text())['prior'])
    records.append({'run':name,'slot':v['proof']['slot'],'passed':True,'prior':str(prior)})
    print(json.dumps(records[-1]),flush=True)
(BASE/'selected-readbacks.json').write_text(json.dumps(records,indent=2))
