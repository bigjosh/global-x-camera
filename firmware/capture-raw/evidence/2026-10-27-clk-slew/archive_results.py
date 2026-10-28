"""Offline CLK-only trial inspection, evidence freezing and hash verification.

Never opens an instrument, runs a subprocess, or uses a network API. Private
frame, slot, sector and PNG data are re-compared locally but are not copied.
The explicitly authorized two 512-byte sensor-pattern header excerpts are
retained separately, with the failed current read labeled untrusted.
The preliminary v1 trial is always separate from the formal *-v3 trials.
No README, NOTES entry, qualification claim, or firmware promotion is written.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import tempfile


def find_root():
    for parent in Path(__file__).resolve().parents:
        if (parent/'firmware/capture-raw').is_dir() and (parent/'AGENTS.md').is_file():
            return parent
    raise RuntimeError('Cannot locate repository root')


ROOT = find_root()
DEFAULT_SOURCE = ROOT/'tmp/bringup/sd-clk-slew-20261026'
DEFAULT_OUT = ROOT/'firmware/capture-raw/evidence/2026-10-27-clk-slew'
FRAME_BYTES, SLOT_BYTES, SECTORS = 1909600, 1909760, 3730
IDENTITY = ('sector_count','cid0','cid1','cid2','cid3')
TEXT_SUFFIXES = {'.json','.jsonl','.log','.txt'}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def digest(data):
    return hashlib.sha256(data).hexdigest()


def bound(path):
    path=Path(path).resolve()
    return dict(path=str(path),bytes=path.stat().st_size,sha256=digest(path.read_bytes()))


def write_new(path,value):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as file:
        json.dump(value,file,indent=2,allow_nan=False)
        file.write('\n')


def category(name):
    if name=='clk3-trial01':
        return 'preliminary_v1'
    if re.fullmatch(r'clk[123]-trial[0-9]+-v3',name):
        return 'formal_v3'
    raise ValueError('Uncategorized trial; do not silently merge variants: '+name)


def check_build(folder,expected_sha):
    folder=Path(folder).resolve()
    manifest=read(folder/'manifest.json')
    require(manifest['binary_sha256']==expected_sha==digest((folder/'capture.bin').read_bytes()),
            'Build binary identity differs: '+str(folder))
    for relative,expected in manifest['source_hashes'].items():
        source=(folder/relative).resolve()
        source.relative_to(folder)
        require(digest(source.read_bytes())==expected,'Frozen build input changed: '+str(source))
    fixed=dict(flash=False,standby=False,sd_bus_width=4,sd_clock_hz=25000000,
        sd_gpio_speed=3,sd_clock_negedge=True,sd_clock_negedge_init=True,
        sd_review_profile=True,sd_startup_opt=True,sd_high_speed=False,
        sd_early_run_clock=False,sd_idma_read=False,sd_fixed_compensation=False,
        sd_compensation_modified=False,raw_dma_tail_wait=False,dma_sleep=False,
        magic_format=True,line_stream=True,async_stop=True,transport='idma')
    require(all(manifest.get(key)==value and type(manifest.get(key)) is type(value)
                for key,value in fixed.items()),'Unexpected trial build profile')
    require(type(manifest.get('sd_clk_gpio_speed')) is int and
            manifest['sd_clk_gpio_speed'] in (1,2,3),'Missing explicit CLK speed')
    return manifest


def check_gpio(gpio,speed):
    require((gpio['magic'],gpio['version'],gpio['requested_speed'],gpio['clk_mask'],
             gpio['c_mask'],gpio['e_mask'],gpio['applied']) ==
            (0x314B4C43,1,speed,0x30,0xFF3,0x300,1) and
            gpio['c_configured']&0xFF3==0xFF3 and
            gpio['c_after']&0xFF3==((0xFF3&~0x30)|(speed<<4)) and
            gpio['e_after']&0x300==0x300 and
            (gpio['c_before']^gpio['c_configured'])&~0xFF3==0 and
            (gpio['c_configured']^gpio['c_after'])&~0x30==0 and
            (gpio['e_before']^gpio['e_after'])&~0x300==0,
            'CLK proof does not isolate PC2 or has wrong requested speed')


def check_proof(record,manifest,operation,identity=None):
    require(record.get('passed') is True and record['binary_sha256']==manifest['binary_sha256'],
            'Operation identity/result differs')
    p,c=record['proof'],record['card']
    request=record['request_words']
    require(len(request)==16 and request[0]==0x52535131 and request[1]==p['nonce'] and
            request[1]!=0 and request[2]==operation and not any(request[6:]),'Request/nonce differs')
    fixed=dict(magic=0x52535731,schema=1,words=96,state=3,result=0,
        terminal=0x5253444E,operation=operation,clock_hz=25000000,
        media_idle=1,initialized=0,controller_owned=0,cleanup_error=0,sd_error=0)
    require(all(p.get(key)==value for key,value in fixed.items()),'Terminal is not exact successful operation')
    require(not p['ccr']&0x30000 and record['context']['registers']['PC']==manifest['park'],
            'Terminal execution/cache context differs')
    require(c['clock_hz']==25000000 and c['media_idle']==1 and
            all(c[key]==0 for key in ('initialized','controller_owned','error','error_stage',
                'error_command','error_sta','cleanup_error','timer_owned')) and
            c['last_ready_r1']&0x1F00==0x900 and not c['last_ready_r1']&0xFDFFE008,
            'Card did not finish cleanly READY/TRAN')
    width=c['bus_width_proof']
    require(width['requested_width']==width['negotiated_width']==4 and
            width['configured_clkcr']==0x34003 and width['acmd6_accepted']==1,
            'Four-bit25MHz falling launch differs')
    check_gpio(c['clk_gpio_speed_proof'],manifest['sd_clk_gpio_speed'])
    current={key:c[key] for key in IDENTITY}
    require(identity is None or identity==current,'Card identity changed')
    if operation==1:
        require(c['written_sectors']==p['written_sectors']==SECTORS and p['frames']==1 and
                p['dma_bytes']==p['camera_ready']==FRAME_BYTES and
                not any(p[key] for key in ('errors','capture_error','canary')),
                'Capture/frame/write extent differs')
    else:
        require(p['read_lba']==request[3] and p['read_count']==request[4] and
                p['read_bytes']==request[4]*512 and c['read_sectors']==request[4] and
                not c['written_sectors'],'Read scope/counters differ')
    return current


def verify_success(folder,manifest):
    import numpy as np
    from PIL import Image
    saved=read(folder/'summary.json')
    require(saved.get('passed') is True,'Trial summary does not pass')
    capture=read(folder/'capture/verified.json')
    identity=check_proof(capture,manifest,1)
    slot=capture['proof']['slot']
    frame=(folder/'capture/frame.bin').read_bytes()
    require(len(frame)==FRAME_BYTES and digest(frame)==capture['frame_sha256'],'Original frame changed')
    parts=[]
    for offset in range(0,SECTORS,512):
        part=folder/f'readback/payload-{offset:04d}'
        record=read(part/'verified.json')
        check_proof(record,manifest,3,identity)
        count=min(512,SECTORS-offset)
        require(record['proof']['read_lba']==slot*SECTORS+offset and
                record['proof']['read_count']==count,'Incomplete or repeated read coverage')
        data=(part/'sectors.bin').read_bytes()
        require(len(data)==count*512 and digest(data)==record['read_sha256'],'Read chunk changed')
        parts.append(data)
    obj=(folder/'readback/slot.bin').read_bytes()
    require(obj==b''.join(parts)==b'GXR2'+bytes(152)+frame+b'GXRE',
            'Entire object/source frame/header/metadata/trailer comparison failed')
    require((folder/'readback/frame.bin').read_bytes()==frame,'Extracted frame differs')
    groups=np.frombuffer(frame,dtype=np.uint8).reshape(-1,5).astype(np.uint16)
    samples=np.empty((len(groups),4),dtype=np.uint16)
    for index in range(4):
        samples[:,index]=((groups[:,index]<<2)|((groups[:,4]>>(2*index))&3))<<6
    expected=samples.reshape(1364,1120)
    png=folder/'readback/scene.png'
    with Image.open(png) as image:
        require(np.array_equal(np.asarray(image),expected),'Independent PNG sample check failed')
    for key in ('capture','frame','slot_file','png','readback_validation','final_proof','fresh_final_idle'):
        item=saved[key]
        require(digest(Path(item['path']).read_bytes())==item['sha256'],'Saved summary artifact changed: '+key)
    trace=read(folder/'trace/cycle-trace.json') if (folder/'trace/cycle-trace.json').exists() else None
    read_cycles=sum(read(folder/f'readback/payload-{offset:04d}/verified.json')['card']['read_cycles']
                    for offset in range(0,SECTORS,512))
    return dict(outcome='complete_source_verified',slot=slot,card_identity=identity,
        entire_object_equal=True,object_bytes=len(obj),frame_bytes=len(frame),read_operations=8,
        png_samples_equal=True,minimum_sample=int(expected.min())>>6,
        maximum_sample=int(expected.max())>>6,source_frame_sha256=digest(frame),
        complete_slot_sha256=digest(obj),png_sha256=digest(png.read_bytes()),
        private_artifacts=[bound(folder/name) for name in
            ('capture/frame.bin','readback/frame.bin','readback/slot.bin','readback/scene.png')],
        card_write_counter_ms=capture['card']['write_cycles']/400000,
        card_read_counter_ms=read_cycles/400000,
        trace_present=trace is not None,source_summary=bound(folder/'summary.json'))


def failure_details(folder,manifest):
    failed=read(folder/'failed.json')
    require(failed.get('passed') is False and failed.get('automatic_retry') is False,
            'Failure record is ambiguous')
    snapshot_path=folder/'failure-snapshot/snapshot.json'
    snapshot=read(snapshot_path) if snapshot_path.exists() else None
    proof_path=folder/'capture/proof.json'
    proof=read(proof_path) if proof_path.exists() else None
    if snapshot and snapshot.get('binary_sha256'):
        require(snapshot['binary_sha256']==manifest['binary_sha256'],'Failure snapshot build differs')
    gpio=(snapshot or {}).get('clk_gpio_speed_proof')
    gpio_valid=None
    gpio_error=None
    if gpio:
        try:
            check_gpio(gpio,manifest['sd_clk_gpio_speed'])
            gpio_valid=True
        except (KeyError,ValueError) as error:
            # A failed attempt may stop before GPIO setup; retain it without
            # calling an incomplete configuration a qualified speed trial.
            gpio_valid=False
            gpio_error=str(error)
    terminal=(snapshot or {}).get('raw') or proof or {}
    return dict(outcome='failed_attempt',stage=failed.get('stage'),
        failure=bound(folder/'failed.json'),snapshot=bound(snapshot_path) if snapshot else None,
        captured_proof=bound(proof_path) if proof else None,
        result=terminal.get('result'),failed_operation=terminal.get('operation'),
        card=(snapshot or {}).get('card'),
        requested_gpio_proven=gpio_valid,gpio_proof_error=gpio_error,
        failure_is_not_successful_idle_permission=True,
        full_source_comparison=False)


def inspect(source):
    source=Path(source).resolve()
    trials=[]
    builds={}
    for folder in sorted(source.iterdir()):
        if not folder.is_dir() or 'trial' not in folder.name:
            continue
        group=category(folder.name)
        plan=read(folder/'plan.json')
        build=Path(plan['build']).resolve()
        manifest=check_build(build,plan['binary_sha256'])
        key=build.name
        existing=builds.get(key)
        require(existing is None or existing['binary_sha256']==manifest['binary_sha256'],
                'Build basename collision')
        builds[key]=dict(path=str(build),binary_sha256=manifest['binary_sha256'],
            manifest_sha256=digest((build/'manifest.json').read_bytes()),
            clk_gpio_speed=manifest['sd_clk_gpio_speed'])
        successful=(folder/'summary.json').exists()
        failed=(folder/'failed.json').exists()
        require(not (successful and failed),'Trial has both successful and failed summaries')
        if successful:
            result=verify_success(folder,manifest)
        elif failed:
            result=failure_details(folder,manifest)
        else:
            result=dict(outcome='incomplete_attempt',full_source_comparison=False)
        trials.append(dict(name=folder.name,group=group,clk_gpio_speed=manifest['sd_clk_gpio_speed'],
            build=key,binary_sha256=manifest['binary_sha256'],**result))
    require(trials,'No trial directories found')
    groups={}
    for group in ('preliminary_v1','formal_v3'):
        selected=[item for item in trials if item['group']==group]
        groups[group]=dict(attempts=len(selected),outcomes=dict(Counter(item['outcome'] for item in selected)),
            by_speed={str(speed):dict(Counter(item['outcome'] for item in selected
                if item['clk_gpio_speed']==speed)) for speed in (3,2,1)})
    formal_builds={item['build'] for item in trials if item['group']=='formal_v3'}
    isolation=[]
    for left_index,left in enumerate(sorted(formal_builds)):
        for right in sorted(formal_builds)[left_index+1:]:
            a=(Path(builds[left]['path'])/'capture.bin').read_bytes()
            b=(Path(builds[right]['path'])/'capture.bin').read_bytes()
            require(len(a)==len(b),'Formal executable lengths differ')
            offsets=[index for index,(x,y) in enumerate(zip(a,b)) if x!=y]
            require(len(offsets)==1 and a[offsets[0]]==builds[left]['clk_gpio_speed'] and
                    b[offsets[0]]==builds[right]['clk_gpio_speed'],
                    'Formal executables differ beyond the single CLK selector byte')
            isolation.append(dict(left=left,right=right,changed_byte_offsets=offsets,
                only_clock_selector_differs=True))
    return dict(schema=1,generated_utc=datetime.now(timezone.utc).isoformat(),source=str(source),
        groups=groups,trials=trials,builds=builds,
        formal_binary_isolation=isolation,
        preliminary_exclusion='clk3-trial01 used v1 compiler layout; excluded from formal v3 comparisons',
        all_found_attempts_terminal=all(item['outcome']!='incomplete_attempt' for item in trials),
        qualification_claim=False,analog_reflections_proven=False,automatic_retry=False,
        private_scene_pixels_published=False,full_images_published=False,
        sensor_pattern_header_excerpts='Explicitly authorized 512-byte current/historical pair when present',
        limits=['Observed writes/reads only; failures are retained, not relabeled successful.',
            'Private image bytes are re-compared locally and represented publicly by hashes.',
            'Warm RAM trials do not qualify cold flash, Standby, energy or analog timing margins.',
            'Reported card counters exclude debugger/host gaps and are not cycle energy.'])


def safe_status_binary(path):
    name=path.name.lower()
    if path.suffix.lower()!='.bin' or path.stat().st_size>4096:
        return False
    exact={'proof.bin','card.bin','clk-gpio.bin','scb.bin','cycle-trace.bin','chunks.bin','producer.bin',
        'request.bin','request-readback.bin','raw-request.bin','raw-request-readback.bin',
        'clear.bin','cleared.bin','raw-clear.bin','raw-clear-readback.bin','memory-proof.bin',
        'ccr.bin','fpccr.bin','xspi-sr.bin','ahb5rstr.bin','ahb5enr.bin'}
    sd_suffixes=('-sd-width.bin','-sd-gpio.bin','-sd-clk-gpio.bin','-sd-compensation.bin',
        '-sd-startup.bin','-sd-early-clock.bin','-sd-high-speed.bin','-sd-clock-profile.bin')
    return (name in exact or name.endswith('-proof.bin') or name.endswith('-card.bin') or
        name.startswith('proof-') or name.endswith(sd_suffixes) or name.startswith('recovery-status') or
        name.startswith('vcp-status') or name.startswith('boot-proof-') or
        name.endswith('-ccr.bin') or name.endswith('-fpccr.bin'))


def copy_exact(source,destination):
    destination.parent.mkdir(parents=True,exist_ok=True)
    require(not destination.exists(),'Refusing archive overwrite: '+str(destination))
    shutil.copyfile(source,destination)
    require(digest(source.read_bytes())==digest(destination.read_bytes()),'Copy changed bytes')


def freeze_pattern_header_comparisons(source,out):
    """Explicitly admitted 512-byte sensor-pattern excerpts, never full photos."""
    records=[]
    for comparison_path in sorted(source.glob('clk*-trial*/failed-header/comparison.json')):
        comparison=read(comparison_path)
        current_path=comparison_path.parent/'untrusted-header.bin'
        current=current_path.read_bytes()
        historical_proof=Path(comparison['historical_read_proof']).resolve()
        proof=read(historical_proof)
        historical_path=historical_proof.parent/'sectors.bin'
        original=historical_path.read_bytes()
        require(proof.get('passed') is True and proof['proof']['operation']==3 and
                proof['proof']['read_lba']==0 and proof['proof']['result']==0 and
                digest(original)==proof['read_sha256']==comparison['historical_read_sha256'],
                'Historical source read is not a complete matching LBA0 read')
        historical=original[:512]
        require(len(current)==len(historical)==512 and historical[:4]==b'GXRS' and
                digest(historical)==comparison['historical_header_sha256'] and
                digest(current)==comparison['current_header_sha256'],
                'Sensor-pattern header comparison hashes differ')
        differences=[dict(offset=index,before=before,now=now,xor=before^now)
            for index,(before,now) in enumerate(zip(historical,current)) if before!=now]
        require(differences==comparison['differences'] and len(differences)==comparison['differing_bytes'],
                'Saved header byte-difference report differs from independent comparison')
        destination=out/'pattern-header-comparison'/comparison_path.parent.parent.name
        destination.mkdir(parents=True,exist_ok=False)
        copy_exact(current_path,destination/'untrusted-current-header.bin')
        copy_exact(historical_proof,destination/'historical-read-proof.json')
        (destination/'historical-header.bin').write_bytes(historical)
        copy_exact(comparison_path,destination/'comparison.json')
        provenance=dict(historical_full_payload=bound(historical_path),
            historical_proof=bound(historical_proof),current_untrusted_header=bound(current_path),
            included_offset=0,included_length=512,full_historical_payload_hash_verified=True,
            content='Sensor-generated test pattern; explicit root-authorized small excerpt',
            current_crc_failed=True,current_data_trusted=False,differing_bytes=len(differences),
            historical_header_sha256=digest(historical),current_header_sha256=digest(current))
        write_new(destination/'provenance.json',provenance)
        records.append(dict(trial=comparison_path.parent.parent.name,
            differing_bytes=len(differences),historical_header_sha256=digest(historical),
            current_header_sha256=digest(current),current_crc_failed=True))
    write_new(out/'pattern-header-comparison/index.json',records)


def freeze(source,out,allow_incomplete=False):
    source,out=Path(source).resolve(),Path(out).resolve()
    require(not out.exists(),'Refusing existing archive destination')
    report=inspect(source)
    require(allow_incomplete or report['all_found_attempts_terminal'],
            'In-progress attempt present; freeze requires --allow-incomplete')
    out.mkdir(parents=True,exist_ok=False)
    (out/'.gitattributes').write_text('* -text\n',encoding='ascii')
    copy_exact(Path(__file__).resolve(),out/'archive_results.py')
    write_new(out/'results.json',report)
    build_names=set(report['builds'])
    for path in sorted(source.rglob('*')):
        if not path.is_file():
            continue
        rel=path.relative_to(source)
        if rel.parts[0] in build_names or '__pycache__' in rel.parts:
            continue
        if len(rel.parts)>1 and rel.parts[0].startswith(('ram-','default-normal')):
            continue
        if path.suffix.lower() in TEXT_SUFFIXES or safe_status_binary(path):
            # Every trial/recovery/failure status and log is retained; image and
            # generic memory-dump filenames are excluded by the binary allowlist.
            copy_exact(path,out/'inputs'/rel)
    for name,item in report['builds'].items():
        build=Path(item['path'])
        manifest=read(build/'manifest.json')
        paths={'manifest.json','capture.bin',*manifest['source_hashes'].keys()}
        for optional in ('capture.elf','capture.lst','capture.map','symbols.txt'):
            if (build/optional).is_file():
                paths.add(optional)
        for relative in sorted(paths):
            src=(build/relative).resolve()
            src.relative_to(build.resolve())
            copy_exact(src,out/'builds'/name/relative)
        write_new(out/'builds'/name/'identity.json',dict(binary=bound(build/'capture.bin'),
            manifest=bound(build/'manifest.json'),source_hashes=manifest['source_hashes']))
    # Freeze the orchestration and live-validation code used to obtain results.
    helper_paths=[source/name for name in ('run_trial.py','test_trial.py','snapshot_failure.py')]
    helper_paths += [ROOT/name for name in ('firmware/capture-raw/bench.py',
        'firmware/capture-raw/cycle_trace.py','tmp/bringup/sd-fourbit-20261024/magic_readback.py',
        'tmp/bringup/sd-early-clock-20261026/fresh_idle.py',
        'tmp/bringup/sd50-reviewed-20261026/read_trace.py')]
    for helper in helper_paths:
        if helper.is_file():
            copy_exact(helper,out/'tools'/helper.relative_to(ROOT))
    freeze_pattern_header_comparisons(source,out)
    seal(out)
    return verify(out)


def seal(out):
    out=Path(out).resolve()
    require((out/'results.json').is_file(),'Not a CLK evidence archive')
    hashes={str(path.relative_to(out)).replace('\\','/'):
        dict(bytes=path.stat().st_size,sha256=digest(path.read_bytes()))
        for path in sorted(out.rglob('*')) if path.is_file() and path.name!='SHA256SUMS.json'
        and '__pycache__' not in path.parts}
    target=out/'SHA256SUMS.json'
    target.write_text(json.dumps(hashes,indent=2)+'\n',encoding='utf-8')
    return dict(files=len(hashes),bytes=sum(item['bytes'] for item in hashes.values()))


def verify(out):
    out=Path(out).resolve()
    hashes=read(out/'SHA256SUMS.json')
    for relative,item in hashes.items():
        path=(out/relative).resolve()
        path.relative_to(out)
        require(path.is_file() and path.stat().st_size==item['bytes'] and
                digest(path.read_bytes())==item['sha256'],'Archive changed: '+relative)
    actual={str(path.relative_to(out)).replace('\\','/') for path in out.rglob('*') if path.is_file()
        and path.name!='SHA256SUMS.json' and '__pycache__' not in path.parts}
    require(actual==set(hashes),'Archive has unsealed files; seal after adding final documentation')
    report=read(out/'results.json')
    return dict(passed=True,files=len(hashes),bytes=sum(item['bytes'] for item in hashes.values()),
        groups=report['groups'],qualification_claim=False)


def self_test():
    require(category('clk3-trial01')=='preliminary_v1','Preliminary separation failed')
    require(category('clk2-trial03-v3')=='formal_v3','Formal classification failed')
    try:
        category('clk2-trial03')
    except ValueError:
        pass
    else:
        raise AssertionError('Unknown trial accepted')
    with tempfile.TemporaryDirectory(prefix='clk-archive-offline-') as temporary:
        out=Path(temporary)
        write_new(out/'results.json',dict(groups={}))
        (out/'status.bin').write_bytes(b'abc')
        seal(out)
        require(verify(out)['passed'],'Valid seal rejected')
        (out/'status.bin').write_bytes(b'abd')
        try:
            verify(out)
        except ValueError:
            pass
        else:
            raise AssertionError('Changed archive accepted')
        for name in ('frame.bin','slot.bin','sectors.bin','before-read.bin','scene.png','snapshots.bin'):
            path=out/name
            path.write_bytes(b'x')
            require(not safe_status_binary(path),'Private image filename admitted: '+name)
    return dict(passed=True,scope='Offline classification/checksum/privacy tests; no hardware')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='action',required=True)
    for action in ('inspect','freeze'):
        command=sub.add_parser(action)
        command.add_argument('--source',type=Path,default=DEFAULT_SOURCE)
        command.add_argument('--out',type=Path,default=DEFAULT_OUT if action=='freeze' else None)
        if action=='freeze':
            command.add_argument('--allow-incomplete',action='store_true')
    for action in ('seal','verify'):
        command=sub.add_parser(action)
        command.add_argument('--out',type=Path,default=DEFAULT_OUT)
    sub.add_parser('self-test')
    args=parser.parse_args()
    if args.action=='inspect':
        result=inspect(args.source)
        if args.out:
            write_new(args.out,result)
    elif args.action=='freeze':
        result=freeze(args.source,args.out,args.allow_incomplete)
    elif args.action=='seal':
        result=seal(args.out)
    elif args.action=='verify':
        result=verify(args.out)
    else:
        result=self_test()
    print(json.dumps(result,indent=2,allow_nan=False))


if __name__=='__main__':
    main()
