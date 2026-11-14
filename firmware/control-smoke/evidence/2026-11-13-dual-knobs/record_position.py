"""Tag stable user-positioned samples from the existing monitor; no instruments."""
from pathlib import Path
from datetime import datetime, timezone
import json, statistics, sys, time

here = Path(__file__).resolve().parent
label = sys.argv[1]
if label not in ('clockwise', 'center', 'counterclockwise'):
    raise SystemExit('Unknown physical position')
out = here / ('position-' + label + '.json')
if out.exists():
    raise SystemExit('Position already recorded; retain original evidence')
after = datetime.now(timezone.utc).isoformat()
deadline = time.monotonic() + 25
selected = []
while time.monotonic() < deadline:
    samples = []
    for line in (here/'monitor01/readings.jsonl').read_text(encoding='utf-8').splitlines():
        try:
            p = json.loads(line)
        except json.JSONDecodeError:
            continue
        if p['host_utc'] >= after:
            samples.append(p)
    selected = samples
    if len(selected) >= 8:
        break
    time.sleep(.25)
if len(selected) < 8:
    raise SystemExit('Not enough fresh monitor samples; target left untouched')
assert all(p['STATE']==4 and p['ERROR_CODE']==0 and p['HOLD_IDR']==1 for p in selected)
assert all(p['SEQUENCE']==p['SEQUENCE_END'] and not(p['SEQUENCE']&1) for p in selected)
assert len({p['SAMPLE_COUNT'] for p in selected}) == len(selected)
fields = ['RAW','ASA_RAW','A0_RAW','A2_RAW','A4_RAW','exposure_position','asa_position','PAIR_CYCLES']
stats = {f:dict(median=statistics.median(p[f] for p in selected),
                mean=statistics.mean(p[f] for p in selected),
                minimum=min(p[f] for p in selected), maximum=max(p[f] for p in selected)) for f in fields}
record = dict(position=label,view='looking at knob faces',user_confirmed_position=True,
              after_utc=after,first_utc=selected[0]['host_utc'],last_utc=selected[-1]['host_utc'],
              count=len(selected),stats=stats,samples=selected)
out.write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in record.items() if k!='samples'},indent=2))
