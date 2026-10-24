"""Freeze the observed MVE PREPARE refusal without calling it a speed result."""
from pathlib import Path
from add_trial import ROOT,HERE,read,sha,dump

def main():
    source=ROOT/'tmp/bringup/png-tune-20261024/mve-emitter-hardware'
    plan=read(source/'plan.json');terminal=read(source/'prepare/terminal.json')
    assert not (source/'verified.json').exists() and not (source/'fixture').exists()
    assert terminal['operation']==1 and terminal['state']==3 and terminal['result']==2
    build=Path(plan['build']);m=read(build/'manifest.json');code=(build/'bench.bin').read_bytes()
    assert sha(code)==plan['module_sha256']==m['binary_sha256']
    out=HERE/'failures/mve-emitter-cpacr';out.mkdir(parents=True,exist_ok=False);files=[];omitted=[]
    def copy(path,relative):
        raw=path.read_bytes();dest=out/relative;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
        files.append(dict(original_path=path.relative_to(ROOT).as_posix(),archived_path=relative.as_posix(),bytes=len(raw),sha256=sha(raw)))
    for name,digest in m['source_hashes'].items():
        assert sha((build/name).read_bytes())==digest;copy(build/name,Path('build')/name)
    for name in ('manifest.json','bench.bin','symbols.txt','bench.lst'):copy(build/name,Path('build')/name)
    runner=ROOT/'tmp/bringup/png-row-study-20261024/mve_emitter_run.py'
    assert sha(runner.read_bytes())==plan['adapter_sha256']
    copy(runner,Path('support/mve_emitter_run.py'))
    copy(ROOT/'firmware/png-encoder/bench/protocol.py',Path('support/protocol.py'))
    for path in sorted(source.rglob('*')):
        if not path.is_file():continue
        rel=path.relative_to(source)
        if path.name.endswith('-code.bin') or path.name in ('benchmark-readback.bin','bridge-readback.bin'):
            omitted.append(dict(path=rel.as_posix(),bytes=path.stat().st_size,reason='Redundant code readback'));continue
        assert path.stat().st_size<65536 and path.suffix not in ('.sal','.csv','.png')
        copy(path,Path('records')/rel)
    dump(out/'archive.json',dict(schema=1,status='Failed PREPARE, not a benchmark result',files=files,omitted=omitted,
        module_sha256=sha(code),raw_uploaded=False,encoder_run=False,performance_claim=False,hardware_accessed_by_archiver=False,
        observation='PB_BAD_CONTEXT during PREPARE; post-C proof recorded CPACR=0. The prior SRAM bootstrap had not enabled FP/MVE access.',
        response='A separately reviewed candidate must explicitly own FP/MVE access after validating inherited context; this failed executable is preserved.'))
    print({'files':len(files),'failure_result':terminal['result']})

if __name__=='__main__':main()
