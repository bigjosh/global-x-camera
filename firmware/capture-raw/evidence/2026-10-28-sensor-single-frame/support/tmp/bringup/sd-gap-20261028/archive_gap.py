"""Offline compact archive: --plan is read-only; --seal is explicitly gated.

Do not seal until the bench owner says the campaign is finished. --verify
replays identity and GAP/ETH proof checks using only frozen files and stdlib;
it never imports an instrument API. Native streams/private image bytes remain
local and are SHA-256 inventoried, so their numerical analysis/image decoding
cannot be recomputed from this compact archive alone.
"""
import argparse
import ast
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import zlib

SOURCE = Path(__file__).resolve().parent
ROOT = SOURCE.parents[2]
DESTINATION = ROOT/'firmware/capture-raw/evidence/2026-10-28-sd-init-gap'
MAX_BYTES = 100 * 1024**2
BUILD_NAMES = ('ram-gap', 'flash-gap', 'flash-default')
NORMAL = {
    'capture.bin': '69c5a5c0cc434eb7496371d9e5b9c007db346b8bb7b9a1a650c90f0eade79d28',
    'staged/stage1.bin': '2b9724bc4b60af52b1c4ab45e1b232578e9640efc3a30a57772a810d99c3f344',
    'staged/capture_sector_0.bin': 'a10e4894d79cd3fe182b95b48eb56a308280f3201736d295860ecfe725a62645',
}
SUPPORT = (
    'firmware/capture-raw/bench.py', 'firmware/capture-raw/build.py',
    'firmware/capture-raw/late_build.py', 'firmware/capture-raw/runtime.c',
    'firmware/capture-raw/runtime.h', 'firmware/capture-raw/magic_runtime.inc',
    'firmware/capture-raw/sd_init_gap.inc', 'firmware/capture-raw/board_eth_powerdown.inc',
    'firmware/capture-raw/test_sd_init_gap.py', 'firmware/capture-raw/test_sd_init_gap_bench.py',
    'firmware/capture-raw/test_board_eth_powerdown.py', 'firmware/capture-raw/test_board_eth_bench.py',
    'firmware/capture-raw/test_bench.py', 'firmware/capture-sd/build.py',
    'firmware/capture-timing/recovery_gpio/check_park.py',
    'firmware/capture-sd/low_power/readback_recovery/run.py',
    'firmware/capture-sd/low_power/read_standby_flag.py',
    'tmp/bringup/sd-fourbit-20261024/magic_readback.py',
    'tmp/bringup/ethernet-normal-20261028/cold_logger.py',
    'tmp/bringup/ethernet-normal-20261028/analysis/analyze_cycles.py',
    'tmp/bringup/power-ablation-20261028/aligned_logger.py',
    'tmp/bringup/power-ablation-20261028/analyze_warm_ablations.py',
    'tmp/bringup/power-ablation-20261028/analyze_existing_baseline.py',
    'tmp/bringup/sd125-negedge-20261026/uart_recover.py',
    'tmp/bringup/error-blinks-20261026/install.py',
)
GENERATED = {'manifest.json', 'local-payloads.json', 'archive-source-inventory.json',
             'archive-gates.json', 'archive-audit.json', '.gitattributes', 'README.md'}


def readj(path):
    return json.loads(path.read_text(encoding='utf-8'))


def writej(path, value):
    path.write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8', newline='\n')


def sha_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def stamp(path):
    st = path.stat()
    return st.st_size, st.st_mtime_ns


def sha(path):
    before = stamp(path)
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1048576), b''):
            h.update(chunk)
    if stamp(path) != before:
        raise ValueError('Source changed while hashing: '+str(path))
    return h.hexdigest()


def checked_path(parent, name):
    path = parent/name
    path.resolve().relative_to(parent.resolve())
    return path


def disposition(rel, size):
    """Conservative payload policy; NOR verification bytes are always retained."""
    name = rel.name.lower(); suffix = rel.suffix.lower()
    if '__pycache__' in rel.parts or suffix in ('.o', '.obj', '.pyc', '.elf'):
        return 'omit', 'rebuildable object/debug intermediate'
    if suffix in ('.f32', '.f64', '.u1', '.jls', '.sal', '.npy', '.npz'):
        return 'omit', 'native instrument stream; sample/chunk/event ledgers retained'
    if suffix in ('.png', '.jpg', '.jpeg', '.webp', '.tif', '.tiff'):
        if rel.parts[0] != 'analysis' or any(x in name for x in ('scene', 'image', 'frame')):
            return 'omit', 'private image or preview'
    if suffix == '.bin':
        if (name in ('frame.bin', 'slot.bin', 'sectors.bin', 'payload.bin', 'image.bin') or
                re.match(r'frame-[0-9a-f]+\.bin$', name) or name == 'frame-metadata.bin'):
            return 'omit', 'private image, metadata or SD payload'
        # Retain code/boot/prefix, small status proofs and complete NOR readbacks.
        if size > 65536 and not (rel.parts[0] == 'design' and rel.parts[1] in BUILD_NAMES):
            raise ValueError('Unclassified large binary requires review: '+rel.as_posix())
    if size > 16*1024**2:
        raise ValueError('Unclassified large file requires review: '+rel.as_posix())
    return ('gzip', 'lossless exact-byte chunk ledger') if name == 'chunks.jsonl' else ('copy', None)


def inventory(source, root, hashes):
    entries = []
    for p in sorted(source.rglob('*')):
        if p.is_symlink():
            raise ValueError('Archive refuses symbolic links: '+str(p))
        if not p.is_file():
            continue
        rel = p.relative_to(source)
        if rel.as_posix() in GENERATED or rel.parts[0] == 'support':
            raise ValueError('Reserved archive path in campaign: '+str(rel))
        size, mtime = stamp(p); action, reason = disposition(rel, size)
        entry = dict(source=str(p), path=rel.as_posix(), bytes=size, mtime_ns=mtime,
                     action=action, reason=reason, origin='campaign')
        if hashes: entry['sha256'] = sha(p)
        entries.append(entry)
    dependencies=set(SUPPORT)
    tests=source/'offline-tests.json'
    if tests.exists():
        for name,digest in readj(tests)['sources_sha256'].items():
            if not name.startswith('firmware/capture-raw/') or Path(name).suffix!='.py':
                raise ValueError('Unexpected test-source dependency: '+name)
            assert sha(checked_path(root,name))==digest, name
            dependencies.add(name)
    for name in sorted(dependencies):
        p = checked_path(root, name)
        if not p.is_file(): raise FileNotFoundError(p)
        size, mtime = stamp(p)
        entry = dict(source=str(p), path='support/'+name, bytes=size, mtime_ns=mtime,
                     action='copy', reason=None, origin='dependency')
        if hashes: entry['sha256'] = sha(p)
        entries.append(entry)
    names = [e['path'] for e in entries]
    if len(names) != len(set(names)): raise ValueError('Duplicate inventory path')
    if sum(e['bytes'] for e in entries if e['action'] != 'omit') >= MAX_BYTES:
        raise ValueError('Compact archive exceeds 100 MiB before compression')
    return entries


def seal_gates(source):
    if not (source/'REPORT.md').is_file(): raise FileNotFoundError(source/'REPORT.md')
    final = readj(source/'final-state.json')
    assert final.get('completed') is True and final.get('normal_restored') is True
    ram = readj(source/'ram-readback/summary.json')
    cold = readj(source/'cold-images-readback/summary.json')
    assert ram.get('passed') is True and cold.get('passed') is True
    assert sorted(x['slot'] for x in ram['slots']) == [132]
    assert sorted(x['slot'] for x in cold['slots']) == [133, 134]
    rv = readj(source/'ram-readback/readback-validation.json')
    assert rv.get('passed') is True and rv.get('full_slot_read') is True
    assert rv.get('original_sensor_frame_comparison') is True
    assert rv['source_reference_comparison'].get('bytes_equal') is True
    assert rv.get('png_samples_match_read_raw') is True
    restore = readj(source/'restore-normal/complete.json')
    assert all(restore.get(k) is True for k in ('passed', 'independent_full_readback', 'following4096_unchanged'))
    assert restore['new_sector_sha256'] == NORMAL['staged/capture_sector_0.bin']
    tests=readj(source/'offline-tests.json')
    assert tests.get('passed') is True and tests.get('sources_unchanged') is True
    assert tests.get('tests')==236 and tests.get('returncode')==0
    assert sha(source/'offline-tests.log')==tests['log_sha256']
    paths = ['REPORT.md', 'final-state.json', 'ram-readback/summary.json', 'ram-readback/readback-validation.json',
             'cold-images-readback/summary.json', 'restore-normal/complete.json', 'offline-tests.json','offline-tests.log']
    return dict(passed=True, gates=[dict(path=n, sha256=sha(source/n)) for n in paths],
                scope='Recorded completion, full-image verification and normal NOR restoration; no new hardware observation')


def frozen_functions(path, functions, constants=(), globals_=None):
    """Execute only selected pure definitions, never module imports or mains."""
    tree = ast.parse(path.read_text(encoding='utf-8')); nodes = []; found = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in functions:
            nodes.append(node); found.add(node.name)
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in constants: nodes.append(node); found.add(name)
    assert found == set(functions) | set(constants), (path, found)
    env = dict(globals_ or {})
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), env)
    return env


def audit(archive, support_root=None):
    support = Path(support_root) if support_root is not None else archive/'support'
    tests=archive/'offline-tests.json'
    if tests.exists():
        for name,digest in readj(tests)['sources_sha256'].items():
            assert sha(checked_path(support,name))==digest,name
    host = frozen_functions(support/'firmware/capture-raw/bench.py',
        ('board_eth_layout', 'board_eth_snapshot', 'sd_init_gap_layout', 'sd_init_gap_snapshot'),
        ('SD_INIT_GAP_FIELDS',), dict(struct=struct, LOAD=0x34300000))
    late = frozen_functions(support/'firmware/capture-raw/late_build.py',
        ('audit_layout',), ('COLD_RUNTIME',), dict(struct=struct, re=re))
    builds = {}; by_hash = {}
    for name in BUILD_NAMES:
        p = archive/'design'/name; m = readj(p/'manifest.json'); code = (p/'capture.bin').read_bytes()
        assert sha_bytes(code) == m['binary_sha256'] and len(code) == m['binary_bytes']
        assert struct.unpack_from('<II', code) == (m['stack'], m['entry'])
        for fn, digest in m['source_hashes'].items(): assert sha(checked_path(p, fn)) == digest, (name, fn)
        assert host['sd_init_gap_layout'](m, 1) is (name != 'flash-default')
        assert host['sd_init_gap_layout'](m, 3) is (name != 'flash-default')
        if m['flash']:
            info=m['late_load']; begin=info['late_address']; end=begin+info['late_bytes']
            assert info['early_bytes']==15804 and begin==0x34303DBC and end<=0x3430E000
            assert zlib.crc32(code[begin-m['load']:end-m['load']])==info['late_crc32']
            late['audit_layout'](code,(p/'symbols.txt').read_text(),(p/'capture.lst').read_text(),begin,end)
            staged=p/'staged'; sm=readj(staged/'manifest.json')
            full=(staged/'stage2-full.bin').read_bytes(); early=(staged/'stage2.bin').read_bytes()
            assert full==code and len(early)==15804 and early==full[:15804]
            sector=(staged/'capture_sector_0.bin').read_bytes(); boot=(staged/'stage1_boot.bin').read_bytes()
            assert len(sector)==65536 and sha_bytes(sector)==sm['program_sha256']
            assert sector[:len(boot)]==boot and sector[0x2000:0x2000+len(full)]==full
            prefix=(staged/'stage1.bin').read_bytes(); crc=zlib.crc32(early)
            assert sha_bytes(prefix)==sm['stage1_raw_sha256'] and int(sm['stage2_crc32'],16)==crc
            for off in (0xC9C,0x1354): assert struct.unpack_from('<I',prefix,off)[0]==crc
        builds[name]=dict(sha256=m['binary_sha256'],bytes=len(code),frozen_sources=len(m['source_hashes']))
        by_hash[m['binary_sha256']] = (p,m)
    for fn, digest in NORMAL.items(): assert sha(archive/'design/flash-default'/fn)==digest
    default=archive/'design/flash-default/staged'; gap=archive/'design/flash-gap/staged'
    a=(default/'stage1.bin').read_bytes(); b=(gap/'stage1.bin').read_bytes()
    allowed={i for off in (0xC9C,0x1354) for i in range(off,off+4)}
    diffs=[i for i,(x,y) in enumerate(zip(a,b)) if x!=y]
    assert len(a)==len(b)==6720 and diffs and set(diffs)<=allowed
    assert (default/'stage1-unrelocated.bin').read_bytes()==(gap/'stage1-unrelocated.bin').read_bytes()
    offsets=readj(default/'manifest.json')['checked_recovery_literal_offsets']
    assert offsets==readj(gap/'manifest.json')['checked_recovery_literal_offsets'] and len(offsets)==20
    assert all(a[off:off+4]==b[off:off+4] for off in offsets)
    proofs=[]
    for path in sorted(archive.rglob('verified.json')):
        v=readj(path)
        if 'sd_init_gap' not in v: continue
        assert v.get('passed') is True
        build,m=by_hash[v['binary_sha256']]; p=v['proof']
        folders=[x for x in (path.parent/'bootstrap',path.parent/'operation') if (x/'final-proof.bin').exists()]
        assert len(folders)==1, str(path)
        folder=folders[0]; h=(build/'runtime.h').read_text()
        names=re.findall(r'\bRP_([A-Z0-9_]+)\b',h[h.index(' RP_MAGIC,'):h.index('};',h.index(' RP_MAGIC,'))])
        names=[n.lower() for n in names]+['reserved_'+str(i) for i in range(len(names),96)]
        binary_proof=dict(zip(names,struct.unpack('<96I',(folder/'final-proof.bin').read_bytes())))
        assert all(binary_proof[k]==value for k,value in p.items()), str(path)
        assert p['state']==3 and p['result']==0 and p['cleanup_error']==0 and p['media_idle']==1
        class FrozenUpload:
            def upload(self,address,size,label):
                names={m['sd_init_gap_proof']:'completed-sd-init-gap.bin',m['board_eth_proof']:'completed-board-eth.bin'}
                raw=(folder/names[address]).read_bytes(); assert len(raw)==size; return raw
        fake=FrozenUpload()
        result=host['sd_init_gap_snapshot'](fake,m,p,'replay')
        eth=host['board_eth_snapshot'](fake,m,p,'replay')
        assert result==v['sd_init_gap'] and eth==v['board_eth'], str(path)
        proofs.append(dict(path=path.relative_to(archive).as_posix(),operation=p['operation'],
                           gap_completed=result['completed'],binary_sha256=v['binary_sha256']))
    assert any(p['operation']==1 and p['gap_completed'] for p in proofs)
    assert any(p['operation']==3 and not p['gap_completed'] for p in proofs)
    inventory_path=archive/'archive-source-inventory.json'
    normalize=lambda value:str(value).replace('\\','/').casefold()
    identity=({normalize(e['source']):e['sha256'] for e in readj(inventory_path)['files']}
              if inventory_path.exists() else None)
    def linked_hash(record):
        actual=identity[normalize(record['path'])] if identity is not None else sha(Path(record['path']))
        assert actual==record['sha256'],record['path']
    readbacks=[]
    for path in sorted(archive.rglob('readback-validation.json')):
        v=readj(path)
        assert all(v.get(k) is True for k in ('passed','full_slot_read','full_payload_read',
            'start_magic_valid','completion_marker_valid','png_samples_match_read_raw')),str(path)
        assert v['bytes']==1909600 and v['slot_bytes']==1909760
        for record in v['artifacts']: linked_hash(record)
        reference=v.get('source_reference_comparison')
        if reference:
            linked_hash(reference['source'])
            assert reference.get('bytes_equal') is True
        linked_hash(v['scr_source']['proof']); linked_hash(v['scr_source']['scr_binary'])
        readbacks.append(dict(path=path.relative_to(archive).as_posix(),slot=v['slot'],
            full_slot_read=True,recorded_png_samples_match=True,
            original_sensor_frame_comparison=v.get('original_sensor_frame_comparison',False),
            raw_sha256=v['raw_sha256'],slot_sha256=v['slot_sha256'],png_sha256=v['png_sha256']))
    assert any(x['slot']==132 and x['original_sensor_frame_comparison'] for x in readbacks)
    nor=[]
    for path in sorted(archive.rglob('complete.json')):
        v=readj(path)
        if 'independent_full_readback' not in v: continue
        p=path.parent
        assert all(v.get(k) is True for k in ('passed','independent_full_readback','following4096_unchanged'))
        assert sha(p/'nor-before/readback.bin')==v['old_sector_sha256']
        assert sha(p/'nor-after/readback.bin')==v['new_sector_sha256']
        assert (p/'following-before/readback.bin').read_bytes()==(p/'following-after/readback.bin').read_bytes()
        nor.append(path.relative_to(archive).as_posix())
    assert 'install-gap/complete.json' in nor and 'restore-normal/complete.json' in nor
    return dict(passed=True,builds=builds,replayed_gap_and_eth_proofs=proofs,nor_verifications=nor,
                readback_validation_identity=readbacks,
                prefix_changed_offsets=diffs,disabled_normal_identity=True,
                scope='Offline exact bytes/source hashes, pure frozen host proof validators and retained NOR verification bytes. '
                      'Private image decoding and native-current integration require omitted local payloads.')


def verify(destination):
    manifest=readj(destination/'manifest.json')
    expected=set()
    for item in manifest['files']:
        p=checked_path(destination,item['path']); expected.add(item['path'])
        assert p.is_file() and p.stat().st_size==item['bytes'] and sha(p)==item['sha256'],item['path']
    actual={p.relative_to(destination).as_posix() for p in destination.rglob('*') if p.is_file()}
    assert actual==expected|{'manifest.json'}, sorted(actual^expected^{'manifest.json'})
    assert (destination/'README.md').read_bytes()==(destination/'REPORT.md').read_bytes()
    for item in readj(destination/'archive-source-inventory.json')['files']:
        if item['action']=='omit': continue
        p=checked_path(destination,item['path']+('.gz' if item['action']=='gzip' else ''))
        raw=gzip.decompress(p.read_bytes()) if item['action']=='gzip' else p.read_bytes()
        assert len(raw)==item['bytes'] and sha_bytes(raw)==item['sha256'],item['path']
    gates=seal_gates(destination); assert gates==readj(destination/'archive-gates.json')
    result=audit(destination); assert result==readj(destination/'archive-audit.json')
    return dict(passed=True,files=len(manifest['files']),bytes=sum(x['bytes'] for x in manifest['files']),
                proof_replays=len(result['replayed_gap_and_eth_proofs']))


def seal(source,root,destination):
    # This function is called only by explicit --seal after owner authorization.
    gates=seal_gates(source)
    if destination.exists(): raise FileExistsError(destination)
    partial=destination.with_name(destination.name+'.partial')
    if partial.exists(): raise FileExistsError(partial)
    entries=inventory(source,root,hashes=True)
    partial.mkdir(parents=True)
    for item in entries:
        if item['action']=='omit': continue
        p=Path(item['source']); assert stamp(p)==(item['bytes'],item['mtime_ns'])
        q=checked_path(partial,item['path']+('.gz' if item['action']=='gzip' else ''))
        q.parent.mkdir(parents=True,exist_ok=True)
        if item['action']=='gzip':
            with p.open('rb') as src,q.open('wb') as dst,gzip.GzipFile(filename='',mode='wb',fileobj=dst,mtime=0) as gz:
                shutil.copyfileobj(src,gz)
        else: shutil.copyfile(p,q)
        assert stamp(p)==(item['bytes'],item['mtime_ns'])
    # Detect files appended/created during sealing, not only copy-time changes.
    fresh=inventory(source,root,hashes=False)
    assert [(x['path'],x['bytes'],x['mtime_ns']) for x in fresh]==[(x['path'],x['bytes'],x['mtime_ns']) for x in entries]
    (partial/'.gitattributes').write_text('* -text\n',encoding='utf-8',newline='\n')
    shutil.copyfile(partial/'REPORT.md',partial/'README.md')
    writej(partial/'archive-source-inventory.json',dict(source=str(source),files=entries))
    writej(partial/'local-payloads.json',dict(source=str(source),files=[e for e in entries if e['action']=='omit']))
    writej(partial/'archive-gates.json',gates)
    writej(partial/'archive-audit.json',audit(partial))
    files=[dict(path=p.relative_to(partial).as_posix(),bytes=p.stat().st_size,sha256=sha(p))
           for p in sorted(partial.rglob('*')) if p.is_file()]
    assert sum(x['bytes'] for x in files)<MAX_BYTES
    writej(partial/'manifest.json',dict(schema=2,source=str(source),files=files,
        scope='Compact exact-byte evidence and replayable proof/source/NOR checks. Private image/SD payloads, '
              'native instrument streams and rebuildable intermediates are hash-inventoried omissions. '
              'Analysis outputs and sample/chunk/event ledgers retained; full numerical replay requires local native streams.'))
    result=verify(partial)
    partial.rename(destination)
    return dict(archive=str(destination),omitted_files=sum(x['action']=='omit' for x in entries),**result)


def self_test():
    assert disposition(Path('install-gap/nor-after/readback.bin'),65536)[0]=='copy'
    assert disposition(Path('restore-normal/write/readback.bin'),65536)[0]=='copy'
    assert disposition(Path('ram-readback/payload-0/operation/sectors.bin'),512)[0]=='omit'
    assert disposition(Path('capture/frame-00000000.bin'),262144)[0]=='omit'
    assert disposition(Path('capture/frame-metadata.bin'),152)[0]=='omit'
    assert disposition(Path('capture/frame-guard.bin'),32)[0]=='copy'
    assert disposition(Path('trace/current.f32'),500000000)[0]=='omit'
    assert disposition(Path('trace/chunks.jsonl'),1000000)[0]=='gzip'
    assert disposition(Path('analysis/cold-current.png'),100000)[0]=='copy'
    assert disposition(Path('analysis/scene.png'),100000)[0]=='omit'
    assert disposition(Path('design/flash-gap/capture.bin'),34064)[0]=='copy'
    assert disposition(Path('design/flash-gap/capture.elf'),3000000)[0]=='omit'
    try: disposition(Path('unknown.bin'),262144)
    except ValueError: pass
    else: raise AssertionError('Unknown large binary silently included')
    return dict(passed=True,scope='Pure archive classification and privacy/NOR retention cases')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    mode=p.add_mutually_exclusive_group()
    mode.add_argument('--plan',action='store_true',help='Read-only file counts/classification; default')
    mode.add_argument('--seal',action='store_true',help='Only after bench owner explicitly authorizes final archive')
    mode.add_argument('--verify',type=Path,help='Replay only the supplied existing compact archive')
    mode.add_argument('--self-test',action='store_true',help='Pure in-memory policy checks')
    mode.add_argument('--check-source',action='store_true',help='Read-only completed-campaign gates and proof replay before sealing')
    args=p.parse_args()
    if args.self_test: result=self_test()
    elif args.verify: result=verify(args.verify.resolve())
    elif args.check_source:
        seal_gates(SOURCE)
        result=audit(SOURCE,ROOT)
    elif args.seal: result=seal(SOURCE,ROOT,DESTINATION)
    else:
        entries=inventory(SOURCE,ROOT,hashes=False)
        result=dict(source=str(SOURCE),destination=str(DESTINATION),destination_exists=DESTINATION.exists(),
            read_only=True,files=len(entries),retained_files=sum(x['action']!='omit' for x in entries),
            retained_uncompressed_bytes=sum(x['bytes'] for x in entries if x['action']!='omit'),
            omitted_files=sum(x['action']=='omit' for x in entries),
            omitted_bytes=sum(x['bytes'] for x in entries if x['action']=='omit'),
            gates='Not evaluated by plan; --seal requires final-state, successful RAM/cold readback, exact normal NOR restoration')
    print(json.dumps(result,indent=2))


if __name__=='__main__': main()
