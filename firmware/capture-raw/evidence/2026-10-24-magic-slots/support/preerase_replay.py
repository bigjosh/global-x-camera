"""Replay explicit RAW preerase A/B evidence offline; never infer bench state."""
import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import statistics
import struct
import zlib

HERE=Path(__file__).resolve().parent
CORE_SHA='f76221c82f3295526d131b3c371e3bb44538ca99c2fade92d17b34d86d649470'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def req(ok,message):
    if not ok:raise ValueError(message)
def js(raw):return json.loads(raw)
def core_module():
    p=HERE/'support/core_replay.py';req(sha(p.read_bytes())==CORE_SHA,'Replay dependency changed')
    s=importlib.util.spec_from_file_location('preerase_replay_core',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);m.HERE=HERE;return m
# materialize.py uses these names; loading the core is entirely offline.
def checked_name(name):return core_module().checked_name(name)
def read_object(item):return core_module().read_object(item)
def file_bytes(record):return core_module().file_bytes(record)

def privacy(index,records):
    for name,files in records.items():
        selected=index['records'][name]
        if selected['pixels']=='pattern':continue
        for path,raw in files.items():
            stem=path.rsplit('/',1)[-1]
            req(not stem.lower().endswith(('.png','.jpg','.jpeg','.bmp','.webp')),'Scene preview included')
            if stem in ('frame.bin','payload-padded.bin','snapshots.bin','sectors.bin'):
                req(path in selected.get('metadata_sectors',[]) and len(raw)==512 and
                    raw[:8] in (b'GXRWVOL1',b'GXRAWSL1') and
                    int.from_bytes(raw[508:],'little')==zlib.crc32(raw[:508]),'Scene payload included')

def phases(files,protocol):
    raw=files['phase/binary/digital_1.bin']
    magic,version,kind,initial,begin,end,n=struct.unpack_from('<8siiIddQ',raw)
    req(magic==b'<SALEAE>' and version==kind==initial==0 and n%2==0 and len(raw)==44+8*n,'Marker geometry')
    edges=struct.unpack_from('<'+'d'*n,raw,44)
    req(all(math.isfinite(x) and begin<=x<=end for x in edges) and
        all(a<b for a,b in zip(edges,edges[1:])),'Marker transitions')
    decoded=js(files['phase-summary.json']);req(len(decoded['pulses'])==n//2,'Marker count')
    ids=[];step=protocol['nominal_high_us_per_id']*1e-6;tol=protocol['pulse_width_tolerance_us']*1e-6
    for saved,(a,b) in zip(decoded['pulses'],zip(edges[::2],edges[1::2])):
        width=b-a;v=math.floor(width/step+.5);v=v if 1<=v<=10 and abs(width-v*step)<=tol+1e-15 else None
        req(saved['event_id']==v and saved['start_s']==a and saved['end_s']==b and saved['width_s']==width,'Marker decode changed')
        ids.append(v)
    return ids

def group(core,index,records,definition):
    build=core.file_bytes(index['builds'][definition['build']]);m=js(build['manifest.json'])
    pm=js(build['staged/manifest.json']);prefix=build['staged/stage1.bin']
    sector=sha(build['staged/capture_sector_0.bin']);prefix_sha=sha(prefix)
    report=records[definition['analysis']];summary=js(report['summary.json']);am=js(report['manifest.json'])
    for name,digest in am['files'].items():req(sha(report[name])==digest,'Analysis artifact changed')
    req(summary['sector_sha256']==sector and summary['prefix_sha256']==prefix_sha and
        summary['terminal_state_qualified'],'Group firmware/completion identity')
    req(len(definition['cycles'])>=3 and len(summary['cycles'])==len(definition['cycles']),'Three or more cycles required')
    results=[]
    for spec,row in zip(definition['cycles'],summary['cycles']):
        name=spec['record'];f=records[name];r=js(f['result.json']);q=js(f['attachments/qualification.json'])
        req(row['name']==name and r['recording_complete'] and r['expected_end']=='standby' and
            r['sector_sha256']==sector and sha(f['raw/manifest.json'])==r['raw_manifest_sha256'] and
            sha(f['phase-summary.json'])==r['phase_summary_sha256'] and
            sha(f['safe-start-proof.json'])==r['safe_start_proof_sha256'],'Cycle identity')
        raw=js(f['raw/manifest.json']);req(raw['finalized'] and raw['status']['complete'] and raw['status']['coverage']['passed'],'Raw recording incomplete')
        req(sha(f['raw/chunks.jsonl'])==raw['chunks_sha256'],'Raw chunk metadata changed')
        for item in raw['files'].values():
            omitted=index['records'][name]['omitted']['raw/'+item['path']]
            req((omitted['sha256'],omitted['bytes'])==(item['sha256'],item['bytes']),'Raw omission binding')
        parkfiles=records[spec['park']];park=js(parkfiles['result.json']);sf=records[spec['sbf']];sbf=js(sf['result.json'])
        req(q['bench_owner']=='root' and q['cycle']==name and q['sector_sha256']==sector and
            q['recording_result_sha256']==sha(f['result.json']) and q['owner_attests_no_intervening_poweroff'] is True and
            q['owner_attests_sbf_cleared_before_cycle'] is True and q['owner_attestation'] and
            q['sbf_evidence']['sha256']==sha(sf['result.json']),'Root SBF attribution')
        if spec.get('image'):
            image_raw=records[spec['image']]['readback-validation.json'];image=js(image_raw)
            req(q.get('owner_attests_complete_slot_readback') is True and
                q.get('slot')==image['slot'] and q.get('image_evidence',{}).get('sha256')==sha(image_raw) and
                image.get('passed') is True and image.get('full_payload_read') is True,
                'Cycle-to-image attribution differs')
        req(park['passed'] and park['prefix_sha256']==prefix_sha and parkfiles['live-prefix.bin']==prefix and
            parkfiles['recovery-status.bin']==struct.pack('<24I',*park['status'].values()) and
            parkfiles['vcp-status.bin']==struct.pack('<32I',*park['vcp_status'].values()) and
            park['context']['PC']==int(pm['recovery_gpio']['park_address'],0) and
            park['context']['CONTROL']==0 and park['context']['PRIMASK']==1 and
            not park['ccr']&0x30000 and not park['xspi_sr']&32 and
            park['vcp_status']['request']==1 and park['vcp_status']['bad_pulses']==0,'Exact recovery park')
        req(sbf['passed'] and sbf['sbf'] and sbf['cpucr']&512 and sbf['prefix_sha256']==prefix_sha and
            not sbf['cpucr_written'] and not sbf['reset_or_power_changed'] and not sbf['ram_writes'] and not sbf['nor_commands'] and
            sbf['prior_park_result_sha256']==sha(parkfiles['result.json']) and sbf['fresh_park_result']==park and
            sf['registers/before-prefix.bin']==prefix and sf['registers/pwr-cpucr.bin']==struct.pack('<I',sbf['cpucr']) and
            sbf['guard_before']==sbf['guard_after'],'Read-only SBF')
        ids=phases(f,m['phase_markers']);e=js(report[name+'/energy.json']);context=js(report[name+'/context.json'])
        req(row['terminal_state_qualified'] and row['qualification_sha256']==sha(f['attachments/qualification.json']) and
            row['sbf_evidence_sha256']==sha(sf['result.json']) and e['terminal_evidence_sha256']==sha(report[name+'/context.json']) and
            context['recording_result_sha256']==sha(f['result.json']) and e['criteria']==summary['same_boundary_criteria'],'Energy evidence bindings')
        req(e['onset_to_plateau_s']==row['onset_to_plateau_s'] and e['onset_to_plateau_energy_j']==row['onset_to_plateau_energy_j'],'Energy summary')
        results.append(dict(name=name,events=ids,standby_attributed=True,time_s=e['onset_to_plateau_s'],energy_j=e['onset_to_plateau_energy_j']))
    compact=core.replay_compacts(records,definition['compacts'],definition['analysis'])
    req(compact and compact['cycles']==len(results),'Missing compact native energy replay')
    return dict(build=definition['build'],sector_sha256=sector,cycles=results,compact=compact,
        median_time_s=statistics.median(v['time_s'] for v in results),median_energy_j=statistics.median(v['energy_j'] for v in results),
        criteria=summary['same_boundary_criteria'])

def run():
    core=core_module();index=js((HERE/'index.json').read_bytes());spec=index['experiment']
    builds=core.verify_builds(index)
    # Verify every stored object, including tools not executed by replay.
    records={name:core.file_bytes(item) for name,item in index['records'].items()}
    for item in index['tools'].values():core.read_object(item)
    privacy(index,records);terminals=[]
    installations=[]
    for install in spec.get('installs',[]):
        f=records[install['write']];v=js(f['verified.json']);request=js(f['request.json'])
        build=core.file_bytes(index['builds'][install['build']]);sector=build['staged/capture_sector_0.bin']
        diag=js(records[install['diagnostic']]['result.json'])
        following=records[install['following']]['following-sector.bin']
        reference=records[install['following_reference']]['following-sector.bin']
        req(v['byte_for_byte_match'] is True and v['bytes']==65536 and
            f['readback.bin']==sector and v['sha256']==request['desired_sha256']==sha(sector),
            'NOR install/readback differs')
        req(diag['diag_sequence']==request['sequence'] and not diag['pending_operations'] and
            not diag['first_failure_result'] and not diag['last_status']&3,'NOR completion differs')
        req(len(following)==4096 and following==reference,'Following NOR region changed')
        installations.append(dict(build=install['build'],full_sector_verified=True,
            following4096_unchanged=True,sector_sha256=sha(sector)))
    for name,files in records.items():
        for path,raw in files.items():
            if not path.endswith('verified.json'):continue
            v=js(raw)
            if 'proof' not in v or v.get('binary_sha256') not in builds:continue
            prefix=path[:-len('verified.json')]
            terminals.append(dict(record=name,path=path,**core.terminal_proof(v,files,prefix,builds)))
            m=builds[v['binary_sha256']][1]
            if v['proof']['operation']==1 and m.get('whole_image_preerase'):
                candidates=['inspection/'] if v.get('kind')=='raw-flash-inspection' else ['operation/','bootstrap/']
                matches=[sub for sub in candidates if prefix+sub+'whole-proof.bin' in files]
                req(len(matches)==1,'Exact whole-image proof location')
                sub=matches[0]
                expected=struct.pack('<8I',0x52575031,3,0,0,1909600,1909760,160,3730)
                req(files[prefix+sub+'whole-proof.bin']==expected and files[prefix+sub+'frame-padding.bin']==bytes(160),'Whole image padding proof')
                req(files[prefix+sub+'frame-guard.bin']==struct.pack('<8I',*(0xA15A1000+i for i in range(8))),'Post-padding guard')
                chunk=struct.unpack('<8I',files[prefix+sub+'whole-chunk.bin'])
                req(v['proof']['chunk_count']==1 and chunk[2:5]==(0,3730,1909600) and chunk[5]&0x1f00==0x900 and chunk[6]==0,'One-transfer trace')
    fmt=core.load_tool(index,'raw_slots.py');comparisons=[]
    for entry in spec.get('image_comparisons',[]):
        name=entry['readback'];f=records[name];v=js(f['readback-validation.json'])
        volume=fmt.parse_volume(f['volume.bin']);slot=fmt.parse_slot(f['header.bin'],volume,v['slot'])
        req(v['passed'] and v['full_payload_read'] and v['header_crcs_valid'] and v['padding_zero'] and
            v['png_samples_match_read_raw'] and v['bytes']==1909600 and slot==v['header'] and slot['state']=='FULL','Image report/header')
        item=index['records'][name];payload=item['files'].get('frame.bin',item['omitted'].get('frame.bin'))
        req(payload['sha256']==v['raw_sha256'] and payload['bytes']==1909600,'Payload report binding')
        if item['pixels']=='pattern':
            camera=records[entry['capture']]['frame.bin'];raw=f['payload-padded.bin']
            req(camera==f['frame.bin']==raw[:1909600] and raw[1909600:]==bytes(160),'Pattern SD/camera equality')
            reads=[value for key,value in sorted(f.items()) if key.startswith('payload-') and key.endswith('/operation/sectors.bin')]
            req(b''.join(reads)==raw,'Pattern read transaction assembly')
        else:
            req(item['omitted']['scene.png']['sha256']==v['png_sha256'],'Scene preview report binding')
            if entry.get('capture'):
                cap=index['records'][entry['capture']]
                ref=cap['files'].get('frame.bin',cap['omitted'].get('frame.bin'))
                req(ref['sha256']==v['raw_sha256'] and v['original_sensor_frame_comparison'],'Same-capture frame hash binding')
        comparisons.append(dict(record=name,slot=v['slot'],pixels_replayed=item['pixels']=='pattern',original_sensor_frame_comparison=v['original_sensor_frame_comparison']))
    groups=[group(core,index,records,g) for g in spec['groups']]
    req(len(groups)==2 and groups[0]['criteria']==groups[1]['criteria'],'A/B comparison requires same criteria')
    tests=js(records['test-output']['manifest.json'])
    for name,item in tests['files'].items():
        raw=records['test-output'][name]
        req(len(raw)==item['bytes'] and sha(raw)==item['sha256'] and b'\nOK' in raw,'Test result binding')
    req(tests['all_logs_report_ok'] and sum(tests['reported_counts'].values())==tests['reported_total']==70,'Offline test count')
    handoff=spec['final_handoff'];state=js(records[handoff['state']]['result.json'])
    last=records[handoff['cycle']];response=js(last['response.json'])
    installed=core.file_bytes(index['builds'][handoff['build']])
    req(state['sector_sha256']==sha(installed['staged/capture_sector_0.bin']) and
        state['prefix_sha256']==sha(installed['staged/stage1.bin']) and state['bench_owner']=='root', 'Final installed image binding')
    req(state['target_power_on'] and state['js_clean_stop'] and state['com8_closed'] and
        state['break_released'] and state['logic2_left_running'] and state['root_process_check_no_bench_helpers'] and
        response['event']=='stopped' and response['ok'] and response['range']==state['js_range']==128 and
        response['restore_error'] is None and state['utc']==response['utc'], 'Final clean stop')
    req(state['voltage_v']==response['statistics']['voltage']['avg'] and
        state['current_a']==response['statistics']['current']['avg'] and
        state['final_expected_slot']==18 and not state['final_slot_readback'] and not state['final_sbf_read'], 'Final measurement or qualification limit')
    for item in state['evidence']:
        name=item['path'].replace('\\','/').rsplit('/',1)[-1]
        req(sha(last[name])==item['sha256'],'Final state evidence binding')
    req(handoff['cycle'] not in {c['name'] for g in groups for c in g['cycles']},'Unqualified final cycle included in A/B')
    return dict(passed=True,hardware_access=False,no_scene_pixels=True,builds=len(builds),terminal_proofs=len(terminals),installations=installations,
        offline_tests=tests['reported_total'],final_handoff=dict(verified=True,utc=state['utc'],slot18_not_read=True,sbf_not_read=True),
        image_reports=comparisons,groups=groups,time_reduction_fraction=1-groups[1]['median_time_s']/groups[0]['median_time_s'],
        energy_reduction_fraction=1-groups[1]['median_energy_j']/groups[0]['median_energy_j'],
        limitations=['Scene pixels omitted: historical checks are hash-bound, not independently recomputed.',
            'Compact native sums replay energy integrals but cannot repeat raw boundary classification.',
            'No power-loss, isolated-DUT, battery-energy or statistical-significance claim.'])

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path);a=p.parse_args();r=run()
    raw=json.dumps(r,indent=2)+'\n'
    if a.out:a.out.write_text(raw,encoding='utf-8')
    print(raw,end='')
if __name__=='__main__':main()
