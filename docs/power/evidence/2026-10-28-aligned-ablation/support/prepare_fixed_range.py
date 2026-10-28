"""Offline copy/transform only: does not import or open instrument APIs."""
from pathlib import Path
import hashlib
import json

ROOT=Path(__file__).resolve().parents[3]
src=ROOT/'tmp/bringup/js-gpi-smoke-20261028/gpi_capture.py'
dst=Path(__file__).with_name('fixed_range_cold.py')
s=src.read_text()
def swap(old,new):
    global s
    assert s.count(old)==1,(old[:80],s.count(old))
    s=s.replace(old,new)
swap('Bounded root-owned JS110 wire test. No target writes, UART, or firmware changes.',
     'Bounded JS110 fixed-range/auto cold comparison. No debugger or firmware changes.')
swap("'s/gpi/0/!data':'gpi0','s/gpi/1/!data':'gpi1'}",
     "'s/gpi/0/!data':'gpi0','s/gpi/1/!data':'gpi1',\n         's/i/range/!data':'current_range'}")
swap("'s/gpi/0/ctrl':1,'s/gpi/1/ctrl':1}","'s/gpi/0/ctrl':1,'s/gpi/1/ctrl':1,'s/i/range/ctrl':1}")
swap("RANGE='s/i/range/select'", """RANGE='s/i/range/select'
# Official local pyjoulescope_driver record.py advertises this range stream.
# Its binding.c expands source uint4 into one uint8 per sample (not packed).
MEASUREMENT_TOPICS=(RANGE,'s/v/range/select','s/i/range/mode',
                    's/i/range/pre','s/i/range/win','s/i/range/win_sz',
                    's/i/range/post','s/i/lsb_src','s/v/lsb_src')
EXTENSIONS={'current':'.f32','voltage':'.f32','power':'.f32',
            'gpi0':'.u1','gpi1':'.u1','current_range':'.u8'}""")
swap("    ap.add_argument('--pd0-test',action='store_true')",
     "    ap.add_argument('--on-range',type=int,choices=(1,128),default=128,\n                    help='Cold-cycle ON range: 1=fixed10A, 128=auto; always restore initial range')")
swap("    if a.cycle and a.pd0_test:raise ValueError('Choose cycle or parked GPIO test')\n    if a.cycle or a.pd0_test:","    if a.cycle:")
swap("s+('.u1' if s.startswith('gpi') else '.f32')","s+EXTENSIONS[s]")
swap("                else:\n                    if data.dtype.kind!='f' or data.dtype.itemsize!=4:raise ValueError('Unexpected analog dtype')",
     "                elif s=='current_range':\n                    if data.dtype!=np.dtype('uint8'):raise ValueError('Unexpected range dtype')\n                    if len(data) and int(data.max())>15:raise ValueError('Range values exceed source uint4')\n                    payload=data.tobytes()\n                else:\n                    if data.dtype.kind!='f' or data.dtype.itemsize!=4:raise ValueError('Unexpected analog dtype')")
swap("                else:\n                    good=data[np.isfinite(data)]", """                elif s=='current_range':
                    row['encoding']='source uint4 expanded by binding to uint8; one byte per sample'
                    row['delivered_samples']=len(data)
                    row['value_counts']={str(int(v)):int(n) for v,n in zip(*np.unique(data,return_counts=True))}
                else:
                    good=data[np.isfinite(data)]""")
swap('initial={};changed=[];subs=[];cleanup=[];success=False',
     'initial={};restored={};changed=[];subs=[];cleanup=[];success=False')
swap('for t in [RANGE,*SETTINGS]:initial[t]=dev.query(t,timeout=5)',
     'for t in dict.fromkeys([*MEASUREMENT_TOPICS,*SETTINGS]):initial[t]=dev.query(t,timeout=5)')
swap("event('opened',driver=__version__,initial=initial,", "event('opened',driver=__version__,initial=initial,on_range=a.on_range,")
swap("                        dev.publish(RANGE,128,timeout=5)\n                        if dev.query(RANGE,timeout=5)!=128:raise RuntimeError('ON readback failed')\n                        event('power_on');on=time.monotonic()",
     "                        dev.publish(RANGE,a.on_range,timeout=5)\n                        if dev.query(RANGE,timeout=5)!=a.on_range:raise RuntimeError('ON readback failed')\n                        event('power_on',on_range=a.on_range);on=time.monotonic()")
a=s.index('                    elif a.pd0_test:')
b=s.index('                    else:time.sleep(1)',a)
s=s[:a]+s[b:]
swap('                    for t in subs:', """                    for t,value in initial.items():
                        try:
                            restored[t]=dev.query(t,timeout=5)
                            if restored[t]!=value:raise RuntimeError('Final setting differs from original')
                        except Exception as ex:cleanup.append([t,repr(ex)])
                    for t in subs:""")
swap('initial_settings=initial,counts=count,bytes=offsets,',
     'initial_settings=initial,restored_settings=restored,on_range=a.on_range,counts=count,bytes=offsets,')
swap("scope='Wire/cycle observation only; no independent SD readback or Standby flag proof'",
     "scope='Range comparison only; source-side voltage, no independent SD readback or Standby flag proof; fixed10A resolution and startup accuracy remain unqualified'")
assert 'pd0_test' not in s and 'nor_bench' not in s
compile(s,str(dst),'exec')
dst.write_text(s)
Path(__file__).with_name('fixed_range_cold-source.json').write_text(json.dumps({
    'base':str(src.relative_to(ROOT)),'base_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),
    'new_sha256':hashlib.sha256(dst.read_bytes()).hexdigest(),
    'hardware_access':False,'transform':'Added selectable ON range, uint8 current-range stream, measurement setting snapshots/final equality; removed parked GPIO test.'},indent=2)+'\n')
print(dst)
