"""Record one guarded same-frame SAVE; never reset or switch target power.

Dry-run by default. Requires exclusive ownership and the already-qualified
v60c READ/cache park. The existing bench helper owns all live storage guards.
No failed SAVE is retried. Recording cleanup preserves the starting range.
"""
import argparse
from datetime import datetime,timezone
import hashlib,importlib.util,json
from pathlib import Path
import subprocess,sys,time

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
OWNER_SOURCE=HERE/'single_cycle.py'
OWNER_SHA='45919bdaa9900f228a1666f2a421ebbd3d8db8e7166de15865f2aa405f72b322'
MODULE_SHA='51c067de2859588fc87cf1249fdff4186b17a4e0ab85585c72fc9b5dc94379f5'
DEVICE='6753424D9C96677D';CHANNELS=[0,1,4,6]

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def stamp():return dict(utc=datetime.now(timezone.utc).isoformat(),monotonic_ns=time.monotonic_ns())
def put(path,value):Path(path).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf-8')

def owner_module():
    if sha(OWNER_SOURCE)!=OWNER_SHA:raise ValueError('Reviewed JS owner source changed')
    spec=importlib.util.spec_from_file_location('reviewed_save_record_owner',OWNER_SOURCE)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def run_bench(command,output):
    """A host timeout never terminates a potentially active storage operation."""
    with (output/'bench-output.txt').open('w',encoding='utf-8') as stream:
        process=subprocess.Popen(command,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        put(output/'bench-process.json',dict(pid=process.pid,command=command,**stamp()))
        try:code=process.wait(timeout=180)
        except subprocess.TimeoutExpired:
            put(output/'bench-process-timeout.json',dict(pid=process.pid,still_running=True,
                action='No kill/reset/retry; inspect existing process and target status',**stamp()))
            raise RuntimeError(f'Bench PID{process.pid} remains active; no retry or target change')
    return code

def record(owner,output,command,*,api=None,runner=run_bench,validate_owner=None):
    """The only target operation is one invocation of the guarded bench SAVE."""
    output=Path(output);phase=output/'phase';meta=dict(schema=1,requested=stamp(),
        device_id=DEVICE,enabled_digital_channels=CHANNELS,digital_sample_rate=100000000,
        enabled_analog_channels=[],capture_mode='manual',target_stimulus='one guarded RAM SAVE only',
        reset_sent=False,power_switch_sent=False,module_sha256=MODULE_SHA,
        phase_width_qualified=False,image_integrity_verified=False)
    failure=None;bench_code=None;cap=None;stopped=False
    try:
        owner.start()
        if validate_owner:validate_owner()
        phase.mkdir();(phase/'binary').mkdir()
        put(phase/'capture-config.json',meta)
        if api is None:
            sys.path.insert(0,str(ROOT/'tmp/bringup/saleae-deps'))
            from saleae import automation as api
        with api.Manager.connect(port=10430,connect_timeout_seconds=5) as manager:
            if not any(d.device_id==DEVICE and not d.is_simulation for d in manager.get_devices()):
                raise RuntimeError('Required physical Logic Pro8 missing')
            dc=api.LogicDeviceConfiguration(enabled_digital_channels=CHANNELS,
                digital_sample_rate=100000000,digital_threshold_volts=3.3,
                enabled_analog_channels=[],analog_sample_rate=None)
            cc=api.CaptureConfiguration(buffer_size_megabytes=256,capture_mode=api.ManualCaptureMode())
            with manager.start_capture(device_id=DEVICE,device_configuration=dc,capture_configuration=cc) as cap:
                meta['started']=stamp();put(phase/'capture-config.json',meta)
                try:
                    meta['bench_before']=stamp();bench_code=runner(command,output)
                    meta['bench_after']=stamp();meta['bench_returncode']=bench_code
                    if bench_code:failure=RuntimeError('Guarded SAVE failed; no retry or target change')
                except Exception as exc:failure=exc
                finally:
                    # stop() exactly once for ManualCaptureMode; never wait().
                    try:cap.stop();stopped=True;meta['stopped']=stamp()
                    except Exception as exc:failure=failure or exc;meta['capture_stop_error']=str(exc)
                    try:owner.stop()
                    except Exception as exc:failure=failure or exc;meta['owner_stop_error']=str(exc)
                    owner=None  # Never request stop twice, including failed cleanup.
                if stopped:
                    cap.save_capture(str(phase/'phase.sal'));meta['sal_saved']=stamp()
                    cap.export_raw_data_binary(str(phase/'binary'),digital_channels=CHANNELS,analog_channels=[])
                    if any(not (phase/'binary'/f'digital_{ch}.bin').is_file() for ch in CHANNELS):
                        raise RuntimeError('Requested digital export file missing')
                    meta['binary_exported']=stamp()
    except Exception as exc:failure=failure or exc
    finally:
        if owner is not None:
            try:owner.stop()
            except Exception as exc:failure=failure or exc;meta['owner_stop_error']=str(exc)
        if failure:meta['error']=dict(type=type(failure).__name__,text=str(failure))
        if phase.is_dir():put(phase/'capture-config.json',meta)
        if output.is_dir():put(output/'recording-result.json',dict(
            recording_complete=stopped and 'binary_exported' in meta and 'owner_stop_error' not in meta,
            bench_returncode=bench_code,guarded_save_process_succeeded=bench_code==0,
            phase_width_qualified=False,image_integrity_verified=False,
            reset_sent=False,power_switch_sent=False,error=str(failure) if failure else None))
    if failure:raise failure
    return meta

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--build',type=Path,default=ROOT/'tmp/bringup/sd-phase-20261023/v60c-awake/module')
    for flag in ('execute','owner-confirmed','probes-confirmed'):ap.add_argument('--'+flag,action='store_true')
    a=ap.parse_args();out=a.out.resolve();build=a.build.resolve()
    if not out.is_relative_to(ROOT/'tmp'):ap.error('Output must remain under repo/tmp')
    command=[sys.executable,str(ROOT/'firmware/capture-sd/bench.py'),'save','--build',str(build),
        '--out',str(out/'save'),'--expected-sha256',MODULE_SHA,'--mode','fast-none',
        '--sd-clock-hz','25000000','--timeout','60','--execute']
    js=[sys.executable,str(ROOT/'firmware/boot-timing/js110_session.py'),'--control',str(out/'control.json'),
        '--response',str(out/'response.json'),'--log',str(out/'session.jsonl'),
        '--cycle-raw-dir',str(out/'raw'),'--raw-max-mib','6144','--raw-queue-chunks','1024','--duration','240']
    if not a.execute:
        print(json.dumps(dict(plan_only=True,bench_command=command,js_command=js,
            capture='manual100MS/s digital0,1,4,6; stop after guarded bench returns',
            reset_sent=False,power_switch_sent=False),indent=2));return 0
    if not (a.owner_confirmed and a.probes_confirmed):ap.error('Owner/probe confirmation required')
    if out.exists():ap.error('New output directory required')
    if sha(build/'save.bin')!=MODULE_SHA:raise ValueError('Exact reviewed module required')
    manifest=json.loads((build/'manifest.json').read_bytes())
    if manifest.get('binary_sha256')!=MODULE_SHA:raise ValueError('Module manifest identity differs')
    m=owner_module();owner=m.Owner(out,js)
    record(owner,out,command,validate_owner=lambda:m.fresh_sample(owner.latest(),time.monotonic_ns()))
    raw=json.loads((out/'raw/manifest.json').read_bytes())
    if raw.get('finalized') is not True:raise RuntimeError('Raw recording not finalized')
    # Preserve the strict width result even if known overhead makes it fail.
    sys.path.insert(0,str(ROOT/'firmware/capture-sd/phase_markers'))
    from decode import summarize_folder
    decoded=summarize_folder(out/'phase',sequence='storage');put(out/'phase-summary.json',decoded)
    print(json.dumps(dict(recording_complete=True,guarded_save_process_succeeded=True,
        strict_phase_decode_passed=decoded['decode_passed'],image_integrity_verified=False,
        reset_sent=False,power_switch_sent=False),indent=2));return 0

if __name__=='__main__':raise SystemExit(main())
