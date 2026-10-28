"""Freeze compact exact-byte evidence; private images/native streams stay local."""
from pathlib import Path
import gzip,hashlib,json,shutil
S=Path(__file__).resolve().parent;R=S.parents[2]
D=R/'firmware/capture-raw/evidence/2026-10-28-ethernet-powerdown'
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for v in iter(lambda:f.read(1048576),b''):h.update(v)
    return h.hexdigest()
def copy(p,rel):
    q=D/rel;q.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,q)
if __name__=='__main__':
    assert json.loads((S/'cold-images-readback/summary.json').read_text())['passed']
    assert json.loads((S/'final-state.json').read_text())['normal_flash_restored']
    D.mkdir(parents=True,exist_ok=False);omitted=[]
    builds={'ram-candidate','flash-candidate','flash-disabled'}
    for p in sorted(S.rglob('*')):
        if not p.is_file() or '__pycache__' in p.parts:continue
        rel=p.relative_to(S);name=p.name
        if p.suffix in ('.o','.obj','.pyc'):continue
        native=p.suffix in ('.f32','.u1')
        private=(p.suffix=='.png' and rel.parts[0]!='analysis')
        binary=(p.suffix=='.bin' and rel.parts[0] not in builds and name not in
            ('completed-board-eth.bin','completed-request.bin','completed-proof.bin',
             'final-proof.bin','proof-0000.bin','completed-scr.bin','before-scr.bin',
             'cpucr.bin','rcc-ahb4enr-before.bin','rcc-ahb4rstr.bin'))
        if native or private or binary:
            omitted.append(dict(path=rel.as_posix(),bytes=p.stat().st_size,sha256=sha(p),
                reason='native instrument stream' if native else 'image or duplicate binary payload'))
            continue
        if name=='chunks.jsonl':
            q=D/rel.with_suffix('.jsonl.gz');q.parent.mkdir(parents=True,exist_ok=True)
            with gzip.GzipFile(filename=str(q),mode='wb',mtime=0) as f:f.write(p.read_bytes())
        else:copy(p,rel)
    support=['firmware/capture-raw/bench.py','firmware/capture-raw/build.py',
        'firmware/capture-raw/late_build.py','firmware/capture-raw/board_eth_powerdown.inc',
        'firmware/capture-raw/test_board_eth_powerdown.py','firmware/capture-raw/test_board_eth_bench.py',
        'firmware/capture-timing/recovery_gpio/check_park.py',
        'firmware/capture-sd/low_power/readback_recovery/run.py',
        'firmware/capture-sd/low_power/read_standby_flag.py',
        'tmp/bringup/sd-fourbit-20261024/magic_readback.py',
        'tmp/bringup/power-ablation-20261028/analyze_warm_ablations.py',
        'tmp/bringup/power-ablation-20261028/analyze_existing_baseline.py',
        'tmp/bringup/sd125-negedge-20261026/uart_recover.py',
        'tmp/bringup/error-blinks-20261026/install.py']
    for src in support:copy(R/src,Path('support')/src)
    (D/'.gitattributes').write_text('* -text\n')
    (D/'local-payloads.json').write_text(json.dumps(dict(source=str(S),files=omitted),indent=2)+'\n')
    files=[dict(path=p.relative_to(D).as_posix(),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(D.rglob('*')) if p.is_file()]
    assert sum(x['bytes'] for x in files)<100*1024**2
    (D/'manifest.json').write_text(json.dumps(dict(schema=1,source=str(S),files=files,
        scope='Exact compact diagnostics, frozen builds, analysis and host scripts. Native JS streams and private images remain local and hash-inventoried. Timing/analysis scripts retain original workspace dependencies; not a self-contained SDK/toolchain package.'),indent=2)+'\n')
    print(json.dumps(dict(archive=str(D),files=len(files),bytes=sum(x['bytes'] for x in files),omitted_files=len(omitted))))
