"""Archive closed PNG readback proofs without image/data payloads."""
from pathlib import Path
import hashlib,json

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
SOURCE=ROOT/'tmp/bringup/sd-normal-20261024/standby-png-readback'
OUT=HERE/'standby-png-readback'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def read(path):return json.loads(path.read_text(encoding='utf-8'))

def main():
    OUT.mkdir(exist_ok=False);files=[];omitted=[]
    for source in sorted(SOURCE.rglob('*')):
        if not source.is_file():continue
        rel=source.relative_to(SOURCE);size=source.stat().st_size
        reason=None
        if source.suffix.lower()=='.png' or source.name=='data.bin':
            reason='Photo/SD-read payload intentionally omitted; verification metadata retained'
        elif source.name in ('frozen-save.bin','module-readback.bin','initial-code.bin','prior-code.bin'):
            reason='Repeated frozen READ firmware omitted; exact identity remains in guards/results'
        elif size>131072:reason='Large source retained locally'
        if reason:
            omitted.append(dict(original_path=source.relative_to(ROOT).as_posix(),bytes=size,reason=reason))
            continue
        raw=source.read_bytes();dest=OUT/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
        files.append(dict(original_path=source.relative_to(ROOT).as_posix(),archived_path=rel.as_posix(),
                          bytes=len(raw),sha256=sha(raw)))
    verification=read(OUT/'verified.json');plan=read(OUT/'plan.json')
    assert verification['read_only'] and not verification['raw_frame_comparison']
    assert plan['recovery_identity']['name']=='v66c-normal-standby'
    for image in verification['files']:
        assert image['all_png_chunk_crcs_valid'] and image['complete_independent_decode']
        assert image['all_samples_10bit_left_aligned'] and not image['exact_capture_pixel_comparison']
        assert image['readonly_card_writes']==0
    old=next(x for x in verification['files'] if x['name']=='IMG00001.PNG')
    assert old['known_file_hash_matched'] and old['sha256']=='466e42c170b5af6a962df03d853d688b6cfb17da68f38c3ef157692457494330'
    summary=dict(qualified_names=[x['name'] for x in verification['files']],
        png_structure_and_independent_decode_passed=True,exact_raw_comparison=False,
        limitation='Captured RAW buffers were lost; structural decoding and dynamic range do not prove exact sensor-sample identity',
        old_img1_byte_identity_preserved=True,read_only_card_writes=0,
        visual_review='Hardware owner viewed IMG00071.PNG and reported a discernible brick wall and monitors',
        earlier_pending_records_superseded=['../v65-refusal/summary.json: IMG68 readback pending',
            '../standby02/summary.json: IMG69 readback pending','../standby03/summary.json: IMG70 readback pending',
            '../standby04/summary.json: IMG71 readback pending'],
        original_records_unchanged=True,images_archived=False,sd_read_payloads_archived=False,
        hardware_accessed_by_archiver=False)
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    (OUT/'index.json').write_text(json.dumps(dict(files=files,omitted=omitted),indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(indexed_files=len(files),bytes=sum(x['bytes'] for x in files),omitted=len(omitted)),indent=2))

if __name__=='__main__':main()
