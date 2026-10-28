"""Read completed isolated-run files only; no hardware imports/actions."""
from pathlib import Path
import json, struct
from analyze_isolated import analyze, HERE, CAMPAIGN

reports=[]; excluded=[]; pending=[]
proofs={p.parents[1].name:p for p in sorted(list(CAMPAIGN.glob('*/resume/completed-proof.bin'))+list(CAMPAIGN.glob('*/operation/completed-proof.bin')))}
for p in CAMPAIGN.glob('*/reobserve/completed-proof.bin'):
    if (p.parent/'verified.json').exists(): proofs[p.parents[1].name]=p
for proof in sorted(proofs.values()):
    run=proof.parents[1]
    w=struct.unpack('<256I',proof.read_bytes())
    if w[3]!=8 or w[4]!=0:
        excluded.append(dict(run=run.name, version=w[1], state=w[3], error=w[4], reason='Diagnostic refused/failed; no successful bounded comparison.'))
        continue
    if not (run/'trace/result.json').exists() or not (proof.parent/'verified.json').exists():
        pending.append(run.name);continue
    manifest=CAMPAIGN/f'probe-v{w[1]}'/'manifest.json'
    reports.append(analyze(run,proof,manifest))

result=dict(runs=reports,excluded=excluded,pending=pending)
(HERE/'isolated-summary.json').write_text(json.dumps(result,indent=2)+'\n')
lines=['Isolated Nucleo results: warm RAM probes; camera and SD disconnected.','',
       'Run | MHz nominal | flags | DBG_SLEEP active | busy mA | sleep mA | reduction mA | busy ms | sleep ms']
for r in reports:
    p=r['proof'];v=r['intervals']
    lines.append(f"{r['run']} | {p.get('CPU_HZ',400000000)/1e6:g} | {p['FLAGS']} | {p['DBG_ACTIVE']&1} | {v['busy_middle']['current_mean_mA']:.6f} | {v['sleep_middle']['current_mean_mA']:.6f} | {r['reduction']['current_mA']:.6f} | {v['busy_full']['duration_ms']:.6f} | {v['sleep_full']['duration_ms']:.6f}")
lines += ['', 'All reported means use native sample windows with25ms trimmed from both ends.',
          'Busy=LFSR/SRAM workload; sleep includes100Hz timer wakes. Not a capture-cycle energy comparison.',
          'Only exact successful proof + binary readback + complete native streams qualify a row.',
          'Excluded: '+json.dumps(excluded), 'Pending: '+json.dumps(pending)]
(HERE/'isolated-summary.txt').write_text('\n'.join(lines)+'\n')
print('\n'.join(lines))
