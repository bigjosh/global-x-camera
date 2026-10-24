"""Preserve compact initial recovery evidence, including the failed first attempt."""
import json
from pathlib import Path
from add_trial import ROOT,HERE,read,sha,dump

def compact(value):
    if isinstance(value,list):return dict(omitted_list=True,items=len(value))
    if isinstance(value,dict):return {key:compact(item) for key,item in value.items()}
    return value

def main():
    source=ROOT/'tmp/bringup/png-tune-20261024';out=HERE/'initial-recovery'
    out.mkdir(exist_ok=False);files=[];omitted=[]
    for name in ('preflight','preflight02','early-park','early-park02','recovery-signal','recovery-signal02'):
        for path in sorted((source/name).rglob('*')):
            if not path.is_file():continue
            rel=path.relative_to(source);size=path.stat().st_size
            if path.suffix in ('.csv','.sal') or size>65536:
                item=dict(path=rel.as_posix(),bytes=size,reason='Large signal detail/recording omitted')
                if path.name=='signal-summary.json':
                    raw=path.read_bytes();item['sha256']=sha(raw)
                    dest=out/rel;dest.parent.mkdir(parents=True,exist_ok=True)
                    dump(dest.with_name('signal-summary-compact.json'),compact(json.loads(raw)))
                omitted.append(item);continue
            raw=path.read_bytes();dest=out/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
            files.append(dict(path=rel.as_posix(),bytes=size,sha256=sha(raw)))
    dump(out/'archive.json',dict(schema=1,source=source.relative_to(ROOT).as_posix(),files=files,omitted=omitted,
        first_attempt='No successful early-park result; original CLI/status remain failed/incomplete',
        second_attempt='Exact v66c early-recovery park verified by original result.json',
        authorization_provenance='Bench owner recorded user authorization for exclusive hardware access and memory/flash/SD changes; compute trials deliberately used RAM only.',
        authorization_is_policy_change=False,hardware_accessed_by_archiver=False))
    derived=[]
    for path in sorted(out.glob('*/signal-summary-compact.json')):
        raw=path.read_bytes();derived.append(dict(path=path.relative_to(out).as_posix(),bytes=len(raw),sha256=sha(raw)))
    dump(out/'derived-index.json',dict(schema=1,
        transform='Recursive dictionaries retained; lists replaced with omitted_list/items markers',files=derived))
    print(json.dumps(dict(files=len(files),omitted=len(omitted))))

if __name__=='__main__':main()
