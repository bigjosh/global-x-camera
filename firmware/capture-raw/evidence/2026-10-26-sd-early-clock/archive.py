"""Freeze completed early-clock A/B records without publishing image bytes.

Offline only. Run from any directory after all six full readbacks complete.
Existing immutable data is never replaced. The separate verifier checks the
public trace/proof bundle; original camera/SD/PNG equality is checked here
against private files before recording their hashes.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
DEFAULT_SOURCE=ROOT/'tmp/bringup/sd-early-clock-20261026'
RUNS=('control01','early01','control02','early02','control03','early03')
BUILDS={'control':'ram-control-trace-v1','early':'ram-early-trace-v1'}


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def require(condition,message):
    if not condition:raise ValueError(message)
def write(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,indent=2,allow_nan=False)+'\n',encoding='utf-8',newline='\n')
def copy(source,dest):
    dest.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(source,dest)
def module(path):
    spec=importlib.util.spec_from_file_location('early_clock_summary',path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value)
    return value


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,default=DEFAULT_SOURCE)
    p.add_argument('--check-inputs',action='store_true')
    a=p.parse_args();source=a.source.resolve()
    require(not (HERE/'FREEZE.json').exists(),'Archive already frozen; do not replace it')
    analysis=module(source/'analyze_ab.py')
    results=[];inputs={};readbacks={};bindings={}
    for name in RUNS:
        folder=source/name
        results.append(analysis.analyze_files(name,folder/'capture/verified.json',folder/'trace/cycle-trace.json'))
        report=read(folder/'readback/readback-validation.json')
        capture=read(folder/'capture/verified.json')
        require(report.get('passed') is True and report.get('slot')==capture['proof']['slot'],name+': incomplete readback')
        for flag in ('full_payload_read','full_slot_read','start_magic_valid','completion_marker_valid',
                     'png_samples_match_read_raw','original_sensor_frame_comparison'):
            require(report.get(flag) is True,name+': missing '+flag)
        camera=(folder/'capture/frame.bin').read_bytes()
        raw=(folder/'readback/frame.bin').read_bytes();slot=(folder/'readback/slot.bin').read_bytes()
        require(len(camera)==1909600 and raw==camera,name+': private SD bytes differ from original camera RAM')
        require(len(slot)==1909760 and slot[:4]==b'GXR2' and slot[4:156]==bytes(152) and
                slot[156:-4]==camera and slot[-4:]==b'GXRE',name+': slot structure/source bytes differ')
        for filename,key in (('frame.bin','raw_sha256'),('slot.bin','slot_sha256'),('scene.png','png_sha256')):
            require(digest(folder/'readback'/filename)==report[key],name+': image artifact hash differs')
        require(report['source_reference_comparison']['kind']=='sensor-ram' and
                report['source_reference_comparison']['bytes_equal'] is True and
                report['source_reference_comparison']['source']['sha256']==digest(folder/'capture/frame.bin'),
                name+': original-source binding differs')
        readbacks[name]=report
        inputs[name]=folder
        bindings[name]={str(path.relative_to(source)).replace('\\','/'):digest(path) for path in (
            folder/'capture/verified.json',folder/'capture/frame.bin',folder/'trace/cycle-trace.json',
            folder/'trace/reads/cycle-trace.bin',folder/'readback/readback-validation.json',
            folder/'readback/frame.bin',folder/'readback/slot.bin',folder/'readback/scene.png')}
    groups=analysis.summarize(results)
    require(groups['groups_by_observed_clock_order']['control']['n']==3 and
            groups['groups_by_observed_clock_order']['early']['n']==3,'Expected three runs of each order')
    if a.check_inputs:
        print(json.dumps({'inputs_passed':True,'runs':list(RUNS),**groups},indent=2));return
    require(not (HERE/'runs').exists() and not (HERE/'builds').exists(),'Partial archive exists; inspect without overwriting')
    copy(source/'analyze_ab.py',HERE/'analyze_ab.py')
    summary=dict(schema=1,hardware_access=False,complete_runs=6,runs=results,**groups,
        limits=['Warm RAM trials; no cold power/Standby or new total-energy qualification.',
                'ACMD41 card-state variation and growing slot scan confound whole-cycle comparisons.',
                'The early candidate changes clock order and removes the redundant post-switch CMD13.',
                'Trace intervals are software observations at nominal 400 MHz, not physical wire edges.',
                'Original image bytes and PNGs stay private; their hashes and comparison reports are retained.'])
    write(HERE/'summary.json',summary)
    write(HERE/'private-input-bindings.json',bindings)
    for name,folder in inputs.items():
        for rel in ('capture/verified.json','trace/cycle-trace.json','trace/reads/cycle-trace.bin',
                    'readback/readback-validation.json','readback/payload-3584/verified.json'):
            copy(folder/rel,HERE/'runs'/name/rel)
        capture=read(folder/'capture/verified.json')
        require(capture['binary_sha256']==read(source/BUILDS['early' if name.startswith('early') else 'control']/'manifest.json')['binary_sha256'],
                name+': executable differs')
        proofs=folder/'capture/bootstrap'
        if not proofs.exists():proofs=folder/'capture/operation'
        for filename in ('completed-card.bin','completed-sd-startup.bin','completed-sd-width.bin'):
            copy(proofs/filename,HERE/'runs'/name/'raw-proofs'/filename)
        if name.startswith('early'):
            copy(proofs/'completed-sd-early-clock.bin',HERE/'runs'/name/'raw-proofs/completed-sd-early-clock.bin')
        park=folder/'park/result.json'
        if not park.exists() and name=='control01':park=source/'initial-park/result.json'
        copy(park,HERE/'runs'/name/'recovery-park.json')
    for label,build in BUILDS.items():
        folder=source/build;m=read(folder/'manifest.json')
        require(digest(folder/'capture.bin')==m['binary_sha256'],label+': executable hash differs')
        for filename in ('manifest.json','capture.bin','sd_card.c','sd_card.h','runtime.c','runtime.h',
                         'magic_runtime.inc','cycle_trace.h','cycle_trace_events.h','cycle_trace_sd.h'):
            copy(folder/filename,HERE/'builds'/label/filename)
    for filename in ('integration-builds.json','integration-offline-checks.json','driver-disabled-identity.json',
                     'analyzer-state.json','js-response.json'):
        copy(source/filename,HERE/filename)
    session=[json.loads(line) for line in (source/'js-session.jsonl').read_text().splitlines() if line.strip()]
    stopped=next(row for row in reversed(session) if row.get('event')=='stopped')
    require(stopped['ok'] is True and stopped['range']==128 and stopped['restore_error'] is None,
            'Joulescope session did not stop with range restored')
    write(HERE/'final-state.json',dict(
        terminal='Powered, awake at successful candidate RAM READ terminal; not Standby',
        terminal_proof='runs/early03/readback/payload-3584/verified.json',
        installed_nor_changed=False,card_erased=False,normal_cold_cycle_performed=False,
        joulescope_stopped=stopped,source_js_session_sha256=digest(source/'js-session.jsonl'),
        scope='The last current sample is awake READ-helper current, not a capture-cycle energy or Standby measurement.'))
    for filename in ('build.py','bench.py','test_sd_early_clock.py','cycle_trace.py'):
        copy(ROOT/'firmware/capture-raw'/filename,HERE/'host-source'/filename)
    copy(ROOT/'firmware/sd-storage/test_sd_early_clock.cpp',HERE/'host-source/test_sd_early_clock.cpp')
    (HERE/'.gitattributes').write_text('* -text\n',encoding='utf-8',newline='\n')
    files={str(path.relative_to(HERE)).replace('\\','/'):digest(path) for path in sorted(HERE.rglob('*'))
           if path.is_file() and path.name not in ('FREEZE.json','README.md') and '__pycache__' not in path.parts}
    write(HERE/'FREEZE.json',dict(schema=1,files=files))
    print(json.dumps({'frozen_files':len(files),'runs':6,'images_published':False,**groups},indent=2))


if __name__=='__main__':main()
