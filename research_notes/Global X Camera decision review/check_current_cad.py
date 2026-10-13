from pathlib import Path
import json, hashlib, xml.etree.ElementTree as ET, sys
ROOT=Path('D:/Github/global-x-camera'); OUT=ROOT/'research_notes/Global X Camera decision review'
sys.path.insert(0,str(ROOT/'tools'))
from kicad_sexpr import parse,children,child
baseline=ROOT/'hardware/reconstruction/schematic-connectivity.json'
b=json.loads(baseline.read_text(encoding='utf-8')); x=ET.parse(OUT/'current-schematic-netlist.xml').getroot()
actual={}; full_nets={}
for n in x.findall('./nets/net'):
 full_nets[n.get('name')]=[dict(v.attrib) for v in n.findall('node') if not v.get('ref','').startswith('#')]
 for p in full_nets[n.get('name')]: actual[(p['ref'],p['pin'])]=n.get('name')
diff=[]
for r,c in b['components'].items():
 for p,info in c['pins'].items():
  if info.get('net') and actual.get((r,p))!=info['net']: diff.append([r,p,info.get('net'),actual.get((r,p))])
comps={n.get('ref'):{'value':n.findtext('value'),'footprint':n.findtext('footprint')} for n in x.findall('./components/comp')}
keys=['BOOT_XSPI_NCS','NAND_RNB','RTC_INT_N','SHUTTER_SENSE','LATCH_PULLDOWN','PWR_HOLD','PMOS_GATE','BAT_FET_COMMON_SOURCE','3V3_USB','1V8']
foot=parse((ROOT/'hardware/kicad/GX.pretty/J3_Recovered.kicad_mod').read_text(encoding='utf-8'))
pads=[dict(pin=p[1],size=child(p,'size')[1:]) for p in children(foot,'pad')]
o=dict(baseline_sha256=hashlib.sha256(baseline.read_bytes()).hexdigest(),review_baseline_matches=hashlib.sha256(baseline.read_bytes()).hexdigest()=='51e7cc050d23652d4eaf891e7384f519d6f3fd94c0c72f2dd945cbf626a62e98',current_export_connected_mismatches=diff,components={r:comps[r] for r in ['U1','U2','U5','U6','U7','Q1','Q2','Q3','R1','R2','C38','L3']},nets={k:full_nets.get(k) for k in keys},J3_pad_sizes=pads)
(OUT/'current-cad-evidence.json').write_text(json.dumps(o,indent=2),encoding='utf-8')
print(json.dumps({**{k:v for k,v in o.items() if k not in ('nets','J3_pad_sizes')},'key_nets':{k:full_nets.get(k) for k in keys[:-2]},'J3_first_pad':pads[0]},indent=2))
