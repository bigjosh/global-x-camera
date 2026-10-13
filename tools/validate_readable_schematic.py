"""Check that the presentation revision preserves the recovered circuit."""
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from kicad_sexpr import child, children, parse, dumps

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'hardware/kicad'
OUT=ROOT/'hardware/kicad-readable'

def read_netlist(path):
    tree=ET.parse(path).getroot()
    return {(n.get('ref'),n.get('pin')):net.get('name')
            for net in tree.findall('./nets/net') for n in net.findall('node')
            if not n.get('ref').startswith('#')}

def read_schematic(folder):
    properties={};pins={};marks=0;buses={};instances=set()
    for f in folder.glob('*.kicad_sch'):
        tree=parse(f.read_text(encoding='utf8'))
        marks+=len(children(tree,'no_connect'))
        for bus in children(tree,'bus_alias'):buses[bus[1]]=child(bus,'members')[1:]
        for s in children(tree,'symbol'):
            pr={p[1]:p[2] for p in children(s,'property')};ref=pr['Reference']
            if ref.startswith('#'):continue
            unit=int(child(s,'unit')[1]);instances.add((ref,unit))
            properties[ref,unit]=(pr,tuple((k,str(child(s,k)[1])) for k in ['in_bom','on_board','dnp']))
        for s in children(child(tree,'lib_symbols'),'symbol'):
            ref=s[1].split(':')[-1]
            if ref not in {r for r,u in instances}:continue
            for group in children(s,'symbol'):
                unit=int(re.search(r'_(\d+)_\d+$',group[1])[1])
                for p in children(group,'pin'):
                    # Geometric coordinates, lengths and text sizes may change.
                    pins[ref,unit,str(child(p,'number')[1])]=(str(p[1]),str(p[2]),str(child(p,'name')[1]),bool(child(p,'hide')))
    return properties,pins,marks,buses,instances

def main():
    source=read_netlist(ROOT/'hardware/reconstruction/kicad-netlist.xml')
    revised=read_netlist(OUT/'review/netlist.xml')
    assert set(source)==set(revised),'Physical endpoint set changed'
    def nc(n):return n.startswith('unconnected-')
    mismatches={str(k):(v,revised[k]) for k,v in source.items() if v!=revised[k] and not(nc(v) and nc(revised[k]))}
    assert not mismatches,mismatches
    # Compare the full connectivity partition, including no-connect isolation.
    for k,n in source.items():
        a={p for p,v in source.items() if v==n}
        b={p for p,v in revised.items() if v==revised[k]}
        assert a==b,(k,a,b)
    a=read_schematic(SRC);b=read_schematic(OUT)
    assert a[0]==b[0],'Component properties or BOM/board/DNP status changed'
    assert a[1]==b[1],'Pin identity, electrical type, shape or unit assignment changed'
    assert a[2]==b[2]==187,'No-connect markers changed'
    assert a[4]==b[4],'Placed component units changed'
    erc=json.loads((OUT/'review/erc.json').read_text())
    violations=[v for s in erc['sheets'] for v in s.get('violations',[])]
    assert not violations,violations
    for f in (SRC/'GX.pretty').glob('*.kicad_mod'):
        assert f.read_bytes()==(OUT/'GX.pretty'/f.name).read_bytes(),f.name
    snapshot=json.loads((OUT/'review/source-snapshot.json').read_text())
    assert all(hashlib.sha256((SRC/f).read_bytes()).hexdigest()==h for f,h in snapshot.items()),'Source changed during generation'
    result={'status':'PASS','component_count':len(set(r for r,u in a[4])),
            'symbol_unit_count':len(a[4]),'physical_pin_count':len(source),
            'connected_endpoints':sum(not nc(n) for n in source.values()),
            'no_connect_endpoints':sum(nc(n) for n in source.values()),
            'named_nets':len(set(n for n in source.values() if not nc(n))),
            'net_name_and_endpoint_mismatches':0,'connectivity_partition_mismatches':0,
            'component_properties_and_status':'unchanged','pin_identity_types_shapes_units':'unchanged',
            'footprints':'byte-identical','source_schematics':'unchanged',
            'erc_errors':0,'erc_warnings':0,'named_functional_buses':b[3]}
    (OUT/'review/validation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
