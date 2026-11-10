"""Three root-owned cold runs using unchanged, already-qualified bench helpers."""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PY = sys.executable
PREFIX_BUILD = ROOT / 'tmp/bringup/sensor-autostop-promote-20261028/flash-standby-v1/staged'

def read(p):
    return json.loads(Path(p).read_text(encoding='utf-8-sig'))

def run(label, args, timeout=65):
    print(label, flush=True)
    with (HERE / (label+'.log')).open('x') as log:
        p = subprocess.run([PY, *map(str,args)], cwd=ROOT, stdout=log,
                           stderr=subprocess.STDOUT, timeout=timeout)
    if p.returncode:
        raise RuntimeError(f'{label} failed; inspect its preserved log')

def main():
    assert sys.argv[1:] == ['--execute']
    headers = [read(HERE / name / 'summary.json') for name in ('before-headers', 'remaining-headers')]
    free = {v['slot'] for h in headers for v in h['slots'] if v['header']['state']=='FREE'}
    allocation = read(HERE/'allocation-capture/verified.json')['proof']['slot']
    expected = [allocation+i for i in (1,2,3)]
    assert all(s in free for s in expected), (free,expected)
    results=[]
    for i, slot in enumerate(expected,1):
        tag=f'cold-normal{i:02d}'
        run(f'before-{tag}-uart', [ROOT/'tmp/bringup/sd125-negedge-20261026/uart_recover.py',HERE/f'before-{tag}-uart'])
        run(f'before-{tag}-park', [ROOT/'firmware/capture-timing/recovery_gpio/check_park.py','--build',PREFIX_BUILD,'--out',HERE/f'before-{tag}-park'])
        run(f'before-{tag}-stats', [HERE/'stats.py',f'before-{tag}-stats'])
        s=read(HERE/f'before-{tag}-stats.json')['statistics']['signals']
        ma=s['current']['avg']['value']*1000
        assert 20 < ma < 150, ma
        run(tag,[HERE/'record_startup.py','--out',HERE/tag/'trace','--mode','cold-normal','--execute',
                 '--park-proof',HERE/f'before-{tag}-park/result.json',
                 '--park-current-min-ma',ma*.7,'--park-current-max-ma',ma*1.3,
                 '--on-range',1,'--off-seconds',15,'--post-seconds',3])
        run(tag+'-analysis',[HERE/'analyze_swapped.py','--trace',HERE/tag/'trace','--out',HERE/tag/'analysis.json'])
        a=read(HERE/tag/'analysis.json')
        assert a['marker_decode']['unique_complete_train'] and len(a['marker_decode']['events'])==11
        assert a['external_exposure_mirror']['complete_envelopes']==1
        assert a['cycle']['plateau_available']
        result={'run':i,'expected_slot':slot,'post5ms_energy_mJ':a['cycle']['post5ms_to_plateau']['energy_mJ'],
                'exposure_ms':a['external_exposure_mirror']['rise_ms'],'all_11_markers':True}
        results.append(result)
        (HERE/'cycle-progress.json').write_text(json.dumps(results,indent=2)+'\n')
        print(json.dumps(result),flush=True)
    run('after-cycles-sleep',[HERE/'stats.py','after-cycles-sleep'])
    print('Three cycles complete; image readback remains.',flush=True)

if __name__=='__main__':
    main()
