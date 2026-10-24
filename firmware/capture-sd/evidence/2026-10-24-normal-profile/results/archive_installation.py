"""Copy closed installation/refusal records; never access hardware."""
from pathlib import Path
import hashlib,json

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
WORK=ROOT/'tmp/bringup/sd-normal-20261024'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def read(path):return json.loads(path.read_text(encoding='utf-8'))
def copy_groups(name,groups):
    out=HERE/name;out.mkdir(exist_ok=False);files=[];omitted=[]
    for group in groups:
        origin=WORK/group
        assert origin.is_dir(),origin
        for path in sorted(origin.rglob('*')):
            if not path.is_file():continue
            rel=path.relative_to(origin);size=path.stat().st_size
            if (path.suffix.lower() in ('.png','.sal','.f32') or path.name.startswith('analog_')
                or ('raw' in rel.parts and path.name!='manifest.json') or size>131072):
                omitted.append(dict(original_path=path.relative_to(ROOT).as_posix(),bytes=size,
                                    reason='Raw recording/image omitted; original retained locally'))
                continue
            raw=path.read_bytes();dst=out/group/rel;dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(raw)
            files.append(dict(original_path=path.relative_to(ROOT).as_posix(),
                              archived_path=dst.relative_to(out).as_posix(),bytes=len(raw),sha256=sha(raw)))
    (out/'index.json').write_text(json.dumps(dict(files=files,omitted=omitted),indent=2)+'\n',encoding='utf-8')
    return out

def main():
    installed=copy_groups('installation-v66',['install-v66','install-v66-diag','following-after-v66','following-after-v62b'])
    refused=copy_groups('v65-refusal',['standby01-cycle','standby01-diagnostic','standby01-safe-failure',
                                     'after-v65-refusal-park','nor-after-v65-refusal'])
    v66=(HERE.parent/'build/v66c-normal-standby/staged/capture_sector_0.bin').read_bytes()
    assert (installed/'install-v66/readback.bin').read_bytes()==v66
    before=(installed/'following-after-v62b/nor.bin').read_bytes()
    after=(installed/'following-after-v66/nor.bin').read_bytes()
    assert len(before)==4096 and before==after
    status=read(installed/'install-v66/status.json')
    assert status['result']==0 and status['cleanup_result']==0 and status['flags']==47
    assert status['changed_mask']==status['erased_mask']==status['completed_mask']
    assert read(installed/'install-v66-diag/result.json')['pending_operations']==0
    prior=(refused/'nor-after-v65-refusal/nor.bin').read_bytes()
    assert prior==(HERE.parent/'build/v65-normal-standby/staged/capture_sector_0.bin').read_bytes()
    failure=read(refused/'standby01-safe-failure/result.json')
    assert failure['passed'] and failure['exact_v65_pretransfer_failure']
    assert failure['late_words'][2:4]==[3,2] and failure['late_words'][8:10]==[0,0]
    assert failure['storage']['report']['result']==0 and failure['storage']['report']['media_idle']==1
    assert read(refused/'after-v65-refusal-park/result.json')['passed']
    summary=dict(verified=True,sector_bytes=len(v66),sector_sha256=sha(v66),
        following_bytes=len(after),following_sha256=sha(after),following_unchanged=True,
        write_sequence=status['sequence'],pages_programmed=status['pages_programmed'],
        programmer_terminal_success=True,cleanup_success=True,pending_operations=0,
        verification_scope='Exact whole-sector host readback plus following 4 KiB comparison; boot/capture/Standby qualification is separate',
        hardware_accessed_by_archiver=False)
    (installed/'verified-installation.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    summary=dict(build='v65-normal-standby',saved_name=failure['storage']['report']['name'],
        save_terminal_success=True,card_idle_verified=True,shutdown_succeeded=False,
        refusal_state=3,refusal_reason=2,late_bytes_loaded=0,
        reason='Stale schema1 gate rejected schema2 before XSPI read or late shutdown code',
        exact_idle_failure_park_verified=True,subsequent_uart_early_recovery_verified=True,
        v65_nor_bytes_unchanged=True,host_png_readback_verified=False,
        warning='Uninitialized LPM bytes are not Standby-entry evidence; original strict-width failure remains preserved',
        correction='../../build/reviews/late-schema-review-correction.json',hardware_accessed_by_archiver=False)
    (refused/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(installation=str(installed),refusal=str(refused),verified=True),indent=2))

if __name__=='__main__':main()
