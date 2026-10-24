"""Copy only compact v60 phase/proof metadata, then run the offline analyzer.

No instrument imports, image payloads, or analog exports. Existing destinations
are refused so the original evidence cannot be silently replaced.
"""
import argparse
import json
from pathlib import Path
from ordered_v60 import SECTOR, MODULE, FRAME_SHA, analyze, read_json, sha, table

HERE = Path(__file__).resolve().parent


def archive(work, name):
    source = work/name
    cold = name == 'v60-cycle-01'
    if not cold and not name.startswith('same-frame-'):
        raise ValueError('Only the v60 cold run or explicit same-frame runs are supported')
    target = HERE/name
    target.mkdir(exist_ok=False)
    inventory = []
    def copy(path, destination):
        raw = path.read_bytes()
        out = target/destination
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(raw)
        inventory.append(dict(original_path=str(path), archived_path=destination,
                              bytes=len(raw), sha256=sha(raw)))
    for channel in (0, 1, 4, 6):
        copy(source/'phase/binary'/f'digital_{channel}.bin', f'binary/digital_{channel}.bin')
    copy(source/'phase-summary.json', 'strict-width-summary.json')
    copy(source/'phase/capture-config.json', 'capture-config.json')
    if cold:
        copy(source/'result.json', 'cycle-result.json')
        copy(work/'v60-independent-read/result.json', 'nor-read-result.json')
        copy(work/'v60-independent-read/nor.bin', 'nor-readback.bin')
        copy(work/'v60-maintenance/result.json', 'maintenance-result.json')
        copy(work/'v60-maintenance/storage-module.bin', 'live-module.bin')
        copy(work/'v60-maintenance/storage-report.bin', 'report.bin')
        copy(work/'v60-frame/capture-result.json', 'capture-result.json')
    else:
        copy(source/'save/result.json', 'bench-result.json')
        copy(source/'save/loaded-module.bin', 'loaded-module.bin')
        copy(source/'save/request-readback.bin', 'request-readback.bin')
        copy(source/'save/request.json', 'request.json')
        copy(source/'save/preflight.json', 'preflight.json')
        result = read_json(source/'save/result.json')
        index = result['host_timing']['polls'][-1]['index']
        copy(source/'save'/f'report-{index:03d}.bin', 'report.bin')
    # The captured RAW is represented only by its existing metadata, never pixels.
    copy(work/'v60-frame/capture-result.json', 'frame-metadata.json')
    context = dict(schema=1, sequence='cold' if cold else 'storage',
                   sector_sha256=SECTOR, module_sha256=MODULE, frame_sha256=FRAME_SHA,
                   inference='Labels only inferred from exact source call order',
                   width_qualification=False, image_integrity_verified=False)
    (target/'context.json').write_text(json.dumps(context, indent=2)+'\n', encoding='utf-8')
    context_raw = (target/'context.json').read_bytes()
    inventory.append(dict(original_path='generated binding; see archived frame metadata and frozen build',
                          archived_path='context.json', bytes=len(context_raw), sha256=sha(context_raw)))
    (target/'inputs.json').write_text(json.dumps(inventory, indent=2)+'\n', encoding='utf-8')
    result = analyze(target)
    (target/'ordered-analysis.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    (target/'timing.md').write_text(table(result), encoding='utf-8')
    return dict(name=name, sequence=result['sequence'], image=result['saved_name'],
                pulses=result['complete_pulse_count'], width_qualification=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('work', type=Path)
    parser.add_argument('names', nargs='+')
    args = parser.parse_args()
    for name in args.names:
        print(json.dumps(archive(args.work.resolve(), name), indent=2))
