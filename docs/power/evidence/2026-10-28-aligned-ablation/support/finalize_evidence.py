"""Offline final-state/qualification record. No device access."""
import json,importlib.util
from pathlib import Path
HERE=Path(__file__).parent
spec=importlib.util.spec_from_file_location('startup_final_analysis',HERE/'analyze_startup_ranges.py')
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
result,_=a.analyze(HERE/'final-normal')
(HERE/'final-normal-startup-analysis.json').write_text(json.dumps(result,indent=2)+'\n')
events=[json.loads(x) for x in (HERE/'final-normal/events.jsonl').read_text().splitlines()]
closed=events[-1];end=next(x for x in events if x['event']=='observation_end')
assert closed['success'] and not closed['cleanup_errors'] and closed['initial_settings']==closed['restored_settings']
park=json.loads((HERE/'park-after-power-sleep/result.json').read_text());assert park['passed']
state={'utc':closed['utc'],'target':'Powered after normal cold flash boot; 10 expected phase markers and low-current plateau. Not a fresh SBF/independent image-readback proof.',
       'current_mA':end['means']['current']*1000,'source_voltage_V':end['means']['voltage'],
       'normal_firmware':'tmp/bringup/error-relocate-20261026/flash-normal-v2','normal_prefix_sha256':park['prefix_sha256'],
       'nor_programmed':False,'nor_full_sector_readback_this_campaign':False,'card_erased':False,
       'marker_ids':result['marker_ids'],'restored_settings':closed['restored_settings'],
       'COM8':'closed, BREAK released; no UART stimulus on final boot',
       'bench_processes':'recorders complete; no active bench helper',
       'sleep_live_observation_passed':False,'sleep_retained_proof':'Abandoned before measured cold recovery; no proven live WFI PC or unchanged-register proof.',
       'recovery':'UART-only and warm hardware reset checks failed; measured 15s output-off + C0 on power-on passed exact early park 9 good/0 bad, then final normal cold boot.',
       'wiring':'bench5V -> JS -> CN5.5; return CN5.6; CN8/LTC disconnected; CN9 shunts absent; CN10 independently powered, D2/R23 removed; U24 fitted; twisted SD CLK/GND CN3.3/CN3.8 and main3V3 CN3.5; JS IN0 CN15.21, IN1 CN15.33, GPIO GND CN15.20',
       'qualification':'Whole recordings retain initial NaNs; native-sample scoped checks and first5ms qualification are in each analysis.'}
(HERE/'final-state.json').write_text(json.dumps(state,indent=2)+'\n')
(HERE/'sleep01/observation-unavailable.json').write_text(json.dumps({'live_observation_passed':False,
    'failed_call':'cli-18.log','error':'Unable to get core ID; AP1 unavailable',
    'external_trace_complete':True,'retained_proof_abandoned_before_cold_recovery':True,
    'restored_exact_park':'../park-after-power-sleep/result.json',
    'interpretation':'Configured diagnostic reached external hold-end marker and lower plateau; no independently read STATE3, WFI PC or unchanged-register proof. Do not promote to qualified MCU sleep saving.'},indent=2)+'\n')
print(json.dumps(state,indent=2))
