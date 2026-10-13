"""Reconcile unchanged Flux sources into physical pin connectivity.

Uses EDIF logical-name groups, native terminal UUID/number mappings and explicit
no-connects, and IPC coordinates for the ambiguous J3 connector. Does not infer
the three unrecovered optional-switch connections; candidate intent is separate.
"""
import base64
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from inventory_parts import names, parse_edif, walk

ROOT = Path(__file__).resolve().parents[1]
SNAP = ROOT / 'imports/flux/2026-09-05'
OUT = ROOT / 'hardware/reconstruction'


def properties(values):
    return {p['name']: p.get('value') for p in values.values() if p.get('name')}


def edif(path):
    tree = parse_edif(path.read_text(encoding='utf-8-sig'))
    cells = {names(c[1])[0]: {names(p[1])[0]: names(p[1])[1] for p in walk(c, 'port')}
             for c in walk(tree, 'cell')}
    instances = {names(i[1])[0]: (names(i[1])[1], next(walk(i, 'cellRef'))[1])
                 for i in walk(tree, 'instance')}
    result = defaultdict(list)
    for n in walk(tree, 'net'):
        for p in walk(n, 'portRef'):
            ref, cell = instances[next(walk(p, 'instanceRef'))[1]]
            result[ref].append({'alias': p[1], 'display_name': cells[cell][p[1]], 'net': names(n[1])[1]})
    return dict(result)


def fields(node, name):
    return next((n[1:] for n in node if isinstance(n, list) and n and n[0] == name), None)


def main():
    source_paths = [SNAP / 'bigjosh-global-x-camera.flx', SNAP / 'bigjosh-global-x-camera.edif',
                    SNAP / 'global-x-camera.ipc2581c', ROOT / 'netlist.edif']
    native = json.loads(source_paths[0].read_text(encoding='utf-8'))
    fresh, original = edif(source_paths[1]), edif(source_paths[3])
    components, groups, conflicts = {}, {}, []
    terminal_lookup = {}

    for uid, element in native['elements'].items():
        ref = element['label']; prop = properties(element.get('properties', {}))
        pins, name_groups = {}, defaultdict(list)
        for tid, t in element['part_version_data_cache']['terminals'].items():
            number = str(t['pin_number'])
            if number in pins:
                raise ValueError(f'Duplicate physical pin: {ref}.{number}')
            is_nc = uid + '__' + tid in native['noConnects']
            pin = {'name': t['name'], 'terminal_uid': tid, 'net': None,
                   'status': 'no_connect' if is_nc else 'unresolved',
                   'evidence': [{'source': source_paths[0].name,
                     'path': f'/elements/{uid}/part_version_data_cache/terminals/{tid}/pin_number'}]}
            if is_nc:
                pin['evidence'].append({'source': source_paths[0].name, 'path': '/noConnects/' + uid + '__' + tid})
            pins[number] = pin; name_groups[t['name']].append(number)
            terminal_lookup[(uid, tid)] = (ref, number)
        components[ref] = {'element_uid': uid, 'part_number': prop.get('Manufacturer Part Number'),
                           'exclude_from_bom': str(prop.get('Exclude from BOM', '')).lower() == 'true',
                           'external_to_host_pcb': uid not in native['pcbLayoutNodes'], 'pins': pins}
        groups[ref] = dict(name_groups)

    def assign(ref, number, net, evidence):
        p = components[ref]['pins'][number]
        if p['status'] == 'no_connect' or (p['net'] is not None and p['net'] != net):
            conflicts.append({'reference': ref, 'pin': number, 'existing': p['net'],
                              'existing_status': p['status'], 'incoming_net': net, 'evidence': evidence})
            return
        p['net'], p['status'] = net, 'connected'
        if evidence not in p['evidence']: p['evidence'].append(evidence)

    # A nonempty canonical name is an explicit native UUID-specific anchor.
    # Generic "Net N" fragments are never accepted as resolved signal names.
    nc_fragments = []
    for nid, n in native['nets'].items():
        for t in n.get('pins', {}).values():
            ref, number = terminal_lookup[(t['elementUid'], t['terminalUid'])]
            if components[ref]['pins'][number]['status'] == 'no_connect':
                nc_fragments.append({'reference': ref, 'pin': number, 'native_fragment': nid})
            if n.get('canonicalName'):
                assign(ref, number, n['label'], {'source': source_paths[0].name,
                    'method': 'explicit canonical net anchor', 'path': f'/nets/{nid}'})

    group_edif = {}
    for ref, by_name in groups.items():
        for name, numbers in by_name.items():
            # Suffixes only identify members of a duplicate-name group. They are
            # not physical pin numbers and their order is never used as one.
            entries = [p for p in fresh.get(ref, []) if p['display_name'] == name or
                       (len(numbers) > 1 and re.fullmatch(re.escape(name) + r'_\d+', p['display_name']))]
            group_edif[(ref, name)] = entries
            active = [n for n in numbers if components[ref]['pins'][n]['status'] != 'no_connect']
            if ref in fresh and len(entries) != len(active):
                conflicts.append({'reference': ref, 'logical_name': name,
                    'issue': 'EDIF endpoint count differs from native non-NC group',
                    'edif_count': len(entries), 'native_count': len(active)})
            if not entries: continue
            remaining = Counter(e['net'] for e in entries)
            unknown = []
            for number in active:
                p = components[ref]['pins'][number]
                if p['status'] == 'connected': remaining[p['net']] -= 1
                else: unknown.append(number)
            if any(c < 0 for c in remaining.values()):
                conflicts.append({'reference': ref, 'logical_name': name,
                    'issue': 'Native canonical anchors exceed EDIF group membership', 'remaining': dict(remaining)})
            candidates = [n for n, count in remaining.items() if count > 0]
            if len(candidates) == 1 and sum(remaining.values()) == len(unknown):
                for number in unknown:
                    assign(ref, number, candidates[0], {'source': source_paths[1].name,
                        'method': 'logical name group / canonical-anchor elimination',
                        'logical_name': name, 'group_aliases': [e['alias'] for e in entries]})

    # Resolve J3's repeated '~' labels with copper coordinates. Both transforms
    # are explicit: this component has no rotation/mirror; IPC Y reverses the
    # embedded KiCad source Y. Match within 0.00002 mm, far below 0.35 mm pitch.
    xml = ET.parse(source_paths[2]).getroot(); ns = {'i': xml.tag.split('}')[0][1:]}
    ipc_components = {e.get('refDes'): e for e in xml.findall('.//i:Component', ns)}
    j3c = ipc_components['J3']; xform = j3c.find('i:Xform', ns)
    if xform is not None and (float(xform.get('rotation', '0')) != 0 or xform.get('mirror', 'false') != 'false'):
        raise ValueError('J3 IPC transform changed; reviewed geometry matcher requires no rotation/mirror')
    location = j3c.find('i:Location', ns); cx, cy = float(location.get('x')), float(location.get('y'))
    j3uid = components['J3']['element_uid']; j3 = native['elements'][j3uid]
    raw_footprint = next(n['pcbNodeRuleSet']['asset']['payloadAsBase64']
        for n in j3['part_version_data_cache']['pcbLayoutNodes'].values() if n['type'] == 'footprint')
    footprint = parse_edif(base64.b64decode(raw_footprint).decode('utf-8-sig'))
    pads = {}
    for node in footprint:
        if isinstance(node, list) and node and node[0] == 'pad':
            xy = fields(node, 'at'); pads[str(node[1])] = (float(xy[0]), float(xy[1]))
    j3_matches, ipc_groups = [], defaultdict(set)
    for layer in xml.findall('.//i:LayerFeature', ns):
        for s in layer.findall('i:Set', ns):
            if not s.get('net'): continue
            for pad in s.findall('.//i:Pad', ns):
                pref = pad.find('i:PinRef', ns)
                if pref is None: continue
                loc = pad.find('i:Location', ns)
                if loc is None: continue
                ref = pref.get('componentRef'); logical = pref.get('pin')
                xy = (float(loc.get('x')), float(loc.get('y')))
                ipc_groups[(ref, logical)].add((xy, s.get('net')))
                if ref != 'J3': continue
                local = (xy[0] - cx, cy - xy[1])
                candidates = [num for num, p in pads.items()
                              if max(abs(p[0] - local[0]), abs(p[1] - local[1])) < 0.00002]
                if len(candidates) != 1 or candidates[0] not in components['J3']['pins']:
                    conflicts.append({'reference': 'J3', 'issue': 'IPC pad did not match one logical physical pad',
                                      'ipc_xy_mm': xy, 'candidate_pins': candidates})
                    continue
                number = candidates[0]
                ev = {'source': source_paths[2].name, 'method': 'IPC net pad to native numbered footprint by location',
                      'ipc_component_origin_mm': [cx, cy], 'ipc_pad_xy_mm': list(xy),
                      'native_pad_xy_mm': list(pads[number]), 'layer': layer.get('layerRef')}
                assign('J3', number, s.get('net'), ev)
                j3_matches.append({'pin': number, 'net': s.get('net'), 'ipc_xy_mm': list(xy)})

    # Verify every resolved EDIF group has exactly its compiled net membership.
    group_checks = []
    for (ref, name), entries in group_edif.items():
        if ref not in fresh: continue
        expected = Counter(e['net'] for e in entries)
        actual = Counter(components[ref]['pins'][p]['net'] for p in groups[ref][name]
                         if components[ref]['pins'][p]['status'] == 'connected')
        if expected != actual:
            conflicts.append({'reference': ref, 'logical_name': name, 'issue': 'Resolved membership differs from EDIF',
                              'expected': dict(expected), 'actual': dict(actual)})
        group_checks.append({'reference': ref, 'logical_name': name, 'matches': expected == actual})

    # Cross-check the complete host-board endpoint inventory against unique IPC
    # net-assigned copper pad locations. U8 uses board aliases pad1..pad8; these
    # are resolved through native node terminalId, not parsed as assumed numbers.
    board_aliases = defaultdict(set)
    for ref, component in components.items():
        uid = component['element_uid']
        for nid, node in native['pcbLayoutNodes'].items():
            if nid.startswith(uid + '__') and node.get('type') == 'pad':
                number = str(node.get('terminalId'))
                if number in component['pins']:
                    board_aliases[(ref, node.get('name'))].add(number)
    ipc_location_counts = Counter()
    ipc_unique_locations = set()
    ipc_alias_mappings = []
    for (ref, logical), records in ipc_groups.items():
        if ref not in components: continue
        for xy, net in records:
            key = (ref, xy, net)
            if key in ipc_unique_locations: continue
            ipc_unique_locations.add(key); ipc_location_counts[(ref, net)] += 1
            candidates = {n for n, p in components[ref]['pins'].items() if p['name'] == logical}
            candidates |= board_aliases[(ref, logical)]
            matched = [n for n in candidates if components[ref]['pins'][n]['net'] == net]
            if not matched:
                conflicts.append({'reference': ref, 'ipc_pin_alias': logical, 'ipc_net': net,
                    'ipc_xy_mm': list(xy), 'issue': 'IPC assigned pad has no matching reconciled terminal'})
            if ref == 'U8':
                ipc_alias_mappings.append({'reference': ref, 'ipc_alias': logical, 'pins': matched, 'net': net})
    compiled_host_counts = Counter((ref, entry['net']) for ref, entries in fresh.items()
        if not components[ref]['external_to_host_pcb'] for entry in entries)
    if ipc_location_counts != compiled_host_counts:
        conflicts.append({'issue': 'IPC unique host pad/net counts differ from compiled EDIF',
            'only_or_excess_ipc': [[*k, v] for k, v in (ipc_location_counts - compiled_host_counts).items()],
            'missing_ipc': [[*k, v] for k, v in (compiled_host_counts - ipc_location_counts).items()]})

    # Optional switches are absent in compiled exports. Keep documented intent
    # as candidates; it is deliberately not an accepted electrical connection.
    candidates = {('SW2', '2'): '1V8', ('SW3', '1'): 'NRST', ('SW3', '2'): 'GND'}
    for (ref, number), candidate in candidates.items():
        pin = components[ref]['pins'][number]
        if pin['status'] == 'unresolved':
            prop = properties(native['elements'][components[ref]['element_uid']]['properties'])
            pin['candidate_net'] = candidate
            pin['candidate_evidence'] = {'source': source_paths[0].name, 'role_details': prop.get('Role Details'),
                'qualification': 'Stored circuit intent only; source graph does not resolve this endpoint. '
                    + ('Assignment of NRST/GND to switch pins 1/2 is arbitrary for a symmetric SPST switch.' if ref == 'SW3' else
                       'The other SW2 terminal is explicitly anchored to BOOT0.')}

    # Audit the native schematic graph rather than assuming that it reconstructs
    # all networks. Vertex links plus terminal references form isolated stubs.
    parent = {}
    def find(x):
        parent.setdefault(x, x)
        if parent[x] != x: parent[x] = find(parent[x])
        return parent[x]
    def union(a, b): parent[find(a)] = find(b)
    for vid, vertex in native['routeVertices'].items():
        for other in vertex.get('connectedVertices', {}): union('v:' + vid, 'v:' + other)
        if vertex.get('terminal'):
            t = vertex['terminal']; union('v:' + vid, 't:' + t['element_uid'] + '__' + t['terminal_uid'])
    graph_terminals = defaultdict(set)
    for uid, tid in terminal_lookup:
        key = 't:' + uid + '__' + tid
        if key in parent: graph_terminals[find(key)].add((uid, tid))

    resolved_nets, unresolved = defaultdict(list), []
    statuses = Counter()
    for ref, component in components.items():
        for number, pin in component['pins'].items():
            statuses[pin['status']] += 1
            if pin['status'] == 'connected': resolved_nets[pin['net']].append({'reference': ref, 'pin': number})
            if pin['status'] == 'unresolved': unresolved.append({'reference': ref, 'pin': number,
                'candidate_net': pin.get('candidate_net'), 'reason': 'No compiled endpoint; native fragment lacks canonical identity'})
    nonj3_edif_equal = {r: sorted((e['display_name'], e['net']) for e in ps) for r, ps in fresh.items() if r != 'J3'} == {
        r: sorted((e['display_name'], e['net']) for e in ps) for r, ps in original.items() if r != 'J3'}
    summary = {'components': len(components), 'physical_pins': sum(statuses.values()), 'pin_status_counts': dict(statuses),
        'resolved_nets': len(resolved_nets), 'compiled_edif_connected_pins': sum(len(x) for x in fresh.values()),
        'old_vs_fresh_non_J3_memberships_equal': nonj3_edif_equal,
        'native_explicit_no_connects': len(native['noConnects']), 'native_no_connect_fragments': nc_fragments,
        'all_compiled_logical_groups_reconciled': all(c['matches'] for c in group_checks),
        'j3_connected_physical_pins': len({m['pin'] for m in j3_matches}),
        'ipc_verified_connected_host_pin_locations': len(ipc_unique_locations),
        'compiled_host_connected_pins': sum(compiled_host_counts.values()),
        'ipc_coverage_matches_compiled_host': ipc_location_counts == compiled_host_counts,
        'native_graph_terminal_components': len(graph_terminals),
        'native_graph_components_with_multiple_terminals': sum(len(t) > 1 for t in graph_terminals.values()),
        'conflicts': len(conflicts)}
    output = {'schema_version': 1, 'sources': [{'path': p.relative_to(ROOT).as_posix(),
                  'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in source_paths],
        'summary': summary, 'components': components,
        'nets': [{'name': n, 'pins': sorted(p, key=lambda p: (p['reference'], p['pin']))} for n, p in sorted(resolved_nets.items())],
        'unresolved': unresolved, 'conflicts': conflicts, 'j3_geometry_matches': j3_matches,
        'ipc_board_alias_mappings': ipc_alias_mappings}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'connectivity.json').write_text(json.dumps(output, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps(summary, indent=2))
    print('Unresolved:', json.dumps(unresolved))
    if conflicts:
        print(json.dumps(conflicts, indent=2))
        raise SystemExit('Reconciliation conflicts remain; do not consume output as authoritative')


if __name__ == '__main__':
    main()
