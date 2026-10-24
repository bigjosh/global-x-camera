"""Archive completed awake-run metadata only; no hardware or image publication."""
from pathlib import Path
import hashlib
import json

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
WORK = ROOT / 'tmp/bringup/sd-normal-20261024'
def sha(raw): return hashlib.sha256(raw).hexdigest()

def archive(run, build, frame_group, provisional):
    out = HERE / run
    out.mkdir(exist_ok=False)
    index = []; omitted = []
    groups = [run + '-maintenance', run + '-cycle', run + '-png']
    groups += [run + '-frame', run + '-frame02', run + '-frame03'] if provisional else [frame_group]
    for group in groups:
        origin = WORK / group
        for source in sorted(origin.rglob('*')):
            if not source.is_file(): continue
            rel = source.relative_to(origin)
            reason = None
            if source.suffix.lower() in ('.png', '.sal') or source.name in ('raw.bin', 'data.bin'):
                reason = 'Image bytes or native waveform intentionally not published'
            elif 'raw' in rel.parts and source.name != 'manifest.json':
                reason = 'Raw Joulescope samples/chunk stream retained locally'
            elif source.name.startswith('analog_'):
                reason = 'Large raw analog waveform retained locally'
            elif source.name in ('frozen-save.bin', 'loaded-module.bin', 'prior-module.bin'):
                reason = 'Repeated firmware payload omitted; identity retained in result and omission hash'
            elif source.stat().st_size > 131072:
                reason = 'Large source retained locally'
            if reason:
                item = dict(original_path=source.relative_to(ROOT).as_posix(),
                            bytes=source.stat().st_size, reason=reason)
                # Do not reread large raw streams while the bench is active.
                if item['bytes'] <= 4 * 1024 * 1024:
                    item['sha256'] = sha(source.read_bytes())
                else:
                    item['sha256'] = None
                    item['hash_scope'] = 'Not computed here; raw manifest/source recorder remains authoritative'
                omitted.append(item)
                continue
            raw = source.read_bytes()
            target = out / group / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            index.append(dict(original_path=source.relative_to(ROOT).as_posix(),
                              archived_path=target.relative_to(out).as_posix(),
                              bytes=len(raw), sha256=sha(raw)))
    verification = json.loads((WORK / (run + '-png') / 'verified.json').read_text(encoding='utf-8'))
    frame = json.loads((WORK / frame_group / 'result.json').read_text(encoding='utf-8'))
    maintenance = json.loads((WORK / (run + '-maintenance') / 'result.json').read_text(encoding='utf-8'))
    report = maintenance['storage_proof']['report']
    assert verification['all_png_chunk_crcs_valid'] and verification['exact_pixels_sample_shift_left_6']
    assert verification['frame_sha256'] == frame['raw_sha256']
    assert report['result'] == 0 and report['state'] == 2
    assert frame['receiver_proof_valid_after_maintenance'] == (not provisional)
    summary = dict(run=run, build=build,
        qualification='Provisional timing/image evidence; receiver proof overlaps LED record' if provisional
                      else 'Corrected normal-profile awake capture/save/readback qualified',
        receiver_proof_valid_after_maintenance=not provisional,
        png_verification=verification, frame_metadata_path=frame_group + '/result.json',
        saved_png_path=run + '-png/verified.json',
        maintenance_path=run + '-maintenance/result.json',
        image_contents_archived=False, raw_samples_archived=False,
        strict_marker_width_qualification=False,
        phase_scope='Original strict decoder failure is preserved. Any source-order inference is separate analysis.',
        power_scope='CN8/JS measured branch; debugger and other bypass paths limit system-energy interpretation',
        terminal_scope='Awake diagnostic completion, not shutdown or Standby',
        visual_review='Root viewed IMG00066.PNG and reported a discernible room scene' if provisional else None,
        proof_correction='../../build/proof-address-correction.json' if provisional else None,
        hardware_accessed_by_archiver=False)
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    (out / 'index.json').write_text(json.dumps(dict(schema=1, run=run, files=index, omitted=omitted), indent=2) + '\n', encoding='utf-8')
    return dict(run=run, files=len(index), bytes=sum(x['bytes'] for x in index), omitted=len(omitted))

if __name__ == '__main__':
    print(json.dumps([
        archive('awake01', 'v62b-normal-awake', 'awake01-frame03', True),
        archive('awake02', 'v64-normal-awake', 'awake02-frame', False)], indent=2))
