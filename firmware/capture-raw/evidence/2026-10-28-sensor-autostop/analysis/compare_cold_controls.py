"""Unchanged normal cold controls bracket the warm-only experiment."""
import json
from analyze_cold import HERE,sha
rows=[]
for name in ('control-before-qualified','control-after-qualified'):
    path=HERE/(name+'-analysis.json');r=json.loads(path.read_text());ph=r['phase_windows_overlapping_not_additive']
    rows.append(dict(run=name,analysis_sha256=sha(path),
        marker_order=[q['id'] for q in r['marker_events']],
        first_strobe_ms=next(q['time_ms'] for q in r['marker_events'] if q['id']==2),
        frame_ms=next(q['time_ms'] for q in r['marker_events'] if q['id']==3),
        pre_WFI_ms=next(q['time_ms'] for q in r['marker_events'] if q['id']==10),
        low_plateau_begin_ms=r['low_plateau_100ms']['start_ms'],
        low_plateau_mA=r['low_plateau_100ms']['current_mean_mA'],
        low_plateau_input_V=r['low_plateau_100ms']['voltage_mean'],
        post5ms_energy_mJ=r['post5ms_to_plateau']['energy_mJ'],
        SD_init_ms=ph['SD_initialization']['duration_ms'],
        scan_preparation_ms=ph['SD_ready_to_first_submission']['duration_ms'],
        slot_transport_ms=ph['slot_transport']['duration_ms'],
        highest1ms_mean_mA=r['peaks_1ms'][0]['current_mean_mA']))
out=dict(rows=rows,scope='Both are unchanged normal FLASH cold controls; no automatic-stop cold test. Different card timings remain explicit. Final plateau/current and all ten GPIO markers do not prove final photo readback or fresh Standby flags.',
    limits='First5ms/inrush and native extrema remain unqualified. Times are from the >=20mA onset rule. Stable plateau endpoint has1ms-bin resolution.')
(HERE/'cold-control-summary.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
