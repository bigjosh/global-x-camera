"""Offline source-order interpretation of exact normal-profile cold captures.

The original pulse-width decoder result is retained, never repaired. All source,
binary, readback and qualification inputs are explicitly hash-bound by a spec.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import zlib
from fine_timing import analyze_report, validate_raw_report, require
sys.path.insert(0,str(Path(__file__).resolve().parent/'support'))
import phase_decode

LABELS=['Receiver main entry','First STROBE interrupt observation',
    'First complete-frame interrupt observation','SAVE timing begin',
    'SD initialization complete','FAT32 mount complete','PNG encoder returned',
    'Final flush and file commit/close complete',
    'Cache cleanup, essential frame check and snapshots complete',
    'Pre-WFI or awake completion checkpoint']


def infer(channels, kind):
    require(kind in ('awake','standby'),'Unknown completion kind')
    mark=channels[1];edges=mark['transitions']
    require(mark['initial_state']==0 and len(edges)==20,'Need ten complete pulses from LOW')
    require(all(a<b for a,b in zip(edges,edges[1:])),'Edges must increase')
    require(mark['begin_s']<edges[0] and edges[-1]<mark['end_s'],'Partial boundary pulse')
    for channel in channels.values():
        require(all(abs(channel[k]-mark[k])<=1e-8+1e-15 for k in ('begin_s','end_s')), 'Mixed capture bounds')
    for number in (0,4):
        c=channels[number]
        require(c['initial_state']==0 and len(c['transitions'])==1 and
                c['transitions'][0]<edges[0],'Need observed reset/power rise before first marker')
    reset,power=channels[0]['transitions'][0],channels[4]['transitions'][0]
    events=[]
    for i,label in enumerate(LABELS):
        if i==9: label='Pre-Standby WFI checkpoint' if kind=='standby' else 'Awake completion checkpoint'
        rise,fall=edges[i*2:i*2+2]
        events.append(dict(inferred_id=i+1,label=label,rising_edge_s=rise,
            falling_edge_s=fall,width_us=(fall-rise)*1e6,
            since_reset_release_ms=(rise-reset)*1e3,
            since_power_threshold_ms=(rise-power)*1e3,
            since_previous_marker_ms=None if i==0 else (rise-edges[i*2-2])*1e3))
    return dict(events=events,ordered_structure_valid=True,width_qualified=False,
        event_assignment='Inferred from exact source call order, not pulse-width identification',
        reset_release_s=reset,power_threshold_s=power,
        frame_irq_to_save_begin_ms=(edges[6]-edges[4])*1e3,
        frame_irq_to_final_marker_ms=(edges[18]-edges[4])*1e3)


def verify_calls(receiver, save, completion, kind):
    require(sorted(map(int,re.findall(r'phase_gpio_emit\((\d+)U\)',receiver)))==[1,2,3],'Receiver calls differ')
    require(sorted(map(int,re.findall(r'phase_gpio_emit\((\d+)U\)',save)))==[4,5,6,7,8,9],'SAVE calls differ')
    require(re.findall(r'phase_gpio_emit\((\d+)U\)',completion)==['10'],'Completion calls differ')
    require('if(fast_strobes==1U)' in receiver and 'if(frames==1U)' in receiver,'First-event gates absent')
    require(receiver.index('phase_gpio_emit(1U)',receiver.index('int main'))<receiver.index('prepare_receiver();',receiver.index('int main')),'Entry marker moved')
    require(save.index('report[P_BEGIN]=last_cycle;')<save.index('phase_gpio_emit(4U)')<save.index('result=sd_init('),'SAVE entry moved')
    require(save.index('pair(P_INIT_LO')<save.index('phase_gpio_emit(5U)')<save.index('photo_fs_mount('),'Init marker moved')
    require(save.index('pair(P_MOUNT_LO')<save.index('phase_gpio_emit(6U)'),'Mount marker moved')
    image=save[save.index('static int save_image('):save.index('int save_main(')]
    require(image.index('if(png_result) return png_result;')<image.index('phase_gpio_emit(7U)')<image.index('result=flush_buffer()'),'PNG marker moved')
    require(image.index('result=photo_fs_finish()')<image.index('phase_gpio_emit(8U)'),'Commit marker moved')
    require(save.index('SCB_DisableDCache()')<save.index('pair(P_FINAL_CHECK_LO')<save.index('phase_gpio_emit(9U)')<save.index('pair(P_COMPLETE_LO')<save.index('report[P_TERMINAL]'),'Final-check/terminal order moved')
    require('if(op==SAVE_OP_SAVE && !result) (void)phase_gpio_emit(9U);' in save,'Success-only marker9 missing')
    if kind=='standby':
        require(completion.index('publish(LPC_STATE_ARMED);')<completion.index('phase_gpio_emit(10U)')<completion.index('"wfi\\n"'),'Pre-WFI marker moved')
        require('if (LP[LPC_PERIPHERAL_RESULT]) refused' in completion,'Shutdown gate missing')
    else:
        require(completion.index('phase_gpio_emit(10U)')<completion.index('"nop\\n"'),'Awake marker moved')


def analyze(spec_path):
    spec_path=Path(spec_path).resolve();spec=json.loads(spec_path.read_text())
    require(spec.get('schema')==1 and spec.get('profile')=='normal','Unknown phase spec/profile')
    artifacts={}
    for key,item in spec['artifacts'].items():
        p=Path(item['path']);p=p if p.is_absolute() else spec_path.parent/p
        data=p.read_bytes()
        require(hashlib.sha256(data).hexdigest()==item['sha256'],'Input identity differs: '+key)
        artifacts[key]=(p,data)
    def raw(k):return artifacts[k][1]
    def js(k):return json.loads(raw(k))
    def text(k):return raw(k).decode('utf-8-sig')
    identity=spec['firmware'];sector=raw('sector_image');module=raw('module_image')
    require(len(sector)==65536 and hashlib.sha256(sector).hexdigest()==identity['sector_sha256'],'Sector identity')
    require(raw('nor_readback')==sector,'Actual NOR readback differs')
    require(hashlib.sha256(module).hexdigest()==identity['module_sha256'],'Module identity')
    require(hashlib.sha256(raw('prefix_image')).hexdigest()==identity['prefix_sha256'],'Prefix identity')
    require(sector[0x6000:0x6000+len(module)]==module,'Module not in sector')
    mm,rm=js('module_manifest'),js('receiver_manifest')
    require(mm['binary_sha256']==identity['module_sha256'] and mm['report_schema']==2 and mm['diagnostics_profile']=='normal','Different SAVE manifest')
    receiver=raw('receiver_image')
    require(hashlib.sha256(receiver).hexdigest()==rm['raw_sha256'] and sector[0x2000:0x2000+len(receiver)]==receiver,'Receiver identity')
    for role,manifest in [('receiver_source',rm),('save_source',mm)]:
        require(hashlib.sha256(raw(role)).hexdigest() in manifest['sources'].values(),'Source not bound by build: '+role)
    kind=spec['completion_kind']
    if kind=='standby':
        late=raw('late_image');lm=js('late_manifest')
        require(hashlib.sha256(late).hexdigest()==lm['binary_sha256'] and sector[0xE000:0xE000+len(late)]==late,'Late image identity')
        require(hashlib.sha256(raw('completion_source')).hexdigest() in lm['sources'].values(),'Late source identity')
    else:
        require(hashlib.sha256(raw('completion_source')).hexdigest() in rm['sources'].values(),'Awake source identity')
    verify_calls(text('receiver_source'),text('save_source'),text('completion_source'),kind)
    proof=js('execution_proof')
    if kind=='awake':
        storage=proof['storage_proof']
        require(storage['recognized'] and storage['automatic_save'] and storage['module_sha256']==identity['module_sha256'],'Automatic SAVE proof mismatch')
        validate_raw_report(storage['report'],raw('raw_report'))
        fine=analyze_report(storage['report'],storage['card'])
        require(fine['profile']=='normal','Wrong profile')
        fs=storage['fs'];require(fs['completed']==1 and fs['bytes_written']==fine['png_bytes'] and fs['final_name']==fine['name'],'Filesystem proof mismatch')
        l=storage['loader_words']
        require(l[0]==0x534C4431 and l[7]==zlib.crc32(module) and l[8]==len(module) and l[9] and l[10]==0 and l[11],'Loader not successful')
    else:
        require(proof['passed'] and proof['sbf'] and proof['cpucr']&0x200 and proof['prefix_sha256']==identity['prefix_sha256'],'SBF proof mismatch')
        park=proof['fresh_park_result']
        require(park['passed'] and park['prefix_sha256']==identity['prefix_sha256'] and park['context']['PC']==0x3418078C,'Exact recovery park absent')
        require(spec.get('owner_attests_no_intervening_poweroff') is True,'Need explicit SBF history attestation')
    channels={n:phase_decode.read_digital(artifacts['digital_'+str(n)][0]) for n in (0,1,4,6)}
    result=infer(channels,kind);strict=js('strict_width_summary')
    require(len(strict['pulses'])==10 and all(p['complete'] for p in strict['pulses']),'Strict pulse structure differs')
    require([p['start_s'] for p in strict['pulses']]==[v['rising_edge_s'] for v in result['events']],'Strict/ordered edges differ')
    result.update(schema=1,completion_kind=kind,firmware=identity,
        original_width_decode_passed=strict['decode_passed'],
        standby_flag_observed=kind=='standby',image_integrity_verified=False,
        input_sha256={k:v['sha256'] for k,v in spec['artifacts'].items()},
        limits=['Event labels are source-order inference; the strict width result is preserved separately.',
            'Interrupt observations include interrupt latency; GPIO marker code affects execution/layout.',
            'CH4 is a digital threshold crossing, not an analog power-good qualification.',
            'Marker9 precedes COMPLETE/terminal publication; marker10 precedes WFI or marks awake completion.',
            'SBF is historical since its last clear/POR; attributing it also uses the owner reset/power-history attestation.',
            'No image bytes are checked here. No Joulescope/host clock alignment is inferred.'])
    if kind=='awake':
        result['save_fine_timing']=fine
        result['loader_read_crc_ms']=((l[9]-l[1])&0xFFFFFFFF)/400000
        result['loader_crc_end_to_save_begin_ms']=((storage['report']['begin']-l[9])&0xFFFFFFFF)/400000
        wall=result['events'][8]['rising_edge_s']-result['events'][3]['rising_edge_s']
        result['clock_consistency']={
            'saleae_marker4_to_marker9_s':wall,
            'dwt_complete_s_at_nominal_400MHz':fine['complete_ms']/1000,
            'wall_to_nominal_duration_ratio':wall/(fine['complete_ms']/1000),
            'approximate_dwt_rate_hz_from_nearby_boundaries':fine['complete_cycles']/wall,
            'calibrated_cpu_frequency':False,
            'limit':'The boundaries are nearby but not identical: P_BEGIN precedes marker4 and COMPLETE follows marker9. This is a consistency comparison, not exact synchronization or a clock calibration. Fine timings remain nominal-400MHz values.'}
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--spec',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();result=analyze(a.spec);a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'ordered_structure_valid':True,'width_qualified':False,
        'frame_irq_to_save_begin_ms':result['frame_irq_to_save_begin_ms']},indent=2))
