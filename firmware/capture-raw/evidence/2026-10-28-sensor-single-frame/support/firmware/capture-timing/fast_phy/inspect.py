"""Decode an already-read, exact FAST diagnostic buffer. No hardware access.

Owner must check RCC_MEMENR[3:0]==0xF before reading high SRAM. Do not use
manifest-provided addresses for arbitrary reads: FAST is fixed at0x343F8000.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

ADDRESS=0x343F8000
WORDS=544
FIELDS=('event cycles tick sr0 sr1 ier0 ier1 prcr pcr cr lmcfgr apb5rstr '
        'pa0 frames vsyncs strobe_ordinal').split()
EVENT_NAMES={399:'entry',405:'before_pen',406:'after_pen',409:'stop_qualified',
             420:'raw_csi_irq_before_hal',422:'vc_armed',425:'start_ack',
             426:'streaming',429:'vsync',430:'frame',431:'frame_wait_complete',
             435:'before_pipe_stop',439:'after_pipe_stop_before_sensor_stop',
             436:'after_sensor_stop',437:'before_data_enable',438:'after_data_enable',
             440:'final',441:'before_arm',442:'before_shutdown_data_disable',
             443:'after_shutdown_data_disable'}


def decode_shutdown(data,manifest,fast_result=None):
    if (len(data)!=64 or not manifest.get('shutdown_data_off') or
        manifest.get('shutdown_proof_address')!='0x343f8900' or
        manifest.get('shutdown_proof_words')!=16 or manifest.get('shutdown_proof_schema')!=1):
        raise ValueError('Unexpected shutdown proof layout')
    w=list(struct.unpack('<16I',data))
    if w[0]!=0x46534431 or w[1]!=1 or not 1<=w[2]<=4:raise ValueError('Invalid shutdown proof header')
    clocks_valid=(w[3]&0x44)==0x44 and (w[4]&0x30000)==0x30000 and not(w[5]&0x44)
    idle={'vc0_idle':not bool(w[6]&0x00020000),'capture_request_clear':not bool(w[7]&0x8),
          'capture_inactive':not bool(w[8]&0x8000),'pipe_disabled':not bool(w[9]&0x80000000)}
    if w[2]<2:idle={key:None for key in idle}
    proof_complete=bool(w[2]==4 and w[15]==0 and clocks_valid and all(idle.values()) and w[10]&2 and w[11]==15 and w[12]==3)
    sequence_matches=False
    if fast_result and not fast_result['overflow'] and fast_result['header'][1]==40:
        relevant=[r for r in fast_result['records'] if r['event'] in (439,442,443,436)]
        if [r['event'] for r in relevant]==[439,442,443,436]:
            # Data-disable timestamps must lie within the corresponding FAST
            # records. A previous invocation's standalone proof is insufficient.
            times=[relevant[0]['cycles'],relevant[1]['cycles'],w[13],w[14],
                   relevant[2]['cycles'],relevant[3]['cycles']]
            sequence_matches=all(((b-a)&0xFFFFFFFF)<0x80000000 for a,b in zip(times,times[1:]))
    return dict(address='0x343f8900',words=w,schema=w[1],stage=w[2],
        apb5enr=w[3],divenr=w[4],apb5rstr=w[5],sr0=w[6],p0fctcr=w[7],cmsr1=w[8],p0fscr=w[9],
        prcr=w[10],pcr_before=w[11],pcr_after=w[12],begin_cycle=w[13],end_cycle=w[14],
        result=w[15] if w[15]<0x80000000 else w[15]-0x100000000,idle=idle,
        clocks_and_reset_valid=clocks_valid,peripheral_reads_performed=w[2]>=2,
        proof_complete=proof_complete,proof_matches_fast_sequence=sequence_matches,
        completed=proof_complete and sequence_matches)


def decode(data,manifest):
    if len(data)!=WORDS*4:raise ValueError('Expected exactly544 little-endian words')
    if (manifest.get('fast_phy_status_address')!='0x343f8000' or
        manifest.get('fast_phy_status_words')!=WORDS or
        manifest.get('fast_phy_status_schema')!=1 or
        manifest.get('fast_phy_record_words')!=16 or
        manifest.get('fast_phy_header_words')!=32 or
        manifest.get('fast_phy_max_records')!=32):
        raise ValueError('Manifest does not match fixed reviewed FAST layout')
    words=list(struct.unpack('<544I',data));h=words[:32]
    if h[0]!=0x46505931 or h[8]!=1 or h[2]>32:raise ValueError('Invalid FAST header')
    mode={'early':0,'streaming':1}.get(manifest.get('data_enable'))
    if mode is None or h[6]!=mode:raise ValueError('FAST mode does not match manifest')
    records=[]
    for i in range(h[2]):
        r=dict(zip(FIELDS,words[32+i*16:48+i*16]));r['name']=EVENT_NAMES.get(r['event'],'unknown')
        r['csi_read']=r['prcr']!=0xFFFFFFFF;records.append(r)
    vsync=[r for r in records if r['event']==429]
    frames=[r for r in records if r['event']==430]
    # This is internal ordinal evidence, not a substitute for the external
    # STROBE/VSYNC timing comparison and native frame byte/content validation.
    association=bool(not h[3] and vsync and frames and h[30]==h[31]==1 and
                     vsync[0]['strobe_ordinal']==frames[0]['strobe_ordinal']==1 and
                     vsync[0]['vsyncs']==1 and frames[0]['frames']==1)
    return dict(schema=1,address=hex(ADDRESS),words=words,header=h,records=records,
        data_enable=manifest['data_enable'],overflow=h[3],
        first_physical_exposure_ordinal_supported=association,
        qualification='Require external STROBE association and complete native frame validation as well',
        start_ack_cycle=h[9],streaming_cycle=h[10],data_enable_begin_cycle=h[11],
        data_enable_end_cycle=h[12],arm_cycle=h[22],strobe_ordinal_at_arm=h[23],
        first_vsync_strobe_ordinal=h[30],first_frame_strobe_ordinal=h[31])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,required=True)
    p.add_argument('--receiver',type=Path,required=True,help='Frozen receiver directory with manifest and binary')
    p.add_argument('--output',type=Path)
    p.add_argument('--shutdown-input',type=Path,help='Optional fixed64-byte proof already read from0x343F8900')
    a=p.parse_args();m=json.loads((a.receiver/'manifest.json').read_text())
    raw=(a.receiver/'capture.bin').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=m['raw_sha256'] or len(raw)!=m['raw_bytes']:
        raise ValueError('Receiver binary does not match manifest')
    result=decode(a.input.read_bytes(),m)
    if a.shutdown_input:result['shutdown_proof']=decode_shutdown(a.shutdown_input.read_bytes(),m,result)
    result['receiver_sha256']=m['raw_sha256'];result['input_sha256']=hashlib.sha256(a.input.read_bytes()).hexdigest()
    output=json.dumps(result,indent=2)+'\n'
    if a.output:a.output.write_text(output)
    else:print(output,end='')


if __name__=='__main__':main()
