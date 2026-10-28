"""Offline matched-time comparison; no instruments or firmware imports."""
from pathlib import Path
import json
from analyze_cold import HERE,CAMPAIGN,FS,load,metrics,sha

rows=[]
for name in ('ram-control','ram-auto01','ram-auto02'):
    if not (HERE/(name+'-awake-analysis.json')).exists():continue
    path=HERE/(name+'-awake-analysis.json');r=json.loads(path.read_text())
    m={q['id']:q for q in r['markers']};signals,checks=load(CAMPAIGN/name/'trace')
    frame=m[3]['sample_id'];start=frame+3*FS//1000;end=frame+35*FS//1000
    assert m[5]['sample_id']<start<end<m[6]['sample_id']
    # The automatic stop has been observed before the comparison begins; the
    # normal STOP acknowledgment is after it ends. These are observations,
    # not assertions that normal sensor activity remains constant throughout.
    stop=r['mapped_proof_events']['camera_stop']['sample_id_inferred']
    assert (stop<start) if name.startswith('ram-auto') else (stop>end)
    row=dict(run=name,analysis_sha256=sha(path),window=metrics(signals,start,end,frame),
        window_scope='Same 32ms of external time, FRAME+3ms through FRAME+35ms, inside SD scan/preparation in both runs.',
        whole_warm=r['windows_overlapping_not_additive']['runtime_begin_to_completion'])
    rows.append(row)
a=rows[0]
comparisons=[dict(run=b['run'],metrics={key:dict(normal=a['window'][key],autostop=b['window'][key],
    normal_minus_autostop=a['window'][key]-b['window'][key]) for key in ('current_mean_mA','energy_mJ')}) for b in rows[1:]]
result=dict(runs=rows,comparisons=comparisons,
    qualification='One normal warm control and recorded automatic-stop repeats. This matches elapsed time and SD phase, reducing duration bias. It measures the combined effect of autonomous sensor stop and associated firmware changes on whole-board input; it is not isolated sensor-rail power, and concurrent per-sector card behavior is not controlled.',
    source_sha256=sha(Path(__file__)))
(HERE/'awake-matched-window-comparison.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result['comparisons'],indent=2))
