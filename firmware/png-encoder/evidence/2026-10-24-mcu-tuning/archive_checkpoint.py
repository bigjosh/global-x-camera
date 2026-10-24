"""Freeze a closed restoration attempt without importing any bench code."""
import argparse
from pathlib import Path
from add_trial import ROOT,HERE,read,sha,dump


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--name',required=True)
    p.add_argument('--support',type=Path,action='append',default=[])
    a=p.parse_args();source=a.source.resolve();result=read(source/'result.json')
    assert source.is_relative_to(ROOT/'tmp')
    assert a.name.replace('-','').isalnum()
    assert result['helper_stopped_record']['ok'] is True
    assert result['helper_stopped_record']['range']==128
    out=HERE/'restoration'/a.name;out.mkdir(parents=True,exist_ok=False)
    files=[];omitted=[]
    def copy(path,relative):
        raw=path.read_bytes();dest=out/relative;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
        files.append(dict(original_path=path.relative_to(ROOT).as_posix(),archived_path=relative.as_posix(),
                          bytes=len(raw),sha256=sha(raw)))
    for path in sorted(source.rglob('*')):
        if not path.is_file():continue
        relative=path.relative_to(source);size=path.stat().st_size
        if size>65536 or path.suffix.lower() in ('.f32','.sal','.csv','.png'):
            omitted.append(dict(original_path=path.relative_to(ROOT).as_posix(),bytes=size,
                                reason='Large raw recording/edge list omitted; no image payload archived'))
            continue
        copy(path,Path('records')/relative)
    for path in a.support:
        path=path.resolve();copy(path,Path('support')/path.name)
    dump(out/'archive.json',dict(schema=1,source=source.relative_to(ROOT).as_posix(),files=files,omitted=omitted,
        original_success=result['success'],original_error=result['error'],
        hardware_accessed_by_archiver=False,energy_claim=False,
        limits=['Original success/failure is preserved; recording completion does not establish image integrity',
                'Installed NOR identity is owner-attested unless separately qualified by a live read',
                'Quiet current and pre-WFI intent alone do not prove physical Standby']))
    print({'name':a.name,'files':len(files),'original_success':result['success']})


if __name__=='__main__':main()
