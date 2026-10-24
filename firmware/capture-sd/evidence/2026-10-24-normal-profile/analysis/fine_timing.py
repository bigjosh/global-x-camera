"""Offline schema-2 SAVE timing partition; no hardware access or clock alignment."""
import argparse
import hashlib
import json
from pathlib import Path
import struct


def require(ok, why):
    if not ok:
        raise ValueError(why)


def validate_raw_report(report, raw):
    require(len(raw)==512,'Report length')
    words=struct.unpack('<128I',raw)
    require(list(words)==report['raw_words'],'Raw report/decoded words disagree')
    single={'magic':0,'schema':1,'words':2,'state':3,'operation':4,'mode':5,
        'result':6,'cpu_hz':10,'rows':32,'stack_used':30,'fnv_before':38,
        'fnv_after':39,'width':40,'height':41,'frame_bytes':42,'media_idle':43,
        'card_error':44,'fs_result':45,'png_result':47,'terminal':63,
        'final_ccr':70,'postclean_fnv':77,'postclean_validated':78,
        'profile':79,'checks_performed':80,'png_clock_calls':109,'png_clock_error':110}
    paired={'total':16,'encode':18,'callback':20,'finish':22,'init':24,
        'mount':26,'validate':28,'png_bytes':36,'cleanup':71,'postclean_validate':73,
        'complete':75,'open':81,'posthash':83,'deinit':85,'stack_scan':87,
        'png_total':89,'png_conversion':91,'png_deflate':93,'png_framing':95,
        'png_callback':97,'png_other':99,'png_deflate_inclusive':101,
        'png_deflate_output':103,'png_framing_inclusive':105,
        'png_framing_callback':107,'final_check':113,'flush':115}
    for key,offset in single.items():
        require(report.get(key)==words[offset], 'Decoded raw field differs: '+key)
    for key,offset in paired.items():
        require(report.get(key)==words[offset]+(words[offset+1]<<32),
                'Decoded raw cycle count differs: '+key)


def analyze_report(report, card=None):
    r = report
    for key, expected in {'magic':0x53564431,'schema':2,'words':128,'state':2,
            'operation':1,'result':0,'terminal':0x444F4E45,'cpu_hz':400000000,
            'media_idle':1,'card_error':0,'fs_result':0,'png_result':0,
            'png_clock_error':0,'width':1120,'height':1364,'frame_bytes':3055360}.items():
        require(r.get(key)==expected, 'Unqualified SAVE field: '+key)
    require(r.get('profile') in (0,1), 'Unknown profile')
    require(r.get('checks_performed')==(0x1E1 if r['profile']==0 else 0x1FF), 'Incomplete/unknown checks')
    require(r.get('png_clock_calls',0)>0 and r.get('rows')==1364, 'Incomplete PNG timing/rows')
    require(r.get('final_ccr',0)&0x30000==0, 'Caches still enabled')
    timing = ['total','complete','init','mount','validate','open','encode','finish',
        'flush','posthash','deinit','stack_scan','cleanup','final_check','postclean_validate',
        'png_total','png_conversion','png_deflate','png_framing','png_callback','png_other',
        'png_deflate_inclusive','png_deflate_output','png_framing_inclusive',
        'png_framing_callback','callback']
    for key in timing:
        require(type(r.get(key)) is int and 0<=r[key]<2**64, 'Invalid cycle count: '+key)
    if r['profile']==0:
        for key in ['fnv_before','fnv_after','postclean_fnv','postclean_validated',
                    'posthash','postclean_validate','stack_scan','stack_used']:
            require(r.get(key)==0, 'Normal profile invents diagnostic result: '+key)
    else:
        require(r.get('fnv_before')==r.get('fnv_after')==r.get('postclean_fnv') and
                r.get('postclean_validated')==1, 'Diagnostic hash checks disagree')
    require(sum(r[k] for k in ['png_conversion','png_deflate','png_framing','png_callback','png_other'])==r['png_total'], 'PNG disjoint sum mismatch')
    require(r['png_deflate_inclusive']-r['png_deflate_output']==r['png_deflate'], 'DEFLATE nesting mismatch')
    require(r['png_framing_inclusive']-r['png_framing_callback']==r['png_framing'], 'Framing nesting mismatch')
    require(r['png_callback']>=r['callback']>=0 and r['png_callback']>=r['png_framing_callback'], 'Callback nesting mismatch')
    groups = {
        'card_initialization':r['init'], 'filesystem_mount':r['mount'],
        'frame_validation_and_optional_prehash':r['validate'],
        'free_space_check_name_search_and_file_open':r['open'],
        'png_conversion_sample_validation_and_filter':r['png_conversion'],
        'deflate_including_adler_excluding_output_subtree':r['png_deflate'],
        'png_framing_crc_and_headers_excluding_callbacks':r['png_framing'],
        'synchronous_output_callbacks_including_buffering_and_sd':r['png_callback'],
        'png_other_and_timer_accounting':r['png_other'],
        'encoder_call_wrapper':r['encode']-r['png_total'],
        'final_partial_buffer_flush':r['flush'],
        # P_FINISH uses the start sampled BEFORE flush_buffer(), deliberately
        # preserving the old measurement. Do not add P_FLUSH to P_FINISH.
        'file_commit_and_close_after_flush':r['finish']-r['flush'],
        'optional_post_encode_frame_hash':r['posthash'],
        'sd_deinitialization':r['deinit'],
        'pre_cleanup_bookkeeping':r['total']-sum(r[k] for k in
            ['init','mount','validate','open','encode','finish','posthash','deinit']),
        'optional_stack_scan':r['stack_scan'], 'cache_cleanup':r['cleanup'],
        'final_essential_frame_check':r['final_check'],
        'optional_uncached_frame_hash':r['postclean_validate'],
        'final_report_snapshot_led_and_icache_bookkeeping':r['complete']-r['total']-
            sum(r[k] for k in ['stack_scan','cleanup','final_check','postclean_validate']),
    }
    require(all(v>=0 for v in groups.values()), 'Negative timing residual/nesting')
    require(sum(groups.values())==r['complete'], 'SAVE disjoint sum mismatch')
    output = {'schema':1,'profile':'normal' if r['profile']==0 else 'diagnostic',
        'name':r.get('name'),'png_bytes':r.get('png_bytes'),'mode':r.get('mode'),
        'cpu_hz_assumed':r['cpu_hz'],'complete_cycles':r['complete'],
        'complete_ms':r['complete']/400000,
        'disjoint_cycles':groups,'disjoint_ms':{k:v/400000 for k,v in groups.items()},
        'png_partition_sum_exact':True,'save_partition_sum_exact':True,
        'nested_evidence_only':{k:r[k] for k in ['encode','finish','callback',
            'png_total','png_deflate_inclusive','png_deflate_output',
            'png_framing_inclusive','png_framing_callback']},
        'png_clock_calls':r['png_clock_calls'],
        'limits':[
            'Cycle durations assume the reported 400 MHz clock; timing-hook overhead is included.',
            'DEFLATE includes compressor initialization and Adler work; it is not a pure match-loop timer.',
            'Conversion includes input range validation and any selected row filter; framing includes PNG CRC and headers.',
            'Output callbacks synchronously copy into a 32 KiB buffer and flush SD; encoding pauses during them. No concurrent DMA/double buffering is measured.',
            'P_FINISH includes the final flush; the disjoint table subtracts it before reporting commit/close.',
            'Driver read/write/ready counters and inclusive PNG counters overlap these groups and must not be added.',
            'COMPLETE ends before terminal publication/return; it excludes receiver work and power/rail startup.',
            'No Saleae-to-Joulescope or host-to-device clock synchronization is inferred.',
            'Normal-profile zero hashes mean skipped diagnostics; only separate full readback establishes image identity.']}
    if card:
        require(card.get('media_idle')==1 and card.get('error')==0 and card.get('cleanup_error')==0, 'Card not idle/successful')
        output['nested_driver_evidence_only']={k:card[k] for k in ['read_sectors','written_sectors','read_cycles','write_cycles','ready_cycles','init_cycles']}
    return output


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--maintenance',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--trial-status',choices=['provisional','qualified'],required=True)
    p.add_argument('--receiver-result',type=Path)
    a=p.parse_args()
    source=a.maintenance/'result.json'; raw_path=a.maintenance/'storage-report.bin'
    evidence=json.loads(source.read_text()); proof=evidence['storage_proof']
    require(proof.get('recognized') and proof.get('automatic_save'), 'Missing automatic SAVE ownership proof')
    raw=raw_path.read_bytes()
    validate_raw_report(proof['report'],raw)
    result=analyze_report(proof['report'],proof['card'])
    result.update(trial_status=a.trial_status,module_sha256=proof['module_sha256'],
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        raw_report_sha256=hashlib.sha256(raw).hexdigest(),
        image_readback_verified=False)
    if a.receiver_result:
        receiver=json.loads(a.receiver_result.read_text())
        valid=receiver.get('receiver_proof_valid_after_maintenance') is True
        result['receiver_proof_valid_after_maintenance']=valid
        result['receiver_source_sha256']=hashlib.sha256(a.receiver_result.read_bytes()).hexdigest()
        if not valid:
            require(a.trial_status=='provisional','Invalid receiver proof cannot label final qualified trial')
            result['receiver_timing_omitted_reason']='Post-maintenance RCP2 header invalid; do not silently accept surviving timing words.'
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'out':str(a.out),'status':a.trial_status,'name':result['name'],
                      'complete_ms':result['complete_ms'],'exact_partition':True},indent=2))


if __name__=='__main__':
    main()
