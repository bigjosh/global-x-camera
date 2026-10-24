"""Replay compact read-only transfer evidence; image pixels are not archived."""
from pathlib import Path
import hashlib
import json
import struct

HERE = Path(__file__).resolve().parent / 'standby-png-readback'
MODULE = '91e1edfa43f95a9608b94457cfbf900c6f51d5ecd10d2b3b7667c84d40cd3844'
PREFIX = '247f27c231e0053b7024af29914c6a0cb1b7decb1632ac0d6142a68b89e2da58'
SECTOR = '8129f9cc79e92c678207b4aee838810cc805d0b860c40b2f77b434ae746c8b61'
BRIDGE = '9d0a4553845dbf033264bde3629e2601aac561799cac9e34ed841f32485abdb6'

def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

def verify():
    index = read(HERE / 'index.json')
    for item in index['files']:
        path = HERE / item['archived_path']
        assert path.suffix.lower() != '.png' and path.name != 'data.bin', path
        raw = path.read_bytes()
        assert len(raw) == item['bytes']
        assert hashlib.sha256(raw).hexdigest() == item['sha256'], path
    plan = read(HERE / 'plan.json')
    assert plan['read_only'] and not plan['raw_frame_available']
    assert plan['module_sha256'] == MODULE and plan['bridge_sha256'] == BRIDGE
    assert plan['recovery_identity']['sector_sha256'] == SECTOR
    assert plan['recovery_identity']['prefix_sha256'] == PREFIX
    boot = read(HERE / 'bootstrap/verified.json')
    assert boot['early_recovery']['passed']
    assert boot['proof']['result'] == boot['proof']['memory_result'] == 0
    assert boot['proof']['stage'] == 3 and boot['proof']['ccr'] == 513
    verified = read(HERE / 'verified.json')
    assert verified['read_only'] and not verified['raw_frame_comparison']
    assert plan['names'] == [image['name'] for image in verified['files']]
    chunks = 0
    for image in verified['files']:
        assert image['all_png_chunk_crcs_valid'] and image['complete_independent_decode']
        assert image['all_samples_10bit_left_aligned']
        assert image['width'] == 1120 and image['height'] == 1364
        assert image['pixels'] == 1527680 and image['sBIT'] == 10
        assert not image['exact_capture_pixel_comparison'] and image['readonly_card_writes'] == 0
        total = 0
        for chunk in sorted((HERE / Path(image['name']).stem).glob('chunk-*')):
            result = read(chunk / 'result.json')
            request, report, card = result['request'], result['report'], result['card']
            assert request['operation'] == report['operation'] == 3
            assert request['name'] == image['name'] and request['offset'] == total
            assert report['nonce'] == request['nonce']
            assert report['state'] == 2 and report['result'] == 0
            assert report['terminal'] == 0x444f4e45 and report['media_idle'] == 1
            assert 0 < report['read_bytes'] <= request['length'] <= 262144
            assert card['written_sectors'] == card['initialized'] == card['controller_owned'] == 0
            assert card['error'] == card['cleanup_error'] == 0 and card['media_idle'] == 1
            assert result['module_sha256'] == MODULE
            assert not any(result[key] for key in ('reset_sent', 'power_changed', 'nor_commands_sent'))
            raw = (chunk / 'report-00.bin').read_bytes()
            assert list(struct.unpack('<128I', raw)) == report['raw_words']
            total += report['read_bytes']
            chunks += 1
        assert total == image['bytes'], image['name']
    old = next(image for image in verified['files'] if image['name'] == 'IMG00001.PNG')
    assert old['known_file_hash_matched']
    assert old['sha256'] == '466e42c170b5af6a962df03d853d688b6cfb17da68f38c3ef157692457494330'
    return dict(passed=True, indexed_files=len(index['files']), images=len(verified['files']),
                read_chunks=chunks, image_decoding_replayed=False,
                scope='Archived proof/hash/READ coverage replay; original PNG decoding metadata is retained, not rerun without pixels')

if __name__ == '__main__':
    print(json.dumps(verify(), indent=2))
