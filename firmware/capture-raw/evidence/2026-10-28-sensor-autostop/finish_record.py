"""Record completed campaign evidence; no instrument imports or commands."""
from pathlib import Path
import hashlib,json
H=Path(__file__).resolve().parent
def read(p): return json.loads((H/p).read_text(encoding='utf-8-sig'))
def bind(p):
    f=H/p
    return dict(path=p,sha256=hashlib.sha256(f.read_bytes()).hexdigest())
trace=read('control-after/trace/result.json')
assert trace['success'] and not trace['errors'] and not trace['cleanup_errors']
for p in ('ram-readback/readback-validation.json','ram-auto02-readback/readback-validation.json'):
    v=read(p)
    assert v['passed'] and v['original_sensor_frame_comparison'] and v['source_reference_comparison']['bytes_equal']
header=read('before-final-headers/summary.json')
assert header['passed'] and header['slots'][0]['slot']==140 and header['slots'][0]['header']['state']=='FREE'
checks=read('design/final-build-results.json')
assert all(q.get('equal',True) and q.get('returncode',0)==0 for q in checks)
record=dict(schema=1,completed=True,normal_unchanged=True,nor_programming=False,
    active_helpers=False,logger_closed_utc=trace['utc'],
    target_state='Powered after unchanged normal cold boot, low-current plateau; not RAM diagnostic or recovery park.',
    final_state_scope='Ten phase markers and current signature only; final image and SBF not reread.',
    final_plateau_mA=8.560202,final_plateau_V=4.994354,
    sensor_autostop_installed=False,cold_sensor_autostop_qualified=False,
    expected_final_slot=140,expected_final_slot_was_free=True,final_slot_readback=False,
    verified_sensor_slots=[138,139],full_original_frame_equality=True,
    visual_checks='Root inspected both recovered PNGs: dim but recognizable patterned screen, ceiling and beams.',
    uart_recovery='Exact unchanged normal prefix/park passed after each RAM test/readback; COM8 closed and BREAK released.',
    settings='JS output left enabled; range128, stream and EXTIO settings restored without cleanup errors.',
    hardware='Direct bench5V through JS to CN5.5, common return CN5.6; CN8/LTC disconnected, no CN9 shunts; CN10 separately powered, D2/R23 removed, U24 fitted. CN15 JS markers21/33 and ground20. Twisted SD CLK/GND CN3.3/8, VCC CN3.5. No resistor or SD signal probes. Camera/SD connected; normal boot jumpers.',
    normal_receiver_sha256='69c5a5c0cc434eb7496371d9e5b9c007db346b8bb7b9a1a650c90f0eade79d28',
    normal_prefix_sha256='2b9724bc4b60af52b1c4ab45e1b232578e9640efc3a30a57772a810d99c3f344',
    normal_sector_sha256='a10e4894d79cd3fe182b95b48eb56a308280f3201736d295860ecfe725a62645',
    nor_identity_scope='No programming occurred; exact prefix reread at recovery, normal artifacts rebuilt identically. Complete physical NOR was not reread in this task.',
    evidence=[bind(p) for p in ('control-after/trace/result.json','analysis/control-after-qualified-analysis.json',
        'before-final-normal/park/result.json','before-final-headers/summary.json',
        'ram-readback/readback-validation.json','ram-auto02-readback/readback-validation.json',
        'design/final-build-results.json')])
with (H/'final-state.json').open('x',encoding='utf-8') as f: json.dump(record,f,indent=2);f.write('\n')
print(json.dumps(record,indent=2))
