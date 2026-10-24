"""Offline strict-width RAW phase decoder; never invent event IDs from order."""
import importlib.util
from pathlib import Path
import math
from phase_protocol import EVENTS, PRECEDENCE, PHASE_PROTOCOL, APPROVED_PROTOCOLS

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'firmware/capture-sd/phase_markers/decode.py'
spec=importlib.util.spec_from_file_location('qualified_phase_parser',SOURCE)
parser=importlib.util.module_from_spec(spec)
spec.loader.exec_module(parser)


def summarize_folder(folder, *, standby=True, protocol=None):
    protocol=PHASE_PROTOCOL if protocol is None else protocol
    if protocol not in APPROVED_PROTOCOLS: raise ValueError('Unknown RAW phase protocol')
    step=protocol['nominal_high_us_per_id']*1e-6
    tolerance=protocol.get('pulse_width_tolerance_us',.15)*1e-6
    folder=Path(folder)
    binary=folder/'binary' if (folder/'binary').is_dir() else folder
    channels={n:parser.read_digital(binary/f'digital_{n}.bin') for n in (0,1,4,6)
              if (binary/f'digital_{n}.bin').exists()}
    if 1 not in channels: raise ValueError('Missing marker digital_1.bin')
    for n,channel in channels.items():
        if any(abs(channel[k]-channels[1][k])>1e-8+1e-15 for k in ('begin_s','end_s')):
            raise ValueError(f'Channel {n} capture bounds differ from markers')
    pulses=[]; errors=[]
    for index,pulse in enumerate(parser.pulses(channels[1])):
        item=dict(pulse,index=index,event_id=None,event=None)
        if not pulse['complete']:
            item['error']='partial_high_pulse_at_capture_boundary'
        else:
            ident=int(math.floor(pulse['width_s']/step+.5))
            delta=pulse['width_s']-ident*step
            if ident not in EVENTS or abs(delta)>tolerance+1e-15:
                item['error']='unknown_pulse_width'
            else:
                item.update(event_id=ident,event=EVENTS[ident],width_error_s=delta)
        if 'error' in item: errors.append(dict(pulse_index=index,error=item['error']))
        pulses.append(item)
    ids=[p['event_id'] for p in pulses]
    expected=set(EVENTS) if standby else set(range(1,10))
    constraints=[(a,b) for a,b in PRECEDENCE if a in expected and b in expected]
    complete=len(ids)==len(expected) and set(ids)==expected
    positions={ident:ids.index(ident) for ident in EVENTS if ident in ids}
    ordered=complete and all(positions[a]<positions[b] for a,b in constraints)
    if not complete: errors.append(dict(error='expected_each_raw_event_once'))
    elif not ordered: errors.append(dict(error='raw_phase_precedence_violation'))
    return dict(schema=2,protocol=protocol,decode_passed=complete and ordered and not errors,
        pulses=pulses,event_ids=ids,errors=errors,expected_event_ids=sorted(expected),
        expected_precedence=constraints,
        input_files={str(n):{k:v for k,v in c.items() if k!='transitions'} for n,c in channels.items()},
        reset_rises_s=parser.rising_edges(channels[0]) if 0 in channels else [],
        power_rises_s=parser.rising_edges(channels[4]) if 4 in channels else [],
        actual_standby_verified=False,image_integrity_verified=False,
        limitations=[
            'Strict widths identify events; failed widths are never relabeled by source order.',
            'Sensor and storage events overlap and need not appear in numeric order.',
            'GPIO edges include software and interrupt latency; event10 is pre-WFI intent only.',
            'Rail edges are input threshold crossings, not precision power-good measurements.',
            'Host timestamps do not synchronize independent instruments.'])
