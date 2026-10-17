"""One-off v25 repeat archive. Run only after both root visual reviews."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / 'tmp/bringup/capture-raw10-trim-os-v25-20261017'
DEST = ROOT / 'firmware/capture-timing/evidence/2026-10-17-native-raw10-v25'
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

rm = json.loads((BUILD/'receiver/manifest.json').read_text())
pm = json.loads((BUILD/'staged/manifest.json').read_text())
assert pm['program_sha256'] == sha((BUILD/'staged/capture_sector_0.bin').read_bytes())
ledger, visual = [], []
for name, source in (
    ('cold-01','capture-opt-v25-raw10-cycle-01/cold'),
    ('cold-02','capture-opt-v25-raw10-cold-02')):
    capture=ROOT/'tmp/bringup'/source
    result=json.loads((capture/'ram/capture-result.json').read_text())
    timing=json.loads((capture/'timing.json').read_text())
    assert result['build_sha256'] == rm['raw_sha256'] == pm['stage2_sha256']
    assert result['completed'] and result['image_integrity_matches'] and timing['matched']
    assert result['frame_bytes'] == result['raw10_status_words'][1] == 3055360
    assert result['raw10_status_words'][7] == 0
    assert result['sample_statistics']['invalid_upper_bits'] == 0
    assert result['host_image']['sha256'] == sha((capture/'ram/frame.bin').read_bytes())
    rail=json.loads((capture/'logic/rail-validation.json').read_text())
    assert rail['passed']
    for path in ('timing.json','ram/capture-result.json','logic/digital.csv',
                 'logic/capture-config.json','logic/rail-validation.json',
                 'logic/boot-summary.json','ram/events.bin','ram/error-events.bin',
                 'ram/memory_status.bin','ram/prefix-status.bin','ram/raw10_status.bin','ram/trace-00.bin'):
        copy(capture/path,Path('captures')/name/path)
    summary=summarize_documents(timing,result)
    summary.update(experiment_id='v25-native-raw10-'+name,rail_validation=rail,
                   note='Raw visual fields unchanged; see separate visual-review.json.')
    ledger.append(summary)
    visual.append(dict(experiment_id='v25-native-raw10-'+name,
        reviewer='root bench controller',status='discernible LED panel',
        method='Root viewed fixed RAW10 >> 2 preview, without adaptive gain.',
        provenance='Root direct assertion in delegated messages; archiving agent did not inspect image.',
        source_result_sha256=sha((capture/'ram/capture-result.json').read_bytes()),
        frame_sha256=result['host_image']['sha256'],raw_result_visual_field_preserved=True))

cycle=ROOT/'tmp/bringup/capture-opt-v25-raw10-cycle-01'
for path in ('programmed-image.json','write/verified.json'):
    copy(cycle/path,Path('programming')/path)
verified=json.loads((cycle/'write/verified.json').read_text())
assert verified['byte_for_byte_match'] and verified['bytes']==65536
assert verified['sha256']==pm['program_sha256']
assert json.loads((cycle/'programmed-image.json').read_text())['sha256']==pm['program_sha256']
sources=[]
for name,manifest in (('receiver',rm),('staged',pm)):
    copy(BUILD/name/'manifest.json',Path('builds')/name/'manifest.json')
    for path,expected in manifest['sources'].items():
        source=ROOT/path
        assert sha(source.read_bytes())==expected,path
        object_path=Path('source-objects')/(expected+source.suffix.lower())
        if not (DEST/object_path).exists():copy(source,object_path)
        sources.append(dict(build=name,source=path.replace('\\','/'),expected_sha256=expected,
                            archive=object_path.as_posix(),status='verified exact bytes archived'))
for name in ('build_raw10.py','analyze.py','summarize.py'):
    copy(ROOT/'firmware/capture-timing'/name,Path('tools')/name)
copy(Path(__file__),Path('archive-script.py'))
licenses=ROOT/'firmware/capture-timing/evidence/2026-10-17-through-v16/licenses'
for source in licenses.rglob('*'):
    if source.is_file():copy(source,Path('licenses')/source.relative_to(licenses))
document('ledger.json',dict(schema=1,time_unit='us',experiments=ledger))
document('source-provenance.json',sources)
document('visual-review.json',dict(date='2026-10-17',reviews=visual))
document('archive-index.json',dict(schema=1,scope='Two native full-resolution RAW10 v25 cold captures.',
    exclusions=['frame.bin','frame.png','frame-16bit.png','analog.csv','boot.sal','NOR image/readback dumps'],
    files=records))
for record in records:
    data=(DEST/record['archive']).read_bytes()
    assert len(data)==record['bytes'] and sha(data)==record['sha256']
print(json.dumps(dict(files=len(records),bytes=sum(r['bytes'] for r in records),
    runs=[dict(experiment=e['experiment_id'],first_strobe_us=e['first_strobe_us'],
               first_frame_us=e['phases_us']['first_frame_complete']) for e in ledger]),indent=2))
