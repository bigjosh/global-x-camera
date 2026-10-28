"""Bounded root-owned JS110 wire test. No target writes, UART, or firmware changes.

One optional cold cycle requires a fresh exact UART-park proof. Native analog
samples and packed digital bytes are retained without inventing padding bits.
All modified device settings are restored, including starting power range.
"""
import argparse, hashlib, json, queue, sys, threading, time
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tmp/bringup/joulescope-deps'))
import numpy as np
from pyjoulescope_driver import Driver, __version__

DEVICE='u/js110/000163'
STREAMS={'s/i/!data':'current','s/v/!data':'voltage','s/p/!data':'power',
         's/gpi/0/!data':'gpi0','s/gpi/1/!data':'gpi1'}
SETTINGS={'h/fs':2000000,'s/extio/voltage':3300,'s/i/lsb_src':2,'s/v/lsb_src':3,
          's/i/ctrl':1,'s/v/ctrl':1,'s/p/ctrl':1,'s/gpi/0/ctrl':1,'s/gpi/1/ctrl':1}
RANGE='s/i/range/select'
def stamp():return {'utc':datetime.now(timezone.utc).isoformat(),'monotonic':time.monotonic()}
def clean(x):
    if isinstance(x,np.generic):return x.item()
    if isinstance(x,dict):return {k:clean(v) for k,v in x.items()}
    if isinstance(x,(list,tuple)):return [clean(v) for v in x]
    return x

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--park-proof',type=Path);ap.add_argument('--cycle',action='store_true')
    ap.add_argument('--pd0-test',action='store_true')
    a=ap.parse_args();out=a.out.resolve();out.relative_to(ROOT/'tmp')
    if a.cycle and a.pd0_test:raise ValueError('Choose cycle or parked GPIO test')
    if a.cycle or a.pd0_test:
        if not a.park_proof:raise ValueError('Exact fresh park proof required')
        p=json.loads(a.park_proof.read_bytes())
        if not (p.get('passed') and p['context']['PC']==0x3418078C and
                p['prefix_sha256']=='99dbb0f9ecdd56a9313e4e62bbbfec22ec8e5e5901c852d956315844cd066eba'
                and 0<=time.time()-a.park_proof.stat().st_mtime<600):
            raise ValueError('Park proof identity/freshness failed')
    out.mkdir(parents=True,exist_ok=False)
    q=queue.Queue(1024);errors=[];latest={};recent=[];lock=threading.Lock()
    chunks=(out/'chunks.jsonl').open('x',encoding='utf-8');events=(out/'events.jsonl').open('x',encoding='utf-8')
    files={s:(out/(s+('.u1' if s.startswith('gpi') else '.f32'))).open('xb') for s in STREAMS.values()}
    offsets={s:0 for s in files};hashes={s:hashlib.sha256() for s in files};count={s:0 for s in files}
    def event(name,**kw):
        row=dict(event=name,**stamp(),**clean(kw));events.write(json.dumps(row,allow_nan=False)+'\n');events.flush()
        print(json.dumps(row,allow_nan=False),flush=True)
    def callback(topic,value):
        try:
            val=dict(value);val['data']=np.array(value['data'],copy=True)
            q.put_nowait((topic.removeprefix(DEVICE+'/'),val,time.monotonic()))
        except Exception as ex:errors.append('callback: '+repr(ex))
    def worker():
        try:
            while True:
                item=q.get()
                if item is None:break
                topic,val,received=item;s=STREAMS[topic];data=val.pop('data')
                if s.startswith('gpi'):
                    if data.dtype!=np.dtype('uint8'):raise ValueError('Unexpected GPI dtype')
                    payload=data.tobytes()
                else:
                    if data.dtype.kind!='f' or data.dtype.itemsize!=4:raise ValueError('Unexpected analog dtype')
                    payload=data.astype('<f4',copy=False).tobytes()
                if sum(offsets.values())+len(payload)>768*1024**2:raise RuntimeError('Raw byte budget exceeded')
                row=dict(signal=s,byte_offset=offsets[s],byte_count=len(payload),dtype=str(data.dtype),
                         received_monotonic=received,**clean(val))
                if s.startswith('gpi'):row['packed_bits']='little; terminal padding unresolved until next sample_id'
                else:
                    good=data[np.isfinite(data)];row['nonfinite']=int(len(data)-len(good))
                    row['mean']=float(np.mean(good,dtype=np.float64)) if len(good) else None
                    row['min']=float(np.min(good)) if len(good) else None
                    row['max']=float(np.max(good)) if len(good) else None
                if files[s].write(payload)!=len(payload):raise OSError('Short sample write')
                offsets[s]+=len(payload);hashes[s].update(payload);count[s]+=1
                chunks.write(json.dumps(row,allow_nan=False)+'\n')
                with lock:
                    latest[s]=row
                    if s=='current':recent.append(row);del recent[:-30]
        except Exception as ex:errors.append('worker: '+repr(ex))
    thread=threading.Thread(target=worker);thread.start()
    initial={};changed=[];subs=[];cleanup=[];success=False
    try:
        with Driver() as d:
            if DEVICE not in d.device_paths():raise RuntimeError('JS110 absent')
            with d.open(DEVICE,mode='restore',timeout=5) as dev:
                try:
                    for t in [RANGE,*SETTINGS]:initial[t]=dev.query(t,timeout=5)
                    if initial[RANGE]!=128:raise RuntimeError('Expected starting auto range')
                    event('opened',driver=__version__,initial=initial,
                          boundary='regulated bench5V -> JS110 -> CN5.5; GPIO IN0 PD12, IN1 PD0')
                    for t in STREAMS:
                        d.subscribe(DEVICE+'/'+t,'pub',callback);subs.append(DEVICE+'/'+t)
                    for t,v in SETTINGS.items():
                        if initial[t]!=v:
                            changed.append(t);dev.publish(t,v,timeout=5)
                            if dev.query(t,timeout=5)!=v:raise RuntimeError('Setting mismatch '+t)
                    def observations():
                        if errors:raise RuntimeError(str(errors))
                        with lock:r=dict(latest)
                        for s in STREAMS.values():
                            x=r.get(s,{})
                            if not x.get('byte_count') or time.monotonic()-x['received_monotonic']>1:
                                raise RuntimeError('Missing/stale stream '+s)
                        for s in ('current','voltage'):
                            x=r.get(s,{})
                            if x.get('mean') is None or time.monotonic()-x['received_monotonic']>1 or x['nonfinite']:
                                raise RuntimeError('Missing/stale/nonfinite '+s)
                        if not 4.5<r['voltage']['mean']<5.5:raise RuntimeError('Source outside 5V range')
                        return r
                    start=time.monotonic()
                    while time.monotonic()-start<2:time.sleep(.05)
                    r=observations()
                    event('ready',means={s:r[s].get('mean') for s in r},counts=count)
                    if a.cycle:
                        if not .025<r['current']['mean']<.25:raise RuntimeError('Expected awake park current')
                        changed.append(RANGE);dev.publish(RANGE,0,timeout=5)
                        if dev.query(RANGE,timeout=5)!=0:raise RuntimeError('OFF readback failed')
                        off=time.monotonic();event('power_off')
                        while time.monotonic()-off<15:observations();time.sleep(.1)
                        with lock:tail=list(recent)[-10:]
                        if len(tail)<10 or any(x['nonfinite'] or x['mean'] is None or abs(x['mean'])>=.0001 for x in tail):
                            raise RuntimeError('No verified off-current interval')
                        event('off_verified',mean_a=tail[-1]['mean'],seconds=time.monotonic()-off)
                        dev.publish(RANGE,128,timeout=5)
                        if dev.query(RANGE,timeout=5)!=128:raise RuntimeError('ON readback failed')
                        event('power_on');on=time.monotonic()
                        while time.monotonic()-on<6:observations();time.sleep(.05)
                    elif a.pd0_test:
                        import struct
                        sys.path.insert(0,str(ROOT/'firmware/boot-timing'))
                        from nor_bench import Bench
                        b=Bench(out/'gpio-access')
                        en=struct.unpack('<I',b.upload(0x5602825C,4,'ahb4enr.bin'))[0]
                        if not en&8:raise RuntimeError('GPIOD clock disabled; no GPIO access')
                        before=struct.unpack('<6I',b.upload(0x56020C00,24,'gpio-before.bin'))
                        if before[0]&3!=1 or before[1]&1 or not before[5]&1:
                            raise RuntimeError('Expected PD0 push-pull output HIGH in exact park')
                        states=[]
                        try:
                            for n,level in enumerate([0,1,0,1,0,1]):
                                event('pd0_command_begin',index=n,level=level)
                                # CLI verifies writes; BSRR is write-only. Use the
                                # readable ODR with the core halted at exact park,
                                # preserving every unowned output bit.
                                b.call('-halt','-w32','0x56020C14',hex((before[5]&~1)|level))
                                words=struct.unpack('<6I',b.upload(0x56020C00,24,f'gpio-{n}.bin'))
                                if words[:4]!=before[:4] or (words[5]&~1)!=(before[5]&~1):
                                    raise RuntimeError('Unexpected GPIO configuration change')
                                if words[4]&1!=level or words[5]&1!=level:
                                    raise RuntimeError('PD0 did not take requested level')
                                states.append(level);event('pd0_level_verified',index=n,level=level)
                                time.sleep(.08)
                        finally:
                            b.call('-halt','-w32','0x56020C14',hex(before[5]))
                            after=struct.unpack('<6I',b.upload(0x56020C00,24,'gpio-restored.bin'))
                            if after[:4]!=before[:4] or after[5]!=before[5]:
                                raise RuntimeError('PD0 restoration failed')
                        event('pd0_test_complete',levels=states,original_output_restored=True)
                        time.sleep(.5)
                    else:time.sleep(1)
                    event('observation_end',means={s:v.get('mean') for s,v in observations().items()},counts=count)
                    success=True
                finally:
                    for t in reversed(changed):
                        try:
                            if t==RANGE and dev.query(t,timeout=5)!=initial[t]:
                                event('cleanup_power_restore',value=initial[t],qualified_cycle=False,
                                      note='Restoring starting power can boot target after an aborted OFF hold')
                            dev.publish(t,initial[t],timeout=5)
                            if dev.query(t,timeout=5)!=initial[t]:raise RuntimeError('Restore mismatch')
                        except Exception as ex:cleanup.append([t,repr(ex)])
                    for t in subs:
                        try:d.unsubscribe(t,callback)
                        except Exception as ex:cleanup.append([t,repr(ex)])
    except Exception as ex:
        errors.append(repr(ex));event('error',error=repr(ex))
    finally:
        if thread.is_alive():
            try:q.put(None,timeout=3)
            except queue.Full:errors.append('Writer stop sentinel could not be queued')
        thread.join(timeout=10)
        if thread.is_alive():raise RuntimeError('Writer did not stop; files retained, no claimed completion')
        for f in files.values():f.close()
        chunks.close()
        result=dict(success=success and not errors and not cleanup,**stamp(),errors=errors,cleanup_errors=cleanup,
                    initial_settings=initial,counts=count,bytes=offsets,
                    sha256={s:h.hexdigest() for s,h in hashes.items()},
                    scope='Wire/cycle observation only; no independent SD readback or Standby flag proof')
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
        event('closed',**{k:v for k,v in result.items() if k not in ('utc','monotonic')});events.close()
    return 0 if result['success'] else 1
if __name__=='__main__':raise SystemExit(main())
