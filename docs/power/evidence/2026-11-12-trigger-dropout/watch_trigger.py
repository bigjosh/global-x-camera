"""Passive JS observation with bounded, non-resetting ST-LINK reads on current rise."""
from pathlib import Path
import collections, datetime, hashlib, json, queue, struct, subprocess, sys, threading, time
ROOT=Path.cwd()
sys.path.insert(0,str(ROOT/'tmp/bringup/joulescope-deps'))
import numpy as np
from pyjoulescope_driver import Driver
OUT=Path(__file__).resolve().parent/sys.argv[1]
OUT.mkdir(exist_ok=False)
PARK=len(sys.argv)>2 and sys.argv[2]=='park'
CLI=ROOT/'tmp/bringup/control-smoke-20261107/tools/programmer-2.23.0/bin/STM32_Programmer_CLI.exe'
DEVICE='u/js110/000163'
SETTINGS={'h/fs':2000000,'s/i/ctrl':1,'s/v/ctrl':1}
q=queue.Queue(256); rise=threading.Event(); errors=[]; detected={}; calls=[]

def stamp():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def save(name,value):(OUT/name).write_text(json.dumps(value,indent=2)+'\n')
def cb(topic,value):
    try:
        a=np.array(value['data'],copy=True)
        signal='current' if '/s/i/' in topic else 'voltage'
        assert a.dtype==np.float32 and value['sample_rate']==2000000 and value['decimate_factor']==1
        sid=int(value['sample_id']); finite=np.isfinite(a)
        if signal=='current' and not rise.is_set():
            hits=np.flatnonzero(finite & (a>.02))
            if len(hits)>20:
                detected.update(utc=stamp(),monotonic=time.monotonic(),sample_id=sid+int(hits[0]))
                rise.set()
        # Store 100us mean/min/max bins; this is not an inrush peak qualification.
        n=len(a)//200
        if n:
            b=a[:n*200].reshape(n,200)
            with np.errstate(invalid='ignore'):
                rows=np.column_stack((sid+np.arange(n,dtype=np.int64)*200,
                    np.nanmean(b,axis=1),np.nanmin(b,axis=1),np.nanmax(b,axis=1),
                    np.count_nonzero(~np.isfinite(b),axis=1)))
            q.put_nowait((signal,time.monotonic(),rows))
    except Exception as e:errors.append(repr(e))

def debugger():
    # Wait for a user-generated rise, then only read SRAM/GPIO/fault registers.
    if not rise.wait(1800):return
    for attempt in range(3):
        p=OUT/f'debug{attempt+1:02}';p.mkdir()
        argv=[str(CLI),'-c','port=SWD','mode=HOTPLUG','ap=1','sn=002100203335511035383531',
              '-u','0x343F3000','4224',str(p/'stage1-sensor.bin'),
              '-u','0x343F9000','64',str(p/'usb-selector.bin'),
              '-u','0x56020000','24',str(p/'gpioa.bin'),
              '-u','0xE000ED28','24',str(p/'faults.bin')]
        if PARK:
            argv.extend(['-u','0x34180400','7160',str(p/'prefix.bin'),'-coreReg'])
        record=dict(utc=stamp(),monotonic=time.monotonic(),argv=argv)
        try:
            r=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                timeout=3,creationflags=subprocess.CREATE_NO_WINDOW)
            (p/'cli.log').write_bytes(r.stdout);record['returncode']=r.returncode
        except subprocess.TimeoutExpired as e:
            (p/'cli.log').write_bytes(e.stdout or b'');record['timeout']=True
        calls.append(record);save('debug-calls.json',calls)
        if (p/'stage1-sensor.bin').exists():
            raw=(p/'stage1-sensor.bin').read_bytes()
            if len(raw)==4224:
                save('snapshot.json',dict(stage1=list(struct.unpack('<53I',raw[:212])),
                    sensor=list(struct.unpack('<32I',raw[4096:4224])),attempt=attempt+1))
                break
        time.sleep(.05)

thread=threading.Thread(target=debugger,daemon=True);thread.start()
ring=collections.deque(); recorded={'current':[],'voltage':[]}; initial={};final={}
start=time.monotonic();ready=False;last_report=start
try:
    with Driver() as driver:
        with driver.open(DEVICE,mode='restore',timeout=5) as dev:
            initial={k:dev.query(k,timeout=5) for k in ('s/i/range/select',*SETTINGS)}
            assert initial['s/i/range/select']!=0,'JS output is off; no power change authorized by this recorder'
            save('initial.json',dict(utc=stamp(),settings=initial,power_changed=False))
            topics=[DEVICE+'/s/i/!data',DEVICE+'/s/v/!data']
            try:
                for t in topics:driver.subscribe(t,'pub',cb)
                for k,v in SETTINGS.items():dev.publish(k,v,timeout=5)
                while time.monotonic()-start<1790:
                    assert not errors,errors
                    try:signal,when,rows=q.get(timeout=.25)
                    except queue.Empty:
                        if time.monotonic()-start>5 and not ready:raise RuntimeError('No current/voltage samples')
                        continue
                    if not ready:
                        ready=True;print('ARMED: passive power recording; press trigger once.',flush=True)
                    if rise.is_set():
                        if not recorded['current'] and not recorded['voltage']:
                            for rs,rw,rr in ring:recorded[rs].append(rr)
                            ring.clear();save('rise.json',detected)
                            print('Current rise detected; reading boot/error records without reset.',flush=True)
                        recorded[signal].append(rows)
                        if time.monotonic()-detected['monotonic']>15:break
                    else:
                        ring.append((signal,when,rows))
                        while ring and when-ring[0][1]>.5:ring.popleft()
                    if time.monotonic()-last_report>30:
                        print('Waiting for trigger' if not rise.is_set() else 'Recording cycle',flush=True)
                        last_report=time.monotonic()
            finally:
                for k in reversed(SETTINGS):dev.publish(k,initial[k],timeout=5)
                for t in topics:driver.unsubscribe(t,cb)
                final={k:dev.query(k,timeout=5) for k in initial}
                assert final==initial
finally:
    thread.join(10 if rise.is_set() else 0)
    for s,rows in recorded.items():
        if rows:np.save(OUT/(s+'-100us.npy'),np.concatenate(rows))
    save('result.json',dict(utc=stamp(),rise=detected,initial=initial,final=final,
        errors=errors,power_changed=False,halt=False,reset=False,target_writes=False,
        columns=['native_sample_id','mean','min','max','nonfinite_samples'],sample_rate=2000000,
        bin_samples=200,voltage_boundary='JS input, before trigger circuit'))
    print(json.dumps(dict(finished=True,rise_detected=rise.is_set(),directory=str(OUT),errors=errors)),flush=True)
