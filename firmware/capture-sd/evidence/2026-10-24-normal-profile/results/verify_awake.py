"""Verify compact awake-run records and readback coverage without image bytes."""
from pathlib import Path
import hashlib
import json
import struct

HERE = Path(__file__).resolve().parent
def sha(raw): return hashlib.sha256(raw).hexdigest()
def read(path): return json.loads(path.read_text(encoding='utf-8'))

def verify(run):
    root = HERE / run
    index = read(root / 'index.json')
    for entry in index['files']:
        path = (root / entry['archived_path']).resolve()
        assert path.is_relative_to(root.resolve())
        raw = path.read_bytes()
        assert len(raw) == entry['bytes'] and sha(raw) == entry['sha256'], path
        assert path.suffix.lower() not in ('.png', '.sal', '.f32')
        assert path.name not in ('raw.bin', 'data.bin')
    summary = read(root / 'summary.json')
    png = read(root / (run + '-png') / 'verified.json')
    frame = read(root / summary['frame_metadata_path'])
    assert png == summary['png_verification']
    assert png['all_png_chunk_crcs_valid'] and png['exact_pixels_sample_shift_left_6']
    assert png['pixels'] == 1527680 and png['sBIT'] == 10
    assert png['frame_sha256'] == frame['raw_sha256']
    assert summary['receiver_proof_valid_after_maintenance'] == frame['receiver_proof_valid_after_maintenance']
    chunks = sorted((root / (run + '-png')).glob('chunk-*/result.json'))
    assert len(chunks) == png['hardware_reads'] == 6
    offset = 0
    for path in chunks:
        result = read(path)
        request = result['request']; report = result['report']; data = result['readback']
        assert request['operation'] == 3 and request['offset'] == offset
        assert report['result'] == 0 and report['state'] == 2 and report['media_idle'] == 1
        assert report['terminal'] == 0x444F4E45 and report['nonce'] == request['nonce']
        assert not any(result[k] for k in ('reset_sent', 'power_changed', 'nor_commands_sent'))
        assert data['offset'] == offset and data['name'] == request['name']
        omitted = next(x for x in index['omitted'] if x['original_path'].endswith(
            run + '-png/' + path.parent.name + '/data.bin'))
        assert data['bytes'] == omitted['bytes'] and data['sha256'] == omitted['sha256']
        offset += data['bytes']
    assert offset == png['bytes']
    maintenance = read(root / (run + '-maintenance') / 'result.json')
    words = struct.unpack('<128I', (root / (run + '-maintenance') / 'storage-report.bin').read_bytes())
    assert list(words) == maintenance['storage_proof']['report']['raw_words']
    assert words[1] == 2 and words[3] == 2 and words[6] == 0
    # Exact-pixel/PNG verification is an archived host result, not replayed
    # here: deliberately omitted image bytes cannot be decoded again.
    return dict(run=run, indexed_files=len(index['files']), read_chunks=len(chunks),
                bytes_covered=offset, metadata_verified=True,
                image_decoding_replayed=False, hardware_accessed=False)

if __name__ == '__main__':
    print(json.dumps([verify('awake01'), verify('awake02')], indent=2))
