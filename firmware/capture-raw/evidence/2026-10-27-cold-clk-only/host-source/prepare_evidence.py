"""Copy completed evidence only; no hardware/network/subprocess access."""
import gzip
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[3]
SOURCE=Path(__file__).resolve().parent
DEST=ROOT/'firmware/capture-raw/evidence/2026-10-27-cold-clk-only'
OLD=ROOT/'firmware/capture-raw/evidence/2026-10-26-error-handler-fix'
PIO=ROOT/'firmware/capture-raw/evidence/2026-10-27-pio-idma-read'


def sha(data):return hashlib.sha256(data).hexdigest()


def main():
    DEST.mkdir(parents=True,exist_ok=True)
    origins={}
    def copy(source,target):
        source=Path(source);target=DEST/target
        target.parent.mkdir(parents=True,exist_ok=True)
        raw=source.read_bytes()
        if target.exists():assert target.read_bytes()==raw, f'Existing evidence differs: {target}'
        else:target.write_bytes(raw)
        origins[target.relative_to(DEST).as_posix()]={
            'source':source.relative_to(ROOT).as_posix(),'bytes':len(raw),'sha256':sha(raw)}
    def tree(source,target):
        for path in sorted(source.rglob('*')):
            if path.is_file():copy(path,Path(target)/path.relative_to(source))
    for name in ('observe_error.py','summarize_current.py','analyze_normal_current.py','compare_cold_header.py','prepare_evidence.py'):
        copy(SOURCE/name,Path('host-source')/name)
    copy(ROOT/'tmp/bringup/error-blinks-20261026/analyze_led_current.py','host-source/analyze_led_current.py')
    copy(ROOT/'tmp/bringup/error-relocate-20261026/cold_led_trace.py','host-source/cold_led_trace.py')
    copy(ROOT/'tmp/bringup/sd-read-pio-dma-20261027/analyze_reads.py','host-source/analyze_reads.py')
    copy(ROOT/'tmp/bringup/sd-read-pio-dma-20261027/run_read.py','host-source/run_read.py')
    compressed=[]
    for number in (1,2,3):
        name=f'clk-only{number:02d}'
        tree(SOURCE/f'{name}-observation',Path('attempts')/name/'observation')
        for old,suffix in ((f'{name}-ready.json','ready.json'),(f'{name}-current.power-on.json','power-on.json')):
            copy(SOURCE/old,Path('attempts')/name/suffix)
        raw=(SOURCE/f'{name}-current.jsonl').read_bytes()
        assert json.loads(raw.splitlines()[-1])['event']=='stopped'
        blob=gzip.compress(raw,compresslevel=9,mtime=0)
        target=DEST/'traces'/f'{name}-current.jsonl.gz';target.parent.mkdir(exist_ok=True)
        if target.exists():assert target.read_bytes()==blob
        else:target.write_bytes(blob)
        assert gzip.decompress(blob)==raw
        compressed.append(dict(path=target.relative_to(DEST).as_posix(),
            original_path=(SOURCE/f'{name}-current.jsonl').relative_to(ROOT).as_posix(),
            original_bytes=len(raw),original_sha256=sha(raw),compressed_bytes=len(blob),compressed_sha256=sha(blob)))
        copy(SOURCE/f'{name}-current-summary.json',Path('reports')/f'{name}-current-summary.json')
        if number>1:copy(SOURCE/f'{name}-current-pattern.json',Path('reports')/f'{name}-current-pattern.json')
    for name in ('clk-only03-header-comparison.json','clk-only03-header-comparison.bin',
                 'normal-vs-warm-read-audit.json','observer-self-test.json','observer-self-test.log'):
        copy(SOURCE/name,Path('reports')/name)
    tree(SOURCE/'warm-pio25-01','attempts/warm-pio25-01')
    for name in ('warm-control-uart','before-cmd-uart','before-cmd-park'):
        tree(SOURCE/name,Path('recovery')/name)
    copy(ROOT/'tmp/bringup/sd-read-pio-dma-20261027/reference125/read/sectors.bin','reference/verified-lba0.bin')
    copy(ROOT/'tmp/bringup/sd-read-pio-dma-20261027/reference125/read/verified.json','reference/verified-lba0-proof.json')
    copy(ROOT/'tmp/bringup/sd-read-pio-dma-20261027/pio25-01/read/read-buffer.bin','reference/prior-bad-k10.bin')
    copy(ROOT/'tmp/bringup/sd-clk-slew-20261026/clk1-trial03-v3/failed-header/untrusted-header.bin','reference/prior-bad-k8.bin')
    copy(ROOT/'tmp/bringup/error-relocate-20261026/normal-analysis.json','reference/prior-normal-current-analysis.json')
    installed=OLD/'snapshots/offline/inputs/flash-normal-v2'
    copy(installed/'manifest.json','configs/installed-manifest.json')
    bindings=[]
    for path in [installed/name for name in ('manifest.json','capture.bin','runtime.h','runtime.c',
            'magic_runtime.inc','magic_slots.c','magic_slots.h','error_codes.h','sd_card.c','sd_card.h')]:
        raw=path.read_bytes();bindings.append(dict(path=path.relative_to(ROOT).as_posix(),bytes=len(raw),sha256=sha(raw)))
    for path in (PIO/'builds/ram-pio25/manifest.json',PIO/'builds/ram-pio25/capture.bin'):
        assert path.is_file(),path
        raw=path.read_bytes();bindings.append(dict(path=path.relative_to(ROOT).as_posix(),bytes=len(raw),sha256=sha(raw)))
    def save(name,value):(DEST/name).write_text(json.dumps(value,indent=2)+'\n')
    save('compression.json',dict(schema=1,method='gzip level9 mtime0; decompressed bytes equal original JSONL',traces=compressed))
    save('source-origins.json',origins)
    save('sealed-reference-bindings.json',dict(schema=1,repo_root_relative_paths=True,files=bindings,
        note='Reuse earlier sealed installed sources/builds. This campaign did not read or program NOR. Bindings are offline identity, not fresh physical NOR proof.'))
    (DEST/'.gitattributes').write_bytes(b'* -text\n')
    print(DEST)


if __name__=='__main__':main()
