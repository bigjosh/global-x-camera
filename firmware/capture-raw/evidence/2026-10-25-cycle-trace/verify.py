"""Replay this frozen cycle-log archive offline; never touch the bench.

Validates published hashes, decodes the raw RAM logs again using archived event
headers, and cross-checks the recorded capture/image identities. Full original
camera RAM and SD-slot buffers remain private: their historical byte equality
cannot be independently rerun from this archive. If Pillow is already present,
also decode the public PNG and check its dimensions, bit depth and sample range.
No dependency is installed and no archive file is changed.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import zlib

HERE = Path(__file__).resolve().parent
EXPECTED_BINARIES = {
    'firmware/capture.bin': ('receiver_sha256', 28168,
        '0681708de7474c31159eb7125d8ed0a7d0d72844868bdfc6c184714fc2709380'),
    'firmware/stage1.bin': ('prefix_sha256', 5140,
        '0e37d33e1ede9008525feffb7f20c81112daf2169171f7130f68798366a4eec0'),
    'firmware/capture_sector_0.bin': ('sector_sha256', 65536,
        '9c9b65f023bb0c36e5c5149fddf8fbe2922c07294d25e859511b4cff9139810b'),
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def json_file(root, name):
    return json.loads((root / name).read_text(encoding='utf-8'))


def without_paths(value):
    """Paths may be sanitized or local; numeric/semantic/hash fields may not."""
    if isinstance(value, list):
        return [without_paths(item) for item in value]
    if isinstance(value, dict):
        return {key: without_paths(item) for key, item in value.items()
                if not (key in ('path', 'source') and isinstance(item, str))}
    return value


def png_check(root, image_record):
    data = (root / 'scene.png').read_bytes()
    require(sha(data) == image_record['png_sha256'], 'PNG identity mismatch')
    require(data[:8] == b'\x89PNG\r\n\x1a\n', 'Not a PNG')
    require(data[12:16] == b'IHDR' and struct.unpack('>I', data[8:12])[0] == 13,
            'Invalid PNG IHDR')
    width, height, depth, color, compression, filtering, interlace = struct.unpack('>IIBBBBB', data[16:29])
    require((width, height, depth, color, compression, filtering, interlace) ==
            (1120, 1364, 16, 0, 0, 0, 0), 'Unexpected PNG geometry/format')
    result = {'sha256': sha(data), 'width': width, 'height': height,
              'bit_depth': depth, 'grayscale': True, 'independent_decode': False}
    try:
        from PIL import Image
    except ImportError:
        result['decoder'] = 'Pillow absent; PNG hash and IHDR checked, no package installed'
        return result
    with Image.open(root / 'scene.png') as image:
        image.verify()
    with Image.open(root / 'scene.png') as image:
        image.load()
        read_pixels = getattr(image, 'get_flattened_data', None) or image.getdata
        values = list(read_pixels())
    require(len(values) == width * height, 'PNG pixel count mismatch')
    require(all(isinstance(value, int) and 0 <= value <= 65535 and not value & 63 for value in values),
            'PNG samples are not RAW10 values shifted left six bits')
    samples = [value >> 6 for value in values]
    minimum, maximum, mean = min(samples), max(samples), sum(samples) / len(samples)
    require(minimum == image_record['minimum_sample'] and maximum == image_record['maximum_sample'],
            'PNG sample extrema disagree with recorded image verification')
    require(abs(mean - image_record['mean_sample']) < 1e-9, 'PNG mean disagrees with recorded verification')
    result.update(independent_decode=True, decoder='Pillow already installed', pixels=len(samples),
                  minimum_raw10=minimum, maximum_raw10=maximum, mean_raw10=mean)
    return result


def verify(root=HERE):
    root = Path(root).resolve()
    freeze = json_file(root, 'FREEZE.json')
    require(freeze['schema'] == 1 and isinstance(freeze['files'], dict), 'Unsupported freeze schema')
    files = freeze['files']
    required = {'identity.json', 'capture-proof.json', 'image-validation.json', 'timings.json',
                'cycle-trace.bin', 'prefix-telemetry.json', 'prefix-trace-header.bin',
                'prefix-trace-events.bin', 'prefix-sensor.bin', 'prefix-loader.bin', 'scene.png',
                'headers/cycle_trace.h', 'headers/cycle_trace_events.h', 'headers/cycle_trace_sd.h',
                *EXPECTED_BINARIES}
    require(required <= files.keys(), 'Freeze omits a required replay input')
    for name, digest in files.items():
        path = (root / name).resolve()
        require(path != root and root in path.parents, f'Freeze path escapes archive: {name}')
        require(sha(path.read_bytes()) == digest, f'Frozen file SHA-256 mismatch: {name}')

    identity = json_file(root, 'identity.json')
    for name, (field, size, digest) in EXPECTED_BINARIES.items():
        data = (root / name).read_bytes()
        require(len(data) == size and sha(data) == digest == identity[field], f'Binary identity differs: {name}')
    receiver = (root / 'firmware/capture.bin').read_bytes()
    prefix = (root / 'firmware/stage1.bin').read_bytes()
    sector = (root / 'firmware/capture_sector_0.bin').read_bytes()
    require(identity['receiver_bytes'] == len(receiver) and identity['early_load_bytes'] == 15804 and
            identity['late_load_bytes'] == 12364 and 15804 + 12364 == len(receiver), 'Split load geometry differs')
    require(sector[0x400:0x400 + len(prefix)] == prefix, 'Sector does not contain the exact prefix')
    require(sector[0x2000:0x2000 + len(receiver)] == receiver, 'Sector does not contain the exact receiver')
    early_crc = zlib.crc32(receiver[:15804])
    require(all(struct.unpack_from('<I', prefix, offset)[0] == early_crc for offset in (0xC9C, 0x1354)),
            'Reviewed prefix CRC literals disagree with early receiver')
    require(identity['prefix_changed_bytes'] == [3228, 3229, 3230, 3231, 4948, 4949, 4950, 4951],
            'Recorded prefix changes extend beyond the reviewed CRC literals')
    require(identity['recovery_literals_unchanged'] is True and identity['disabled_control_matches'] is True,
            'Recorded recovery/default-control checks did not pass')

    spec = importlib.util.spec_from_file_location('archived_cycle_trace_decoder', HERE.parents[1] / 'cycle_trace.py')
    decoder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(decoder)
    header_names = ['cycle_trace_events.h', 'cycle_trace_sd.h']
    header_paths = [root / 'headers' / name for name in header_names]
    for name in ['cycle_trace.h', *header_names]:
        require(sha((root / 'headers' / name).read_bytes()) == identity['source_hashes'][name],
                f'Header is not the recorded build source: {name}')
    definitions = decoder.load_definitions(header_paths, {
        str(path): identity['source_hashes'][path.name] for path in header_paths})
    trace = decoder.decode((root / 'cycle-trace.bin').read_bytes(), definitions, require_complete=True)
    expected_trace = json_file(root, 'timings.json')
    require(without_paths(trace) == without_paths(expected_trace), 'Replayed timing/counter report differs')
    require(trace['status'] == 'complete' and trace['result'] == 0, 'Trace did not finish successfully')
    require(len(trace['events']) == identity['qualified_events'] == 101, 'Observed event count differs')
    require(trace['address'] == identity['trace_address'] == 0x343FB000 and
            trace['bytes'] == identity['trace_words'] * 4 == 1024, 'Trace ABI binding differs')
    prefix_trace = decoder.decode_prefix(*[(root / name).read_bytes() for name in (
        'prefix-trace-header.bin', 'prefix-trace-events.bin', 'prefix-sensor.bin', 'prefix-loader.bin')])
    require(prefix_trace == json_file(root, 'prefix-telemetry.json'), 'Replayed prefix report differs')
    require(prefix_trace['prefix_success'] is True, 'Prefix success not recorded')
    exceptions = prefix_trace['software_clock_exceptions']
    require(len(exceptions) == 1 and exceptions[0]['record_index'] == 23 and
            exceptions[0]['event_id'] == 2 and exceptions[0]['reported_software_clock_hz'] == 64000000 and
            exceptions[0]['qualified_dwt_clock_hz'] == 400000000, 'Unexpected software-clock exception')

    capture = json_file(root, 'capture-proof.json')
    proof = capture['proof']
    for field, expected in {'state': 3, 'result': 0, 'media_idle': 1, 'initialized': 0,
                            'controller_owned': 0, 'cleanup_error': 0, 'frames': 1, 'errors': 0,
                            'slot': 12, 'written_sectors': 3730, 'bytes': 1909600}.items():
        require(proof[field] == expected, f'Capture proof {field} differs')
    require(capture['halt_after_success_idle_only'] is True, 'Halt ordering qualification absent')
    image = json_file(root, 'image-validation.json')
    for flag in ('passed', 'full_payload_read', 'full_slot_read', 'start_magic_valid',
                 'completion_marker_valid', 'png_samples_match_read_raw', 'original_sensor_frame_comparison'):
        require(image[flag] is True, f'Image verification did not pass {flag}')
    require(image['source_reference_comparison']['kind'] == 'sensor-ram' and
            image['source_reference_comparison']['bytes_equal'] is True, 'Original-RAM comparison missing')
    require(image['raw_sha256'] == image['source_reference_comparison']['source']['sha256'] ==
            capture['frame_sha256'], 'Image/source capture hashes disagree')
    require(image['slot'] == proof['slot'] and image['bytes'] == proof['bytes'] and
            image['slot_bytes'] == proof['written_sectors'] * 512, 'Image/capture geometry differs')
    png = png_check(root, image)
    return {
        'passed': True, 'frozen_files_checked': len(files),
        'firmware_identities_checked': True, 'prefix_bytes': len(prefix),
        'trace_events_replayed': len(trace['events']), 'trace_counters_replayed': len(trace['counters']),
        'trace_result': trace['result'], 'prefix_events_replayed': prefix_trace['event_count'],
        'known_software_clock_exceptions': len(exceptions),
        'recorded_image_to_original_ram_equality_consistent': True,
        'original_ram_equality_independently_replayed': False,
        'png': png,
        'limits': [
            'Replay checks frozen files and their internal consistency; it does not access live hardware.',
            'Original camera RAM and full SD-slot buffers remain private, so their byte comparison cannot be independently replayed here.',
            'PNG decoding validates the public image and sample statistics, not a fresh camera-to-card readback.',
            'This awake run contains no new Standby-entry timing, complete-cycle energy or power-loss qualification.',
        ],
    }


if __name__ == '__main__':
    print(json.dumps(verify(), indent=2))
