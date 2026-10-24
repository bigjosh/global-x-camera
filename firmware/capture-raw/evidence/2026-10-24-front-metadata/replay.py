"""Offline compact v18 proof replay; stdlib only, never connects hardware.

Private image bytes are absent. This verifies frozen firmware, recorded proof
invariants, complete READ extents, hashes, metadata and attribution. It cannot
repeat image decoding/source-RAM comparisons or integrate omitted power traces.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path,PurePosixPath
import struct
import zipfile
import zlib

def sha(data):return hashlib.sha256(data).hexdigest()
def js(data):return json.loads(data.decode('utf-8-sig'))
def req(ok,msg):
    if not ok:raise ValueError(msg)


def pure_guards(source):
    names={'magic_geometry','frame_layout','magic_layout','capture_geometry','request','validate'}
    tree=ast.parse(source);nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names]
    req({n.name for n in nodes}==names,'Frozen pure guard function set differs')
    env=dict(struct=struct,LOAD=0x34300000,FRAME=0x34000000,REQUEST=0x343FD000,PROOF=0x343FD100,
             READ_BUFFER=0x34200000,READ_MAX=262144,FRAME_BYTES=1909600,MAGIC=0x52535731,DONE=0x5253444E,
             MAGIC_FRAME=0x34000010,MAGIC_BUFFER=0x3400000C,SLOT_BYTES=1909760,
             FRONT_MAGIC_FRAME=0x340000A0,FRONT_MAGIC_BUFFER=0x34000004,
             OPS={'capture':1,'format':2,'read':3})
    exec(compile(ast.Module(body=nodes,type_ignores=[]),'frozen-bench-pure-guards','exec'),env)
    return env


def replay(folder):
    index=js((folder/'index.json').read_bytes());zipraw=(folder/'objects.zip').read_bytes()
    req(index['schema']==1 and sha(zipraw)==index['objects_zip_sha256'],'Archive identity differs')
    with zipfile.ZipFile(folder/'objects.zip') as z:
        want={'objects/'+v['sha256'] for v in index['files'].values()}
        req(set(z.namelist())==want and len(z.namelist())==len(want),'Unexpected/duplicate archive object')
        files={}
        for name,entry in index['files'].items():
            req('..' not in PurePosixPath(name).parts and not name.startswith('/'),'Unsafe logical path')
            data=z.read('objects/'+entry['sha256'])
            req(len(data)==entry['bytes'] and sha(data)==entry['sha256'],'Object hash/size differs')
            if entry['kind']=='firmware':
                req((name.startswith('builds/') and Path(name).name in ('capture.bin','stage1.bin','stage1_boot.bin','stage2.bin','stage2-full.bin','capture_sector_0.bin')) or name=='external/previous-stage1.bin','Unapproved binary path')
                req(len(data)<=65536,'Unexpected binary extent')
            elif entry['kind']=='json':js(data)
            else:data.decode('utf-8-sig')
            files[name]=data
    get=lambda name:js(files[name])
    guards=pure_guards(files['tools/firmware/capture-raw/bench.py'])
    manifests={};bysha={};old=files['external/previous-stage1.bin'];oldm=get('external/previous-prefix-manifest.json')
    req(sha(old)=='44c3425ea8e22c06168d8a8d0b65ae7813a0cad147a6d06ad18278f71bd4b9c2','Wrong prior prefix')
    for name,build in index['builds'].items():
        f={k:files[v] for k,v in build['files'].items()};m=js(f['manifest.json']);code=f['capture.bin']
        req(sha(code)==m['binary_sha256'] and len(code)==m['binary_bytes'],'Receiver executable differs')
        for path,digest in m['source_hashes'].items():req(sha(f[path])==digest,'Frozen source differs')
        guards['magic_layout'](m)
        req(m['magic_layout_version']==2 and m['frame']==0x340000A0 and m['slot_buffer']==0x34000004 and m['image_offset']==156 and m['metadata_bytes']==152,'Wrong v18 geometry')
        req(m['source_hashes']['sd_card.c']=='34512a0074cf6d7dee5a00ff36104f2177433bf2eaa5240673e5648f3bab39da','SD driver differs')
        manifests[name]=m;bysha[m['binary_sha256']]=m
        if m['flash']:
            p=js(f['staged/manifest.json']);prefix=f['staged/stage1.bin'];sector=f['staged/capture_sector_0.bin']
            for path,digest in p['sources'].items():
                base=path.replace('\\','/').rsplit('/',1)[-1]
                req(sha(f['staged/'+base])==digest,'Frozen prefix source differs')
            req(len(prefix)==len(old)==5140 and len(sector)==65536,'Flash extents differ')
            req(sha(prefix)==p['stage1_raw_sha256']=='9401bed4076d6e9e4d2e4f9236661faf7b8f0e051cb332ea4dcbba09da336eba','Prefix identity differs')
            req(sha(sector)==p['program_sha256']=='174424c6792f96c72e336fc68e442474e9da665718552d3239a772d59ba73e2e','Sector identity differs')
            changed=[i for i,(a,b) in enumerate(zip(old,prefix)) if a!=b]
            req(changed==list(range(0xC9C,0xCA0))+list(range(0x1354,0x1358)),'Recovery changed outside CRC words')
            offsets=p['checked_recovery_literal_offsets'];req(len(offsets)==20 and offsets==oldm['checked_recovery_literal_offsets'] and all(old[i:i+4]==prefix[i:i+4] for i in offsets),'Recovery literals differ')
            req(p['recovery_gpio']==oldm['recovery_gpio'] and p['recovery_vcp']==oldm['recovery_vcp'],'Recovery metadata differs')
            req(p['stage2_manifest_sha256']==sha(f['manifest.json']) and p['stage2_full_sha256']==sha(code) and sector[0x2000:0x2000+len(code)]==code,'Receiver binding differs')
            late=m['late_load'];req(late==p['late_load'] and late['early_bytes']==p['stage2_bytes']==15804,'Split-load length differs')
            req(f['staged/stage2.bin']==code[:15804] and f['staged/stage2-full.bin']==code,'Staged receiver differs')
            req(zlib.crc32(code[:15804])==int(p['stage2_crc32'],0) and zlib.crc32(code[15804:])==late['late_crc32'],'Split CRCs differ')
    records={name:{rel:files[key] for rel,key in record['files'].items()} for name,record in index['records'].items()}
    rget=lambda name,rel='verified.json':js(records[name][rel])
    selection=index['selection'];capture_results=[];read_results=[];card_identity={}
    def terminal(v):
        req(v['passed'] is True and v['binary_sha256'] in bysha,'Unrecognized terminal image')
        m=bysha[v['binary_sha256']];guards['validate'](v['proof'],m,v['request_words'])
        card=v['card'];req(card['media_idle']==1 and card['initialized']==card['controller_owned']==card['error']==card['cleanup_error']==0 and card['last_ready_r1']&0x1F00==0x900,'Card terminal differs')
        actual={k:card[k] for k in ('sector_count','cid0','cid1','cid2','cid3')}
        if not card_identity:card_identity.update(actual)
        req(actual==card_identity,'Card identity changed between recorded operations')
        return m,v['proof']
    for item in selection['captures']:
        v=rget(item['name']);m,p=terminal(v);req(p['operation']==1,'Capture record is not capture')
        w=v['whole_image'];stream=v['magic_format']['stream']
        req(w['proof']==[0x524D4732,3,0,0,0x32525847,0x45525847,152,3730] and w['original_guard_checked_before_trailer'] and w['post_padding_guard_intact'] and w['end_guard_word_bias']==1,'Completion/guard proof differs')
        req(len(bytes.fromhex(w['metadata_hex']))==152 and stream['mode'] in (1,2) and stream['published_bytes']==stream['queued_bytes']==1909760 and not stream['producer_error'],'Metadata/stream completion differs')
        req((stream['mode']==1)==(stream['initial_available_bytes']==1909760),'Stream mode differs')
        capture_results.append(dict(name=item['name'],slot=p['slot'],stream_mode=stream['mode'],raw_sha256=v['frame_sha256']))
    for item in selection['images']:
        name=item['name'];v=rget(name,'readback-validation.json');summary=rget(name,'summary.json')
        req(v['passed'] and v['full_slot_read'] and v['full_payload_read'] and v['bytes']==1909600 and v['slot_bytes']==1909760 and v['png_samples_match_read_raw'],'Recorded image validation failed')
        h=v['header'];req(h['state']=='COMPLETE' and h['completion_marker_valid'] and h['start_magic_valid'],'Image markers differ')
        req((h['format_revision'],h['image_offset'],h['trailer_offset'],h['metadata_bytes']) in ((1,4,1909604,0),(2,156,1909756,152)),'Image layout differs')
        expected_lba=v['slot']*3730;read_count=0
        read_proofs=sorted((path,js(raw)) for path,raw in records[name].items() if path.startswith('payload-') and path.endswith('/verified.json'))
        req(len(read_proofs)==8,'Incomplete bounded READ count')
        for path,r in read_proofs:
            _,p=terminal(r);count=min(512,3730-read_count)
            req(p['operation']==3 and p['read_lba']==expected_lba+read_count and p['read_count']==count and p['read_bytes']==count*512,'READ extent differs')
            read_count+=count
        req(read_count==3730 and summary['passed'] and summary['slots'][0]['slot']==v['slot'],'Slot READ coverage differs')
        comparison=v['source_reference_comparison']
        if item.get('capture'):
            captured=rget(item['capture'])
            req(comparison and comparison['kind']=='sensor-ram' and comparison['bytes_equal'] and v['original_sensor_frame_comparison'] and captured['frame_sha256']==v['raw_sha256']==comparison['source']['sha256'] and captured['proof']['slot']==v['slot'],'Source-RAM comparison binding differs')
        elif item.get('preservation'):
            req(comparison and comparison['kind']=='preservation' and comparison['bytes_equal'] and comparison['source']['sha256']==v['raw_sha256'] and h['format_revision']==1,'Legacy preservation binding differs')
            old_image=get('external/legacy-slot0-validation.json')
            req(old_image['passed'] and old_image['slot']==v['slot']==0 and old_image['slot_sha256']==v['slot_sha256'] and old_image['raw_sha256']==v['raw_sha256'],'Original full slot0 hash changed')
        else:req(not v['original_sensor_frame_comparison'] and comparison is None,'Standby image cannot claim retained source RAM')
        read_results.append(dict(name=name,slot=v['slot'],format_revision=h['format_revision'],read_sectors=read_count,recorded_raw_sha256=v['raw_sha256'],pixels_redecoded=False))
    d=rget(selection['directory']['name'],'summary.json');req(d['passed'] and d['one_sector_per_slot'] and d['read_sectors']==len(d['slots']),'Directory count differs')
    for row in d['slots']:
        _,p=terminal(rget(selection['directory']['name'],f"slot-{row['slot']}/verified.json"));h=row['header']
        req(p['operation']==3 and p['read_count']==1 and p['read_lba']==row['slot']*3730 and not h['completion_checked'] and h['completion_marker_valid'] is None,'Directory read/completion boundary differs')
        if h.get('metadata_bytes'):req(len(bytes.fromhex(h['metadata_hex']))==152,'Directory metadata extent differs')
        for item in selection['images']:
            im=rget(item['name'],'readback-validation.json')
            if im['slot']==row['slot'] and h.get('metadata_bytes'):
                req(h['metadata_hex']==im['header']['metadata_hex'],'Directory metadata differs from full image READ')
    sector_sha='174424c6792f96c72e336fc68e442474e9da665718552d3239a772d59ba73e2e'
    install=get('installation-checks.json')
    req(install['passed'] and install['full_sector_byte_equal'] and install['following_region_byte_equal'] and
        install['readback_bytes']==65536 and install['following_bytes']==4096 and
        install['readback_sha256']==sector_sha and install['following_sha256']==install['preceding_reference_sha256'],'Installation preservation differs')
    extra={item.get('kind'):item for item in selection['extras'] if item.get('kind')}
    req({'sbf','qualification','nor-write'}<=set(extra),'Required qualification records missing')
    def extra_json(kind):
        e=extra[kind];return rget(e['name'],Path(e['path']).name)
    write=extra_json('nor-write');req(write['byte_for_byte_match'] and write['bytes']==65536 and write['sha256']==sector_sha,'NOR write verification differs')
    sbf=extra_json('sbf');req(sbf['passed'] and sbf['sbf'] and not sbf['cpucr_written'] and not sbf['reset_or_power_changed'],'SBF read failed or changed state')
    cycle_name=selection['cycle']['name'];cycle=rget(cycle_name,'result.json');phase=rget(cycle_name,'phase-summary.json');response=rget(cycle_name,'response.json')
    req(cycle['recording_complete'] and cycle['expected_end']=='standby' and cycle['sector_sha256']==sector_sha,'Cold cycle identity/completion differs')
    ids=phase['event_ids'];req(len(ids)==10 and set(ids[:9])==set(range(1,10)) and ids[-1] in (None,10),'Cold event set differs')
    for order in ((1,2,3),(4,5,6,7,8,9),(3,7)):
        req(all(ids.index(a)<ids.index(b) for a,b in zip(order,order[1:])),'Cold event order differs')
    req(response['event']=='stopped' and response['ok'] and response['range']==128 and response['restore_error'] is None,'Cold recorder stop differs')
    q=extra_json('qualification')
    req(q['schema']==1 and q['bench_owner']=='root' and q['cycle']==cycle_name and q['sector_sha256']==sector_sha and
        q['owner_attests_no_intervening_poweroff'] and q['owner_attests_sbf_cleared_before_cycle'] and
        q['recording_result_sha256']==sha(records[cycle_name]['result.json']) and
        q['sbf_evidence']['sha256']==sha(records[extra['sbf']['name']][Path(extra['sbf']['path']).name]),'Root Standby attribution binding differs')
    image_name=selection['standby_image'];image=rget(image_name,'readback-validation.json')
    visual=rget('visual-review','visual-review.json')
    req(visual['reviewer']=='root' and visual['visual_inspection_passed'] and visual['slot']==image['slot'] and
        visual['scene_png_sha256']==image['png_sha256'],'Visual review is not bound to the retrieved scene')
    req(q['owner_attests_complete_slot_readback'] and q['slot']==image['slot'] and
        q['image_evidence']['sha256']==sha(records[image_name]['readback-validation.json']),
        'Root cold-cycle image attribution missing or changed')
    prior_free=[row for row in d['slots'] if row['slot']==image['slot']]
    req(len(prior_free)==1 and prior_free[0]['header']['state']=='FREE' and
        not prior_free[0]['header']['occupied'] and image['header']['format_revision']==2,
        'Cold image was not bound to the previously observed free slot')
    long_v=rget('long');long_report=rget('long-overlap','report.json');lp=long_v['proof']
    timing=long_report['timing'];elapsed={key:(lp[key]-lp['begin'])&0xFFFFFFFF for key in timing['elapsed_cycles_since_begin']}
    req(long_report['passed'] and long_report['image_verified'] and
        long_report['capture']['sha256']==sha(records['long']['verified.json']) and
        long_report['image_evidence']['sha256']==sha(records['long-image']['readback-validation.json']) and
        timing['elapsed_cycles_since_begin']==elapsed and all(0<value<2**31 for value in elapsed.values()),'Long overlap record binding differs')
    req(elapsed['sd_ready']<elapsed['first_write']<elapsed['frame_done']<elapsed['payload_done'] and
        timing['first_write_to_frame_done_ms']==(elapsed['frame_done']-elapsed['first_write'])/400000 and
        long_v['magic_format']['sensor']['exposure_us']==230597 and long_v['magic_format']['stream']['mode']==2,
        'Long progressive write overlap differs')
    line=rget('long-line','report.json')
    req(line['passed'] and line['capture']['sha256']==sha(records['long']['verified.json']) and
        line['artifacts']['frame.bin']['sha256']==long_v['frame_sha256'] and line['snapshot_count']==20 and line['bytes_compared']==10240,
        'Recorded LINE snapshot comparison differs')
    req([(v['offset'],v['bytes']) for v in line['snapshots']]==[((i+1)*89600-512,512) for i in range(20)],'Recorded snapshot extents differ')
    review=get('review-v18.json');req(review['passed'] and review['allowlists_checked'] and not review['hardware_access'],'Review failed')
    test=get('tests/manifest.json');req(test['all_logs_report_ok'],'Tests failed')
    for name,log in test['files'].items():req(sha(files['tests/'+name])==log['sha256'],'Test log changed')
    final=get('final-state.json');last=rget(selection['final_cycle']['name'],'response.json')
    req(final['bench_owner']=='root' and final['sector_sha256']=='174424c6792f96c72e336fc68e442474e9da665718552d3239a772d59ba73e2e','Final firmware differs')
    req(final['prefix_sha256']=='9401bed4076d6e9e4d2e4f9236661faf7b8f0e051cb332ea4dcbba09da336eba','Final prefix differs')
    req(all(final[k] for k in ('target_power_on','js_clean_stop','com8_closed','break_released','logic2_left_running','root_process_check_no_bench_helpers')),'Final ownership state incomplete')
    req(last['event']=='stopped' and last['ok'] and last['range']==final['js_range']==128 and last['restore_error'] is None and final['utc']==last['utc'],'Final clean JS stop differs')
    req(final['voltage_v']==last['statistics']['voltage']['avg'] and final['current_a']==last['statistics']['current']['avg'] and not final['final_slot_readback'] and not final['final_sbf_read'],'Final measurement/qualification limits differ')
    req(final['final_expected_slot']==image['slot']+1,'Final expected slot differs from next sequential capture')
    return dict(schema=1,passed=True,hardware_access=False,builds_verified=len(manifests),objects_verified=len(want),
                captures=capture_results,images=read_results,directory_sector_reads=d['read_sectors'],
                reported_tests=test['reported_total'],final_expected_slot=final['final_expected_slot'],
                installation_preserved=True,one_cold_cycle_sbf_attributed=True,
                long_first_write_before_frame_ms=timing['first_write_to_frame_done_ms'],recorded_line_snapshots=20,
                image_pixels_in_archive=False,pixels_redecoded=False,power_integrated=False,
                limits=index['limits'])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--archive',type=Path,default=Path(__file__).resolve().parent)
    p.add_argument('--out',type=Path);a=p.parse_args();result=replay(a.archive)
    if a.out:
        with a.out.open('x',encoding='utf-8') as out:json.dump(result,out,indent=2);out.write('\n')
    print(json.dumps(result,indent=2))
