"""Replay magic-slot experiment from stored bytes; no device or bench imports."""
import argparse
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import types
import zlib

HERE=Path(__file__).resolve().parent
PREERASE_SHA='133940809052ac17f367340b6fce4237f3d6ca2ebeb2324ab694f3453bc42c49'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def js(raw):return json.loads(raw)
def req(ok,text):
    if not ok:raise ValueError(text)
def base_module():
    p=HERE/'support/preerase_replay.py';req(sha(p.read_bytes())==PREERASE_SHA,'Pinned group replay changed')
    s=importlib.util.spec_from_file_location('magic_group_replay',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);m.HERE=HERE;return m
def checked_name(name):return base_module().checked_name(name)
def read_object(item):return base_module().read_object(item)
def file_bytes(record):return base_module().file_bytes(record)

def selected_functions(raw,names,namespace):
    tree=ast.parse(raw);nodes=[node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name in names]
    req({node.name for node in nodes}==set(names),'Offline pure validator selection changed')
    # Deliberately excludes all imports, top-level initialization and runners.
    exec(compile(ast.Module(body=nodes,type_ignores=[]),'<archived-pure-validators>','exec'),namespace)

def magic_validators(core,index):
    b=dict(struct=struct,LOAD=0x34300000,FRAME=0x34000000,FRAME_BYTES=1909600,
        MAGIC_FRAME=0x34000010,MAGIC_BUFFER=0x3400000C,SLOT_BYTES=1909760,
        READ_MAX=262144,READ_BUFFER=0x34200000,MAGIC=0x52535731,DONE=0x5253444E,
        OPS={'capture':1,'format':2,'read':3})
    selected_functions(core.read_object(index['tools']['bench.py']),
        ['frame_layout','whole_layout','magic_layout','capture_geometry','frame_guards',
         'request','validate','magic_snapshot','card_snapshot'],b)
    f=dict(struct=struct,bench=types.SimpleNamespace(**b))
    selected_functions(core.read_object(index['tools']['inspect_flash.py']),['validate_proof','validate_loader'],f)
    return b,f


def magic_parser(core,index):
    # Extraction CLI imports a neighboring codec by filesystem path. Replay
    # needs only these pure format functions, with the reviewed fixed geometry.
    ns=dict(FormatError=ValueError,SECTOR=512,STRIDE=3730,IMAGE_OFFSET=4,
        IMAGE_BYTES=1909600,TRAILER_OFFSET=1909604,PADDED_BYTES=1909760,
        START_MAGIC=b'GXRS',END_MAGIC=b'GXRE')
    selected_functions(core.read_object(index['tools']['magic_slots.py']),['parse_probe','parse_slot'],ns)
    return types.SimpleNamespace(**ns)

class StoredReads:
    def __init__(self,files,prefix):self.files=files;self.prefix=prefix
    def upload(self,address,count,name):
        raw=self.files[self.prefix+name];req(len(raw)==count,'Stored SRAM read extent differs: '+name);return raw

def magic_terminal(v,files,prefix,builds,b,f):
    name,m,code=builds[v['binary_sha256']];p=v['proof'];flash=v.get('kind')=='raw-flash-inspection'
    req(v.get('passed') is True,'Missing successful terminal')
    subs=['inspection/'] if flash else ['operation/','bootstrap/']
    key='proof-final.bin' if flash else 'final-proof.bin'
    hits=[prefix+sub for sub in subs if prefix+sub+key in files]
    req(len(hits)==1,'Ambiguous exact terminal binary');sub=hits[0]
    req(files[sub+key]==struct.pack('<96I',*p.values()),'Terminal JSON differs from SRAM bytes')
    if flash:
        req(m['flash'] and not m['standby'],'Expected awake FLASH inspection')
        f['validate_proof'](p,m)
        f['validate_loader'](files[sub+'late-loader.bin'],m)
        for i,(start,end) in enumerate(m['immutable_ranges']):
            req(files[sub+f'code-{i}.bin']==code[start-m['load']:end-m['load']],'Flash immutable code differs')
        label='before'
    else:
        b['validate'](p,m,v['request_words'])
        req(files[sub+'executable-readback.bin']==code and
            files[sub+'completed-code.bin']==code[:m['immutable_bytes']],'RAM executable differs')
        req(files[sub+'raw-request-readback.bin']==struct.pack('<16I',*v['request_words']),'RAM request differs')
        label='completed'
    reads=StoredReads(files,sub);card=b['card_snapshot'](reads,m,p,label)
    req(card==v['card'],'Card JSON differs from SRAM bytes')
    snapshot=b['magic_snapshot'](reads,m,p,label,card)
    req(snapshot==v['slots' if flash else 'magic_format'],'Magic JSON differs from SRAM bytes')
    if p['operation']==1:
        req(b['frame_guards'](reads,m,p)==v['whole_image'],'Magic guard JSON differs from SRAM bytes')
    return dict(build=name,operation=p['operation'],slot=p['slot'],slot_count=p['slot_count'],magic_format=True)

def privacy(index,records,binary_validator=None):
    if binary_validator is None:
        path=HERE/'privacy_binary.py'
        if not path.is_file():path=HERE/'support/privacy_binary.py'
        spec=importlib.util.spec_from_file_location('magic_privacy_local',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        binary_validator=module.validate_nonpixel_binary
    for name,files in records.items():
        record=index['records'][name]
        if record['pixels']=='pattern':continue
        for path,raw in files.items():
            stem=path.rsplit('/',1)[-1]
            req(not stem.lower().endswith(('.png','.jpg','.jpeg','.bmp','.webp')),'Scene preview included')
            if stem in ('slot.bin','frame.bin','payload-padded.bin','snapshots.bin','sectors.bin') or re.fullmatch(r'frame-[0-9a-f]+\.bin',stem):
                meta=(path in record.get('metadata_sectors',[]) and len(raw)==512 and raw[:8] in (b'GXRWVOL1',b'GXRAWSL1') and
                    int.from_bytes(raw[508:],'little')==zlib.crc32(raw[:508]))
                erased=path in record.get('erased_sectors',[]) and raw in (bytes(512),bytes([255])*512)
                req(meta or erased,'Scene pixel bytes included: '+name+'/'+path)
            elif stem.lower().endswith('.bin'):
                binary_validator(path,raw)

def image_report(core,index,records,entry):
    name=entry['readback'];files=records[name];v=js(files['readback-validation.json']);item=index['records'][name]
    req(v['passed'] and v['full_payload_read'] and v['bytes']==1909600 and v['padding_zero'] and v['png_samples_match_read_raw'],'Incomplete image report')
    payload=item['files'].get('frame.bin',item['omitted'].get('frame.bin'))
    req(payload['sha256']==v['raw_sha256'] and payload['bytes']==1909600,'Image hash binding differs')
    magic=v.get('format')=='GXRS_RAW10_GXRE'
    if magic:
        req(v['full_slot_read'] and v['slot_bytes']==1909760 and not v['payload_checksum_available'] and
            not v['on_media_metadata'] and v['start_magic_valid'] and v['completion_marker_valid'],'Magic object claims differ')
        slot=item['files'].get('slot.bin',item['omitted'].get('slot.bin'))
        req(slot['sha256']==v['slot_sha256'] and slot['bytes']==1909760,'Magic slot hash differs')
    else:
        fmt=core.load_tool(index,'raw_slots.py');volume=fmt.parse_volume(files['volume.bin'])
        req(fmt.parse_slot(files['header.bin'],volume,v['slot'])==v['header'] and v['header']['state']=='FULL' and v['header_crcs_valid'],'Legacy header differs')
    if item['pixels']=='pattern':
        req(entry.get('capture'),'Pattern needs exact capture provenance')
        camera=records[entry['capture']]['frame.bin'];raw=files['slot.bin' if magic else 'payload-padded.bin']
        offset=4 if magic else 0
        req(camera==files['frame.bin']==raw[offset:offset+1909600],'Pattern SD/camera bytes differ')
        scalar=core.load_tool(index,'verify_decode.py');scalar.self_test()
        req(scalar.decode_scalar(camera)==core.read_object(index['native16_reference']),'Pattern differs from independent native16 reference')
        if magic:
            fmt=magic_parser(core,index)
            req(raw[:4]==b'GXRS' and raw[1909604:1909608]==b'GXRE' and raw[1909608:]==bytes(152),'Pattern marker/padding differs')
            req(fmt.parse_slot(raw,index=v['slot'],erased_byte=v['scr_source']['erased_byte'])==v['header'],'Independent marker parser differs')
        reads=[value for key,value in sorted(files.items()) if key.startswith('payload-') and key.endswith('/operation/sectors.bin')]
        req(b''.join(reads)==raw,'Pattern read transaction assembly differs')
    else:
        req(item['omitted']['scene.png']['sha256']==v['png_sha256'],'Omitted scene PNG hash differs')
    if entry.get('capture'):
        cap=index['records'][entry['capture']];ref=cap['files'].get('frame.bin',cap['omitted'].get('frame.bin'))
        req(ref['sha256']==v['raw_sha256'],'Source frame hash differs')
        if not v['original_sensor_frame_comparison']:
            comparison=v.get('source_reference_comparison',{})
            req(item['pixels']=='pattern' and comparison.get('kind')=='preservation' and comparison.get('bytes_equal') is True and
                comparison.get('source',{}).get('sha256')==ref['sha256'],
                'Missing exact preserved-pattern comparison; historical source-RAM claim stays false')
    return dict(record=name,slot=v['slot'],magic_format=magic,pixels_replayed=item['pixels']=='pattern',original_sensor_frame_comparison=v['original_sensor_frame_comparison'])

def erase_probes(index,records,definition):
    erase=js(records[definition['erase']]['verified.json']);state=erase['magic_format'];p=erase['proof'];card=erase['card']
    req(p['operation']==2 and not p['card_write_lo'] and not p['card_write_hi'],'Expected explicit zero-sector-write erase')
    report=js(records[definition['probes']]['summary.json']);source=report['scr_source']
    req(report['passed'] and source['proof']['sha256']==sha(records[definition['erase']]['verified.json']) and source['erased_byte']==state['erased_byte'],'Erase/probe attribution differs')
    selected=index['records'][definition['probes']];files=records[definition['probes']]
    req(report['sampled_sectors']==len(report['probes'])>=20,'Missing erase probes')
    lbas=[]
    for i,probe in enumerate(report['probes']):
        relative=f'probe-{i:02d}/sectors.bin';raw=files[relative];vraw=files[f'probe-{i:02d}/verified.json'];v=js(vraw)
        req(relative in selected['erased_sectors'] and raw==bytes([state['erased_byte']])*512 and
            probe['entire_sector_erased'] and probe['data']['sha256']==sha(raw) and probe['proof']['sha256']==sha(vraw) and
            probe['lba']==v['proof']['read_lba'] and v['proof']['read_count']==1,'Erased probe binding differs')
        lbas.append(probe['lba'])
    count=card['sector_count']//3730
    expected=sorted(set([i*3730 for i in range(16)]+[card['sector_count']//2,(count-1)*3730,count*3730-1,card['sector_count']-1]))
    req(lbas==expected,'Erase sample geometry differs')
    return dict(verified=True,erased_byte=state['erased_byte'],sampled_sectors=len(lbas),whole_card_contents_not_verified=True)

def installations(core,index,records,spec):
    result=[]
    for entry in spec.get('installs',[]):
        files=records[entry['write']];v=js(files['verified.json']);request=js(files['request.json'])
        build=core.file_bytes(index['builds'][entry['build']]);sector=build['staged/capture_sector_0.bin']
        diag=js(records[entry['diagnostic']]['result.json'])
        following=records[entry['following']]['following-sector.bin'];reference=records[entry['following_reference']]['following-sector.bin']
        req(v['byte_for_byte_match'] is True and v['bytes']==65536 and files['readback.bin']==sector and
            v['sha256']==request['desired_sha256']==sha(sector),'NOR install/readback differs')
        req(diag['diag_sequence']==request['sequence'] and not diag['pending_operations'] and not diag['first_failure_result'] and not diag['last_status']&3,'NOR completion differs')
        req(len(following)==4096 and following==reference,'Following NOR region changed')
        result.append(dict(build=entry['build'],sector_sha256=sha(sector),full_sector_verified=True,following4096_unchanged=True))
    return result

def recovery_review(core,index,spec):
    old=core.file_bytes(index['builds'][spec['recovery_baseline']]);original=old['staged/stage1.bin']
    prior=js(old['staged/manifest.json']);rows=[]
    allowed={i for offset in (0xC9C,0x1354) for i in range(offset,offset+4)}
    for name,item in index['builds'].items():
        files=core.file_bytes(item);m=js(files['manifest.json'])
        if not (m.get('magic_format') and m['flash']):continue
        prefix=files['staged/stage1.bin'];meta=js(files['staged/manifest.json'])
        req(len(prefix)==len(original)==5140 and all(i in allowed or a==b for i,(a,b) in enumerate(zip(prefix,original))),
            'Magic recovery prefix differs outside CRC data words')
        req(prefix[:0xAFE]==original[:0xAFE] and meta['recovery_gpio']==prior['recovery_gpio'] and
            meta['recovery_vcp']==prior['recovery_vcp'],'Recovery code/metadata changed')
        literals=meta['checked_recovery_literal_offsets']
        req(literals==prior['checked_recovery_literal_offsets'] and all(prefix[i:i+4]==original[i:i+4] for i in literals),'Recovery literals differ')
        early=files['staged/stage2.bin'];crc=zlib.crc32(early)
        req(len(early)==15804 and all(struct.unpack_from('<I',prefix,offset)[0]==crc for offset in (0xC9C,0x1354)),'Prefix early-code CRC binding differs')
        rows.append(dict(build=name,preserved=True,prefix_sha256=sha(prefix),sector_sha256=sha(files['staged/capture_sector_0.bin'])))
    req(rows,'Missing reviewed magic recovery build');return rows

def long_overlap(core,index,records,definition):
    capture=records[definition['capture']];v=js(capture['verified.json']);report=js(records[definition['report']]['report.json'])
    tool=core.load_tool(index,'long_overlap_report.py')
    req(report['passed'] and report['capture']['sha256']==sha(capture['verified.json']) and
        report['timing']==tool.ordered_timing(v['proof']),'Long overlap proof binding differs')
    image=records[definition['readback']]['readback-validation.json'];r=js(image)
    req(report['image_verified'] and report['image_evidence']['sha256']==sha(image) and r['original_sensor_frame_comparison'] and
        r['raw_sha256']==v['frame_sha256'],'Long capture image comparison differs')
    req(v['magic_format']['sensor']['applied_coarse']==30000 and v['magic_format']['sensor']['exposure_us']==230597 and
        v['magic_format']['stream']['mode']==2 and v['magic_format']['stream']['initial_available_bytes']<1909760,
        'Long overlap did not use incremental producer')
    return dict(verified=True,timing=report['timing'],image_verified=True)

def line_snapshots(core,index,records,definitions):
    rows=[];tool=core.load_tool(index,'verify_producer.py')
    for definition in definitions:
        files=records[definition['capture']];p=tool.decode(files['producer.bin']);frame=files['frame.bin'];snaps=files['snapshots.bin']
        req(index['records'][definition['capture']]['pixels']=='pattern' and len(frame)==1909600 and
            p['magic']==0x50524431 and p['schema']==1 and p['enabled']==p['frame_seen']==p['validated']==1 and
            not p['error'] and p['available_bytes']==1909600 and 2<=p['line_events']<=22,'Producer snapshot state differs')
        count=min(p['line_events'],21)-1
        req(p['snapshot_count']==count and len(snaps)>=count*512 and p['max_prefinal_bytes']==count*89600,'Snapshot extent differs')
        for i in range(p['line_events']):req(p['events'][i][1]==(min(i+1,21)-1)*89600,'LINE watermark differs')
        for i in range(count):
            offset,length=p['snapshots'][i]
            req((offset,length)==((i+1)*89600-512,512) and snaps[i*512:(i+1)*512]==frame[offset:offset+512],'Published prefix differs from final frame')
        rows.append(dict(capture=definition['capture'],snapshot_count=count,bytes_compared=count*512,passed=True))
    return rows

def final_handoff(core,index,records,spec,groups):
    h=spec['final_handoff'];state=js(records[h['state']]['result.json']);last=records[h['cycle']];response=js(last['response.json'])
    build=core.file_bytes(index['builds'][h['build']])
    req(state['sector_sha256']==sha(build['staged/capture_sector_0.bin']) and
        state['prefix_sha256']==sha(build['staged/stage1.bin']) and state['bench_owner']=='root','Final firmware differs')
    req(state['target_power_on'] and state['js_clean_stop'] and state['com8_closed'] and state['break_released'] and
        state['logic2_left_running'] and state['root_process_check_no_bench_helpers'] and response['event']=='stopped' and
        response['ok'] and response['range']==state['js_range']==128 and response['restore_error'] is None and
        state['utc']==response['utc'],'Final clean handoff differs')
    req(state['voltage_v']==response['statistics']['voltage']['avg'] and state['current_a']==response['statistics']['current']['avg'] and
        not state['final_slot_readback'] and not state['final_sbf_read'],'Final measurement/qualification boundary differs')
    req(h['cycle'] not in {c['name'] for g in groups for c in g['cycles']},'Unqualified final cycle included in baseline')
    for evidence in state['evidence']:
        name=evidence['path'].replace('\\','/').rsplit('/',1)[-1]
        req(sha(last[name])==evidence['sha256'],'Final state evidence differs')
    return dict(verified=True,utc=state['utc'],final_expected_slot=state['final_expected_slot'],slot_not_read=True,sbf_not_read=True)

def host_recovery(records,definition):
    helper=records[definition['build']];m=js(helper['manifest.json']);code=helper['recover.bin']
    req(sha(code)==m['binary_sha256'] and len(code)==m['binary_bytes']==1224 and
        m['no_bss'] and m['no_reset'] and m['no_power_switch'] and not m['dtimer_written'],'Host recovery build differs')
    for source,want in m['sources'].items():req(sha(helper[source])==want,'Host recovery source differs')
    req(code[m['park']-m['load']:m['park']-m['load']+2]==b'\xfe\xe7','Host recovery park differs')
    files=records[definition['run']];r=js(files['result.json']);w=struct.unpack('<128I',files['helper-proof.bin'])
    req(r['passed'] and list(w)==r['words'] and r['helper_sha256']==sha(code) and
        w[:4]==(0x53445231,1,128,r['nonce']) and w[4:8]==(2,6,0,0x53445244) and
        w[19]==w[20]==50000000 and w[21] in (2,3),'Successful host recovery proof differs')
    original=files['operation/original-proof-before.bin']
    req(sha(original)==r['original_failure_proof_sha256'] and r['original_failure_proof_unchanged'] and
        r['original_format_remains_failed'] and not r['reset'] and not r['power_switch'],'Original failed FORMAT attribution differs')
    for name in ('original-proof-before-run.bin','original-proof-after.bin','original-proof-final.bin'):
        req(files['operation/'+name]==original,'Original failed FORMAT record changed')
    failed=js(records[definition['failed_format']]['proof.json'])
    req(original==struct.pack('<96I',*failed.values()) and failed['state']==15 and failed['result']==780 and not failed['media_idle'],
        'Failed FORMAT was incorrectly upgraded')
    req(files['operation/helper-readback.bin']==files['operation/helper-after.bin']==code,'Executed recovery helper differs')
    final=w[96:112]
    req(final[4]==13 and final[5]&0x1F00==0x900 and not final[5]&0xFDFFE008 and final[6]==50000000 and
        final[8]==final[9]==final[11]==final[12]==0 and not final[10]&0x1800 and final[13]&16 and not final[3]&128,'Final host/card idle state differs')
    return dict(passed=True,original_format_remains_failed=True,commands=w[21],cmdstop_used=bool(w[24]),dtimer_unchanged=True)


def preserved_slot(records,definition):
    before=records[definition['before']];after=records[definition['after']]
    a=js(before['readback-validation.json']);b=js(after['readback-validation.json'])
    req(a['passed'] and b['passed'] and a['slot']==b['slot']==0 and a['original_sensor_frame_comparison'] and
        b['source_reference_comparison']['kind']=='preservation' and b['source_reference_comparison']['bytes_equal'] and
        before['slot.bin']==after['slot.bin'] and
        a['slot_sha256']==b['slot_sha256']==sha(before['slot.bin']),'Earlier slot changed')
    return dict(passed=True,slot=0,bytes=1909760,slot_sha256=a['slot_sha256'],entire_slot_byte_identical=True)


def next_free(records,definition):
    files=records[definition['record']];vraw=files['verified.json'];v=js(vraw);p=v['proof']
    report=js(files['free-validation.json']);eraw=records[definition['erase']]['verified.json'];erased=js(eraw)['magic_format']['erased_byte']
    raw=files['sectors.bin']
    req(report['passed'] and report['slot']==6 and report['lba']==6*3730 and report['bytes']==512 and
        report['entire_first_sector_erased'] and report['proof_sha256']==sha(vraw) and
        report['scr_proof_sha256']==sha(eraw) and report['sector_sha256']==sha(raw) and
        report['erased_byte']==erased and raw==bytes([erased])*512 and p['operation']==3 and
        p['read_lba']==6*3730 and p['read_count']==1,'Final pre-capture free-sector proof differs')
    return dict(passed=True,slot=6,first_sector_erased_before_final_capture=True,final_image_not_verified=True)


def visual_review(records,definition):
    note=js(records[definition['record']][definition['path']])
    req(note['reviewer']=='root' and len(note['images'])==3,'Expected explicit root visual observations')
    for name,observed in zip(definition['images'],note['images']):
        raw=records[name]['readback-validation.json'];report=js(raw)
        req(observed['inspected'] and observed['observation'] and observed['validation_sha256']==sha(raw) and
            observed['sha256']==report['png_sha256'] and not report['original_sensor_frame_comparison'],
            'Root visual observation attribution differs')
    return dict(passed=True,images=3,root_attestation_only=True,original_camera_ram_comparison=False)

def run():
    base=base_module();core=base.core_module();index=js((HERE/'index.json').read_bytes());spec=index['experiment']
    builds=core.verify_builds(index);records={name:core.file_bytes(item) for name,item in index['records'].items()}
    for item in index['tools'].values():core.read_object(item)
    privacy(index,records,core.load_tool(index,'privacy_binary.py').validate_nonpixel_binary)
    b,f=magic_validators(core,index);terminals=[]
    for name,files in records.items():
        for path,raw in files.items():
            if not path.endswith('verified.json'):continue
            v=js(raw)
            if 'proof' not in v or v.get('binary_sha256') not in builds:continue
            prefix=path[:-len('verified.json')];m=builds[v['binary_sha256']][1]
            result=magic_terminal(v,files,prefix,builds,b,f) if m.get('magic_format') else core.terminal_proof(v,files,prefix,builds)
            terminals.append(dict(record=name,path=path,**result))
    images=[image_report(core,index,records,entry) for entry in spec['image_comparisons']]
    groups=[base.group(core,index,records,g) for g in spec['groups']]
    req(len(groups)==2 and groups[0]['criteria']==groups[1]['criteria'],'Same-criteria A/B groups required')
    erasure=erase_probes(index,records,spec['erase_probes'])
    recovery=recovery_review(core,index,spec)
    overlap=long_overlap(core,index,records,spec['long_overlap'])
    snapshots=line_snapshots(core,index,records,spec.get('line_snapshots',[]))
    host=host_recovery(records,spec['host_recovery']) if spec.get('host_recovery') else None
    tests=js(records['test-output']['manifest.json'])
    for name,item in tests['files'].items():
        raw=records['test-output'][name];req(len(raw)==item['bytes'] and sha(raw)==item['sha256'] and b'\nOK' in raw,'Offline test record differs')
    req(tests['all_logs_report_ok'] and sum(tests['reported_counts'].values())==tests['reported_total'],'Offline test counts differ')
    return dict(passed=True,hardware_access=False,no_scene_pixels=True,builds=len(builds),terminal_proofs=len(terminals),
        installations=installations(core,index,records,spec),erase_probes=erasure,offline_tests=tests['reported_total'],
        recovery_review=recovery,long_overlap=overlap,line_snapshots=snapshots,
        host_recovery=host,
        preserved_slot=preserved_slot(records,spec['preservation']),
        next_free=next_free(records,spec['next_free']),
        visual_review=visual_review(records,spec['visual_review']),
        final_handoff=final_handoff(core,index,records,spec,groups),
        image_reports=images,groups=groups,
        time_reduction_fraction=1-groups[1]['median_time_s']/groups[0]['median_time_s'],
        energy_reduction_fraction=1-groups[1]['median_energy_j']/groups[0]['median_energy_j'],
        limitations=['Scene pixels omitted; their historical equality checks remain hash-bound, not replayed.',
            'Card erase changes internal media state between A/B groups; differences cannot be attributed solely to firmware.',
            'Compact sums replay energy integration, not raw boundary classification.',
            'Completion markers are not payload checksums or power-loss atomicity.',
            'No power-loss, isolated-DUT, production battery-energy or statistical-significance claim.'])

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path);a=p.parse_args();r=run();raw=json.dumps(r,indent=2)+'\n'
    if a.out:a.out.write_text(raw,encoding='utf-8')
    print(raw,end='')
if __name__=='__main__':main()
