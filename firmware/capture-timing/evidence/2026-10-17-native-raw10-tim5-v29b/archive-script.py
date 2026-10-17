"""One-off native RAW10 TIM5 evidence archive; no hardware access."""
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
BUILD=ROOT/'tmp/bringup/capture-raw10-tim5-v29b-20261017'
CYCLE=ROOT/'tmp/bringup/capture-opt-v29b-tim5-cycle-01'
CAPTURE=CYCLE/'cold'
DEST=ROOT/'firmware/capture-timing/evidence/2026-10-17-native-raw10-tim5-v29b'
sys.path.insert(0,str(ROOT/'firmware/capture-timing'))
from analyze_timer import analyze
from summarize import summarize_documents

records=[]
def sha(data):return hashlib.sha256(data).hexdigest()
def publish(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        if path.read_bytes()!=data:raise ValueError(f'Refusing changed overwrite: {path}')
    else:path.write_bytes(data)
def copy(source,relative):
    data=source.read_bytes()
    assert len(data)<2_000_000
    publish(DEST/relative,data)
    records.append(dict(source=source.relative_to(ROOT).as_posix(),archive=Path(relative).as_posix(),
                        bytes=len(data),sha256=sha(data)))
def document(relative,value):publish(DEST/relative,(json.dumps(value,indent=2)+'\n').encode())

rm=json.loads((BUILD/'receiver/manifest.json').read_text())
pm=json.loads((BUILD/'staged/manifest.json').read_text())
result=json.loads((CAPTURE/'ram/capture-result.json').read_text())
timing=json.loads((CAPTURE/'timing.json').read_text())
timer=json.loads((CAPTURE/'timer-analysis.json').read_text())
assert analyze(result,timing)==timer
assert result['build_sha256']==rm['raw_sha256']==pm['stage2_sha256']
assert result['completed'] and result['image_integrity_matches'] and timing['matched']
assert result['frame_bytes']==result['raw10_status_words'][1]==3055360
assert result['raw10_status_words'][7]==0
assert result['sample_statistics']['invalid_upper_bits']==0
assert result['host_image']['sha256']==sha((CAPTURE/'ram/frame.bin').read_bytes())
rail=json.loads((CAPTURE/'logic/rail-validation.json').read_text())
assert rail['passed']
for path in ('timing.json','timer-analysis.json','ram/capture-result.json','logic/digital.csv',
             'logic/capture-config.json','logic/rail-validation.json','logic/boot-summary.json',
             'ram/events.bin','ram/error-events.bin','ram/memory_status.bin','ram/prefix-status.bin',
             'ram/raw10_status.bin','ram/timer-status.bin','ram/trace-00.bin'):
    copy(CAPTURE/path,Path('capture')/path)
for path in ('programmed-image.json','write/verified.json'):
    copy(CYCLE/path,Path('programming')/path)
verified=json.loads((CYCLE/'write/verified.json').read_text())
assert verified['byte_for_byte_match'] and verified['bytes']==65536
assert verified['sha256']==pm['program_sha256']==sha((BUILD/'staged/capture_sector_0.bin').read_bytes())
assert json.loads((CYCLE/'programmed-image.json').read_text())['sha256']==pm['program_sha256']

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
for name in ('build_timer_probe.py','build_raw10.py','analyze_timer.py','test_analyze_timer.py','analyze.py','summarize.py'):
    copy(ROOT/'firmware/capture-timing'/name,Path('tools')/name)
copy(Path(__file__),Path('archive-script.py'))
licenses=ROOT/'firmware/capture-timing/evidence/2026-10-17-through-v16/licenses'
for source in licenses.rglob('*'):
    if source.is_file():copy(source,Path('licenses')/source.relative_to(licenses))
summary=summarize_documents(timing,result)
summary.update(experiment_id='v29b-native-raw10-tim5-cold-01',rail_validation=rail,
    timer_analysis='capture/timer-analysis.json',note='Raw visual fields unchanged; see visual-review.json.')
document('ledger.json',dict(schema=1,time_unit='us',experiments=[summary]))
document('source-provenance.json',sources)
document('visual-review.json',dict(date='2026-10-17',reviews=[dict(
    experiment_id=summary['experiment_id'],reviewer='root bench controller',status='discernible LED panel',
    method='Root viewed fixed RAW10 >> 2 preview, without adaptive gain.',
    provenance='Root direct assertion in delegated message; archiving agent did not inspect image.',
    source_result_sha256=sha((CAPTURE/'ram/capture-result.json').read_bytes()),
    frame_sha256=result['host_image']['sha256'],raw_result_visual_field_preserved=True)]))
long=next(o for o in timer['independent_frequency_calibration']['observations']
          if (o['first_event'],o['last_event'])==(3,40))
w=result['timer_status_words']
ticks=(w[32+12+4]-w[32+4])&0xFFFFFFFF
rejected_width=ticks*1e6/long['timer_hz']
document('rejected-long-calibration.json',dict(
    status='rejected constant-frequency assumption; no hardware failure',
    provenance='Reconstructed calculation from unchanged raw timer and external-event records; the earlier decoder raised before saving JSON.',
    assumption='Apply the event 3-to-40 average clock to the first exposure pulse.',
    independent_interval=long,first_pulse_ticks=ticks,
    predicted_first_pulse_us=rejected_width,
    external_first_pulse_us=timer['pulses'][0]['external_marker_width_us'],
    difference_us=rejected_width-timer['pulses'][0]['external_marker_width_us'],
    finding='Different non-strobe interval rates were observed across startup; the long interval is not used as a constant clock for first exposure.',
    resolution='Use independent near-exposure events 26-to-29 and retain the observed rate envelope with explicit endpoint uncertainty.',
    limitation='Observed empirical envelope, not a universal pointwise frequency bound; no physical cause for rate variation established.'))
document('archive-index.json',dict(schema=1,scope='One native full-resolution RAW10 TIM5 v29b cold capture.',
    exclusions=['frame.bin','frame.png','frame-16bit.png','analog.csv','boot.sal','NOR image/readback dumps'],files=records))
for record in records:
    data=(DEST/record['archive']).read_bytes()
    assert len(data)==record['bytes'] and sha(data)==record['sha256']
print(json.dumps(dict(files=len(records),bytes=sum(r['bytes'] for r in records),
    first_strobe_us=summary['first_strobe_us'],first_frame_us=summary['phases_us']['first_frame_complete'],
    first_edge=timer['records'][0],max_lag_us=timer['maximum_observed_marker_lag_us']),indent=2))
