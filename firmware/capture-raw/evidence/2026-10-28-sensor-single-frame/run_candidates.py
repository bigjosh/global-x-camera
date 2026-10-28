"""Root-owned bounded cold qualification; each next cycle needs fresh exact park.
Stop on any logger, phase, exposure, plateau or recovery failure. No retries.
"""
from pathlib import Path
import importlib.util,json,subprocess,sys
H=Path(__file__).resolve().parent;R=H.parents[2]
B=H/'flash-standby-v1'
spec=importlib.util.spec_from_file_location('single_frame_cold_analysis',H/'analysis/analyze_promotion.py')
analysis=importlib.util.module_from_spec(spec);spec.loader.exec_module(analysis)
prefix=json.loads((B/'staged/manifest.json').read_text())['stage1_raw_sha256']
assert prefix=='6378483a91b560ffc6b31d74a9dd1205996a14c8030447ffddf7deddc9d23874'
def run(log,*args):
    with log.open('xb') as f:
        subprocess.run([sys.executable,*map(str,args)],cwd=R,stdout=f,stderr=subprocess.STDOUT,
            check=True,creationflags=subprocess.CREATE_NO_WINDOW)
park=H/'standby-park/result.json';reports=[json.loads((H/'analysis/control-before-analysis.json').read_text())]
for n in range(1,4):
    name=f'candidate{n:02d}';out=H/name;out.mkdir(exist_ok=False)
    run(H/(name+'.log'),R/'tmp/bringup/ethernet-normal-20261028/cold_logger.py',
        '--out',out/'trace','--cycle','--park-proof',park,'--expected-prefix-sha',prefix)
    q=analysis.analyze(dict(run=name,group='autostop',trace=str(out/'trace'),evidence=dict(build=str(B))))
    assert q['unique_marker_train'] and q['marker_precedence_pass'] and q['all_expected_markers_observed']
    assert q['single_external_exposure_envelope_observed'] and q['exposure_envelopes_end_before_frame_IRQ']
    assert q['no_external_exposure_edges_between_standby_observed_and_commit']
    assert 6<q['low_plateau_100ms']['current_mean_mA']<12
    reports.append(q);analysis.summarize(reports)
    print('COLD_PHASE_CURRENT_PASS',name,flush=True)
    run(out/'recovery.log',R/'tmp/bringup/sd125-negedge-20261026/uart_recover.py',out/'recovery')
    run(out/'park.log',R/'firmware/capture-timing/recovery_gpio/check_park.py',
        '--build',B/'staged','--out',out/'park')
    park=out/'park/result.json'
    print('EXACT_UART_PARK_PASS',name,flush=True)
print('THREE_COLD_CYCLES_AND_RECOVERIES_PASS',flush=True)
