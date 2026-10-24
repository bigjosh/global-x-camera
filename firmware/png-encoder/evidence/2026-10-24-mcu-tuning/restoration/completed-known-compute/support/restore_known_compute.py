"""One root-owned known-compute restoration, allowing unexplained initial draw.

Offline plan by default. The execute path first reads the completed nonce/report,
then verifies exact live code and high parked context using the reviewed adapter.
Only afterward may it acquire JS110, record six fresh finite 5 V samples
without classifying initial current as normal, and issue one off/auto cycle. It never sends
SD, NOR, UART or reset commands. Quiet current/phase intent do not prove a saved
image or physical Standby. An error never retries the cycle; clean JS ownership
release restores its original auto range, which can re-enable power after error.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
ADAPTER=HERE/'mve_pair_o2_run.py'
ADAPTER_SHA='9c96a7c4f1a2d903d816dda3ea23020259643118d2160d9a47310f86c7f56463'
BUILD=HERE/'mve-pair-noinline-o2-owned-01'
MODULE_SHA='eb59e3b724bdff4e361179aeb7b24c540594afcd0ec838895f817e7cf0616543'
SECTOR_SHA='8129f9cc79e92c678207b4aee838810cc805d0b860c40b2f77b434ae746c8b61'
PREFIX_SHA='247f27c231e0053b7024af29914c6a0cb1b7decb1632ac0d6142a68b89e2da58'
COLD=ROOT/'tmp/bringup/sd-baseline-20261023/phase_cold_cycle.py'
COLD_SHA='1a22bcde2e0b2a4dca9ed0257aa73967ae86f258d827aa0d2609fe94b90aea65'
JS=ROOT/'firmware/boot-timing/js110_session.py'
PINNED={JS:'6dcce357d16987b0628303405d5a41d09d5db13f3439f64f5738e842ab4f5cf0',
    ROOT/'firmware/capture-sd/phase_markers/capture.py':'1d3aa2c9701c1f541ec8ef9f9cac44a3f894ccb174213aaa2dad3289b9abe09a',
    ROOT/'firmware/capture-sd/phase_markers/decode.py':'44329fa2df7e8005d6f66374443fe8cfbb75f7092b68d96da017f41e4a44352e'}

def sha_file(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def dump(path,value):Path(path).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def load(path,name,digest):
    if sha_file(path)!=digest:raise ValueError('Reviewed support changed: '+str(path))
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

def checked_run(folder,adapter):
    """Bind the final successful mode-3 invocation; no target access here."""
    folder=Path(folder).resolve()
    aggregate=read(folder/'verified.json');plan=read(folder/'plan.json')
    exact=dict(compute_only=True,hardware_access=True,module_sha256=MODULE_SHA,
        nor_unchanged_by_design=True,sd_commands_sent=False,mve_candidate=True,
        adapter_sha256=ADAPTER_SHA,normalization_checked_after_C=True,
        cpacr_restored_each_invocation=True,final_exact_park='0x3432003c')
    if any(aggregate.get(k)!=v for k,v in exact.items()):raise ValueError('Unqualified final compute aggregate')
    results=aggregate.get('results')
    if not isinstance(results,list) or not results or aggregate.get('runs')!=len(results):
        raise ValueError('Missing completed compute results')
    identity=plan.get('recovery_identity',{})
    if (plan.get('execute') is not True or plan.get('module_sha256')!=MODULE_SHA or
        plan.get('adapter_sha256')!=ADAPTER_SHA or identity.get('sector_sha256')!=SECTOR_SHA or
        identity.get('prefix_sha256')!=PREFIX_SHA):raise ValueError('Compute plan identity differs')
    last=results[-1]
    if (last.get('module_sha256')!=MODULE_SHA or any(last.get(k) is not False for k in
        ('sd_commands','nor_commands','reset_sent','power_changed'))):
        raise ValueError('Final invocation has unknown hardware scope')
    words=last.get('request_words')
    if (not isinstance(words,list) or len(words)!=16 or any(type(x) is not int or not 0<=x<2**32 for x in words)
        or words[0]!=adapter.p.MAGIC or words[1]!=1 or words[2]!=2 or not words[3] or words[4]!=3
        or any(words[8:])):raise ValueError('Final trial must be the exact mode-3 RUN request')
    request=struct.pack('<16I',*words)
    adapter.p.validate(last['report'],request)
    repeat=last.get('repeat')
    if type(repeat) is not int or not 1<=repeat<=10:raise ValueError('Invalid final trial repeat')
    trial=folder/f'mode-3-run-{repeat:02d}'
    if read(trial/'verified.json')!=last:raise ValueError('Final invocation proof differs from aggregate')
    if (trial/'request.bin').read_bytes()!=request or (trial/'completed-request.bin').read_bytes()!=request:
        raise ValueError('Saved final request/nonce differs')
    return dict(aggregate_sha256=sha_file(folder/'verified.json'),plan_sha256=sha_file(folder/'plan.json'),
        trial_sha256=sha_file(trial/'verified.json'),trial_path=str(trial),request=request,last=last)

def fresh_compute(b,adapter,code,bound):
    """No halt before fresh DONE/nonce equality; no target writes at any point."""
    request=bound['request'];expected=bound['last']['report']
    report=adapter.p.decode(b.upload(adapter.p.REPORT,512,'fresh-report.bin'))
    adapter.p.validate(report,request)
    if report!=expected:raise ValueError('Live compute proof differs from last verified invocation')
    if b.upload(adapter.p.REQUEST,64,'fresh-request.bin')!=request:raise ValueError('Live request/nonce differs')
    context=adapter.exact_code_context(b,code,adapter.LOAD+0x3c,'fresh-compute')
    if context['cpacr']!=report['reserved7']:raise ValueError('Live CPACR differs from restored proof')
    # A separate CLI connection may resume, but exact branch-to-self remains safe.
    if adapter.p.decode(b.upload(adapter.p.REPORT,512,'confirmed-report.bin'))!=report:
        raise ValueError('Completed proof changed during live verification')
    if b.upload(adapter.p.REQUEST,64,'confirmed-request.bin')!=request:
        raise ValueError('Request changed during live verification')
    return dict(start_kind='compute-completed',live_code_sha256=hashlib.sha256(code).hexdigest(),
        nonce=report['nonce'],mode=3,report=report,context=context,
        verified_monotonic_ns=time.monotonic_ns(),no_storage_commands=True,
        scope='Fresh exact PNB1 completion and high park; installed NOR identity is separately owner-attested')

def perform_cycle(owner,phase,proof,*,fresh,clock=time.monotonic,sleep=time.sleep):
    if proof.get('start_kind')!='compute-completed':raise ValueError('Only compute-completed start accepted')
    def sample():return fresh(owner.latest(),int(clock()*1e9))
    def recent():
        if not 0<=int(clock()*1e9)-proof['verified_monotonic_ns']<60_000_000_000:
            raise RuntimeError('Live completed-compute verification expired; no power switch')
    recent()
    initial=[];seen=None;deadline=clock()+6
    while clock()<deadline:
        s=sample()
        if s['sequence']!=seen:
            seen=s['sequence']
            # Exclusive known-compute recovery: current is evidence, not an idle
            # qualification. Fresh exact PNB1/code/context supplies the safe-start
            # condition; the unexpected current's cause remains unestablished.
            initial.append(s)
            if len(initial)>=6:break
        sleep(.1)
    if len(initial)<6:raise RuntimeError('Six fresh finite known-compute samples absent; no power switch')
    recent()
    owner.log('compute_completed_start',statistics=initial,nonce=proof['nonce'],start_kind='compute-completed',
        initial_current_is_normal_claim=False,high_current_cause_established=False,
        policy='Only fresh exact completed compute state permits this one-shot restoration; initial current has no idle range gate')
    owner.command('off');off_at=clock();off=[];seen=None
    while clock()-off_at<15:
        s=sample()
        if s['sequence']!=seen:
            seen=s['sequence']
            if clock()-off_at>=1:off=off+[s] if abs(s['current']['avg'])<.0001 else []
        sleep(.1)
    if len(off)<3 or abs(sample()['current']['avg'])>=.0001:
        raise RuntimeError('Off-current baseline absent; no explicit auto/retry; clean stop restores range128')
    owner.log('off_baseline',off_seconds=clock()-off_at,statistics=off[-3:])
    phase.start_wait();sample()
    owner.command('auto');on_at=clock();active=False;terminal=[];seen=None
    while clock()-on_at<12:
        s=sample()
        if s['sequence']!=seen:
            seen=s['sequence'];active=active or s['current']['avg']>.03
            terminal=terminal+[s] if active and clock()-on_at>3 and .006<s['current']['avg']<.012 else []
            if len(terminal)>=6:
                owner.log('terminal_current_signature',statistics=terminal,
                    elapsed_after_on_command_s=clock()-on_at,terminal_state_qualified=False)
                return dict(final_statistics=terminal[-1],terminal_statistics=terminal,
                    elapsed_after_on_command_s=clock()-on_at,active_signature_observed=True,
                    terminal_state_qualified=False,image_integrity_verified=False,sbf_verified=False)
        sleep(.1)
    raise RuntimeError('No active-then-quiet signature; leave powered and never retry')

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--compute-run',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--owner-confirmed',action='store_true')
    ap.add_argument('--probes-confirmed',action='store_true')
    ap.add_argument('--installed-v66c-unchanged',action='store_true')
    ap.add_argument('--execute',action='store_true')
    a=ap.parse_args();out=a.out.resolve();recording=out/'recording'
    if not out.is_relative_to(ROOT/'tmp'):ap.error('Output must remain below repo/tmp')
    command=[sys.executable,str(JS),'--control',str(recording/'control.json'),
        '--response',str(recording/'response.json'),'--log',str(recording/'session.jsonl'),
        '--cycle-raw-dir',str(recording/'raw'),'--raw-max-mib','2048',
        '--raw-queue-chunks','1024','--duration','60']
    if not a.execute:
        print(json.dumps(dict(plan_only=True,start_kind='compute-completed',module_sha256=MODULE_SHA,
            compute_run=str(a.compute_run),command=command,off_seconds=15,phase_seconds=10,
            before_power='Fresh final mode3 PNB1/nonce, exact high park/code/cache/context via pinned MVE adapter',
            limits='One cycle/no retry; no SD/NOR/UART/reset; no image or SBF qualification; preserve Logic2 and JS range128'),indent=2))
        return 0
    if not (a.owner_confirmed and a.probes_confirmed and a.installed_v66c_unchanged):
        ap.error('Execute requires exclusive owner, probes, and unchanged installed v66c attestations')
    if out.exists():ap.error('New output directory required')
    for path,digest in PINNED.items():
        if sha_file(path)!=digest:raise ValueError('Reviewed recording support changed: '+str(path))
    adapter=load(ADAPTER,'restore_reviewed_mve',ADAPTER_SHA)
    cold=load(COLD,'restore_reviewed_phase',COLD_SHA);module=cold.owner_module()
    _,code=adapter.checked_build(BUILD,MODULE_SHA)
    bound=checked_run(a.compute_run,adapter)
    out.mkdir(parents=True,exist_ok=False)
    proof=fresh_compute(adapter.sd.Bench(out/'preflight'),adapter,code,bound)
    proof.update(bench_owner='root',installed_sector_owner_attested=SECTOR_SHA,
        installed_prefix_owner_attested=PREFIX_SHA,nor_identity_read_this_run=False,
        original_compute_aggregate_sha256=bound['aggregate_sha256'],original_compute_plan_sha256=bound['plan_sha256'],
        original_final_trial_sha256=bound['trial_sha256'],original_final_trial_path=bound['trial_path'],
        adapter_sha256=ADAPTER_SHA,source_sha256=sha_file(__file__))
    dump(out/'compute-completed-start.json',proof)
    owner=module.Owner(recording,command);phase=cold.PhaseCapture(recording/'phase')
    failure=None;result=None
    try:
        owner.start()
        result=perform_cycle(owner,phase,proof,fresh=module.fresh_sample)
    except Exception as exc:
        failure=exc
        if recording.exists():owner.log('restore_error',error=str(exc),action='No retry; clean stop restores original range128')
    finally:
        # Finish raw sampling before potentially slow Saleae export.
        try:owner.stop()
        except Exception as exc:failure=failure or exc
        try:phase.finish()
        except Exception as exc:failure=failure or exc
    final=dict(success=failure is None,start_kind='compute-completed',observations=result,
        initial_current_is_normal_claim=False,high_current_cause_established=False,
        compute_start_sha256=sha_file(out/'compute-completed-start.json'),
        installed_sector_owner_attested=SECTOR_SHA,nor_identity_read_this_run=False,
        explicit_cold_cycles_attempted_at_most=1,sd_commands_sent=False,nor_commands_sent=False,
        uart_commands_sent=False,reset_commands_sent=False,logic2_left_running=True,
        terminal_state_qualified=False,image_integrity_verified=False,sbf_verified=False,
        helper_stopped_record=owner.stopped_record,error=None if failure is None else str(failure))
    raw=recording/'raw/manifest.json'
    if raw.exists():
        manifest=read(raw);final['raw_manifest_sha256']=sha_file(raw)
        final['raw_finalized']=manifest.get('finalized') is True
        status=manifest.get('status',{})
        final['raw_logging_complete']=(final['raw_finalized'] and status.get('complete') is True
            and status.get('dropped_chunks')==0 and status.get('error') is None
            and status.get('coverage',{}).get('passed') is True)
        final['raw_scope']='Logging/received coverage only; native-window finiteness and energy require separate analysis'
        if not final['raw_logging_complete']:
            failure=failure or RuntimeError('Raw logging/coverage incomplete; no complete energy claim')
    else:
        failure=failure or RuntimeError('Raw manifest missing; no complete recording claim')
    if failure is None:
        try:
            decoder=load(ROOT/'firmware/capture-sd/phase_markers/decode.py','restore_phase_decoder',
                PINNED[ROOT/'firmware/capture-sd/phase_markers/decode.py'])
            decoded=decoder.summarize_folder(recording/'phase')
            dump(out/'phase-summary.json',decoded)
            final['phase_decode_passed']=decoded['decode_passed']
            final['phase_summary_sha256']=sha_file(out/'phase-summary.json')
        except Exception as exc:failure=exc
        # Width decoding failure is preserved, not promoted to a power/recovery retry.
    final['success']=failure is None;final['error']=None if failure is None else str(failure)
    dump(out/'result.json',final);print(json.dumps(final,indent=2))
    if failure:raise failure
    return 0

if __name__=='__main__':raise SystemExit(main())
