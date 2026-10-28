"""Offline compact AST1 archive, using the prior exact-byte archive mechanics.

--plan is read-only. Seal only after the bench owner finishes the campaign.
Native streams and private image/SD bytes are inventoried omissions. This
helper imports only an offline archive module, never an instrument module.
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
spec=importlib.util.spec_from_file_location('offline_archive_mechanics',basepath)
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
DESTINATION=ROOT/'firmware/capture-raw/evidence/2026-10-28-sensor-autostop'
BUILDS=('ram-auto-v2','ram-default-final','flash-default-final')
PAIRS=(('ram-auto01','ram-readback'),('ram-auto02','ram-auto02-readback'))
SUPPORT=(BASE_REL,'firmware/capture-raw/bench.py','firmware/capture-raw/build.py',
    'firmware/capture-raw/runtime.c','firmware/capture-raw/runtime.h',
    'firmware/capture-raw/sensor_autostop.inc','firmware/capture-raw/sensor_autostop_transform.py',
    'firmware/capture-raw/magic_runtime.inc','firmware/capture-raw/late_build.py',
    'firmware/capture-raw/test_autostop_bench.py','firmware/capture-raw/test_sensor_autostop.py',
    'firmware/capture-raw/board_eth_powerdown.inc',
    'tmp/bringup/sd-fourbit-20261024/magic_readback.py',
    'tmp/bringup/power-ablation-20261028/aligned_logger.py',
    'tmp/bringup/power-ablation-20261028/analyze_warm_ablations.py',
    'tmp/bringup/ethernet-normal-20261028/cold_logger.py',
    'tmp/bringup/ethernet-normal-20261028/analysis/analyze_cycles.py',
    'tmp/bringup/sd125-negedge-20261026/uart_recover.py',
    'firmware/capture-timing/recovery_gpio/check_park.py',
    'firmware/capture-sd/low_power/readback_recovery/run.py')
base.BUILD_NAMES=BUILDS
readj=base.readj
sha=base.sha
frozen_functions=base.frozen_functions


def tests(source):
    stem='host-final-offline-tests' if (source/'host-final-offline-tests.json').exists() else 'host-offline-tests'
    t=readj(source/(stem+'.json'))
    assert t.get('passed') is True and t.get('sources_unchanged') is True and t.get('returncode')==0
    assert sha(source/(stem+'.log'))==t['log_sha256']
    count=re.search(r'Ran (\d+) tests\b',(source/(stem+'.log')).read_text())
    assert count and int(count[1])>=249
    t['archive_ledger_stem']=stem
    return t


def gates(source):
    assert (source/'REPORT.md').is_file()
    final=readj(source/'final-state.json')
    assert final.get('completed') is True and final.get('normal_unchanged') is True
    assert final.get('nor_programming') is False and final.get('active_helpers') is False
    assert final.get('sensor_autostop_installed') is False and final.get('cold_sensor_autostop_qualified') is False
    stem=tests(source)['archive_ledger_stem']
    paths=['REPORT.md','final-state.json',stem+'.json',stem+'.log',
           'ram-v2-offline-audit.json']
    observed=[]
    for run,reader in PAIRS:
        capture=readj(source/run/'capture/verified.json')
        assert capture['passed'] is True and capture['proof']['operation']==1
        assert capture['sensor_autostop']['completed'] is True
        assert capture['sensor_autostop']['exact_one_frame_observed'] is True
        assert capture['sensor_autostop']['sensor_delta']==capture['sensor_autostop']['strobe_delta']==1
        slot=capture['proof']['slot'];observed.append(slot)
        summary=readj(source/reader/'summary.json')
        assert summary['passed'] is True and [x['slot'] for x in summary['slots']]==[slot]
        validation=readj(source/reader/'readback-validation.json')
        assert validation['slot']==slot
        assert all(validation.get(k) is True for k in ('passed','full_slot_read','full_payload_read',
            'original_sensor_frame_comparison','png_samples_match_read_raw'))
        assert validation['source_reference_comparison']['bytes_equal'] is True
        paths.extend((run+'/capture/verified.json',reader+'/summary.json',reader+'/readback-validation.json'))
    assert len(set(observed))==2
    assert observed==final['verified_sensor_slots']
    for item in final['evidence']:
        assert sha(base.checked_path(source,item['path']))==item['sha256'],item['path']
        if item['path'] not in paths:paths.append(item['path'])
    return dict(passed=True,slots=observed,gates=[dict(path=n,sha256=sha(source/n)) for n in paths],
        scope='Two recorded warm RAM auto-stop captures and complete original-frame readback; '
              'normal FLASH unchanged. No cold auto-stop or final normal photo readback is implied.')


def audit(archive,support_root=None):
    support=Path(support_root) if support_root is not None else archive/'support'
    for name,digest in tests(archive)['source_hashes'].items():
        assert sha(base.checked_path(support,name))==digest,name
    host=frozen_functions(support/'firmware/capture-raw/bench.py',
        ('board_eth_layout','board_eth_snapshot','sd_init_gap_layout','sd_init_gap_snapshot',
         'sensor_autostop_layout','sensor_autostop_record','sensor_autostop_snapshot'),
        ('SD_INIT_GAP_FIELDS','SENSOR_AUTOSTOP_FIELDS'),dict(struct=struct,LOAD=0x34300000))
    builds={};by_hash={}
    for name in BUILDS:
        folder=archive/'design'/name;m=readj(folder/'manifest.json');code=(folder/'capture.bin').read_bytes()
        assert base.sha_bytes(code)==m['binary_sha256'] and len(code)==m['binary_bytes']
        assert struct.unpack_from('<II',code)==(m['stack'],m['entry'])
        for fn,digest in m['source_hashes'].items():assert sha(base.checked_path(folder,fn))==digest,(name,fn)
        assert host['sensor_autostop_layout'](m,1) is (name=='ram-auto-v2')
        builds[name]=dict(sha256=m['binary_sha256'],bytes=len(code),sources=len(m['source_hashes']))
        by_hash[m['binary_sha256']]=(folder,m)
    assert builds['ram-auto-v2']['sha256']=='5bf9e515bb28d74efa3cdee21c9a9f373fedbc3c36b73dd954e136f6df348e65'
    for name,digest in base.NORMAL.items():assert sha(archive/'design/flash-default-final'/name)==digest
    replay=[]
    for path in sorted(archive.rglob('verified.json')):
        v=readj(path)
        if 'sensor_autostop' not in v:continue
        assert v['passed'] is True
        folder,m=by_hash[v['binary_sha256']];p=v['proof']
        records=[d for d in (path.parent/'bootstrap',path.parent/'operation') if (d/'final-proof.bin').exists()]
        assert len(records)==1,str(path)
        record=records[0];header=(folder/'runtime.h').read_text()
        enum=header[header.index(' RP_MAGIC,'):header.index('};',header.index(' RP_MAGIC,'))]
        names=[n.lower() for n in re.findall(r'\bRP_([A-Z0-9_]+)\b',enum)]
        names+=['reserved_'+str(i) for i in range(len(names),96)]
        terminal=dict(zip(names,struct.unpack('<96I',(record/'final-proof.bin').read_bytes())))
        assert all(terminal[k]==value for k,value in p.items())
        assert p['state']==3 and p['result']==p['cleanup_error']==0 and p['media_idle']==1
        class Frozen:
            def upload(self,address,size,label):
                names={m['sensor_autostop_proof']:'completed-sensor-autostop.bin',
                       m['sensor_autostop_prestart']:'completed-sensor-prestart.bin',
                       m['board_eth_proof']:'completed-board-eth.bin'}
                raw=(record/names[address]).read_bytes();assert len(raw)==size;return raw
        ast=host['sensor_autostop_snapshot'](Frozen(),m,p,'replay')
        eth=host['board_eth_snapshot'](Frozen(),m,p,'replay')
        assert ast==v['sensor_autostop'] and eth==v['board_eth']
        replay.append(dict(path=path.relative_to(archive).as_posix(),operation=p['operation'],
            completed=ast['completed'],sensor_delta=ast.get('sensor_delta'),strobe_delta=ast.get('strobe_delta'),
            exact_one_frame_observed=ast.get('exact_one_frame_observed')))
    assert sum(v['operation']==1 and v['completed'] for v in replay)==2
    assert any(v['operation']==3 and not v['completed'] for v in replay)
    # Match private bytes to their sealed inventory without publishing them.
    inventory=archive/'archive-source-inventory.json'
    norm=lambda p:str(p).replace('\\','/').casefold()
    identity={norm(v['source']):v['sha256'] for v in readj(inventory)['files']} if inventory.exists() else None
    def linked(record):
        actual=identity[norm(record['path'])] if identity is not None else sha(Path(record['path']))
        assert actual==record['sha256'],record['path']
    readbacks=[]
    for _,reader in PAIRS:
        v=readj(archive/reader/'readback-validation.json')
        assert v['bytes']==1909600 and v['slot_bytes']==1909760
        for item in v['artifacts']:linked(item)
        linked(v['source_reference_comparison']['source'])
        linked(v['scr_source']['proof']);linked(v['scr_source']['scr_binary'])
        assert v['source_reference_comparison']['bytes_equal'] is True
        readbacks.append(dict(path=reader+'/readback-validation.json',slot=v['slot'],
            raw_sha256=v['raw_sha256'],slot_sha256=v['slot_sha256'],png_sha256=v['png_sha256'],
            full_original_frame_equality=True,recorded_independent_png_decoding=True))
    # Relative chart/file links must resolve in the root archive layout.
    missing=[]
    for target in re.findall(r'\]\(([^)]+)\)',(archive/'REPORT.md').read_text()):
        target=target.split('#',1)[0].strip('<>')
        if not target or re.match(r'^[a-zA-Z]+:',target) or target.startswith('/'):continue
        if not (archive/target).is_file():missing.append(target)
    assert not missing,missing
    return dict(passed=True,builds=builds,replayed_ast_and_eth_proofs=replay,
        readback_validation_identity=readbacks,disabled_normal_identity=True,relative_report_links_resolve=True,
        scope='Pure frozen AST1/ETH validator replays, exact binary/source hashes and recorded full-image '
              'validation identity. Native current integration and private image decoding require local omitted bytes. '
              'The historical storage_overlap text in RAMv2 manifest is corrected in REPORT; no gap was inserted.')


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


def setup(source,root):
    dependencies=set(SUPPORT)
    testfile=source/'host-final-offline-tests.json'
    if not testfile.exists():testfile=source/'host-offline-tests.json'
    if testfile.exists():
        for name,digest in readj(testfile)['source_hashes'].items():
            dependencies.add(name)
    base.SUPPORT=tuple(sorted(dependencies));base.seal_gates=gates;base.audit=audit;base.verify=verify


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--plan',action='store_true')
    mode.add_argument('--check-source',action='store_true')
    mode.add_argument('--seal',action='store_true')
    mode.add_argument('--verify',type=Path)
    args=parser.parse_args()
    if args.verify:
        result=verify(args.verify.resolve())
    else:
        setup(SOURCE,ROOT)
        if args.check_source:
            gates(SOURCE);result=audit(SOURCE,ROOT)
        elif args.seal:
            # Verify both directory-rename endpoints are inside the explicit
            # evidence workspace before the inherited atomic seal operation.
            evidence=(ROOT/'firmware/capture-raw/evidence').resolve()
            DESTINATION.resolve().relative_to(evidence)
            DESTINATION.with_name(DESTINATION.name+'.partial').resolve().relative_to(evidence)
            result=base.seal(SOURCE,ROOT,DESTINATION)
        else:
            entries=base.inventory(SOURCE,ROOT,hashes=False)
            result=dict(read_only=True,files=len(entries),destination=str(DESTINATION),
                retained_files=sum(v['action']!='omit' for v in entries),
                retained_uncompressed_bytes=sum(v['bytes'] for v in entries if v['action']!='omit'),
                omitted_files=sum(v['action']=='omit' for v in entries),
                gates='Require completed final state, two warm AST1 successes and full original-frame equality')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
