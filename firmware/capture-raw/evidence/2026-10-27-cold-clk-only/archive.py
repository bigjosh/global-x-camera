"""Offline integrity and numeric replay. Never opens an instrument or network."""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile

HERE=Path(__file__).resolve().parent
ROOT=next(p for p in HERE.parents if (p/'NOTES.md').is_file() and (p/'firmware').is_dir())
EXCLUDED={'archive-index.json','SHA256SUMS'}


def sha(data):return hashlib.sha256(data).hexdigest()
def read(path):return json.loads(Path(path).read_text())
def need(ok,message):
    if not ok:raise ValueError(message)


def module(name):
    path=HERE/'host-source'/name
    spec=importlib.util.spec_from_file_location(path.stem,path)
    item=importlib.util.module_from_spec(spec);spec.loader.exec_module(item);return item


def files():
    return {p.relative_to(HERE).as_posix():{'bytes':p.stat().st_size,'sha256':sha(p.read_bytes())}
        for p in sorted(HERE.rglob('*')) if p.is_file() and
        p.relative_to(HERE).as_posix() not in EXCLUDED and '__pycache__' not in p.parts}


def verify():
    index=read(HERE/'archive-index.json')
    need(index['files']==files(),'Archive contents differ from index')
    for item in read(HERE/'compression.json')['traces']:
        packed=(HERE/item['path']).read_bytes();raw=gzip.decompress(packed)
        need(len(packed)==item['compressed_bytes'] and sha(packed)==item['compressed_sha256'],'Compressed trace differs')
        need(len(raw)==item['original_bytes'] and sha(raw)==item['original_sha256'],'Decompressed trace differs')
        need(json.loads(raw.splitlines()[-1])['event']=='stopped','Trace is incomplete')
    for item in read(HERE/'sealed-reference-bindings.json')['files']:
        raw=(ROOT/item['path']).read_bytes()
        need(len(raw)==item['bytes'] and sha(raw)==item['sha256'],'External sealed reference differs: '+item['path'])
    need((HERE/'reports/clk-only03-header-comparison.bin').read_bytes()==
         (HERE/'attempts/clk-only03/observation/reads/magic-slots.bin').read_bytes()[64:576],
         'Retained slot io offset differs')
    return dict(passed=True,sealed=index['sealed'],files=len(index['files']),hardware_access=False)


def replay():
    stats=module('summarize_current.py');pulses=module('analyze_led_current.py');model=module('analyze_reads.py')
    results=[]
    with tempfile.TemporaryDirectory(prefix='cold-clk-replay-') as directory:
        for name in ('clk-only01','clk-only02','clk-only03','both01'):
            trace=Path(directory)/(name+'.jsonl')
            trace.write_bytes(gzip.decompress((HERE/'traces'/f'{name}-current.jsonl.gz').read_bytes()))
            observer=HERE/'attempts'/name/'observation/observation.json'
            actual=stats.summarize(trace,observer)
            expected=read(HERE/'reports'/f'{name}-current-summary.json')
            for key in ('post_on_current_A','post_on_js_input_voltage_V','total_nonfinite_current_samples',
                        'whole_session_valid','observer_debug_reads','cleanup_errors','device_context_closed'):
                need(actual[key]==expected[key],f'{name} summary mismatch: {key}')
            result=dict(attempt=name,summary_replayed=True)
            if name in ('clk-only02','clk-only03'):
                pattern=pulses.analyze(trace,actual['power_on']['utc'],4)
                saved=read(HERE/'reports'/f'{name}-current-pattern.json')
                for key in ('complete_pattern_observed','checks','timing_consistency','measured','low_current_plateau'):
                    need(pattern[key]==saved[key],f'{name} pattern mismatch: {key}')
                result['pattern_replayed']=True
            if name=='both01':
                signature=module('summarize_signature.py').analyze(trace)
                saved=read(HERE/'reports/both01-current-signature.json')
                for key,value in signature.items():
                    if key!='trace':need(value==saved[key],'Both-probe current signature mismatch: '+key)
                result['signature_replayed']=True
            results.append(result)
    header=(HERE/'reports/clk-only03-header-comparison.bin').read_bytes()
    reference=(HERE/'reference/verified-lba0.bin').read_bytes()
    actual=model.model_report(reference,header)
    saved=read(HERE/'reports/clk-only03-header-comparison.json')
    for key,value in actual.items():need(value==saved[key],'Header model mismatch: '+key)
    warm=HERE/'attempts/warm-pio25-01/read'
    diagnostic=read(warm/'read-diagnostics.json');proof=read(warm/'proof.json')
    need((warm/'read-buffer.bin').read_bytes()==header,'Warm and cold failure bytes differ')
    need(header==(HERE/'reference/prior-bad-k8.bin').read_bytes(),'Prior k8 failure differs')
    need(diagnostic['diagnostics']['sta']==2 and diagnostic['diagnostics']['dcount']==0 and
         diagnostic['diagnostics']['mode']==0 and diagnostic['diagnostics']['lba']==0 and
         diagnostic['diagnostics']['count']==1 and diagnostic['camera']['held']==1 and
         diagnostic['camera']['c_ospeed']&0xFF3==0xFF3 and diagnostic['camera']['e_ospeed']&0x300==0x300 and
         diagnostic['card']['written_sectors']==0 and diagnostic['card']['cleanup_error']==10 and
         diagnostic['card']['clock_hz']==25000000 and diagnostic['operation_result']==1038 and
         diagnostic['attribution']['immutable_code_equal'] and diagnostic['attribution']['final_proof_equal'] and
         diagnostic['attribution']['cfsr']==diagnostic['attribution']['hfsr']==0,'Warm failure attribution differs')
    final=read(HERE/'recovery/before-cmd-park/result.json')
    need(final['passed'] and final['vcp_status']['good_pulses']==9 and final['vcp_status']['bad_pulses']==0,
         'Final recovery park differs')
    both=HERE/'attempts/both-warm-pio25-01/read'
    both_proof=read(both/'verified.json');both_diag=read(both/'read-diagnostics.json')
    need(both_proof['passed'] and (both/'sectors.bin').read_bytes()==reference and
        both_diag['operation_result']==0 and both_diag['card']['error']==0 and
        both_diag['card']['cleanup_error']==0 and both_diag['card']['written_sectors']==0 and
        both_diag['camera']['held']==1 and both_diag['attribution']['immutable_code_equal'] and
        both_diag['attribution']['binary_sha256']==diagnostic['attribution']['binary_sha256'],
        'Both-probe same-binary warm reference pass differs')
    return dict(passed=True,hardware_access=False,current_replays=results,
        header_model_k=actual['fitted_k'],warm_cold_header_identical=True,
        prior_k8_header_identical=True,pre_comparison_park_verified=True,both_probe_warm_read_passed=True,
        limitations='Replays saved bytes, not physical hardware or analog causes; failures remain failures.')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['seal','verify','replay'])
    a=p.parse_args()
    if a.action=='seal':
        replayed=replay();data=files()
        index=dict(schema=1,sealed=True,created_utc=datetime.now(timezone.utc).isoformat(),
            hardware_access=False,files=data)
        (HERE/'archive-index.json').write_text(json.dumps(index,indent=2)+'\n')
        (HERE/'SHA256SUMS').write_text(''.join(f'{v["sha256"]}  {k}\n' for k,v in data.items()))
        result=dict(integrity=verify(),replay=replayed)
    elif a.action=='verify':result=verify()
    else:result=replay()
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
