"""One-off byte-exact compact evidence archive; no hardware access."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
CAPTURE = ROOT / 'tmp/bringup/capture-opt-v24b-raw10-cycle-01'
BUILD = ROOT / 'tmp/bringup/capture-raw10-relocated-v24b-20261017'
DEST = ROOT / 'firmware/capture-timing/evidence/2026-10-17-native-raw10-v24b'
sys.path.insert(0, str(ROOT / 'firmware/capture-timing'))
from summarize import summarize_documents

records = []

def sha(data):
    return hashlib.sha256(data).hexdigest()

def publish(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError(f'Refusing changed overwrite: {path}')
    else:
        path.write_bytes(data)

def copy(source, relative):
    data = source.read_bytes()
    assert len(data) < 2_000_000
    publish(DEST / relative, data)
    records.append(dict(source=source.relative_to(ROOT).as_posix(), archive=Path(relative).as_posix(),
                        bytes=len(data), sha256=sha(data)))

def document(relative, value):
    publish(DEST / relative, (json.dumps(value, indent=2) + '\n').encode())

result = json.loads((CAPTURE/'cold/ram/capture-result.json').read_text())
timing = json.loads((CAPTURE/'cold/timing.json').read_text())
rm = json.loads((BUILD/'receiver/manifest.json').read_text())
pm = json.loads((BUILD/'staged/manifest.json').read_text())
assert result['build_sha256'] == rm['raw_sha256'] == pm['stage2_sha256']
assert result['completed'] and result['image_integrity_matches'] and timing['matched']
assert result['frame_bytes'] == result['raw10_status_words'][1] == 3055360
assert result['raw10_status_words'][7] == 0
assert result['sample_statistics']['invalid_upper_bits'] == 0
assert pm['program_sha256'] == sha((BUILD/'staged/capture_sector_0.bin').read_bytes())
assert result['host_image']['sha256'] == sha((CAPTURE/'cold/ram/frame.bin').read_bytes())

for path in ('analysis-note.json','programmed-image.json','cold.log','cold/timing.json',
             'cold/ram/capture-result.json','cold/logic/digital.csv',
             'cold/logic/capture-config.json','cold/logic/rail-validation.json',
             'cold/logic/boot-summary.json','write/verified.json',
             'cold/ram/events.bin','cold/ram/error-events.bin',
             'cold/ram/memory_status.bin','cold/ram/prefix-status.bin',
             'cold/ram/raw10_status.bin','cold/ram/trace-00.bin'):
    copy(CAPTURE/path, Path('capture')/path)

sources = []
for name, manifest in (('receiver',rm),('staged',pm)):
    copy(BUILD/name/'manifest.json', Path('builds')/name/'manifest.json')
    for path, expected in manifest['sources'].items():
        source = ROOT/path
        assert sha(source.read_bytes()) == expected, path
        object_path = Path('source-objects')/(expected+source.suffix.lower())
        if not (DEST/object_path).exists():
            copy(source,object_path)
        sources.append(dict(build=name, source=path.replace('\\','/'), expected_sha256=expected,
                            archive=object_path.as_posix(), status='verified exact bytes archived'))

for name in ('build_raw10.py','analyze.py','summarize.py'):
    copy(ROOT/'firmware/capture-timing'/name,Path('tools')/name)
copy(Path(__file__),Path('archive-script.py'))
licenses=ROOT/'firmware/capture-timing/evidence/2026-10-17-through-v16/licenses'
for source in licenses.rglob('*'):
    if source.is_file():
        copy(source,Path('licenses')/source.relative_to(licenses))

summary = summarize_documents(timing,result)
summary.update(experiment_id='v24b-native-raw10-cold',
               note='Raw capture visual field intentionally unchanged; see separate visual-review.json.')
document('ledger.json',dict(schema=1,time_unit='us',experiments=[summary]))
document('source-provenance.json',sources)
document('visual-review.json',dict(date='2026-10-17',experiment_id='v24b-native-raw10-cold',
    reviewer='root bench controller',status='discernible LED panel',
    method='Root viewed fixed RAW10 >> 2 preview, without adaptive gain.',
    provenance='Root direct assertion in delegated message and captured analysis-note.json; archiving agent did not inspect image.',
    source_result_sha256=sha((CAPTURE/'cold/ram/capture-result.json').read_bytes()),
    frame_sha256=result['host_image']['sha256'],raw_result_visual_field_preserved=True))
document('archive-index.json',dict(schema=1,scope='First verified native full-resolution RAW10 cold capture, v24b.',
    exclusions=['frame.bin','frame.png','frame-16bit.png','analog.csv','boot.sal','NOR image/readback dumps'],
    files=records))
for record in records:
    content=(DEST/record['archive']).read_bytes()
    assert len(content)==record['bytes'] and sha(content)==record['sha256']
print(json.dumps(dict(files=len(records),bytes=sum(r['bytes'] for r in records),
                     first_strobe_us=summary['first_strobe_us'],
                     first_frame_us=summary['phases_us']['first_frame_complete'],
                     errors=summary['error_counts']),indent=2))
