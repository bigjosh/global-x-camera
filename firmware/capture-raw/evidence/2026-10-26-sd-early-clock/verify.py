"""Offline replay of frozen clock-order timings and qualification reports.

No debugger/instrument or private image access. Public verification checks
hashes, raw timestamp decoding, aggregate arithmetic, ECK1 values and the
retained source/readback reports. Image equality itself is established by the
private-byte checks performed during archiving, not recreated from hashes.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

HERE=Path(__file__).resolve().parent
RUNS=('control01','early01','control02','early02','control03','early03')


def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def require(condition,message):
    if not condition:raise ValueError(message)
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def module(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value)
    return value


def main():
    freeze=read(HERE/'FREEZE.json')
    for relative,expected in freeze['files'].items():
        path=(HERE/relative).resolve();path.relative_to(HERE)
        require(digest(path)==expected,'Frozen artifact changed: '+relative)
    analysis=module(HERE/'analyze_ab.py','early_ab_analysis')
    decoder=module(HERE/'host-source/cycle_trace.py','early_cycle_decoder')
    results=[]
    for name in RUNS:
        early=name.startswith('early');folder=HERE/'runs'/name
        build=HERE/'builds'/('early' if early else 'control')
        manifest=read(build/'manifest.json')
        require(digest(build/'capture.bin')==manifest['binary_sha256'],name+': executable hash')
        require(manifest['sd_early_run_clock'] is early and manifest['sd_clock_hz']==12500000 and
                not manifest['flash'] and not manifest['standby'],name+': unexpected experiment profile')
        for path in build.iterdir():
            if path.name in manifest['source_hashes']:
                require(digest(path)==manifest['source_hashes'][path.name],name+': frozen source hash '+path.name)
        definitions=decoder.load_definitions([build/'cycle_trace_events.h',build/'cycle_trace_sd.h'])
        decoded=decoder.decode((folder/'trace/reads/cycle-trace.bin').read_bytes(),definitions,require_complete=True)
        recorded=read(folder/'trace/cycle-trace.json')
        for kind,key in (('events','ticks'),('counters','value')):
            require({row['name']:row[key] for row in decoded[kind]}==
                    {row['name']:row[key] for row in recorded[kind]},name+': timestamp/counter replay differs')
        for key in ('init_ticks','completion_ticks','clock_hz','result','status'):
            require(decoded[key]==recorded[key],name+': trace header differs '+key)
        result=analysis.analyze_files(name,folder/'capture/verified.json',folder/'trace/cycle-trace.json')
        require(result['clock_switched_before_select'] is early,name+': observed order differs')
        results.append(result)
        capture=read(folder/'capture/verified.json');report=read(folder/'readback/readback-validation.json')
        require(capture['binary_sha256']==manifest['binary_sha256'],name+': captured executable differs')
        require(report['passed'] is True and report['slot']==capture['proof']['slot'] and
                report['full_slot_read'] is True and report['original_sensor_frame_comparison'] is True and
                report['png_samples_match_read_raw'] is True and report['bytes']==1909600 and
                report['slot_bytes']==1909760 and report['raw_sha256']==capture['frame_sha256'] and
                report['source_reference_comparison']['source']['sha256']==capture['frame_sha256'],
                name+': retained image comparison lacks original-RAM binding')
        final_read=read(folder/'readback/payload-3584/verified.json')
        require(final_read['passed'] is True and final_read['binary_sha256']==manifest['binary_sha256'] and
                final_read['proof']['operation']==3 and final_read['proof']['result']==0 and
                final_read['proof']['media_idle']==1 and
                not any(final_read['proof'][key] for key in ('initialized','controller_owned','cleanup_error','sd_error')),
                name+': final READ did not complete idle')
        park=read(folder/'recovery-park.json')
        require(park['passed'] is True and park['vcp_status']['good_pulses']==9 and
                park['vcp_status']['bad_pulses']==0,name+': exact recovery proof differs')
        if early:
            names=('magic version requested_hz csd_tran_speed csd_max_hz csd_command_count '
                   'switch_command_count select_command_count clock_before clock_after timer_before timer_after '
                   'switch_begin_cycles switch_end_cycles select_begin_cycles result').split()
            proof=dict(zip(names,struct.unpack('<16I',(folder/'raw-proofs/completed-sd-early-clock.bin').read_bytes())))
            retained=capture['card']['early_clock_proof']
            require(all(retained[k]==v for k,v in proof.items()),name+': raw ECK1 differs')
            require((proof['magic'],proof['version'],proof['requested_hz'],proof['csd_tran_speed'],proof['csd_max_hz'],
                     proof['clock_before'],proof['clock_after'],proof['timer_before'],proof['timer_after'],proof['result'])==
                    (0x314B4345,1,12500000,0x32,25000000,0x302ee,0x30006,200000,25000000,0),
                    name+': early clock encoding differs')
            require(0<proof['csd_command_count']==proof['switch_command_count'] and
                    proof['select_command_count']==proof['switch_command_count']+1,name+': command order differs')
            origin=recorded['init_ticks']
            relative=lambda value:(value-origin)&0xffffffff
            event={e['name']:relative(e['ticks']) for e in recorded['events']}
            require(event['SD_CLOCK_SWITCH_BEGIN']<=relative(proof['switch_begin_cycles'])<=
                    relative(proof['switch_end_cycles'])<=event['SD_CLOCK_SWITCH_DONE']<=
                    event['SD_SELECT_BEGIN']<=relative(proof['select_begin_cycles'])<=event['SD_SELECT_DONE'],
                    name+': ECK1 timestamps do not lie inside the matching trace phases')
    replay=analysis.summarize(results);summary=read(HERE/'summary.json')
    for key,value in replay.items():require(summary[key]==value,'Aggregate differs: '+key)
    print(json.dumps({'verified_files':len(freeze['files']),'runs':len(results),
        'source_ram_comparison_reports':6,'images_publicly_redecoded':False,
        'raw_phase_window_reduction_ms':replay['control_minus_early_median_ms']['csd_ready_to_width_begin'],
        'frame_adjusted_targeted_reduction_ms':replay['control_minus_early_median_ms'][
            'csd_ready_to_width_begin_minus_fully_nested_frame_validation'],
        'limit':'Observed RAM sequence change; raw window includes rescheduled frame validation, not whole-cycle/energy savings.'},indent=2))


if __name__=='__main__':main()
