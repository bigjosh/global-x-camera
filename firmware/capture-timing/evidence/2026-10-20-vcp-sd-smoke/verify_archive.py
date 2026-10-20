"""Read-only verification of compact VCP/NOR and selected SD evidence."""
import hashlib
import json
from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    index = json.loads((HERE/'source-index.json').read_text())
    checked = 0
    for entry in index['entries']:
        if entry['archived_path'] is None:
            continue
        path = (HERE/entry['archived_path']).resolve()
        assert path.is_relative_to(HERE) and path.is_file()
        raw = path.read_bytes()
        assert len(raw) == entry['archived_bytes']
        assert sha(raw) == entry['archived_sha256']
        if path.suffix != '.bin':
            assert b'\r' not in raw
            raw.decode('utf-8')
        checked += 1
    pm = json.loads((HERE/'build/staged/manifest.json').read_text())
    prefix = (HERE/'build/staged/stage1.bin').read_bytes()
    boot = (HERE/'build/staged/stage1_boot.bin').read_bytes()
    sector = (HERE/'build/staged/capture_sector_0.bin').read_bytes()
    receiver = (HERE/'build/receiver/capture.bin').read_bytes()
    assert sha(prefix) == pm['stage1_raw_sha256']
    assert sha(sector) == pm['program_sha256'] and len(sector) == 65536
    assert sha(receiver) == pm['stage2_sha256']
    assert sector[:len(boot)] == boot and boot[0x400:0x400+len(prefix)] == prefix
    assert sector[0x2000:0x2000+len(receiver)] == receiver
    assert struct.unpack_from('<I', boot, 0x64)[0] == sum(boot[0x240:]) & 0xffffffff
    assert struct.unpack_from('<I', boot, 0x6c)[0] == len(boot)-0x240
    park = int(pm['recovery_gpio']['park_address'], 16)
    assert prefix[park-0x34180400:park-0x34180400+2] == bytes.fromhex('fee7')
    for folder in ('recovery-park-cold-c0-01', 'recovery-park-c0-02'):
        path = HERE/'parks'/folder
        d = json.loads((path/'result.json').read_text())
        status = struct.unpack('<24I', (path/'recovery-status.bin').read_bytes())
        proof = struct.unpack('<32I', (path/'vcp-status.bin').read_bytes())
        assert d['passed'] and d['prefix_sha256'] == sha(prefix)
        assert (path/'live-prefix.bin').read_bytes() == prefix
        assert status[3:5] == (3, 1) and status[23] == 2 and status[12] & 2
        assert proof[20] == 1 and proof[24] == 2 and proof[17] >= 3
        assert (path/'recovery-status.bin').read_bytes() == (path/'recovery-status-rechecked.bin').read_bytes()
        assert (path/'vcp-status.bin').read_bytes() == (path/'vcp-status-rechecked.bin').read_bytes()
        assert d['context']['PC'] == park and not d['ccr'] & 0x30000
    info = json.loads((HERE/'nor-info/status.json').read_text())
    assert info['result'] == 0 and info['wren_count'] == 0 and info['pages_programmed'] == 0
    sd = HERE / 'sd-results'
    sd_index = json.loads((sd / 'source-index.json').read_text())
    for entry in sd_index:
        path = (sd / entry['archive']).resolve()
        assert path.is_relative_to(sd) and path.is_file()
        raw = path.read_bytes()
        assert sha(raw) == entry['archive_sha256']
        if path.suffix != '.bin':
            assert b'\r' not in raw
            raw.decode('utf-8')
    manifest = json.loads((sd / 'helper-v3-manifest.json').read_text())
    binary = (sd / 'helper-v3-sd-smoke.bin').read_bytes()
    assert sha(binary) == manifest['binary_sha256'] == (
        '790b240b4246d61daf6361da67cb2bca6084d666897902e0bfd1dc9555c03db6')
    assert len(binary) == 3120 and binary[0x5e4:0x5e6] == bytes.fromhex('fee7')
    for name, count in (('sd-read-100k-05', 2), ('sd-read-25m-01', 6)):
        report = json.loads((sd / (name + '.json')).read_text())
        assert report['read_smoke_pass'] and report['host_data_verified']
        assert report['status']['result'] == 0 and report['status']['read_count'] == count
        assert report['park_verification']['context']['PC'] == 0x341e05e4
        assert report['park_verification']['instruction'] == 'fee7'
        assert not report['sd_writes_or_erases']
        for i, b in enumerate(report['buffers']):
            if i >= 2:
                assert b['same_as_slow_read'] and b['crc32'] == report['buffers'][i % 2]['crc32']
    print(json.dumps(dict(passed=True, indexed_files_checked=checked,
                          sector_sha256=sha(sector), prefix_sha256=sha(prefix),
                          sd_indexed_files_checked=len(sd_index),
                          raw_card_bytes_inspected=False)))


if __name__ == '__main__':
    main()
