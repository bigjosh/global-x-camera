"""Offline extraction of the independently repeated v24 cold capture."""
import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
DEST=Path(__file__).resolve().parent
SOURCE=ROOT/'tmp/bringup/capture-opt-v24-os-cold-02'
sys.path.insert(0,str(ROOT/'firmware/capture-timing'))
from summarize import summarize_documents
files=[]
def save(relative,data):
 p=DEST/relative;p.parent.mkdir(parents=True,exist_ok=True)
 if p.exists() and p.read_bytes()!=data: raise ValueError(str(p))
 p.write_bytes(data)
def copy(relative):
 source=SOURCE/relative; data=source.read_bytes();save(relative,data)
 files.append(dict(source=str(source.relative_to(ROOT)).replace('\\','/'),archive=relative,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
for relative in ['timing.json','ram/capture-result.json','ram/trace-00.bin','ram/events.bin','ram/error-events.bin','ram/prefix-status.bin','logic/digital.csv','logic/capture-config.json','logic/boot-summary.json','logic/rail-validation.json']:
 if (SOURCE/relative).exists():copy(relative)
timing=json.loads((SOURCE/'timing.json').read_text());result=json.loads((SOURCE/'ram/capture-result.json').read_text())
manifest=json.loads((ROOT/'tmp/bringup/capture-receiver-trim-v23-20261017/manifest.json').read_text())
assert result['build_sha256']==manifest['raw_sha256']
summary=summarize_documents(timing,result)
summary.update(experiment_id='v24-os-cold-repeat2',rail_validation=json.loads((SOURCE/'logic/rail-validation.json').read_text()),build_reference='../2026-10-17-v17-through-v24/builds/capture-receiver-trim-v23-20261017/manifest.json',prefix_reference='../2026-10-17-v17-through-v24/builds/capture-early-trim-os-v24-20261017/manifest.json')
for name,value in [('ledger.json',summary),('archive-index.json',dict(schema=1,files=files)),('visual-review.json',dict(status='LED grid discernible',reviewer='root bench controller',provenance='Root explicitly confirmed personal inspection of repeat2 frame.png; archiving agent did not inspect image.',raw_result_visual_field_preserved=True))]:
 save(name,(json.dumps(value,indent=2)+'\n').encode())
print(json.dumps(dict(files=len(files),first_strobe_us=summary['first_strobe_us'],first_frame_us=summary['phases_us']['first_frame_complete'])))
