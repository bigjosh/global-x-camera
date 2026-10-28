"""Summarize completed analysis without any instrument access."""
from pathlib import Path
import json
from analyze_cold import HERE,sha
rows=[]
for name in ('ram-control','ram-auto01','ram-auto02'):
    path=HERE/(name+'-awake-analysis.json');r=json.loads(path.read_text());w=r['windows_overlapping_not_additive']
    row=dict(run=name,analysis_sha256=sha(path),binary_sha256=r['binary_sha256'],startup=r['startup'],
        frame_to_stop_JS_ms=w['frame_IRQ_to_sensor_stop_observation']['duration_ms'],
        frame_to_stop_nominal_DWT_ms=r['DWT_frame_to_stop_observation_ms'],
        whole_warm_duration_ms=w['runtime_begin_to_completion']['duration_ms'],
        whole_warm_energy_mJ=w['runtime_begin_to_completion']['energy_mJ'],
        SD_init_ms=w['SD_init']['duration_ms'],scan_preparation_ms=w['scan_prep']['duration_ms'],
        slot_transport_ms=w['slot_transport']['duration_ms'],
        external_strobe_count=None if r['external_strobe'] is None else r['external_strobe']['external_complete_pulses'])
    if rows:
        row['first_strobe_added_ms_vs_normal']=row['startup']['first_strobe_phase2_from_runtime_begin_ms']-rows[0]['startup']['first_strobe_phase2_from_runtime_begin_ms']
    rows.append(row)
out=dict(rows=rows,scope='One normal warm RAM control and two same-binary automatic-stop repeats. No automatic-stop cold boot or Standby campaign; normal FLASH is unchanged.',
    limitations=['Automatic-stop sensor standby is first observed by I2C polling, not exact physical transition.',
        'The experiment adds pre-START configuration writes/readbacks and delays first STROBE slightly; retain this cost.',
        'Whole warm runtime and energy include card variability and slot scanning, so there is no demonstrated whole-cycle speedup.',
        'All power is whole-board5V input; no sensor-only current attribution.'])
(HERE/'awake-summary.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
