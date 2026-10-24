"""Replay compact installation and v65 refusal checks, offline only."""
from pathlib import Path
import hashlib,json,struct

HERE=Path(__file__).resolve().parent
def read(path):return json.loads(path.read_text(encoding='utf-8'))
def sha(raw):return hashlib.sha256(raw).hexdigest()
def verify():
    count=0
    for name in ('installation-v66','v65-refusal'):
        root=HERE/name
        for entry in read(root/'index.json')['files']:
            path=(root/entry['archived_path']).resolve()
            assert path.is_relative_to(root.resolve())
            raw=path.read_bytes()
            assert len(raw)==entry['bytes'] and sha(raw)==entry['sha256']
            count+=1
    installed=HERE/'installation-v66';refused=HERE/'v65-refusal'
    assert (installed/'install-v66/readback.bin').read_bytes()==(
        HERE.parent/'build/v66c-normal-standby/staged/capture_sector_0.bin').read_bytes()
    following=(installed/'following-after-v66/nor.bin').read_bytes()
    assert len(following)==4096 and following==(installed/'following-after-v62b/nor.bin').read_bytes()
    assert read(installed/'verified-installation.json')['following_sha256']==sha(following)
    status=read(installed/'install-v66/status.json')
    assert status['result']==status['cleanup_result']==0 and status['flags']==47
    assert status['changed_mask']==status['erased_mask']==status['completed_mask']
    assert read(installed/'install-v66-diag/result.json')['pending_operations']==0
    failure=read(refused/'standby01-safe-failure/result.json')
    words=struct.unpack('<16I',(refused/'standby01-safe-failure/late.bin').read_bytes())
    assert list(words)==failure['late_words']
    assert words[0]==0x4C504C31 and words[2:4]==(3,2) and words[8:10]==(0,0) and words[15]==0
    assert failure['passed'] and failure['exact_v65_pretransfer_failure']
    assert failure['storage']['report']['state']==2 and failure['storage']['report']['result']==0
    assert failure['storage']['report']['media_idle']==1
    assert read(refused/'after-v65-refusal-park/result.json')['passed']
    assert (refused/'nor-after-v65-refusal/nor.bin').read_bytes()==(
        HERE.parent/'build/v65-normal-standby/staged/capture_sector_0.bin').read_bytes()
    assert not read(refused/'summary.json')['shutdown_succeeded']
    return dict(verified=True,indexed_files=count,installation_bytes=65536,
                following_bytes=4096,v65_shutdown_succeeded=False,hardware_accessed=False)

if __name__=='__main__':print(json.dumps(verify(),indent=2))
