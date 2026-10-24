"""Reversible PD12 probe test from the freshly verified v59 early park."""
import csv, json, struct, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'firmware/boot-timing'),str(ROOT/'tmp/bringup/saleae-deps')]
from nor_bench import Bench
from saleae import automation
out=Path(sys.argv[1]).resolve()
bench=Bench(out)
evidence={'storage_commands':False,'nor_writes':False,'target_reset':False}
def read(addr,count,name):
    return struct.unpack('<'+'I'*(count//4),bench.upload(addr,count,name))
en=read(0x5602825C,4,'ahb4enr.bin')[0]
rst=read(0x5602821C,4,'ahb4rstr.bin')[0]
if not en&8 or rst&8: raise RuntimeError('GPIOD not enabled/out of reset; no GPIO access')
base=0x56020C00
saved=read(base,24,'gpio-before.bin')
lock=read(base+0x1C,4,'lock.bin')[0]
if lock&(1<<16) and lock&(1<<12): raise RuntimeError('PD12 locked')
evidence.update(ahb4enr=en,ahb4rstr=rst,saved_registers=list(saved),lock=lock)
(out/'request.json').write_text(json.dumps(evidence,indent=2))
mask=1<<12; pair=3<<24
def writes(items):
    args=[]
    for offset,value in items: args+=['-w32',hex(base+offset),hex(value)]
    bench.call(*args)
configured=False
try:
    configured=True
    writes([(20,saved[5]&~mask),(4,saved[1]&~mask),(12,saved[3]&~pair),
            (8,(saved[2]&~pair)|(1<<24)),(0,(saved[0]&~pair)|(1<<24))])
    with automation.Manager.connect(port=10430,connect_timeout_seconds=5) as manager:
        if not any(d.device_id=='6753424D9C96677D' and not d.is_simulation for d in manager.get_devices()):
            raise RuntimeError('Required physical LP8 missing')
        dc=automation.LogicDeviceConfiguration(enabled_digital_channels=[0,1,4,6],digital_sample_rate=6250000,
            digital_threshold_volts=3.3,enabled_analog_channels=[1,4],analog_sample_rate=31250)
        cc=automation.CaptureConfiguration(capture_mode=automation.ManualCaptureMode())
        with manager.start_capture(device_id='6753424D9C96677D',device_configuration=dc,capture_configuration=cc) as cap:
            evidence['levels']=[]
            try:
                time.sleep(.2)
                for n in range(3):
                    for level in (1,0):
                        writes([(20,(saved[5]&~mask)|(mask if level else 0))])
                        idr=read(base+16,4,f'idr-{n}-{level}.bin')[0]
                        evidence['levels'].append({'cycle':n,'requested':level,'idr_bit':int(bool(idr&mask))})
                        if bool(idr&mask)!=bool(level): raise RuntimeError('PD12 IDR mismatch')
                        time.sleep(.15)
            finally:
                cap.stop()
                cap.save_capture(str(out/'pd12-smoke.sal'))
                cap.export_raw_data_csv(str(out),digital_channels=[0,1,4,6],analog_channels=[1,4])
finally:
    if configured:
        writes([(0,saved[0]),(4,saved[1]),(8,saved[2]),(12,saved[3]),(20,saved[5])])
        restored=read(base,24,'gpio-after.bin')
        evidence['restored_config']=all(restored[i]==saved[i] for i in (0,1,2,3,5))
        if not evidence['restored_config']: raise RuntimeError('GPIO restoration mismatch')
    (out/'result.json').write_text(json.dumps(evidence,indent=2))
print(json.dumps(evidence,indent=2))
