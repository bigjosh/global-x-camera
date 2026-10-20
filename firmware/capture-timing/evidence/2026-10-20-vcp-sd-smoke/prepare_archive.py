"""Prepare the compact VCP/NOR evidence subset; never open an SD-data folder.

Explicit source allowlist only. No hardware, deletion, Git operation or
instrument access. Large waveform files are hashed but kept local.
"""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
BENCH = ROOT/'tmp/bringup/vcp-install-20261019'
BUILD = ROOT/'tmp/bringup/capture-vcp-recovery-v45b-20261020'
PREFIX_SHA = 'a8aebf4ed32d735d6352e9d5267759ed7b2c6733ac1a87bd4a0926a51c17e08a'
SECTOR_SHA = '2323caa6b0ef142a6f46adbfdb078f9070877f7665f97337145de75eec60b3d2'
RECEIVER_SHA = '478680d7ca87b19a0bcbab208535b36ab1fd985e141ce69a86b3602963a621ac'
INDEX = []
TEXT = {'.json', '.jsonl', '.log', '.c', '.h', '.S', '.ld', '.txt', '.lst', '.py'}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def describe(source):
    source = source.resolve()
    if not source.is_relative_to(ROOT) or any(p.startswith('sd-') for p in source.parts):
        raise ValueError(f'Outside VCP evidence allowlist: {source}')
    raw = source.read_bytes()
    return raw, dict(original_path=source.relative_to(ROOT).as_posix(),
                     original_bytes=len(raw), original_sha256=digest(raw))


def save(relative, data):
    target = HERE/relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.read_bytes() != data:
        raise ValueError(f'Refusing to replace a differing archive file: {target}')
    target.write_bytes(data)
    return dict(archived_path=target.relative_to(HERE).as_posix(),
                archived_bytes=len(data), archived_sha256=digest(data))


def copy(source, relative):
    raw, entry = describe(source)
    archived = raw
    encoding = None
    if source.suffix in TEXT:
        encoding = 'utf-8-sig'
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError:
            if source.suffix != '.log':
                raise
            # CubeProgrammer's Windows progress output contains ANSI bytes.
            encoding = 'cp1252'
            text = raw.decode(encoding)
        archived = text.replace('\r\n', '\n').replace('\r', '\n').encode()
    entry.update(save(relative, archived), transformation=(
        f'{encoding} to UTF-8 without BOM, LF newlines' if source.suffix in TEXT else 'byte-identical'))
    INDEX.append(entry)


def omitted(source, why):
    _, entry = describe(source)
    entry.update(archived_path=None, archived_bytes=None, archived_sha256=None,
                 retained_local_reason=why)
    INDEX.append(entry)


def emit(relative, value, source=None):
    data = (json.dumps(value, indent=2)+'\n').encode()
    result = save(relative, data)
    if source is not None:
        _, entry = describe(source)
        entry.update(result, transformation='derived compact summary; raw source remains local')
        INDEX.append(entry)
    return result


def stats(items):
    values = [(i['end_s']-i['start_s'])*1e6 for i in items]
    return dict(count=len(values), min_us=min(values) if values else None,
                max_us=max(values) if values else None,
                mean_us=sum(values)/len(values) if values else None)


def archive_signal(name):
    folder = BENCH/name
    source = folder/'signal-summary.json'
    d = json.loads(source.read_text())
    nrst = d['digital_intervals']['Channel 0']
    uart = d['digital_intervals']['Channel 6']
    nrst_lows = [i for i in nrst if i['level'] == 0]
    uart_lows = [i for i in uart if i['level'] == 0]
    # Exclude idle intervals at the beginning/end of the UART observation.
    high_inside = [i for i in uart[1:-1] if i['level'] == 1]
    main_reset = max(nrst_lows, key=lambda i: i['end_s']-i['start_s'])
    summary = dict(
        scope='Compact signal measurements; firmware selection is established by separate park records',
        digital_sample_rate_hz=6250000, channel_map={'0': 'NRST', '6': 'PE6 / VCP TX'},
        analog=d['analog'], nrst_low_intervals=stats(nrst_lows),
        longest_nrst_low=main_reset, pe6_low_pulses=stats(uart_lows),
        pe6_interior_high_intervals=stats(high_inside),
        first_pe6_low_s=uart_lows[0]['start_s'], last_pe6_low_end_s=uart_lows[-1]['end_s'],
        pe6_low_pulses_starting_after_longest_nrst_low=sum(
            i['start_s'] >= main_reset['end_s'] for i in uart_lows),
        pe6_burst_tail_after_longest_nrst_low_s=uart_lows[-1]['end_s']-main_reset['end_s'],
        raw_tool_limitations=d['limitations'],
        limitation_correction=(
            'The raw generic statement "No firmware detector or cold-boot test." is stale here: '
            'v45b was installed for these runs. The cold-c0 run explicitly power-cycled the target. '
            'Use the archived exact park results for firmware selection; host times are not '
            'analyzer timestamps, and API success alone does not prove an electrical level.'))
    emit(f'signals/{name}/summary.json', summary, source)
    for filename in ('config.json', 'events.json', 'off.json', 'auto.json'):
        if (folder/filename).is_file():
            copy(folder/filename, f'signals/{name}/{filename}')
    for filename in ('digital.csv', 'analog.csv', 'signal.sal', 'power-cycle.sal'):
        if (folder/filename).is_file():
            omitted(folder/filename, 'Full waveform remains local; compact measurements archived')


def main():
    prefix = (BUILD/'staged/stage1.bin').read_bytes()
    sector = (BUILD/'staged/capture_sector_0.bin').read_bytes()
    receiver = (BUILD/'receiver/capture.bin').read_bytes()
    assert digest(prefix) == PREFIX_SHA and len(prefix) == 5140
    assert digest(sector) == SECTOR_SHA and len(sector) == 65536
    assert digest(receiver) == RECEIVER_SHA and len(receiver) == 14344
    assert sector[0x400:0x400+len(prefix)] == prefix
    assert sector[0x2000:0x2000+len(receiver)] == receiver
    pm = json.loads((BUILD/'staged/manifest.json').read_text())
    for path, expected in pm['sources'].items():
        source = ROOT/path
        assert digest(source.read_bytes()) == expected
        copy(source, 'build/staged/'+source.name)
    for filename in ('manifest.json', 'stage1.bin', 'stage1_boot.bin',
                     'capture_sector_0.bin', 'stage1.lst', 'symbols.txt'):
        copy(BUILD/'staged'/filename, 'build/staged/'+filename)
    for filename in ('manifest.json', 'capture.bin'):
        copy(BUILD/'receiver'/filename, 'build/receiver/'+filename)
    for path, expected in pm['generator_inputs'].items():
        source = ROOT/path
        assert digest(source.read_bytes()) == expected
        copy(source, 'build/generator/'+source.name)
    copy(ROOT/'firmware/capture-timing/evidence/2026-10-18-phase-leds/toolchain.json',
         'build/toolchain-v44-base.json')

    for filename in ('verified.json', 'before-read.log', 'write.log', 'after-read.log',
                     'read-request.json', 'write-request.json', 'after-read-request.json'):
        copy(BENCH/'development-nor'/filename, 'programming/'+filename)
    before_guard = (BENCH/'development-nor/before-guard.bin').read_bytes()
    after = (BENCH/'development-nor/after-68k.bin').read_bytes()
    assert after[:65536] == sector and after[65536:] == before_guard
    for filename in ('before-guard.bin', 'after-68k.bin', 'before-68k.bin', 'before-64k.bin'):
        omitted(BENCH/'development-nor'/filename,
                'NOR readback buffer remains local; exact compiled sector and verification result archived')

    for folder in ('recovery-park-cold-c0-01', 'recovery-park-c0-02'):
        for source in sorted((BENCH/folder).iterdir()):
            assert source.is_file() and source.suffix in ('.bin', '.json', '.jsonl', '.log')
            assert source.stat().st_size < 10000
            copy(source, f'parks/{folder}/{source.name}')
        result = json.loads((BENCH/folder/'result.json').read_text())
        assert result['passed'] and result['prefix_sha256'] == PREFIX_SHA
        assert result['status']['reserved'] == 2 and result['status']['idr'] & 2
        assert (BENCH/folder/'live-prefix.bin').read_bytes() == prefix
    for filename in ('request.json', 'status.json', 'status-00.bin', 'calls.jsonl',
                     'cli-01.log', 'cli-02.log', 'cli-03.log', 'cli-04.log'):
        copy(BENCH/'recovery-nor-info-01'/filename, 'nor-info/'+filename)
    info = json.loads((BENCH/'recovery-nor-info-01/status.json').read_text())
    assert info['result'] == 0 and info['wren_count'] == 0 and info['pages_programmed'] == 0

    failures = []
    for folder, stimulus in (
            ('normal-inspect-01', 'normal cold boot, no recovery stimulus'),
            ('recovery-park-01', 'first warm 1 Mbaud 0x00 request'),
            ('recovery-park-02', 'second warm 1 Mbaud 0x00 request'),
            ('recovery-park-c0-01', 'first warm 1 Mbaud 0xC0 request')):
        for source in sorted((BENCH/folder).iterdir()):
            assert source.is_file() and source.suffix in ('.jsonl', '.log')
            copy(source, f'failures/{folder}/{source.name}')
        text = (HERE/f'failures/{folder}/cli-01.log').read_text(encoding='utf-8')
        failures.append(dict(attempt=folder, stimulus=stimulus,
                             observation='AP1 access unavailable; no verified recovery park',
                             errors=[line for line in text.splitlines() if line.startswith('Error:')],
                             cause='unestablished'))
    emit('failures/summary.json', failures)
    for name in ('recovery-request-01', 'recovery-request-02', 'recovery-request-c0-01',
                 'recovery-cold-c0-01', 'recovery-request-c0-02'):
        archive_signal(name)
    copy(BENCH/'cycle.py', 'host/cycle.py')
    emit('validation.json', dict(
        prefix_sha256=PREFIX_SHA, sector_sha256=SECTOR_SHA, receiver_sha256=RECEIVER_SHA,
        full_65536_byte_programming_readback_matches=True, following_4096_bytes_unchanged=True,
        both_live_park_prefixes_match=True, both_park_records_select_pe6_with_pe1_high=True,
        nor_info_result=info['result'], nor_info_wren_count=info['wren_count'],
        sd_data_accessed_or_archived_by_this_script=False,
        normalization='Text archived as UTF-8/LF; original and archived hashes recorded separately',
        receiver_source_dependency='Previous 2026-10-18-phase-leds archive; receiver unchanged',
        generator_sha256=digest(Path(__file__).read_bytes())))
    emit('source-index.json', dict(schema=1, entries=INDEX))
    print(json.dumps(dict(files=sum(e['archived_path'] is not None for e in INDEX),
                          retained_local=sum(e['archived_path'] is None for e in INDEX),
                          archived_bytes=sum(e['archived_bytes'] or 0 for e in INDEX),
                          sector_sha256=SECTOR_SHA)))


if __name__ == '__main__':
    main()
