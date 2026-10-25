"""Offline checks for the frozen incremental four-bit diagnostic archive.
No hardware imports or external-file reads. Private source bytes/pixels are not
included, so their recorded source hashes and comparison flags are not recomputed.
"""
from pathlib import Path
import hashlib,json,math,re

HERE=Path(__file__).resolve().parent
EXPECTED_DIAGNOSTICS='15fe523e8dffe416165cf33de8392f1433d317b07807ee97bcd4adf5448245be'
EXPECTED_SELECTOR='f6e70a35adca0bcaa2a06ea6fb078a6d2e0212daea619d769228c69b128ee8d5'
EXPECTED_RECOVERY='35cb57f2ada203fbed18c67e23afce3d0abee0ba7637ef70371cb003c105af54'
READ_RAM='9a541fbe00de3a2c3d92b5fbe48aafe7f3ed4b770aedc3da1275a0c2ca662a52'
PATTERN25='11dd2b0ce63aeef0a0811cb3ee0870314c31ba6108aaed42e2c47fe24e8a0dd4'
PATTERN125='9e0e901bc8283dfa2e66620c39a68ec33f8e7d6de8d6d7f4a5f4d8ac837e50ed'
PREFIX='9401bed4076d6e9e4d2e4f9236661faf7b8f0e051cb332ea4dcbba09da336eba'

def sha(b):return hashlib.sha256(b).hexdigest()
def req(v,message):
    if not v:raise ValueError(message)
def load(name):return json.loads((HERE/name).read_bytes())
def privacy(v):
    if isinstance(v,dict):
        req(not any(k.lower().startswith(('cid','csd')) or k in ('ocr','rca','last_argument','pixels','base64','native_samples') for k in v),'Private identifier/payload field')
        for x in v.values():privacy(x)
    elif isinstance(v,list):
        req(len(v)<=128,'Unreviewed large data array')
        for x in v:privacy(x)
    elif isinstance(v,str):req(not re.search(r'[A-Za-z]:[\\/]',v),'Absolute local path')
def width(record,hz):
    w=record['bus_width_proof'];c=record['card']
    req(w['requested_width']==w['negotiated_width']==4 and w['scr_widths']&5==5 and
        w['acmd6_accepted']==1 and w['acmd6_r1']==0x920 and w['configured_clkcr']==0x24000+(150000000//(2*hz)) and
        c['clock_hz']==hz,'Four-bit/clock evidence differs')
def success(record):
    p=record['proof'];c=record['card']
    req(record['successful_idle'] and p['state']==3 and p['result']==0 and p['media_idle']==1 and
        p['initialized']==p['controller_owned']==p['cleanup_error']==0 and c['media_idle']==1 and
        c['initialized']==c['controller_owned']==c['error']==c['cleanup_error']==0,'Successful terminal qualification differs')
def main():
    index=load('index.json');req(index['schema']==1,'Unknown index schema')
    required={'.gitattributes','README.md','diagnostics.json','source-selector.json','post-readback-recovery.json','check.py'}
    req(set(index['files'])==required,'Unexpected artifact selection')
    for name,item in index['files'].items():
        data=(HERE/name).read_bytes();req(sha(data)==item['sha256'] and len(data)==item['bytes'],'Artifact hash/size differs: '+name)
    for name,digest in [('diagnostics.json',EXPECTED_DIAGNOSTICS),('source-selector.json',EXPECTED_SELECTOR),('post-readback-recovery.json',EXPECTED_RECOVERY)]:
        req(sha((HERE/name).read_bytes())==digest,'Frozen identity differs')
    d=load('diagnostics.json');s=load('source-selector.json');post=load('post-readback-recovery.json')
    privacy(d);privacy(s);privacy(post)
    req(s['summary_sha256']==EXPECTED_DIAGNOSTICS and d['stage']=='incremental diagnostics, not final benchmark' and
        d['hardware_access'] is False and d['hardware_owned_by']=='root','Snapshot scope/binding differs')
    sources={v['path']:v for v in s['selected_sources']};req(len(sources)==len(s['selected_sources']),'Repeated source path')
    for path,item in sources.items():
        req(not Path(path).is_absolute() and '..' not in Path(path).parts and re.fullmatch('[0-9a-f]{64}',item['sha256']) and item['bytes']>0,'Invalid compact source descriptor')
    def bound(v):
        if isinstance(v,dict):
            if set(v)=={'path','sha256','bytes'}:req(sources.get(v['path'])==v,'Selected result/source binding differs')
            else:
                for x in v.values():bound(x)
        elif isinstance(v,list):
            for x in v:bound(x)
    bound(d['records']);r=d['records']
    for name in ('initial_four_bit_cmd8_failure','frozen_one_bit_cmd8_control_failure','rechecked_four_bit_cmd8_failure'):
        p=r[name]['proof'];c=r[name]['card']
        req(not r[name]['successful_idle'] and p['media_idle']==0 and p['controller_owned']==1 and c['error_command']==8 and
            c['error']==8 and c['error_sta']==1 and c['last_r1']==0x7c5 and c['command_count']==2 and
            c['clock_hz']==100000 and c['read_sectors']==c['written_sectors']==c['transfer_words']==0,'Initial failed identification changed')
    for name,lba,count in [('four_bit_first_sector25',0,1),('four_bit_range0_64_25',0,64),('four_bit_range64_64_25',64,64)]:
        v=r[name];success(v);width(v,25000000);p=v['proof'];b=v['private_byte_comparison']
        req(v['binary_sha256']==READ_RAM and p['operation']==3 and p['read_lba']==lba and p['read_count']==count and
            p['read_bytes']==count*512 and b['passed'] and b['bytes_equal'] and b['bytes']==count*512 and not b['private_bytes_published'],'Known-data READ evidence differs')
    h=r['physical_handshake'];req(h['channel_map']=={'2':'breakout CLK','3':'breakout CMD'} and h['CH5_moved'] is False,'Probe conditions changed')
    req([(f['direction'],f['index'],f['value_hex']) for f in h['selected_frames']]==
        [('host_command',0,'0x0'),('host_command',8,'0x1aa'),('card_response',8,'0x1aa')] and
        all(f['crc_ok'] and f['end_bit']==1 for f in h['selected_frames']),'Selected physical handshake differs')
    f=r['four_bit_pattern25_failed_write'];p=f['proof'];c=f['card']
    req(f['binary_sha256']==PATTERN25 and not f['successful_idle'] and p['result']==820 and p['slot']==3 and
        p['media_idle']==0 and p['controller_owned']==1 and c['error']==14 and c['error_command']==25 and
        c['error_sta']==0x5002 and c['transfer_words']==408 and c['last_stop_r1']==0x800c00 and
        c['last_sta']==0x5042 and c['last_r1']==0x900 and c['cleanup_error']==10,'Failed write/cleanup record changed')
    recovery=r['authorized_warm_recovery'];basis=r['explicit_recovery_basis']
    req(recovery['passed'] and recovery['prefix_sha256']==PREFIX and recovery['good_pulses']==8 and recovery['bad_pulses']==0 and
        not recovery['nor_commands'] and basis['bench_owner']=='root' and basis['no_nor_programming'] and basis['not_an_idle_claim'],'Recovery scope changed')
    build=r['isolated_clock_build'];b=build['builds']
    req(build['offline_only'] and build['default_byte_identical'] and not build['driver_or_abort_changed'] and
        b['ram-pattern-v19b']['sha256']==b['ram-pattern25-v20-check']['sha256']==PATTERN25 and
        b['ram-pattern125-v20']['sha256']==PATTERN125 and build['changed_literal_words']=={'0x4e14':[3,6],'0x4e1c':[25000000,12500000]},'Isolated clock change differs')
    v=r['four_bit_pattern125_save'];success(v);width(v,12500000);p=v['proof'];image=r['pattern125_full_readback']
    req(v['binary_sha256']==PATTERN125 and p['operation']==1 and p['slot']==4 and p['written_sectors']==3730 and
        p['frames']==1 and p['errors']==p['capture_error']==0 and v['stream']['mode']==2 and v['stream']['queued_bytes']==1909760,'12.5MHz save proof differs')
    for key in ('passed','full_payload_read','full_slot_read','start_magic_valid','completion_marker_valid','png_samples_match_read_raw','original_sensor_frame_comparison','source_ram_bytes_equal'):
        req(image[key] is True,'Full image verification missing: '+key)
    req(image['slot']==4 and image['bytes']==1909600 and image['slot_bytes']==1909760 and image['raw_sha256']==v['downloaded_frame_sha256']==
        '5edaa1705f76b8434993271c86e71d5d83bce1c0ec7272caeec9564594279c1e','Image/source RAM identity differs')
    expected=((p['commit_done']-p['first_write'])&0xffffffff)/400000
    req(math.isclose(expected,v['first_write_to_commit_ms'],abs_tol=1e-12),'DWT diagnostic interval differs')
    req(post['passed'] and post['prefix_sha256']==PREFIX and post['good_pulses']==9 and post['bad_pulses']==0 and
        not post['ram_writes'] and not post['nor_commands'],'Post-readback early recovery differs')
    req(d['recorded_owner_scope']['no_NOR_programming_in_this_pass'] and d['recorded_owner_scope']['unchanged_installed_firmware']=='v18','Recorded ownership scope differs')
    print(json.dumps(dict(passed=True,hardware_access=False,records=len(r),private_pixels_redecoded=False,
        source_binding='Compact source descriptors and frozen artifact hashes; private source files omitted',
        pattern125_full_image_comparison_recorded=True,cold_cycle_benchmark=False),indent=2))
if __name__=='__main__':main()
