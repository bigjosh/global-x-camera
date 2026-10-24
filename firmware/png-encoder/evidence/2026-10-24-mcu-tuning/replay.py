"""Replay compact compute evidence and explicit hypothetical SD transfer models."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics

HERE=Path(__file__).resolve().parent
RATE=2649960.0
def read(path):return json.loads(path.read_text(encoding='utf-8'))
def sha(raw):return hashlib.sha256(raw).hexdigest()
def pct(values,q):
    values=sorted(values);position=(len(values)-1)*q;lo=int(position);hi=min(lo+1,len(values)-1)
    return values[lo]+(values[hi]-values[lo])*(position-lo)
def stats(values):
    return dict(n=len(values),min=min(values),max=max(values),mean=statistics.mean(values),
                median=statistics.median(values),p95=pct(values,.95))
def pipeline(chunks,hz,rate=RATE):
    if not chunks or hz<=0 or rate<=0:raise ValueError('Positive nonempty model inputs required')
    producer_end=0.;writer_ends=[];prior_bytes=0;prior_cycles=0
    intervals=[]
    for chunk in chunks:
        size=chunk['bytes']-prior_bytes;cost=(chunk['cpu_cycles']-prior_cycles)/hz
        if size<=0 or cost<0:raise ValueError('Nonmonotonic producer intervals')
        producer_end=max(producer_end,writer_ends[-2] if len(writer_ends)>=2 else 0)+cost
        end=max(producer_end,writer_ends[-1] if writer_ends else 0)+size/rate
        writer_ends.append(end);intervals.append(dict(bytes=size,producer_proxy_s=cost,modeled_write_s=size/rate))
        prior_bytes=chunk['bytes'];prior_cycles=chunk['cpu_cycles']
    return writer_ends[-1],intervals

def normalization(report,manifest):
    if manifest.get('miniz_profile') and report['operation']==2:
        assert manifest['scalar_only']
        assert [report['reserved'+str(i)] for i in (0,1,2,46,47)]==[0x4d504631,1,14,1,53]
        assert not any(report['reserved'+str(i)] for i in range(48,53))
    elif manifest['scalar_only']:
        assert not any(report['reserved'+str(i)] for i in range(53))
    else:
        assert manifest.get('mve_conversion')
        assert report['reserved0']&~12==0 and report['reserved1']==0x4d564531
        assert report['reserved2']==0x343b0000 and report['reserved3']==0x343a0000
        if manifest.get('cpacr_policy'):
            assert report['reserved4']==report['reserved5']|0xf00000
            assert report['reserved6']==1 and report['reserved7']==report['reserved5']
            assert not any(report['reserved'+str(i)] for i in range(8,53))
        else:
            assert report['reserved4']&0xf00000==0xf00000
            assert not any(report['reserved'+str(i)] for i in range(5,53))
        if report['operation']==1:assert report['reserved0']==0

def trial(path):
    archive=read(path/'archive.json')
    for item in archive['files']:
        raw=(path/item['archived_path']).read_bytes()
        assert len(raw)==item['bytes'] and sha(raw)==item['sha256'],item['archived_path']
    shared=(path/archive['shared_dependencies']['relative_archive']).resolve()
    for item in archive['shared_dependencies']['files']:
        raw=(shared/item['path']).read_bytes()
        assert len(raw)==item['bytes'] and sha(raw)==item['sha256'],item['path']
    m=read(path/'build/manifest.json');code=(path/'build/bench.bin').read_bytes()
    assert sha(code)==archive['module_sha256']==m['binary_sha256'] and len(code)==m['binary_bytes']
    for name,digest in m['source_hashes'].items():assert sha((path/'build'/name).read_bytes())==digest
    for name in ('ready_park','done_park'):
        offset=int(m[name],0)-int(m['load_address'],0)
        assert code[offset:offset+2]==b'\xfe\xe7'
    spec=importlib.util.spec_from_file_location('archived_compute_protocol',path/archive['protocol_archive_path'])
    protocol=importlib.util.module_from_spec(spec);spec.loader.exec_module(protocol)
    full=read(path/'records/verified.json');plan=read(path/'records/plan.json')
    assert full['runs']==len(full['results']) and full['module_sha256']==archive['module_sha256']
    assert plan['module_sha256']==archive['module_sha256']
    assert full['source_frame_sha256']==plan['frame_sha256']==archive['source_frame_sha256']
    prepare=read(path/'records/prepare/verified.json')
    protocol.validate(prepare['report'],(path/'records/prepare/request.bin').read_bytes())
    normalization(prepare['report'],m)
    assert prepare['final_context']['registers']['PC']==int(m['ready_park'],0)
    assert prepare['final_context']['stack']=={'SP':0x343b0000,'MSP':0x343b0000}
    fixture=read(path/'records/fixture/verified.json')
    assert fixture['raw_sha256']==archive['source_frame_sha256'] and fixture['raw_bytes']==3055360
    assert fixture['high_park_verified_before_and_after'] and fixture['raw_upload_overwrites_retired_low_bridge']
    rows=[]
    for result in full['results']:
        r=result['report'];mode=r['mode'];repeat=result['repeat'];folder=path/'records'/f'mode-{mode}-run-{repeat:02d}'
        verified=read(folder/'verified.json');assert verified==result
        request=(folder/'request.bin').read_bytes()
        protocol.validate(r,request)
        normalization(r,m)
        assert (folder/'completed-request.bin').read_bytes()==request
        snapshots=[protocol.decode(p.read_bytes()) for p in folder.glob('report-*.bin')]
        assert r in snapshots,'No matching raw 512-byte report'
        chunks=protocol.chunks((folder/'chunks.bin').read_bytes(),r['chunk_count'])
        assert chunks==result['chunks'] and chunks[-1]['bytes']==r['output_bytes'] and chunks[-1]['fnv']==r['output_fnv']
        golden=next(g for g in plan['goldens'] if g['mode']==mode)
        assert golden==result['golden'] and golden['exact_pixel_roundtrip'] and golden['independent_decode']
        assert r['output_bytes']==golden['bytes'] and r['output_fnv']==golden['fnv']
        assert result['module_sha256']==archive['module_sha256']
        for key in ('sd_commands','nor_commands','reset_sent','power_changed'):assert not result[key]
        final=result['final_context'];assert final['stack']=={'SP':0x343b0000,'MSP':0x343b0000}
        assert final['registers']['PC']==int(m['done_park'],0) and final['registers']['CONTROL']==0
        assert not final['ccr']&0x30000 and not final['fpccr']&1
        assert final['registers']['XPSR']&0x1ff==0 and final['registers']['PRIMASK']==1 and final['registers']['FAULTMASK']==0
        if m.get('cpacr_policy'):
            assert r['reserved5']==result['initial_context']['cpacr'] and r['reserved7']==final['cpacr']
        for prefix,context in (('before',result['initial_context']),('final',final)):
            for key in ('ccr','fpccr')+ (('cpacr',) if m.get('cpacr_policy') else ()):
                raw=(folder/f'{prefix}-{key}.bin').read_bytes()
                assert len(raw)==4 and int.from_bytes(raw,'little')==context[key]
        hz=r['cpu_hz'];cpu=r['cpu_cycles']/hz;write=r['output_bytes']/RATE
        modeled,intervals=pipeline(chunks,hz)
        fullchunks=[x['producer_proxy_s'] for x in intervals if x['bytes']==32768]
        row=dict(trial=archive['name'],mode=mode,repeat=repeat,png_bytes=r['output_bytes'],
            png_sha256_host=golden['sha256'],png_fnv_target=r['output_fnv'],cpu_s=cpu,
            encode_with_sink_s=r['encode_cycles']/hz,sink_s=r['sink_cycles']/hz,
            phases_s={key:r['png_'+key]/hz for key in ('conversion','deflate','framing','callback','other')},
            producer_interval_proxy_full32k_s=stats(fullchunks),
            producer_interval_proxy_all_s=stats([x['producer_proxy_s'] for x in intervals]),
            modeled_payload_write_s=write,modeled_serial_cpu_plus_write_s=cpu+write,
            modeled_ideal_overlap_s=max(cpu,write),modeled_two_buffer_proxy_s=modeled,
            chunk_producer_proxy_total_s=chunks[-1]['cpu_cycles']/hz)
        if m.get('miniz_profile'):
            decoder=next(p for p in (path/'support').glob('*-decode_profile.py'))
            spec=importlib.util.spec_from_file_location('archived_miniz_profile',decoder)
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            row['miniz_profile']=module.decode([r['reserved'+str(i)] for i in range(53)])
            row['diagnostic_only']=True
        rows.append(row)
    grouped=[]
    for mode in sorted(set(r['mode'] for r in rows)):
        selected=[r for r in rows if r['mode']==mode]
        values=('cpu_s','encode_with_sink_s','sink_s','modeled_payload_write_s',
                'modeled_serial_cpu_plus_write_s','modeled_ideal_overlap_s','modeled_two_buffer_proxy_s')
        grouped.append(dict(mode=mode,png_bytes=selected[0]['png_bytes'],runs=len(selected),
            metrics={key:stats([r[key] for r in selected]) for key in values},
            phases_s={key:stats([r['phases_s'][key] for r in selected])
                      for key in ('conversion','deflate','framing','callback','other')}))
    return dict(name=archive['name'],binary_sha256=archive['module_sha256'],optimization=m['optimization'],
                scalar_only=m['scalar_only'],diagnostic_only=bool(m.get('miniz_profile')),
                runs=rows,groups=grouped,indexed_files=len(archive['files']))

def replay(root=HERE):
    trials=[trial(path.parent) for path in sorted((root/'trials').glob('*/archive.json'))]
    failures=[]
    for index in sorted((root/'failures').glob('*/archive.json')):
        archive=read(index)
        for item in archive['files']:
            raw=(index.parent/item['archived_path']).read_bytes()
            assert len(raw)==item['bytes'] and sha(raw)==item['sha256']
        terminal=read(index.parent/'records/prepare/terminal.json')
        assert terminal['operation']==1 and terminal['state']==3 and terminal['result']!=0
        assert not archive['raw_uploaded'] and not archive['encoder_run'] and not archive['performance_claim']
        failures.append(dict(name=index.parent.name,result=terminal['result'],stage=terminal['stage'],
                             performance_claim=False,module_sha256=archive['module_sha256']))
    recovery=read(root/'initial-recovery/archive.json')
    derived=read(root/'initial-recovery/derived-index.json')
    for item in recovery['files']+derived['files']:
        raw=(root/'initial-recovery'/item['path']).read_bytes()
        assert len(raw)==item['bytes'] and sha(raw)==item['sha256']
    promotion=root/'canonical-promotion/archive.json'
    if promotion.exists():
        index=read(promotion)
        for item in index['files']:
            raw=(promotion.parent/item['archived_path']).read_bytes()
            assert len(raw)==item['bytes'] and sha(raw)==item['sha256']
        promoted=(promotion.parent/'build/bench.bin').read_bytes()
        assert sha(promoted)==index['binary_sha256']
        assert promoted==(root/'trials/pair-o2/build/bench.bin').read_bytes()
    for index_path in sorted((root/'restoration').glob('*/archive.json'))+list((root/'canonical-promotion').glob('encoding-repair/archive.json')):
        index=read(index_path)
        for item in index['files']:
            raw=(index_path.parent/item['archived_path']).read_bytes()
            assert len(raw)==item['bytes'] and sha(raw)==item['sha256']
    if (root/'restoration/final-state.json').exists():
        from final_state import derive
        assert derive(root)==read(root/'restoration/final-state.json')
    return dict(schema=1,passed=True,trials=trials,failed_attempts=failures,modeled_payload_rate_B_s=RATE,
        scope='Fixed uploaded RAW fixture, instrumented compute-only RAM harness, no SD/NOR writes',
        model_limits=['2,649,960 B/s is a prior measured one-bit driver rate, not a simultaneous transfer in these trials',
            'Serial CPU+write and ideal max(CPU,write) omit initialization, metadata, card-busy changes and pipeline setup',
            'Two-buffer simulation uses unscaled measured chunk CPU proxies; no DMA or concurrent hardware transfer was measured',
            'Final CPU excludes the complete PNG callback; chunk CPU excludes only measured sink body and retains callback/timer-edge overhead',
            'Independent host PNG decode metadata and target byte-count/FNV agree; complete target PNG bytes are not archived or downloaded by this harness',
            'No production/full-cycle energy claim; the fixture and other captured imagery are deliberately omitted'])

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path)
    a=p.parse_args();result=replay()
    if a.out:a.out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(passed=result['passed'],trials=[t['name'] for t in result['trials']],
        runs=sum(len(t['runs']) for t in result['trials'])),indent=2))
