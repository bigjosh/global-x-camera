"""Compact production single-frame evidence. No instrument modules are imported.

Use --plan or --check-source offline; --seal only after the bench owner declares
the campaign complete. Native streams/private frames are hash-inventoried
omissions. Python -B keeps standalone archive verification non-mutating.
"""
import argparse
import gzip
import importlib.util
import json
from pathlib import Path
import re
import struct

SOURCE=Path(__file__).resolve().parent
ROOT=SOURCE.parents[2]
BASE_REL='tmp/bringup/sd-gap-20261028/archive_gap.py'
basepath=ROOT/BASE_REL
if not basepath.is_file():basepath=SOURCE/'support'/BASE_REL
spec=importlib.util.spec_from_file_location('single_frame_archive_mechanics',basepath)
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
DESTINATION=ROOT/'firmware/capture-raw/evidence/2026-10-28-sensor-single-frame'
BUILDS=('flash-awake-v3','flash-standby-v1','design/read-helper')
EXPECTED={
    'flash-awake-v3':dict(receiver='298a65b0ab2a00a6256826604bf0ebb0656922ee84c3ebe1237c35666ddf3f60',
        prefix='5330f1d1f606fb9dfd903dbdc39dac282360b1880d756931049eec1797ef6504',
        sector='185d86f0cf2a17c6b1e81880c1ec0b3263e318d477701fa57496cb72cf706638'),
    'flash-standby-v1':dict(receiver='560a8734306436fe95bc1407031e70f1bc5b448949366e1bd007779c1736f646',
        prefix='6378483a91b560ffc6b31d74a9dd1205996a14c8030447ffddf7deddc9d23874',
        sector='79a379470927135bc03841098fe070912cad8275e91c5d5985cc066c294cf64e'),
    'design/read-helper':dict(receiver='ef85e7106b3cb0cb253fe4a174e926a1bd227c006b7bfa46ab0433a1496ae000')}
SUPPORT=(BASE_REL,'firmware/capture-raw/bench.py','firmware/capture-raw/inspect_flash.py',
    'firmware/capture-raw/build.py','firmware/capture-raw/late_build.py',
    'firmware/capture-raw/single_frame_prefix.py','firmware/capture-raw/sensor_autostop_transform.py',
    'firmware/capture-raw/sensor_autostop.inc','firmware/capture-raw/magic_runtime.inc',
    'firmware/capture-raw/board_eth_powerdown.inc','firmware/capture-raw/error_build.py',
    'firmware/capture-raw/test_autostop_bench.py','firmware/capture-raw/test_inspect_flash.py',
    'firmware/capture-raw/test_sensor_single_frame.py','firmware/capture-timing/recovery_gpio/check_park.py',
    'firmware/capture-raw/evidence/2026-10-28-ethernet-powerdown/flash-candidate/staged/stage1.bin',
    'firmware/capture-sd/low_power/readback_recovery/run.py',
    'tmp/bringup/sd-fourbit-20261024/magic_readback.py',
    'tmp/bringup/ethernet-normal-20261028/cold_logger.py',
    'tmp/bringup/ethernet-normal-20261028/analysis/analyze_cycles.py',
    'tmp/bringup/power-ablation-20261028/analyze_warm_ablations.py',
    'tmp/bringup/power-ablation-20261028/analyze_existing_baseline.py',
    'tmp/bringup/sensor-autostop-20261028/analysis/analyze_cold.py',
    'tmp/bringup/sd125-negedge-20261026/uart_recover.py',
    'tmp/bringup/error-blinks-20261026/install.py')
readj=base.readj;sha=base.sha


def tests(source):
    t=readj(source/'offline-tests.json')
    assert t['passed'] is True and t['returncode']==0 and t['changed_sources']==[]
    assert t['source_hashes']==t['source_hashes_after']
    assert sha(source/'offline-tests.log')==t['log_sha256']
    match=re.search(r'Ran (\d+) tests\b',(source/'offline-tests.log').read_text())
    assert match and int(match[1])>=250
    return t


def inventory(source,root,hashes):
    """Same exact-byte inventory, with the broader final source-bound ledger."""
    entries=[]
    for path in sorted(source.rglob('*')):
        if path.is_symlink():raise ValueError('Archive refuses symbolic links: '+str(path))
        if not path.is_file():continue
        rel=path.relative_to(source)
        if rel.as_posix() in base.GENERATED or rel.parts[0]=='support':
            raise ValueError('Reserved archive path in campaign: '+str(rel))
        size,mtime=base.stamp(path)
        if rel.name in ('stage1.elf','stage1-unrelocated.elf') and 'staged' in rel.parts:
            action,reason='copy','ELF-mapped stage-one CRC literal proof'
        else:action,reason=base.disposition(rel,size)
        item=dict(source=str(path),path=rel.as_posix(),bytes=size,mtime_ns=mtime,
            action=action,reason=reason,origin='campaign')
        if hashes:item['sha256']=sha(path)
        entries.append(item)
    for name in base.SUPPORT:
        path=base.checked_path(root,name)
        if not path.is_file():raise FileNotFoundError(path)
        size,mtime=base.stamp(path)
        item=dict(source=str(path),path='support/'+name,bytes=size,mtime_ns=mtime,
            action='copy',reason=None,origin='dependency')
        if hashes:item['sha256']=sha(path)
        entries.append(item)
    names=[v['path'] for v in entries]
    assert len(names)==len(set(names))
    assert sum(v['bytes'] for v in entries if v['action']!='omit')<base.MAX_BYTES
    return entries


def image_validations(source):
    results=[]
    for folder in ('awake-readback','cold-images-readback'):
        partial=folder=='cold-images-readback'
        summary=readj(source/folder/('partial-summary.json' if partial else 'summary.json'))
        if partial:
            assert summary['status']=='stopped_at_user_request' and summary['full_campaign_passed'] is False
            expected=[item['slot'] for item in summary['completed_slots']]
        else:
            assert summary['passed'] is True
            expected=[item['slot'] for item in summary['slots']]
        found=[]
        for path in sorted((source/folder).rglob('readback-validation.json')):
            v=readj(path)
            assert all(v.get(key) is True for key in ('passed','full_slot_read','full_payload_read','png_samples_match_read_raw'))
            assert v['bytes']==1909600 and v['slot_bytes']==1909760
            if folder=='awake-readback':
                assert v['original_sensor_frame_comparison'] is True
                assert v['source_reference_comparison']['bytes_equal'] is True
            found.append(v['slot']);results.append((path,v))
        assert sorted(found)==sorted(expected)
        assert sorted(found)==([142] if not partial else [143,144])
    assert len({v['slot'] for _,v in results})==3
    return results


def partial_readback(source):
    """Bind successful chunks without promoting the interrupted slot to a pass."""
    summary=readj(source/'cold-images-readback/partial-summary.json')
    assert summary['status']=='stopped_at_user_request' and summary['full_campaign_passed'] is False
    assert summary['incomplete_slot']==145 and summary['verified_sectors_in_incomplete_slot']==2560
    assert summary['slot_sectors']==3730 and len(summary['completed_chunks'])==5
    for index,item in enumerate(summary['completed_chunks']):
        path=base.checked_path(source,item['path']);assert sha(path)==item['sha256']
        v=readj(path);p=v['proof']
        assert v['passed'] is True and v['binary_sha256']==EXPECTED['design/read-helper']['receiver']
        assert p['nonce']!=0 and p['operation']==3 and p['state']==3
        assert p['result']==p['cleanup_error']==0 and p['media_idle']==1
        words=v['request_words']
        assert words[3]==145*3730+index*512 and words[4]==512
    assert summary['last_completed_operation']==summary['completed_chunks'][-1]
    for item in summary['completed_slots']:
        assert sha(base.checked_path(source,item['validation']['path']))==item['validation']['sha256']
    failed=summary['last_debug_call']
    assert sha(base.checked_path(source,failed['path']))==failed['sha256']
    interrupted=source/summary['interrupted_operation']
    assert not (interrupted/'verified.json').exists()
    assert not (source/'cold-images-readback/slot-145/readback-validation.json').exists()
    return dict(slot=145,verified_sectors=2560,total_sectors=3730,
        full_image_verified=False,user_requested_stop=True,
        interrupted_operation=summary['interrupted_operation'])


def gates(source):
    final=readj(source/'final-state.json')
    assert final['completed'] is True and final['active_helpers'] is False
    assert final['tests_stopped_at_user_request'] is True
    assert final['final_cold_boot_performed'] is False and final['final_photo_readback_performed'] is False
    assert final['cold_full_readback_slots']==[143,144] and final['cold_partial_readback_slot']==145
    assert final['cold_partial_sectors']==2560 and final['awake_source_equal_slot']==142
    assert final['sensor_single_frame_installed'] is True and final['nor_programming'] is True
    assert final['receiver_sha256']==EXPECTED['flash-standby-v1']['receiver']
    assert final['prefix_sha256']==EXPECTED['flash-standby-v1']['prefix']
    assert final['sector_sha256']==EXPECTED['flash-standby-v1']['sector']
    tests(source)
    awake=readj(source/'awake-inspect/verified.json')
    assert awake['passed'] is True and awake['kind']=='raw-flash-inspection'
    assert awake['proof']['nonce']==0 and awake['proof']['operation']==1
    ast=awake['sensor_autostop']
    assert ast['production_single_frame'] is True and ast['version']==2
    assert ast['completed'] is True and ast['exact_one_frame_observed'] is True
    assert ast['sensor_count_from_reset']==ast['strobe_delta']==1 and ast['explicit_stop_writes']==0
    paths=['REPORT.md','final-state.json','offline-tests.json','offline-tests.log',
        'awake-offline-audit.json','standby-offline-audit.json','awake-inspect/verified.json',
        'awake-readback/summary.json','cold-images-readback/partial-summary.json']
    standby=readj(source/'candidate-standby-flags/result.json')
    assert standby['passed'] is True and standby['sbf'] is True and standby['pdds'] is True
    assert standby['stopf'] is False and standby['trial_entry_proven'] is False
    assert standby['prefix_sha256']==EXPECTED['flash-standby-v1']['prefix']
    assert all(standby[key] is False for key in ('cpucr_written','reset_or_power_changed','ram_writes','nor_commands'))
    paths.append('candidate-standby-flags/result.json')
    comparison=readj(source/'analysis/cold-promotion-comparison.json')
    rows={v['run']:v for v in comparison['runs']}
    assert set(rows)=={'control-before','candidate01','candidate02','candidate03'}
    paths.append('analysis/cold-promotion-comparison.json')
    for name in ('candidate01','candidate02','candidate03'):
        rel='analysis/'+name+'-analysis.json';report=readj(source/rel)
        assert report['all_expected_markers_observed'] is True
        assert report['single_external_exposure_envelope_observed'] is True
        assert report['exposure_envelopes_end_before_frame_IRQ'] is True
        assert report['no_external_exposure_edges_between_standby_observed_and_commit'] is True
        ids=[v['id'] for v in report['marker_events']]
        assert len(ids)==11 and set(ids)==set(range(1,12)) and ids.index(3)<ids.index(11)<ids.index(8)
        assert rows[name]['analysis_sha256']==sha(source/rel)
        logger=readj(source/name/'trace/result.json')
        assert logger['success'] is True and not logger['errors'] and not logger['cleanup_errors']
        paths.extend((rel,name+'/trace/result.json'))
    images=image_validations(source)
    partial=partial_readback(source)
    assert images[0][1]['slot']==awake['proof']['slot']
    paths.extend(path.relative_to(source).as_posix() for path,_ in images)
    for name,build in (('install-awake','flash-awake-v3'),('install-standby','flash-standby-v1')):
        install=readj(source/name/'complete.json')
        assert all(install.get(k) is True for k in ('passed','independent_full_readback','following4096_unchanged'))
        assert install['new_sector_sha256']==EXPECTED[build]['sector']
        paths.append(name+'/complete.json')
    for item in final['evidence']:
        assert sha(base.checked_path(source,item['path']))==item['sha256']
        if item['path'] not in paths:paths.append(item['path'])
    return dict(passed=True,verified_slots=[v['slot'] for _,v in images],partial_readback=partial,
        gates=[dict(path=n,sha256=sha(source/n)) for n in paths],
        scope='One cold-awake exact-one AST2 proof with original-frame equality, three measured Standby cycles, '
              'two full cold-image readbacks and 2560/3730 sectors of a third, two exact NOR installations, '
              'and the bench owner\'s user-requested stop. No final normal boot or verified final execution state is implied.')


def audit(archive,support_root=None):
    support=Path(support_root) if support_root is not None else archive/'support'
    ledger=tests(archive)
    source_hashes=ledger.get('source_hashes',ledger.get('sources_sha256'))
    assert source_hashes
    for name,digest in source_hashes.items():assert sha(base.checked_path(support,name))==digest,name
    host=base.frozen_functions(support/'firmware/capture-raw/bench.py',
        ('board_eth_layout','board_eth_snapshot','sd_init_gap_layout','sd_init_gap_snapshot',
         'sensor_autostop_layout','sensor_autostop_record','sensor_autostop_snapshot'),
        ('SD_INIT_GAP_FIELDS','SENSOR_AUTOSTOP_FIELDS'),dict(struct=struct,LOAD=0x34300000))
    by_hash={};builds={}
    for name in BUILDS:
        folder=archive/name;m=readj(folder/'manifest.json');code=(folder/'capture.bin').read_bytes()
        assert base.sha_bytes(code)==m['binary_sha256']==EXPECTED[name]['receiver']
        assert len(code)==m['binary_bytes'] and struct.unpack_from('<II',code)==(m['stack'],m['entry'])
        for fn,digest in m['source_hashes'].items():assert sha(base.checked_path(folder,fn))==digest
        assert host['sensor_autostop_layout'](m,1) is (name!='design/read-helper')
        if m['flash']:
            staged=folder/'staged';pm=readj(staged/'manifest.json')
            assert sha(staged/'stage1.bin')==EXPECTED[name]['prefix']
            assert sha(staged/'capture_sector_0.bin')==EXPECTED[name]['sector']
            for fn,digest in pm['sources'].items():assert sha(staged/Path(fn).name)==digest
            assert pm['stage2_manifest_sha256']==sha(folder/'manifest.json')
            assert (staged/'stage2-full.bin').read_bytes()==code
            prefix=(staged/'stage1.bin').read_bytes();unrel=(staged/'stage1-unrelocated.bin').read_bytes()
            reference=(support/'firmware/capture-raw/evidence/2026-10-28-ethernet-powerdown/flash-candidate/staged/stage1.bin').read_bytes()
            assert base.sha_bytes(reference)=='2b9724bc4b60af52b1c4ab45e1b232578e9640efc3a30a57772a810d99c3f344'
            assert prefix[:0x67A]==reference[:0x67A]
            for offset in range(0x67C,0x6CC,4):assert prefix[offset:offset+4]==reference[offset:offset+4]
            assert base.sha_bytes(unrel)=='41216a3b2f921e80f401da7cb82806e350149c50fc132c2266ae3706dd2c2de7'
            normalized=bytearray(prefix)
            for offset in (0xC9C,0x1358):struct.pack_into('<I',normalized,offset,0x3E97C7F7)
            assert normalized==unrel
            # Retain and independently bind the two changed ELF data words;
            # no instruction/section/symbol bytes may change during relocation.
            elf=(staged/'stage1.elf').read_bytes();oldelf=(staged/'stage1-unrelocated.elf').read_bytes()
            assert elf[:6]==b'\x7fELF\x01\x01' and len(elf)==len(oldelf)
            shoff=struct.unpack_from('<I',elf,32)[0]
            entsize,count=struct.unpack_from('<HH',elf,46);assert entsize==40
            restored=bytearray(elf)
            for offset in (0xC9C,0x1358):
                address=0x34180400+offset;locations=[]
                for index in range(count):
                    section=struct.unpack_from('<10I',elf,shoff+index*entsize)
                    _,kind,flags,start,at,length,*_=section
                    if kind!=8 and flags&2 and start<=address and address+4<=start+length:
                        locations.append(at+address-start)
                assert len(locations)==1;at=locations[0]
                assert elf[at:at+4]==prefix[offset:offset+4]
                assert oldelf[at:at+4]==unrel[offset:offset+4]
                restored[at:at+4]=oldelf[at:at+4]
            assert restored==oldelf
            assert pm['checked_recovery_literal_offsets']==list(range(0x67C,0x6CC,4))
            assert base.sha_bytes(prefix[0x1440:0x1A40])=='247ad0ddd76963039ed01a2e14beb3499ee9097a8df86f62ad5751047835454e'
        builds[name]=dict(sha256=m['binary_sha256'],bytes=len(code),sources=len(m['source_hashes']))
        by_hash[m['binary_sha256']]=(folder,m)
    replays=[]
    for path in sorted(archive.rglob('verified.json')):
        v=readj(path)
        if v.get('binary_sha256') not in by_hash or 'board_eth' not in v:continue
        assert v['passed'] is True
        folder,m=by_hash[v['binary_sha256']];p=v['proof']
        cold=v.get('kind')=='raw-flash-inspection'
        choices=(path.parent/'inspection',) if cold else (path.parent/'bootstrap',path.parent/'operation')
        terminal_name='proof-final.bin' if cold else 'final-proof.bin'
        record=[d for d in choices if (d/terminal_name).exists()]
        assert len(record)==1,str(path)
        record=record[0]
        header=(folder/'runtime.h').read_text()
        enum=header[header.index(' RP_MAGIC,'):header.index('};',header.index(' RP_MAGIC,'))]
        names=[n.lower() for n in re.findall(r'\bRP_([A-Z0-9_]+)\b',enum)]
        names+=['reserved_'+str(i) for i in range(len(names),96)]
        terminal=dict(zip(names,struct.unpack('<96I',(record/terminal_name).read_bytes())))
        assert all(terminal[k]==value for k,value in p.items())
        assert p['state']==3 and p['result']==p['cleanup_error']==0 and p['media_idle']==1
        assert p['nonce']==0 if cold else p['nonce']!=0
        prefix='before' if cold else 'completed'
        class Frozen:
            def upload(self,address,size,label):
                files={m['board_eth_proof']:prefix+'-board-eth.bin'}
                if m.get('sensor_autostop'):
                    files[m['sensor_autostop_proof']]=prefix+'-sensor-autostop.bin'
                raw=(record/files[address]).read_bytes();assert len(raw)==size;return raw
        ast=host['sensor_autostop_snapshot'](Frozen(),m,p,'replay')
        eth=host['board_eth_snapshot'](Frozen(),m,p,'replay')
        assert ast==v.get('sensor_autostop') and eth==v['board_eth']
        replays.append(dict(path=path.relative_to(archive).as_posix(),cold=cold,operation=p['operation'],
            exact_one_frame_observed=ast.get('exact_one_frame_observed') if ast else None))
    assert sum(v['cold'] and v['exact_one_frame_observed'] for v in replays)==1
    assert any(v['operation']==3 for v in replays)
    nor=[]
    for name in ('install-awake','install-standby'):
        folder=archive/name;v=readj(folder/'complete.json')
        assert sha(folder/'nor-before/readback.bin')==v['old_sector_sha256']
        assert sha(folder/'nor-after/readback.bin')==v['new_sector_sha256']
        assert (folder/'following-before/readback.bin').read_bytes()==(folder/'following-after/readback.bin').read_bytes()
        nor.append(name+'/complete.json')
    inventory=archive/'archive-source-inventory.json'
    norm=lambda p:str(p).replace('\\','/').casefold()
    identities={norm(v['source']):v['sha256'] for v in readj(inventory)['files']} if inventory.exists() else None
    def linked(item):
        digest=identities[norm(item['path'])] if identities is not None else sha(Path(item['path']))
        assert digest==item['sha256'],item['path']
    analysis_sources=readj(archive/'analysis/analysis-sources.json')
    for path,digest in analysis_sources.items():linked(dict(path=path,sha256=digest))
    images=[]
    for path,v in image_validations(archive):
        for item in v['artifacts']:linked(item)
        if v.get('source_reference_comparison'):linked(v['source_reference_comparison']['source'])
        linked(v['scr_source']['proof']);linked(v['scr_source']['scr_binary'])
        images.append(dict(path=path.relative_to(archive).as_posix(),slot=v['slot'],raw_sha256=v['raw_sha256'],
            full_original_frame_equality=v['original_sensor_frame_comparison'],
            png_samples_match_read_raw=True))
    missing=[]
    for target in re.findall(r'\]\(([^)]+)\)',(archive/'REPORT.md').read_text()):
        target=target.split('#',1)[0].strip('<>')
        if not target or re.match(r'^[a-zA-Z]+:',target) or target.startswith('/'):continue
        if not (archive/target).is_file():missing.append(target)
    assert not missing,missing
    return dict(passed=True,builds=builds,replayed_ast_and_eth_proofs=replays,nor_verifications=nor,
        readback_validation_identity=images,relative_report_links_resolve=True,
        analysis_source_chain_verified=len(analysis_sources),
        scope='Pure frozen AST2/ETH validators, exact compiled sources/prefixes and retained physical NOR reads. '
              'Private image decoding and native current integration require omitted local payloads.')


def verify(destination):
    manifest=readj(destination/'manifest.json');expected=set()
    for item in manifest['files']:
        path=base.checked_path(destination,item['path']);expected.add(item['path'])
        assert path.is_file() and path.stat().st_size==item['bytes'] and sha(path)==item['sha256']
    actual={p.relative_to(destination).as_posix() for p in destination.rglob('*') if p.is_file()}
    assert actual==expected|{'manifest.json'}
    assert (destination/'README.md').read_bytes()==(destination/'REPORT.md').read_bytes()
    for item in readj(destination/'archive-source-inventory.json')['files']:
        if item['action']=='omit':continue
        path=base.checked_path(destination,item['path']+('.gz' if item['action']=='gzip' else ''))
        raw=gzip.decompress(path.read_bytes()) if item['action']=='gzip' else path.read_bytes()
        assert len(raw)==item['bytes'] and base.sha_bytes(raw)==item['sha256']
    assert gates(destination)==readj(destination/'archive-gates.json')
    result=audit(destination);assert result==readj(destination/'archive-audit.json')
    return dict(passed=True,files=len(manifest['files']),bytes=sum(v['bytes'] for v in manifest['files']),
        proof_replays=len(result['replayed_ast_and_eth_proofs']))


def setup():
    dependencies=set(SUPPORT)
    if (SOURCE/'offline-tests.json').exists():
        ledger=readj(SOURCE/'offline-tests.json')
        dependencies.update(ledger.get('source_hashes',ledger.get('sources_sha256',{})))
    base.SUPPORT=tuple(sorted(dependencies));base.seal_gates=gates;base.audit=audit;base.verify=verify
    base.inventory=inventory


def main():
    ap=argparse.ArgumentParser(description=__doc__);mode=ap.add_mutually_exclusive_group()
    mode.add_argument('--plan',action='store_true');mode.add_argument('--check-source',action='store_true')
    mode.add_argument('--seal',action='store_true');mode.add_argument('--verify',type=Path)
    args=ap.parse_args()
    if args.verify:result=verify(args.verify.resolve())
    else:
        setup()
        if args.check_source:gates(SOURCE);result=audit(SOURCE,ROOT)
        elif args.seal:
            evidence=(ROOT/'firmware/capture-raw/evidence').resolve()
            DESTINATION.resolve().relative_to(evidence)
            DESTINATION.with_name(DESTINATION.name+'.partial').resolve().relative_to(evidence)
            result=base.seal(SOURCE,ROOT,DESTINATION)
        else:
            entries=base.inventory(SOURCE,ROOT,hashes=False)
            result=dict(read_only=True,files=len(entries),destination=str(DESTINATION),
                retained_files=sum(v['action']!='omit' for v in entries),
                retained_uncompressed_bytes=sum(v['bytes'] for v in entries if v['action']!='omit'),
                omitted_files=sum(v['action']=='omit' for v in entries))
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
