"""Inspect a still-awake normal error cycle without halt; skip after shutdown."""
import sys,json,time,hashlib,struct,re
from pathlib import Path
from datetime import datetime,timezone
root=Path.cwd();base=Path(__file__).resolve().parent
sys.path.insert(0,str(root/'firmware/boot-timing'))
from nor_bench import Bench
signal=base/'normal-current.power-on.json'; trace=base/'normal-current.jsonl'
limit=time.monotonic()+40
while not signal.exists():
    if time.monotonic()>limit:raise TimeoutError('No cold boot')
    time.sleep(.05)
launch=json.loads(signal.read_text());age=(datetime.now(timezone.utc)-datetime.fromisoformat(launch['utc'])).total_seconds()
assert 0<=age<5
time.sleep(max(0,1.5-age))
rows=[]
for line in trace.read_text().splitlines():
    try:r=json.loads(line)
    except json.JSONDecodeError:continue
    if r.get('signal')=='current' and r.get('complete_bin') and r.get('nonfinite_count')==0:rows.append(r)
assert rows and time.monotonic()-rows[-1]['processed_monotonic']<.5
amps=rows[-1]['mean'];out=base/'normal-live-proof'
out.mkdir(exist_ok=False)
if amps<.02:
    (out/'observation.json').write_text(json.dumps(dict(current_A=amps,debug_reads=False,
        reason='Low-current state already reached; preserve it for warm UART/flag check.'),indent=2))
    print('Already low current; no debug reads');sys.exit(0)
assert .02<amps<.8,amps
b=Bench(out/'reads')
m=json.loads((base/'flash-normal-v2/manifest.json').read_text())
raw=b.upload(0x343FD100,384,'raw-proof.bin')
enum=(base/'flash-normal-v2/runtime.h').read_text().split(' RP_MAGIC,',1)[1].split('};',1)[0]
names=['RP_MAGIC']+re.findall(r'\bRP_[A-Z0-9_]+\b',enum)
p=dict(zip(names,struct.unpack('<96I',raw)))
scb=struct.unpack('<16I',b.upload(0xE000ED00,64,'scb.bin'))
copy=b.upload(m['error_runtime_copy']['destination'],1536,'runtime-engine.bin')
assert hashlib.sha256(copy).hexdigest()==m['error_runtime_copy']['sha256']
card=b.upload(p['RP_CARD'],p['RP_CARD_SIZE'],'card.bin')
cardwords=struct.unpack('<38I',card[48:200])
report=dict(utc=datetime.now(timezone.utc).isoformat(),current_A=amps,debug_reads=True,halt=False,
    raw_proof=p,cfsr=scb[10],hfsr=scb[11],runtime_engine_sha256=hashlib.sha256(copy).hexdigest(),
    card_error=cardwords[14],card_error_stage=cardwords[15],card_error_command=cardwords[16],
    card_error_sta=cardwords[17],cleanup_error=cardwords[26])
(out/'observation.json').write_text(json.dumps(report,indent=2))
assert scb[10:12]==(0,0),report
assert p['RP_STATE']==15 and p['RP_RESULT']!=0,report
print(json.dumps({k:report[k] for k in ('current_A','cfsr','hfsr','card_error','card_error_stage','card_error_command','card_error_sta','cleanup_error')},indent=2))
