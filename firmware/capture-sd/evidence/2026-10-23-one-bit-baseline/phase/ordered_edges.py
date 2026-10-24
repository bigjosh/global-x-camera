"""Separate source-order inference for the exact v61b cold-cycle recording.

This does not widen pulse-width tolerances or modify/reclassify the strict
decoder's failed result. No hardware access; no PNG integrity claim.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

HERE=Path(__file__).resolve().parent
ARCHIVE=HERE.parent
SECTOR='cc49159990ecd7aab9b0ab9c9055b3c230cc2ef639b1c295c511bea4a8be943f'
PREFIX='73ec49d0f6b011ca615813886709d429e9dd8e5604af04b5d03447ef5ca7b51e'
LABELS=[
 'Receiver main entry', 'First STROBE rising interrupt observed',
 'First complete-frame interrupt observed', 'SAVE module entry',
 'SD initialization complete', 'FAT32 mount complete', 'PNG encode complete',
 'File close/rename/card-ready complete',
 'Cache cleanup, uncached frame validation and snapshots complete',
 'Pre-Standby WFI checkpoint']

def sha(raw):return hashlib.sha256(raw).hexdigest()
def require(value,message):
    if not value:raise ValueError(message)
def load_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod

def infer(channels):
    """Only assign ordinal labels after strict edge-count/boundary guards."""
    mark=channels[1];edges=mark['transitions']
    require(mark['initial_state']==0,'Marker capture must start LOW')
    require(len(edges)==20,'Exactly20 transitions/10 complete pulses are required')
    require(all(a<b for a,b in zip(edges,edges[1:])),'Edges must strictly increase')
    require(mark['begin_s']<edges[0] and edges[-1]<mark['end_s'],'Boundary pulses must be fully observed')
    require((mark['initial_state']^(len(edges)&1))==0,'Marker capture must end LOW')
    for n,c in channels.items():
        require(all(abs(c[k]-mark[k])<=1e-8+1e-15 for k in ('begin_s','end_s')),
                'All channel bounds must match')
    for n in (0,4):
        c=channels[n]
        require(c['initial_state']==0 and len(c['transitions'])==1,'One observed reset/power rise required')
        require(c['transitions'][0]<edges[0],'Reset/power rise must precede first marker')
    reset=channels[0]['transitions'][0];power=channels[4]['transitions'][0]
    result=[]
    for index,label in enumerate(LABELS):
        rise,fall=edges[2*index:2*index+2]
        result.append(dict(ordinal=index+1,inferred_event_id=index+1,
            inferred_checkpoint=label,assignment_basis='inferred from source call order',
            rising_edge_s=rise,falling_edge_s=fall,width_us=(fall-rise)*1e6,
            nominal_width_us=(index+1)*0.5,width_error_us=(fall-rise)*1e6-(index+1)*0.5,
            from_reset_release_ms=(rise-reset)*1e3,from_power_threshold_ms=(rise-power)*1e3,
            from_receiver_entry_ms=(rise-edges[0])*1e3,
            from_previous_marker_ms=None if index==0 else (rise-edges[2*index-2])*1e3))
    return dict(ordered_structure_valid=True,width_qualification=False,
        event_assignment='inferred from source call order; not decoded from pulse widths',
        marker_initial_state=mark['initial_state'],marker_final_state=0,
        transition_count=20,complete_pulse_count=10,
        observed_reset_release_s=reset,observed_power_threshold_s=power,
        all_marker_edges_s=list(edges),events=result,
        intervals=[dict(from_inferred_event=a['ordinal'],to_inferred_event=b['ordinal'],
                        interval_ms=(b['rising_edge_s']-a['rising_edge_s'])*1e3,
                        assignment_basis='inferred from source call order')for a,b in zip(result,result[1:])])

def verify_calls(build):
    receiver=(build/'receiver/capture.c').read_text(encoding='utf-8')
    save=(build/'module/save_main.c').read_text(encoding='utf-8')
    late=(build/'late/completion.c').read_text(encoding='utf-8')
    require(sorted(map(int,re.findall(r'phase_gpio_emit\((\d+)U\)',receiver)))==[1,2,3],'Receiver marker calls differ')
    require(sorted(map(int,re.findall(r'phase_gpio_emit\((\d+)U\)',save)))==[4,5,6,7,8,9],'SAVE marker calls differ')
    require(re.findall(r'phase_gpio_emit\((\d+)U\)',late)==['10'],'Completion marker calls differ')
    require('if(fast_strobes==1U)' in receiver and 'if(frames==1U)' in receiver,'First-event restrictions absent')
    require(receiver.index('phase_gpio_emit(1U)',receiver.index('int main')) < receiver.index('prepare_receiver();',receiver.index('int main')),'Receiver entry marker moved')
    image=save[save.index('static int save_image('):save.index('int save_main(')]
    require(image.index('if(png_result) return png_result;')<image.index('phase_gpio_emit(7U)')<image.index('result=flush_buffer()'),'Encoding marker moved')
    require(image.index('result=photo_fs_finish()')<image.index('phase_gpio_emit(8U)')<image.index('report[P_FNV_AFTER]'),'Commit marker moved')
    require(save.index('SCB_DisableDCache()')<save.index('uint32_t value=frame_fnv();')<save.index('phase_gpio_emit(9U)')<save.index('pair(P_COMPLETE_LO')<save.index('report[P_TERMINAL]'),'Validation/terminal marker order changed')
    require('if(op==SAVE_OP_SAVE && !result) (void)phase_gpio_emit(9U);'in save,'Success-only marker9 guard changed')
    require(late.index('publish(LPC_STATE_ARMED);')<late.index('phase_gpio_emit(10U)')<late.index('"wfi\\n"'),'Pre-WFI marker moved')
    require('if (LP[LPC_PERIPHERAL_RESULT]) refused' in late,'Completion success guard absent')
    return dict(reviewed_calls=True,receiver_ids=[1,2,3],save_ids=[4,5,6,7,8,9],late_ids=[10],
                note='Exact source hashes/build identity are independently pinned; these checks verify checkpoint placement without treating text order across functions as execution order.')

def analyze(folder):
    folder=folder.resolve()
    inventory=json.loads((folder/'inputs.json').read_text(encoding='utf-8'))
    for e in inventory:
        p=(folder/e['archived_path']).resolve()
        require(p.is_relative_to(folder),'Input path escapes phase record')
        raw=p.read_bytes();require(len(raw)==e['bytes'] and sha(raw)==e['sha256'],'Input changed: '+str(p))
    archive_check=load_module('phase_archive_verify',ARCHIVE/'verify_build.py')
    archive_check.verify(ARCHIVE)
    build=ARCHIVE/'build/v61b-standby'
    sector=(build/'staged/capture_sector_0.bin').read_bytes()
    require(sha(sector)==SECTOR,'Different firmware sector')
    readback=(folder/'nor-readback.bin').read_bytes()
    require(readback==sector,'Independent full NOR read does not match exact v61b')
    nor=json.loads((folder/'nor-read-result.json').read_text())
    require(nor==dict(bytes=65536,offset=0,sha256=SECTOR,read_only=True),'Unexpected NOR read metadata')
    sbf=json.loads((folder/'sbf-result.json').read_text())
    require(sbf['passed'] and sbf['sbf'] and sbf['cpucr']&0x200 and sbf['prefix_sha256']==PREFIX,'Expected Standby/recovery evidence absent')
    park=sbf['fresh_park_result']
    require(park['passed'] and park['prefix_sha256']==PREFIX and park['context']['PC']==0x3418078C,'Exact recovery park missing')
    strict=json.loads((folder/'strict-width-summary.json').read_text())
    require(strict['decode_passed'] is False,'Original strict width failure must remain intact')
    cycle=json.loads((folder/'cycle-result.json').read_text())
    require(cycle['sector_sha256']==SECTOR and cycle['phase_decode_passed'] is False and
            cycle['phase_summary_sha256']==sha((folder/'strict-width-summary.json').read_bytes()),'Cycle/strict result linkage differs')
    decoder=load_module('frozen_phase_parser',ARCHIVE/'support/phase_markers/decode.py')
    channels={n:decoder.read_digital(folder/'binary'/f'digital_{n}.bin')for n in (0,1,4,6)}
    result=infer(channels)
    require(len(strict['pulses'])==10 and all(p['complete']for p in strict['pulses']),'Strict parser did not observe ten complete pulses')
    require([p['start_s']for p in strict['pulses']]==[p['rising_edge_s']for p in result['events']],'Strict/ordered edge extraction differs')
    result.update(schema=1,firmware_sector_sha256=SECTOR,recovery_prefix_sha256=PREFIX,
        source_review=verify_calls(build),independent_full_nor_read_matches=True,
        original_width_decode_passed=False,standby_flag_observed=True,
        sbf_reader_trial_entry_proven=sbf['trial_entry_proven'],image_integrity_verified=False,
        context='The exact successful source path, ten complete pulses and later SBF observation support an ordered interpretation; pulse widths remain unqualified.',
        limitations=[
          'Each event label and interval is inferred from source call order, not independently identified by width.',
          'STROBE/frame observations include interrupt latency; markers add execution and code-loading overhead.',
          'The observed5V edge is a digital threshold crossing, not analog power-good.',
          'Event9 precedes COMPLETE/terminal publication; event10 precedes WFI and is not the electrical Standby-entry time.',
          'The SBF reader reports historical Standby since last clear/POR. Attribution also requires the recorded reset/power history; this analysis does not independently prove that history.',
          'No RAW frame or saved PNG is checked here; image_integrity_verified remains false.',
          'No time alignment with the independent Joulescope stream is inferred.'],
        input_files={str(n):dict({k:v for k,v in c.items()if k not in ('transitions','path')},
                                path=f'binary/digital_{n}.bin')for n,c in channels.items()})
    return result

def table(result):
    lines=['# Ordered-edge timing: v61b cold cycle 01','',
      '**Labels are inferred from source call order. Pulse-width qualification failed and remains false.**','',
      'The exact v61b sector was independently read back before the cycle. Ten complete PD12 pulses were observed with LOW capture boundaries. A later warm recovery observed SBF=1. These facts support this separately labelled ordering analysis; they do not repair the strict decoder or verify a saved PNG.','',
      '| Inferred event | Inferred checkpoint | Width (µs) | After NRST release (ms) | After observed 5 V crossing (ms) | Since previous marker (ms) |',
      '| --- | --- | ---: | ---: | ---: | ---: |']
    for p in result['events']:
        prev='—' if p['from_previous_marker_ms']is None else f"{p['from_previous_marker_ms']:.6f}"
        lines.append(f"| {p['ordinal']} | {p['inferred_checkpoint']} | {p['width_us']:.3f} | {p['from_reset_release_ms']:.6f} | {p['from_power_threshold_ms']:.6f} | {prev} |")
    lines+=['','All timings use observed GPIO rising edges in the same Logic capture. Event 2 is the STROBE interrupt observation, not the exact exposure edge. Event 7 still precedes flushing any buffered tail. Event 9 follows uncached validation but precedes terminal publication. Event 10 is before WFI, not a measured electrical shutdown boundary.','',
      'The pulse-width vector is preserved as measured; no tolerance was expanded and no missing pulse was invented. See `ordered-analysis.json` for every edge, input hash, nominal-width error, and limitation. Full PNG integrity remains unverified by this analysis.','']
    return '\n'.join(lines)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('folder',type=Path)
    a=p.parse_args();result=analyze(a.folder)
    (a.folder/'ordered-analysis.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    (a.folder/'timing.md').write_text(table(result),encoding='utf-8')
    print(json.dumps(dict(ordered_structure_valid=result['ordered_structure_valid'],width_qualification=False,
        inferred_reset_to_pre_wfi_ms=result['events'][-1]['from_reset_release_ms'],image_integrity_verified=False),indent=2))
