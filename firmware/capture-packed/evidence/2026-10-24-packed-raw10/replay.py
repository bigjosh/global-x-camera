"""Offline verification of archived source/binary hashes, proofs and RAW10 pixels.

Imports no instrument, debug, serial or power-control module. Pixel replay uses
the preserved independent scalar decoder and test-pattern payloads only.
"""
import argparse
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import struct
import zipfile
import zlib

HERE = Path(__file__).resolve().parent


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_object(record):
    path = (HERE / record['path']).resolve()
    path.relative_to(HERE)
    raw = path.read_bytes()
    if sha(raw) != record['sha256'] or len(raw) != record['bytes']:
        raise ValueError('Object hash/length mismatch: ' + str(path))
    return raw


def load_tool(index, name):
    record = index['tools'][name]
    raw = read_object(record)
    path = HERE / record['path']
    spec = importlib.util.spec_from_file_location('archived_' + Path(name).stem, path)
    module = importlib.util.module_from_spec(spec)
    # Compiling exact bytes avoids pycache writes inside the evidence tree.
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module


def record_files(record):
    raw = read_object(record['archive'])
    out = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        if set(archive.namelist()) != set(record['entries']):
            raise ValueError('ZIP entry inventory mismatch')
        for name, expected in record['entries'].items():
            data = archive.read(name)
            if sha(data) != expected['sha256'] or len(data) != expected['bytes']:
                raise ValueError('ZIP member differs: ' + name)
            out[name] = data
    return out


def decompress_record(record):
    raw = zlib.decompress(read_object(record['compressed']))
    if sha(raw) != record['raw_sha256'] or len(raw) != record['raw_bytes']:
        raise ValueError('Compressed payload identity differs')
    return raw


def run():
    index = json.loads((HERE / 'index.json').read_bytes())
    if index['schema'] != 1 or index['line_ending_normalization']:
        raise ValueError('Unexpected archive schema or normalization')
    for rel, record in index['objects'].items():
        read_object(dict(path=rel, **record))
    builds = {}
    for name, build in index['builds'].items():
        files = {n: read_object(v) for n, v in build['files'].items()}
        manifest = json.loads(files['manifest.json'])
        if sha(files['capture.bin']) != manifest['binary_sha256']:
            raise ValueError('Build binary differs: ' + name)
        for filename, expected in manifest['source_hashes'].items():
            if sha(files[filename]) != expected:
                raise ValueError('Build source differs: ' + name + '/' + filename)
        if struct.unpack_from('<II', files['capture.bin']) != (manifest['stack'], manifest['entry']):
            raise ValueError('Build entry/vector differs')
        for key in ('park', 'reject_park'):
            off = manifest[key] - manifest['load']
            if files['capture.bin'][off:off+2] != b'\xfe\xe7':
                raise ValueError('Expected terminal park absent')
        builds[manifest['binary_sha256']] = (name, manifest, files['capture.bin'])
    protocol = load_tool(index, 'experiment/protocol.py')
    scalar = load_tool(index, 'experiment/verify_decode.py')
    scalar.self_test()
    qualified, failures = [], []
    for name, record in index['records'].items():
        files = record_files(record)
        if name == 'native-pattern01':
            proof = json.loads(files['proof.json'])
            if (proof['state'], proof['result'], proof['control']) != (15, 0x204, 12):
                raise ValueError('Historical v3 failure was altered')
            failures.append(name)
        verified = record.get('verified')
        if not verified or 'proof' not in verified or 'binary_sha256' not in verified:
            continue
        if not verified['passed'] or not verified['full_repeat_read_match']:
            raise ValueError('Trial lacks qualification')
        proof = verified['proof']
        if name.startswith('early-park'):
            continue
        build_name, manifest, code = builds[verified['binary_sha256']]
        pbytes = struct.pack('<40I', *(proof[k] for k in protocol.FIELDS))
        protocol.success(pbytes, proof['nonce'], manifest['mode'], manifest['pattern'])
        if files['bootstrap/final-proof.bin'] != pbytes:
            raise ValueError('Binary/final JSON proof differs')
        if files['bootstrap/capture-request.bin'] != protocol.request(proof['nonce'], manifest['mode'], manifest['pattern']):
            raise ValueError('Request identity differs')
        if files['bootstrap/capture-readback.bin'] != code:
            raise ValueError('Loaded code differs from build')
        if proof['cpacr'] != 0 or verified['raw10_detail'][10] != 0:
            raise ValueError('Context/allocation guard differs')
        guard = struct.pack('<8I', *(0xA15A1000+i for i in range(8)))
        if files['bootstrap/expected-guard.bin'] != guard or files['bootstrap/capacity-guard.bin'] != guard:
            raise ValueError('Recorded frame guard differs')
        for flag in ('sd_commands', 'nor_commands'):
            if verified[flag]:
                raise ValueError('Unexpected storage activity in capture trial')
        qualified.append(dict(trial=name, build=build_name, bytes=verified['frame_bytes'],
                              frame_sha256=verified['frame_sha256'], pattern=proof['pattern']))
    payloads = {}
    for name, record in index['pattern_payloads'].items():
        raw = decompress_record(record)
        payloads[name] = (record['mode'], raw)
    reference = payloads['native-pattern02'][1]
    if len(reference) != 3055360:
        raise ValueError('Native reference geometry differs')
    matches = []
    for name, (mode, raw) in payloads.items():
        decoded = scalar.decode_scalar(raw) if mode else raw
        if decoded != reference:
            raise ValueError('Test pattern pixels differ: ' + name)
        matches.append(dict(trial=name, pixels=len(decoded)//2,
                            decoded_sha256=sha(decoded), exact=True))
    final_state = None
    if 'bench_session' in index:
        session = {name: decompress_record(record)
                   for name, record in index['bench_session'].items()}
        stop = json.loads(session['js-response.json'])
        lines = [json.loads(line) for line in session['js-session.jsonl'].splitlines()]
        state = json.loads(record_files(index['records']['restore-normal'])['state.json'])
        if (stop['event'] != 'stopped' or stop['ok'] is not True or
                stop['range'] != 128 or stop['starting_range'] != 128 or
                stop['restore_error'] is not None or lines[-1] != stop or
                state['stop_command'] != stop or not state['low_current_plateau'] or
                state['host_sd_commands'] or state['host_nor_commands'] or
                state['final_image_readback'] or state['final_sbf_readback']):
            raise ValueError('Final restoration/session proof differs')
        final_state = dict(completed_utc=state['completed_utc'],
                          current_A=state['final_statistics']['current']['avg'],
                          input_voltage_V=state['final_statistics']['voltage']['avg'],
                          target_powered=True, restored_range=128,
                          final_image_readback=False, final_sbf_readback=False,
                          final_nor_readback=False)
    return dict(passed=True, archived_objects=len(index['objects']),
                source_builds_verified=len(builds), successful_trials=qualified,
                preserved_failed_trials=failures, scalar_test_vectors=4096,
                full_pixel_comparisons=matches,
                final_state=final_state,
                scene_pixels_included=False, hardware_access=False,
                sd_streaming_qualified=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    result = run()
    text = json.dumps(result, indent=2) + '\n'
    if args.out:
        args.out.write_text(text, encoding='utf-8', newline='\n')
    print(text, end='')


if __name__ == '__main__':
    main()
