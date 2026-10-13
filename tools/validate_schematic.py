"""Compare KiCad's exported netlist with the explicit reconstruction baseline."""
from collections import defaultdict
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
REC=ROOT/'hardware/reconstruction'


def main():
    baseline=json.loads((REC/'schematic-connectivity.json').read_text(encoding='utf-8'))
    source=json.loads((REC/'connectivity.json').read_text(encoding='utf-8'))
    xml=ET.parse(REC/'kicad-netlist.xml').getroot()
    actual_refs={e.get('ref') for e in xml.findall('./components/comp') if not e.get('ref','').startswith('#')}
    expected_refs=set(baseline['components'])
    actual={};errors=[];netmap={}
    for net in xml.findall('./nets/net'):
        endpoints=[]
        for n in net.findall('node'):
            if n.get('ref','').startswith('#'):continue
            key=(n.get('ref'),n.get('pin'))
            if key in actual:errors.append({'duplicate_endpoint':key})
            actual[key]=net.get('name');endpoints.append(key)
        netmap[net.get('name')]=endpoints
    expected={};nc=[]
    for ref,c in baseline['components'].items():
        for pin,info in c['pins'].items():
            key=(ref,pin)
            if info.get('net'):expected[key]=info['net']
            elif info['status']=='no_connect':nc.append(key)
            else:errors.append({'unresolved_baseline':key})
    for key,net in expected.items():
        if actual.get(key)!=net:errors.append({'endpoint':key,'expected_net':net,'actual_net':actual.get(key)})
    for key in nc:
        net=actual.get(key)
        if not net or not net.startswith('unconnected-') or len(netmap.get(net,[]))!=1:
            errors.append({'no_connect_not_isolated':key,'actual_net':net})
    expected_all=set(expected)|set(nc)
    if set(actual)!=expected_all:errors.append({'pin_coverage_mismatch':{'extra':sorted(set(actual)-expected_all),'missing':sorted(expected_all-set(actual))}})
    if actual_refs!=expected_refs:errors.append({'reference_mismatch':{'extra':sorted(actual_refs-expected_refs),'missing':sorted(expected_refs-actual_refs)}})
    # Check exported component values against raw source, including separately
    # stored engineering units, independently of the flattened old inventory.
    native=json.loads((ROOT/'imports/flux/2026-09-05/bigjosh-global-x-camera.flx').read_text(encoding='utf-8'))
    actual_components={c.get('ref'):c for c in xml.findall('./components/comp')}
    for element in native['elements'].values():
        ref=element['label'];properties={p['name']:p for p in element['properties'].values()}
        part=properties.get('Manufacturer Part Number',{}).get('value')
        if part:expected_value=str(part)
        else:
            chosen=next((properties[k] for k in ['Resistance','Capacitance','Inductance'] if properties.get(k,{}).get('value') not in (None,'')),None)
            if chosen:
                expected_value=str(chosen['value'])
                if re.fullmatch(r'-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?',expected_value):expected_value+=chosen.get('unit','')
            else:expected_value=ref
        expected_value=expected_value.replace('Ω','ohm').replace('µ','u').replace('μ','u')
        comp=actual_components.get(ref)
        if comp is not None and comp.findtext('value')!=expected_value:
            errors.append({'component_value_mismatch':ref,'expected':expected_value,'actual':comp.findtext('value')})
        if comp is not None and ref!='CAM1' and not comp.findtext('footprint'):
            errors.append({'missing_footprint_assignment':ref})
    preserved=0
    for ref,c in source['components'].items():
        for pin,info in c['pins'].items():
            if info.get('net'):
                preserved+=1
                if actual.get((ref,pin))!=info['net']:errors.append({'recovered_source_changed':[ref,pin]})
    result={'kicad_version':xml.findtext('./design/tool'),'components':len(actual_refs),'physical_pins':len(actual),
        'connected_endpoints':len(expected),'isolated_no_connects':len(nc),'named_nets':len(set(expected.values())),
        'recovered_connected_endpoints_preserved':preserved,'documented_decisions':len(baseline['decisions']),
        'component_values_checked':len(native['elements']),
        'errors':errors,'passed':not errors}
    (REC/'validation.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))
    if errors:raise SystemExit(1)


if __name__=='__main__':main()
