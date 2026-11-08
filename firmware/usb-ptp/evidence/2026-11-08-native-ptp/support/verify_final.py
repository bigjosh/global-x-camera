"""Replay final USB evidence checks without touching hardware."""
from pathlib import Path
import datetime,hashlib,json
H=Path(__file__).resolve().parent

def rows(name):return [json.loads(x) for x in (H/name).read_text(encoding='utf-8').splitlines()]
def native(name,event):return [r['payload'] for r in rows(name) if r.get('event')=='native_output' and r['payload'].get('event')==event]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
pre={r['id'] for r in native('list08.jsonl','object') if r['id'].startswith('o')}
post={r['id'] for r in native('list08-persist.jsonl','object') if r['id'].startswith('o')}
assert len(pre)==190 and len(post)==189 and pre-post=={'oB0'} and not post-pre
assert native('delete08-oB0.jsonl','delete_complete')[0]['success']
expected='a0fb448e7bd4f003015ffa98855403633fff1c8a7b89fb7916ea836baac84bb6'
for name in ('photo08-neighbor.png','photo08-aftercancel.png','photo08-afterlatecancel.png'):
 assert sha(H/name)==expected
assert sha(H/'photo08-new-oBE.png')==sha(H/'photo08-persist.png')
cancels=[]
for name in ('cancel08-100ms.jsonl','cancel08-1500ms.jsonl'):
 c=native(name,'download_async_cancel_observation')[0]
 assert c['api_reported_cancellation'] and c['pending_api_hresult']=='0x800703e3'
 cancels.append(c)
cs=json.loads((H/'status08-cancelpassed/status.json').read_text())
assert cs['ptp'][12]==2 and cs['ptp'][19]==0 and cs['ptp'][4]==0 and cs['usb'][12]==2
fs=json.loads((H/'status08-final/status.json').read_text())
assert fs['status'][2]==4 and fs['status'][8:15]==[0,0,0,0,0,1,1]
assert fs['status'][21:23]==[0,0] and fs['ptp'][4]==0 and fs['ptp'][5]==189
assert fs['usb'][16:18]==[480,1] and fs['vbus'][9]==1
m=json.loads((H/'package08/manifest.json').read_text())
for off,key in [(0,'sector0_sha256'),(1,'sector1_sha256')]:
 v=json.loads((H/f'nor-verify{off}-final08/result.json').read_text())
 assert v['matches'] and v['sha256']==m[key]
assert (H/'nor-verify2-final08/readback.bin').read_bytes()==(H/'nor-backup2/readback.bin').read_bytes()
assert (H/'ram08/usb.bin').read_bytes()==(H/'ram08-audit/usb.bin').read_bytes()
power=json.loads((H/'final-js-stats.json').read_text());assert power['initial']==power['final'] and not power['power_changed']
report=dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),passed=True,photo_count_before=190,photo_count_after=189,
 deleted_object='oB0',deleted_zero_based_slot=175,deletion_persisted_after='normal powered reset and SD reinitialization',
 survivor_object='oBE',survivor_png_sha256=sha(H/'photo08-persist.png'),neighbor_sha256=expected,
 cancel_pending_api_results=cancels,firmware_received_cancels=2,cleanup_failures=0,
 nor_regions_byte_equal=True,adjacent_4k_unchanged=True,independent_usb_build_equal=True,
 final_state='Powered in final normal USB PTP service; SD idle, no active transfer, 189 photos, USB HS 480 Mbps.',
 final_js=dict(range=power['final']['s/i/range/select'],current_mA=1000*power['statistics']['signals']['current']['avg']['value'],voltage_V=power['statistics']['signals']['voltage']['avg']['value']),
 firmware=m,limits=['No physical cable-removal or fully discharged cold-boot qualification.','Capture-control GPIO inputs were constant low; no phase or exposure-timing claim.','Capture tail is exact October28; normal-capture HOLD/DMA-sleep candidates remain uninstalled.','No live instrument calls from this replay.'])
(H/'final-verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k not in ('firmware','cancel_pending_api_results')},indent=2))
