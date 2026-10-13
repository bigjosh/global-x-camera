"""Read the unchanged native export; extract recovery evidence, not a CAD conversion."""
import base64
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import sys

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from inventory_parts import parse_edif

source=BASE/'bigjosh-global-x-camera.flx'
d=json.loads(source.read_text(encoding='utf-8'))
old=json.loads((ROOT/'datasheets/parts-inventory.json').read_text(encoding='utf-8'))

def props(items):
    return {p['name']:p.get('value') for p in items.values() if p.get('name')}

def rules(items):
    return {k:v.get('value') for k,v in items.items()}

def child(node,key):
    return next((v[1:] for v in node if isinstance(v,list) and v and v[0]==key),None)

pin_nets=defaultdict(list)
canonical=defaultdict(list)
for netid,n in d['nets'].items():
    for p in n.get('pins',{}).values():
        key=(p['elementUid'],p['terminalUid'])
        name=n.get('canonicalName') or n.get('label')
        pin_nets[key].append({'net_uid':netid,'canonical_name':name,'label':n.get('label')})
        canonical[name].append({'element_uid':key[0],'terminal_uid':key[1]})

records={}
footprint_hashes=set()
total_terminals=0
missing_numbers=[]
duplicate_numbers={}
for uid,e in d['elements'].items():
    ref=e.get('label',uid); c=e['part_version_data_cache']; rec={
        'element_uid':uid,'part_uid':e.get('part_uid'),'part_version':e.get('part_version'),
        'properties':props(e.get('properties',{})),
        'symbol_placements':e.get('symbol_placements'),
        'pcb_instance_rules':rules(d['pcbLayoutNodes'].get(uid,{}).get('pcbNodeRuleSet',{})),
        'terminals':[], 'footprints':[],
    }
    counts=Counter()
    for tid,t in c.get('terminals',{}).items():
        total_terminals+=1; num=t.get('pin_number'); counts[num]+=1
        if not num:missing_numbers.append({'reference':ref,'terminal_uid':tid,'name':t.get('name')})
        entry={'uid':tid,'name':t.get('name'),'pin_number':num,
            'nets':pin_nets.get((uid,tid),[]),
            'no_connect':uid+'__'+tid in d.get('noConnects',{})}
        terminal_props=props(d.get('subDocumentData',{}).get('elements',{}).get(uid+'__'+tid,{}).get('properties',{}))
        entry['terminal_properties']=terminal_props
        rec['terminals'].append(entry)
    dup={str(k):v for k,v in counts.items() if k and v>1}
    if dup:duplicate_numbers[ref]=dup
    for nid,n in c.get('pcbLayoutNodes',{}).items():
        if n.get('type')!='footprint':continue
        a=n.get('pcbNodeRuleSet',{}).get('asset',{})
        payload=a.get('payloadAsBase64','')
        fr={'cache_node_uid':nid,'payload_filename':a.get('payloadFileName'),'asset_name':a.get('value')}
        if payload:
            raw=base64.b64decode(payload)
            fr['sha256']=hashlib.sha256(raw).hexdigest();footprint_hashes.add(fr['sha256'])
            fr['bytes']=len(raw)
            try:
                tree=parse_edif(raw.decode('utf-8-sig'))
                pads=[x for x in tree if isinstance(x,list) and x and x[0]=='pad']
                fr['pad_record_count']=len(pads)
                fr['numbered_pad_ids']=sorted({str(x[1]) for x in pads if str(x[1]) not in ['', '~']})
                if ref in ['U1','U7','U10','J3','D3','SW2','SW3']:
                    fr['pad_geometry']=[{'number':p[1],'type':p[2],'shape':p[3],
                        'at':child(p,'at'),'size':child(p,'size'),'layers':child(p,'layers'),
                        'custom_primitives':child(p,'primitives')} for p in pads]
            except Exception as exc:fr['parse_error']=str(exc)
        rec['footprints'].append(fr)
    records[ref]=rec

old_refs={e['reference'] for e in old['edif_instances']}
bom_refs={r for row in old['bom_rows'] for r in row['Designator'].split(',')}
stackups=[]
for nid,n in d['pcbLayoutNodes'].items():
    if n.get('type')=='layout':
        r=n.get('pcbNodeRuleSet',{}); stackups.append({'node_uid':nid,'rules':rules(r),
            'decoded_stackup':json.loads(base64.b64decode(r['stackup']['payloadAsBase64']))})
summary={
    'source_file':source.name,'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
    'counts':{'elements':len(records),'terminals':total_terminals,'missing_pin_numbers':len(missing_numbers),
        'top_level_net_records':len(d['nets']),'nonempty_canonical_net_names':len({n.get('canonicalName') for n in d['nets'].values() if n.get('canonicalName')}),
        'singleton_net_records':sum(len(n.get('pins',{}))==1 for n in d['nets'].values()),
        'net_endpoint_records':sum(len(n.get('pins',{})) for n in d['nets'].values()),
        'explicit_no_connects':len(d['noConnects']),'pcb_node_types':dict(Counter(n.get('type') for n in d['pcbLayoutNodes'].values())),
        'board_rule_sets':len(d['pcbLayoutRuleSets']),'unique_embedded_footprint_payloads':len(footprint_hashes),
        'route_records':len(d['routes']),'route_vertices':len(d['routeVertices']),
        'old_edif_instances':len(old_refs),'old_edif_nets':len(old['edif_nets']),
        'old_edif_endpoints':sum(len(n['connections']) for n in old['edif_nets'])},
    'not_in_old_edif':sorted(set(records)-old_refs),'not_in_bom':sorted(set(records)-bom_refs),
    'missing_pin_numbers':missing_numbers,'duplicate_pin_numbers':duplicate_numbers,
    'connectivity_warning':'All 544 native top-level net records are single-pin fragments; only 81 have canonical names. These are NOT 544 resolved electrical nets. Use original EDIF or verified IPC export for connectivity until native fragment semantics are reconciled.',
    'board_layouts':stackups,'board_rule_sets':d['pcbLayoutRuleSets'],'instances':records,
}
(BASE/'native-inventory.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in summary.items() if k not in ['instances','board_layouts','board_rule_sets']},ensure_ascii=True,indent=2))
for ref in ['U1','U7','U10','J3','D3','SW2','SW3']:
    rec=records[ref]
    print(ref,'footprints',[(f.get('bytes'),f.get('pad_record_count'),len(f.get('numbered_pad_ids',[]))) for f in rec['footprints']])
    if ref!='U1':print('  pins',[(t['pin_number'],t['name'],[n['label'] for n in t['nets']],t['no_connect']) for t in rec['terminals']])
