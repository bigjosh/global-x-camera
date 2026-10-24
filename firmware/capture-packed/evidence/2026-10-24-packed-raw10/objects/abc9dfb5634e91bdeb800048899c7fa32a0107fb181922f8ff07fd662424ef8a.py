"""One root-owned return from successful RAM capture to unchanged flash boot.

Requires the already-owned JS110 mailbox. No flash/card command is sent by
this host helper. Normal firmware may save a photo after the cold boot.
"""
import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import time
import run_capture as r

HERE = Path(__file__).resolve().parent
BASE = HERE/'bench'


def latest():
    lines=(BASE/'js-session.jsonl').read_text().splitlines()
    for line in reversed(lines):
        item=json.loads(line)
        if item['event']=='statistics':
            s=item['statistics']
            if not 0 <= time.monotonic_ns()-s['received']['monotonic_ns'] < 2_000_000_000:
                raise RuntimeError('Joulescope statistics stale')
            if not all(math.isfinite(s[k]['avg']) for k in ('voltage','current','power')):
                raise RuntimeError('Nonfinite Joulescope statistics')
            if not 4.5<s['voltage']['avg']<5.5:
                raise RuntimeError('Supply not in the known 5 V range')
            return s
    raise RuntimeError('No live statistics')


def command(state):
    token='raw10-final-'+state+'-'+str(time.monotonic_ns())
    request=BASE/'js-request.tmp'
    request.write_text(json.dumps(dict(id=token,state=state)))
    request.replace(BASE/'js-control.json')
    end=time.monotonic()+8
    while time.monotonic()<end:
        result=json.loads((BASE/'js-response.json').read_text())
        if result.get('id')==token:
            if result.get('error') or result.get('ok') is False or result.get('restore_error'):
                raise RuntimeError(result)
            if state=='stop':
                if result.get('event')!='stopped':
                    time.sleep(.1)
                    continue
                if (result.get('ok') is not True or result.get('range')!=128
                        or result.get('starting_range')!=128):
                    raise RuntimeError('Joulescope settings restoration not confirmed: '+str(result))
            return result
        time.sleep(.1)
    raise TimeoutError('No power-command acknowledgement; do not retry')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--execute',action='store_true')
    a=p.parse_args()
    build=HERE/'experiment/opaque8-diagonal-v4'
    m,code=r.checked_build(build,'353c65c029601408c738677188362029b35fea7c02f9fcdb1514562334dc74c8')
    prior=json.loads((BASE/'packed-pattern02/verified.json').read_text())
    if not a.execute:
        print('Offline restoration inputs validated; no hardware accessed')
        return
    b=r.sd.Bench(BASE/'restore-normal')
    proof=r.decode(b.upload(r.PROOF,160,'capture-proof.bin'))
    assert proof==prior['proof']
    r.validate(proof,m,proof['nonce'])
    assert b.upload(r.LOAD,m['immutable_bytes'],'capture-code.bin')==code[:m['immutable_bytes']]
    context=r.sd.context_proof(b,{m['park']},'capture-final')
    initial=latest()
    if not .003<initial['current']['avg']<.25:
        raise RuntimeError('Unexpected starting load; no power change')
    result=dict(start_proof=proof,context=context,initial=initial,
        installed_sector_sha256='8129f9cc79e92c678207b4aee838810cc805d0b860c40b2f77b434ae746c8b61',
        installed_nor_unchanged_by_design=True,host_sd_commands=False,host_nor_commands=False,
        final_image_readback=False,final_sbf_readback=False)
    r.dump(b.output/'state.json',result)
    result['off_command']=command('off')
    began=time.monotonic()
    samples=[]
    while time.monotonic()-began<15:
        time.sleep(.5)
        s=latest()
        if not samples or s['sequence']!=samples[-1]['sequence']:
            samples.append(s)
    result['off_samples']=samples
    r.dump(b.output/'state.json',result)
    if len(samples)<3 or any(abs(s['current']['avg'])>=.0001 for s in samples[-3:]):
        raise RuntimeError('Off-current baseline absent; no explicit auto/retry')
    result['on_command']=command('auto')
    samples=[]
    for _ in range(24):
        time.sleep(.5)
        s=latest()
        if not samples or s['sequence']!=samples[-1]['sequence']:
            samples.append(s)
    result['on_samples']=samples
    result['final_statistics']=samples[-1]
    result['low_current_plateau']=len(samples)>=3 and all(.006<s['current']['avg']<.012 for s in samples[-3:])
    result['completed_utc']=datetime.now(timezone.utc).isoformat()
    r.dump(b.output/'state.json',result)
    print(json.dumps(dict(low_current_plateau=result['low_current_plateau'],final=result['final_statistics'])))
    if not result['low_current_plateau']:
        raise RuntimeError('Normal boot did not return to expected plateau; leave powered for diagnosis')
    result['stop_command']=command('stop')
    r.dump(b.output/'state.json',result)


if __name__=='__main__':
    main()
