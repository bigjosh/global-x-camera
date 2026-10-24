"""Guarded RAM RAW-slot operations; explicit --execute, no reset/power/NOR API.

Start from the installed exact early recovery via its SRAM bridge, or a fresh
successful terminal proof from this exact RAM image. FORMAT is a separate
explicit operation. A failed/active storage result never authorizes a halt,
replacement image, reset or automatic retry. Image/card data stays local.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import secrets
import struct
import time
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
spec = importlib.util.spec_from_file_location('raw_slots_bridge', ROOT/'firmware/capture-sd/low_power/readback_recovery/run.py')
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)
sd = bridge.sd
LOAD, FRAME, REQUEST, PROOF = 0x34300000, 0x34000000, 0x343FD000, 0x343FD100
READ_BUFFER, READ_MAX, FRAME_BYTES = 0x34200000, 262144, 1909600
MAGIC, DONE = 0x52535731, 0x5253444E
OPS = {'capture': 1, 'format': 2, 'read': 3}
MAGIC_FRAME, MAGIC_BUFFER, SLOT_BYTES = 0x34000010, 0x3400000C, 1909760
FRONT_MAGIC_FRAME, FRONT_MAGIC_BUFFER = 0x340000A0, 0x34000004
DMA_WAIT_FAULTS = ('missing_clock', 'exception', 'primask', 'basepri', 'faultmask',
    'deep_sleep', 'sleep_on_exit', 'systick_control', 'systick_load',
    'ram_sleep_clocks', 'rif_sleep_clocks', 'sd_sleep_clock', 'bus_sleep_clocks',
    'debug_access', 'debug_sleep_emulation')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def dump(path, value):
    path.write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8')


def dma_wait_snapshot(b,m):
    """Decode either frozen20-byte or current24-byte bounded SRAM telemetry."""
    address,size=m['dma_wait'],m.get('dma_wait_bytes')
    if size not in (20,24) or not m['bss_start']<=address<=m['bss_end']-size:
        raise ValueError('DMA wait telemetry bounds differ')
    raw=b.upload(address,size,'dma-wait.bin')
    if len(raw)!=size:raise ValueError('Incomplete DMA wait telemetry')
    words=list(struct.unpack('<'+str(size//4)+'I',raw))
    if m.get('dma_wait_clock') is not None and words[0]!=m['dma_wait_clock']:
        raise ValueError('DMA wait clock callback differs from frozen executable')
    names=('milliseconds_callback','wait_calls','wall_ms','active_cycles','immediate_wakes','context_faults')
    result=dict(zip(names,words));faults=result.get('context_faults')
    result.update(bytes=size,context_fault_names=None if faults is None else
        [name for i,name in enumerate(DMA_WAIT_FAULTS) if faults&(1<<i)],
        unknown_context_fault_bits=None if faults is None else faults&~((1<<len(DMA_WAIT_FAULTS))-1),
        timing_scope='DMA phases including CMD24/25 launch; excludes post-DATAEND CMD12/card-ready waits',
        cycle_qualification='Processor-clock cycles, not wall time or executed-instruction time; sleep emulation can keep this clock running')
    return raw,result


def fields(folder):
    text = (folder/'runtime.h').read_text()
    start = text.index(' RP_MAGIC,')
    end = text.index('};', start)
    names = re.findall(r'\bRP_([A-Z0-9_]+)\b', text[start:end])
    if len(names) != len(set(names)) or not 90 <= len(names) <= 96:
        raise ValueError('Unexpected report enum')
    return [n.lower() for n in names] + ['reserved_'+str(n) for n in range(len(names), 96)]


def magic_geometry(m):
    """Two exact, explicit layouts; never infer a revision from RAM addresses."""
    version=m.get('magic_layout_version')
    if version is None:
        return dict(version=1,frame=MAGIC_FRAME,buffer=MAGIC_BUFFER,
                    proof_magic=0x524D4731,start_magic=b'GXRS',image_offset=4,
                    metadata_offset=None,metadata_bytes=0,guard_word_bias=0)
    if type(version) is not int or version!=2:
        raise ValueError('Unreviewed magic layout version')
    expected=dict(image_offset=156,metadata_offset=4,metadata_bytes=152,end_guard_word_bias=1)
    if any(m.get(k)!=v for k,v in expected.items()):
        raise ValueError('Front metadata geometry differs')
    return dict(version=2,frame=FRONT_MAGIC_FRAME,buffer=FRONT_MAGIC_BUFFER,
                proof_magic=0x524D4732,start_magic=b'GXR2',image_offset=156,
                metadata_offset=4,metadata_bytes=152,guard_word_bias=1)


def frame_layout(m):
    """Exact opt-in geometry; old manifests retain their original addresses."""
    if m.get('magic_format'):
        g=magic_geometry(m)
        return dict(frame=g['frame'],frame_bytes=FRAME_BYTES,
                    guard=g['buffer']+SLOT_BYTES,guard_bytes=32,allocation_bytes=SLOT_BYTES)
    return dict(frame=FRAME,frame_bytes=FRAME_BYTES,
                guard=FRAME+(SLOT_BYTES if m.get('whole_image_preerase') else FRAME_BYTES),
                guard_bytes=32,allocation_bytes=SLOT_BYTES if m.get('whole_image_preerase') else FRAME_BYTES)


def checked_build(folder, digest):
    m = json.loads((folder/'manifest.json').read_text())
    code = (folder/'capture.bin').read_bytes()
    exact = dict(schema=1, kind='raw-slots', load=LOAD, stack=0x343B0000,
        stack_floor=0x343AF000, request=REQUEST, request_words=16, proof=PROOF,
        proof_words=96, read_buffer=READ_BUFFER, read_buffer_bytes=READ_MAX,
        **frame_layout(m), width=1120, height=1364,
        flash=False, standby=False)
    if any(m.get(k) != v for k,v in exact.items()):
        raise ValueError('Only reviewed RAM/awake layout is accepted')
    if m['binary_sha256'] != digest or sha(code) != digest or len(code) != m['binary_bytes']:
        raise ValueError('Explicit executable identity differs')
    if not 0 < len(code) < 0xE000 or len(code) % 4:
        raise ValueError('Code size/alignment')
    if struct.unpack_from('<II', code) != (m['stack'], m['entry']):
        raise ValueError('Entry/vector mismatch')
    if not LOAD < m['data_start'] <= m['system_core_clock'] < m['data_end'] == LOAD+len(code):
        raise ValueError('Immutable/data layout mismatch')
    if m['immutable_bytes'] != m['data_start']-LOAD:
        raise ValueError('Immutable code boundary differs')
    if not m['data_end'] <= m['bss_start'] <= m['card'] < m['card']+200 <= m['bss_end'] < m['stack_floor']:
        raise ValueError('Card/BSS bounds differ')
    if not m['bss_start'] <= m['slots'] < m['slots']+640 <= m['bss_end']:
        raise ValueError('Slots object bounds differ')
    if m['card'] < m['slots']+640 and m['slots'] < m['card']+200:
        raise ValueError('Card and slots overlap')
    for key in ('park', 'reject_park'):
        off = m[key]-LOAD
        if not 0 <= off < len(code)-1 or code[off:off+2] != b'\xfe\xe7':
            raise ValueError('Exact branch-to-self missing')
    for name, expected in m['source_hashes'].items():
        path = (folder/name).resolve()
        path.relative_to(folder.resolve())
        if sha(path.read_bytes()) != expected:
            raise ValueError('Frozen source changed: '+name)
    if m['pattern'] not in (0, 1) or m['transport'] not in ('pio','idma'):
        raise ValueError('Unsupported pattern/transport')
    if not (m['chunk_sectors']==3730 if m.get('whole_image_preerase') or m.get('magic_format') else 1 <= m['chunk_sectors'] <= 1024):
        raise ValueError('Chunk bound')
    flag_names = ('async_stop','line_stream','preinit','line_snapshots','line_poison','dma_sleep','whole_image_preerase','magic_format')
    expected_flags = sum(int(bool(m.get(k,False))) << i for i,k in enumerate(flag_names))
    if m.get('expected_flags',0) != expected_flags:
        raise ValueError('Build feature flags differ')
    if m.get('line_stream') and (m.get('producer_bytes') != 416 or
            not m['bss_start'] <= m['producer'] <= m['bss_end']-416):
        raise ValueError('Producer telemetry bounds differ')
    if m.get('line_snapshots') and (not m.get('line_stream') or
            (m.get('snapshot_address'),m.get('snapshot_capacity'),m.get('snapshot_bytes')) !=
            (0x343D0000,20,512)):
        raise ValueError('Snapshot layout differs')
    whole_layout(m)
    magic_layout(m)
    return m, code


def whole_layout(m):
    if m.get('whole_image_preerase') and (
            m.get('transport')!='idma' or m.get('dma_sleep') or m.get('chunk_sectors')!=3730 or
            m.get('original_guard')!=FRAME+FRAME_BYTES or m.get('whole_proof_words')!=8 or
            not m['bss_start']<=m.get('whole_proof',0)<=m['bss_end']-32):
        raise ValueError('Whole-image preerase layout/features differ')


def magic_layout(m):
    if not m.get('magic_format'): return
    g=magic_geometry(m)
    if (m['magic_format'] is not True or m.get('whole_image_preerase') or
            m.get('transport')!='idma' or m.get('dma_sleep') or m.get('chunk_sectors')!=3730 or
            m.get('slot_buffer')!=g['buffer'] or m.get('original_guard')!=g['frame']+FRAME_BYTES or
            any(m.get(k)!=v for k,v in frame_layout(m).items()) or
            m.get('magic_proof_words')!=8):
        raise ValueError('Magic-slot geometry/features differ')
    spans=[('card',m['card'],200),('slots',m['slots'],640)]
    for key,size in [('magic_slots',576),('magic_proof',32),('sd_scr',16),('sd_erase',32),('sd_stream',44)]:
        if key!='magic_proof' and m.get(key+'_bytes')!=size:
            raise ValueError('Magic object ABI differs: '+key)
        address=m.get(key,0)
        # FLASH has no request dispatcher and cannot enter destructive FORMAT;
        # LTO may remove its unused erase object. RAM must retain that object.
        if key=='sd_erase' and m.get('flash') is True and address is None:
            continue
        if type(address) is not int or address%4 or not m['bss_start']<=address<=m['bss_end']-size:
            raise ValueError('Magic object outside BSS: '+key)
        spans.append((key,address,size))
    if m['magic_slots']%32: raise ValueError('Magic slots object alignment differs')
    for i,(name,start,size) in enumerate(spans):
        for other,begin,length in spans[i+1:]:
            if start<begin+length and begin<start+size:
                raise ValueError('Magic object overlap: '+name+'/'+other)


def capture_geometry(p,m):
    if m.get('magic_format'):
        if (p['payload_lba']!=p['slot']*3730 or p['card_write_hi'] or p['card_write_lo']!=3730 or
                p['generation_lo'] or p['generation_hi'] or p['slot_count']>2**32//3730 or
                p['scan_headers']!=p['slot']+1 or p['chunk_count']!=1 or p['chunk_overflow']):
            raise ValueError('Magic-slot completion geometry differs')
    else:
        if p['payload_lba']!=9+p['slot']*3731 or p['card_write_hi'] or p['card_write_lo']!=3732:
            raise ValueError('Unexpected image sector writes')
        if (not(p['generation_lo'] or p['generation_hi']) or p['slot_count']>(2**32-8)//3731 or
                p['scan_headers']!=p['slot']+1):
            raise ValueError('Slot geometry/generation mismatch')


def frame_guards(b,m,p):
    bias=magic_geometry(m)['guard_word_bias'] if m.get('magic_format') else 0
    expected=struct.pack('<8I',*(0xA15A1000+i+bias for i in range(8)))
    if b.upload(m['guard'],32,'frame-guard.bin')!=expected:
        raise ValueError('Frame/post-padding guard damaged')
    if m.get('magic_format'):
        magic_layout(m)
        g=magic_geometry(m)
        if p['chunk_count']!=1 or p['chunk_overflow']:
            raise ValueError('Magic slot must use exactly one payload call')
        raw=b.upload(m['magic_proof'],32,'magic-proof.bin')
        if raw!=struct.pack('<8I',g['proof_magic'],3,0,0,
                            int.from_bytes(g['start_magic'],'little'),0x45525847,152,3730):
            raise ValueError('Magic original guard/commit proof differs')
        if (b.upload(g['buffer'],4,'leading-magic.bin')!=g['start_magic'] or
                b.upload(g['frame']+FRAME_BYTES,4,'trailing-magic.bin')!=b'GXRE'):
            raise ValueError('Magic markers differ')
        metadata=None
        if g['version']==1:
            if b.upload(g['frame']+FRAME_BYTES+4,152,'frame-padding.bin')!=bytes(152):
                raise ValueError('Legacy magic padding differs')
        else:
            metadata=b.upload(g['buffer']+4,152,'frame-metadata.bin')
            if len(metadata)!=152:raise ValueError('Incomplete front metadata')
        row=struct.unpack('<8I',b.upload(m['chunk_trace'],32,'magic-chunk.bin'))
        if row[2:5]!=(0,3730,FRAME_BYTES) or row[5]&0x1F00!=0x900 or row[6]:
            raise ValueError('Magic single-transaction trace differs')
        result=dict(format='magic',proof=list(struct.unpack('<8I',raw)),chunk=list(row),
                    original_guard_checked_before_trailer=True,post_padding_guard_intact=True)
        if g['version']==1:result['padding_zero']=True
        else:result.update(layout_version=2,metadata_bytes=152,metadata_hex=metadata.hex(),
                           metadata_schema=None,end_guard_word_bias=1)
        return result
    if not m.get('whole_image_preerase'): return None
    whole_layout(m)
    if p['chunk_count']!=1 or p['chunk_overflow']:
        raise ValueError('Whole image must have exactly one payload call')
    raw=b.upload(m['whole_proof'],32,'whole-proof.bin')
    if raw!=struct.pack('<8I',0x52575031,3,0,0,FRAME_BYTES,1909760,160,3730):
        raise ValueError('Original guard/padding transition proof differs')
    if b.upload(FRAME+FRAME_BYTES,160,'frame-padding.bin')!=bytes(160):
        raise ValueError('Whole-image padding is not zero')
    chunks=b.upload(m['chunk_trace'],32,'whole-chunk.bin')
    words=struct.unpack('<8I',chunks)
    if (words[2:5]!=(0,3730,FRAME_BYTES) or words[5]&0x1F00!=0x900 or words[6]):
        raise ValueError('Whole-image payload trace differs')
    return dict(proof=list(struct.unpack('<8I',raw)),chunk=list(words),padding_zero=True,
                original_guard_checked_before_zero_padding=True,post_padding_guard_intact=True)


def decode(raw, names):
    if len(raw) != 384:
        raise ValueError('Incomplete RAW report')
    return dict(zip(names, struct.unpack('<96I',raw)))


def request(operation, nonce, arg0=0, arg1=0, arg2=0, *, magic_format=False):
    if operation not in OPS.values() or not 0 < nonce < 2**32:
        raise ValueError('Unknown operation/nonzero nonce required')
    if any(type(n) is not int or not 0 <= n < 2**32 for n in (arg0,arg1,arg2)):
        raise ValueError('Request argument outside uint32')
    if operation == 1 and (arg0 or arg1 or arg2):
        raise ValueError('Capture has no request arguments')
    if operation == 2:
        if magic_format and (arg0 or arg1 or arg2):
            raise ValueError('Magic erase has no generation or slot-limit arguments')
        if not magic_format and not (arg0 or arg1):
            raise ValueError('Format requires a nonzero new generation')
    if operation == 3 and (not 1 <= arg1 <= READ_MAX//512 or arg2 or arg0+arg1 > 2**32):
        raise ValueError('Read bounds')
    return struct.pack('<16I', 0x52535131, nonce, operation, arg0,arg1,arg2,*([0]*10))


def validate(p, m, words):
    if (not isinstance(words,(list,tuple)) or len(words)!=16 or
            any(type(n) is not int or not 0<=n<2**32 for n in words) or
            words[0]!=0x52535131 or any(words[6:]) or
            request(words[2],words[1],*words[3:6],magic_format=bool(m.get('magic_format')))!=struct.pack('<16I',*words)):
        raise ValueError('Stored request is malformed')
    exact = dict(magic=MAGIC, schema=1, words=96, nonce=words[1],operation=words[2],
        state=3, result=0, stage=8, terminal=DONE, frame=frame_layout(m)['frame'], bytes=FRAME_BYTES,
        width=1120,height=1364,card=m['card'],card_size=200,slots=m['slots'],slots_size=640,
        sd_error=0,media_idle=1,initialized=0,controller_owned=0,cleanup_error=0,
        control=0,ipsr=0,primask=1,cpacr=0,pattern=m['pattern'],
        transport=int(m['transport']=='idma'),chunk_sectors=m['chunk_sectors'],completion=0,
        flags=m.get('expected_flags',0))
    if any(p.get(k) != v for k,v in exact.items()):
        raise ValueError('RAW terminal proof rejected: '+str(p))
    if p['ccr'] & 0x30000 or p['fpccr'] & 1 or p['systick'] & 3:
        raise ValueError('Cache/FP/SysTick context active')
    if p['last_ready'] & 0x1F00 != 0x900:
        raise ValueError('Card did not report ready/TRANSFER')
    if words[2] == 1:
        capture = dict(camera_ready=FRAME_BYTES,dma_bytes=FRAME_BYTES,frames=1,
            errors=0,canary=0,format=10,data_type=0x30,vc0cfgr1=0x201,
            written_sectors=3730,capture_error=0)
        if any(p.get(k) != v for k,v in capture.items()) or not p['slot_count'] > p['slot']:
            raise ValueError('Capture/slot completion mismatch')
        capture_geometry(p,m)
        if p['p0fctcr'] & 8 or p['cmsr1'] & 0x8000 or p['csi_sr0'] & 0x20000:
            raise ValueError('Capture pipe still active')
    elif words[2] == 2:
        if m.get('magic_format'):
            if (not p['slot_count'] or p['slot_count']>2**32//3730 or p['formatted_slots']!=p['slot_count'] or
                    p['generation_lo'] or p['generation_hi'] or p['card_write_hi'] or p['card_write_lo'] or
                    p['slot']!=0xFFFFFFFF or p['written_sectors'] or p['scan_headers'] or
                    p['camera_ready'] or p['card_read_lo'] or p['card_read_hi']):
                raise ValueError('Incomplete magic whole-card erase')
        elif (not p['slot_count'] or p['formatted_slots'] != p['slot_count'] or
                p['generation_lo'] != words[3] or p['generation_hi'] != words[4] or
                p['card_write_hi'] or p['card_write_lo'] != p['slot_count']+2 or
                (words[5] and p['slot_count'] != words[5])):
            raise ValueError('Incomplete format')
    else:
        if (p['read_lba'] != words[3] or p['read_count'] != words[4] or
                p['read_bytes'] != words[4]*512 or p['read_dest'] != READ_BUFFER or
                p['card_write_lo'] or p['card_write_hi'] or p['camera_ready'] or
                p['card_read_lo'] != words[4] or p['card_read_hi']):
            raise ValueError('READ scope/count mismatch')


def magic_snapshot(b,m,p,label,card):
    """Read the new owning object, not a fabricated legacy on-card header."""
    magic_layout(m)
    if p['operation']==3:
        return dict(read_only=True,slot_objects_not_opened=True)
    scr_raw=b.upload(m['sd_scr'],16,label+'-scr.bin')
    if len(scr_raw)!=16: raise ValueError('Incomplete SCR object')
    valid,erased=struct.unpack_from('<2I',scr_raw,8)
    if valid!=1 or scr_raw[0]>>4 or erased!=(255 if scr_raw[1]&0x80 else 0):
        raise ValueError('SCR erased-byte proof differs')
    raw=b.upload(m['magic_slots'],576,label+'-magic-slots.bin')
    if len(raw)!=576: raise ValueError('Incomplete magic-slot object')
    names='card slot_count selected_slot slot_lba erased_byte opened selected_valid active error scan_headers read_sectors written_sectors write_sectors'.split()
    slots=dict(zip(names,struct.unpack_from('<13I',raw)))
    expected=dict(card=m['card'],slot_count=p['slot_count'],selected_slot=p['slot'],slot_lba=p['payload_lba'],
        erased_byte=erased,opened=1,selected_valid=0,active=0,error=0,scan_headers=p['scan_headers'],
        read_sectors=p['scan_headers'],written_sectors=p['written_sectors'],write_sectors=p['written_sectors'])
    if any(slots[k]!=v for k,v in expected.items()):
        raise ValueError('Magic-slot ownership/count snapshot differs')
    if p['operation']==1 and raw[64:68]!=bytes([erased])*4:
        raise ValueError('Retained selected free-word observation differs')
    mirror=b.upload(m['slots'],640,label+'-slots-mirror.bin')
    if len(mirror)!=640: raise ValueError('Incomplete legacy reporting mirror')
    u=struct.unpack_from('<16I',mirror)
    if (list(u[:4])!=[m['card'],0,0,0] or
            list(u[4:14])!=[p['slot_count'],p['slot'],p['payload_lba'],p['written_sectors'],
                1,0,0,0,p['scan_headers'],p['formatted_slots']] or any(mirror[64:])):
        raise ValueError('Magic reporting mirror disagrees with owning object')
    g=magic_geometry(m)
    result=dict(slots=slots,scr_wire_bytes=list(scr_raw[:8]),erased_byte=erased,
                legacy_mirror_only=True,on_media_metadata=g['version']==2)
    if g['version']==2:result.update(metadata_bytes=152,metadata_schema=None,magic_layout_version=2)
    if p['operation']==1:
        sensor_raw=b.upload(0x343F4000,128,label+'-sensor-status.bin')
        if len(sensor_raw)!=128: raise ValueError('Incomplete sensor exposure status')
        sensor_words=struct.unpack('<32I',sensor_raw)
        coarse=m.get('exposure_coarse',1428)
        sensor=dict(applied_coarse=sensor_words[20],exposure_us=sensor_words[21],
            frame_length=sensor_words[18],margin=sensor_words[19],
            nondefault_frame_bound_checked=coarse!=1428)
        if (not 1<=coarse<=63000 or sensor['applied_coarse']!=coarse or not sensor['exposure_us'] or
                (coarse!=1428 and (sensor['frame_length']<sensor['margin']+7 or
                    coarse>sensor['frame_length']-sensor['margin']-7)) or
                (coarse==30000 and sensor['exposure_us']!=230597)):
            raise ValueError('Applied sensor exposure differs from capture manifest/bounds')
        result['sensor']=sensor
        raw=b.upload(m['sd_stream'],44,label+'-stream.bin')
        if len(raw)!=44: raise ValueError('Incomplete SD stream object')
        names='publish context mode initial_available_bytes published_bytes queued_bytes publication_calls starved_polls producer_error producer_wait_cycles max_wait_cycles'.split()
        stream=dict(zip(names,struct.unpack('<11I',raw)))
        code_spans=m.get('immutable_ranges',[[LOAD,LOAD+m['immutable_bytes']]])
        if (not stream['publish']&1 or not any(start<=stream['publish']-1<end for start,end in code_spans) or
                stream['context'] or stream['mode'] not in (1,2) or
                not 512<=stream['initial_available_bytes']<=SLOT_BYTES or
                stream['published_bytes']!=SLOT_BYTES or stream['queued_bytes']!=SLOT_BYTES or
                not stream['publication_calls'] or stream['producer_error'] or
                stream['max_wait_cycles']>stream['producer_wait_cycles'] or
                (stream['mode']==1)!=(stream['initial_available_bytes']==SLOT_BYTES)):
            raise ValueError('SD producer stream completion differs')
        result['stream']=stream
    elif p['operation']==2:
        raw=b.upload(m['sd_erase'],32,label+'-erase.bin')
        if len(raw)!=32: raise ValueError('Incomplete whole-card erase proof')
        names='started completed first_lba last_lba timeout_ms elapsed_ms last_r1 command_count'.split()
        erase=dict(zip(names,struct.unpack('<8I',raw)))
        if (erase['started']!=1 or erase['completed']!=1 or erase['first_lba'] or
                erase['last_lba']!=card['sector_count']-1 or erase['timeout_ms']!=600000 or
                erase['elapsed_ms']>erase['timeout_ms'] or erase['last_r1']&0x1F00!=0x900 or
                erase['command_count']<4):
            raise ValueError('Explicit whole-card erase completion differs')
        result['erase']=erase
    return result


def terminal_gate(b, folder, m, code, prior, label):
    names = fields(folder)
    p = decode(b.upload(PROOF,384,label+'-proof.bin'),names)
    if p != prior['proof'] or prior['binary_sha256'] != sha(code):
        raise ValueError('Live proof differs from prior operation')
    validate(p,m,prior['request_words'])
    card=card_snapshot(b,m,p,label)
    if m.get('magic_format'): magic_snapshot(b,m,p,label,card)
    if b.upload(LOAD,m['immutable_bytes'],label+'-code.bin') != code[:m['immutable_bytes']]:
        raise ValueError('Live executable changed')
    return sd.context_proof(b,{m['park']},label+'-context')


def card_snapshot(b,m,p,label):
    raw=b.upload(m['card'],200,label+'-card.bin')
    values=struct.unpack('<6Q38I',raw)
    names=('sector_count read_sectors written_sectors read_cycles write_cycles ready_cycles '
        'initialized controller_owned media_idle clock_hz ocr rca cid0 cid1 cid2 cid3 '
        'csd0 csd1 csd2 csd3 error error_stage error_command error_sta stage last_command '
        'last_argument last_sta last_r1 command_count last_ready_r1 last_stop_r1 cleanup_error '
        'transfer_words transfer_sta transfer_cycles init_cycles gpioc_idr gpioe_idr '
        'vddio5_control saved_sdmmc_mux saved_demcr saved_dwt timer_owned').split()
    c=dict(zip(names,values))
    if (any(c[k] for k in ('initialized','controller_owned','error','cleanup_error','timer_owned')) or
            c['media_idle']!=1 or c['stage']!=9 or c['last_ready_r1']&0x1f00!=0x900 or
            c['written_sectors']!=(p['card_write_hi']<<32|p['card_write_lo']) or
            c['read_sectors']!=(p['card_read_hi']<<32|p['card_read_lo'])):
        raise ValueError('Live card ownership/idle snapshot differs')
    extent=p['slot_count']*3730 if m.get('magic_format') else 8+p['slot_count']*3731
    if p['slot_count'] and extent>c['sector_count']:
        raise ValueError('Slot volume exceeds card capacity')
    if m.get('magic_format') and p['slot_count'] and p['slot_count']!=c['sector_count']//3730:
        raise ValueError('Magic slot count does not cover full card geometry')
    return c


def run(a):
    folder=a.build.resolve(); m,code=checked_build(folder,a.expected_sha)
    names=fields(folder); op=OPS[a.operation]; nonce=secrets.randbelow(0xffffffff)+1
    if op==2:
        if m.get('magic_format'):
            if a.generation is not None or a.slot_limit:
                raise ValueError('Magic whole-card erase refuses generation/slot-limit options')
            args=(0,0,0)
        else:
            generation=a.generation or secrets.randbits(64) or 1
            args=(generation&0xffffffff,generation>>32,a.slot_limit)
    elif op==3: args=(a.lba,a.count,0)
    else: args=(0,0,0)
    req=request(op,nonce,*args,magic_format=bool(m.get('magic_format'))); words=list(struct.unpack('<16I',req))
    a.out.mkdir(parents=True,exist_ok=False)
    dump(a.out/'plan.json',dict(execute=a.execute,operation=a.operation,request_words=words,
        binary_sha256=sha(code),build=str(folder),prior=str(a.prior) if a.prior else None,
        reset=False,power_switch=False,nor_commands=False))
    if not a.execute:
        print('Offline operation validated; no hardware accessed'); return
    if a.prior:
        b=sd.Bench(a.out/'operation')
        prior=json.loads(a.prior.read_text())
        terminal_gate(b,folder,m,code,prior,'before')
    elif a.bridge_proof:
        # Resume only the exact SRAM bridge after a host-side preparation
        # failure; no RAW firmware operation has executed in this state.
        b=sd.Bench(a.out/'operation')
        prior=json.loads(a.bridge_proof.read_text())
        boot=ROOT/'tmp/bringup/capture-sleep-20261020/recovery-read-bridge-v1'
        _,boot_code=bridge.checked_bridge(boot)
        if prior['bridge_sha256']!=bridge.BOOT_SHA:
            raise ValueError('Unknown prior bridge')
        live=bridge.checked_boot(b.upload(bridge.BOOT_PROOF,92,'bridge-proof.bin'),prior['proof']['nonce'])
        if live!=prior['proof'] or b.upload(bridge.LOAD,len(boot_code),'bridge-code.bin')!=boot_code:
            raise ValueError('Bridge identity changed')
        sd.context_proof(b,{bridge.BOOT_PARK},'bridge-before')
    else:
        boot=ROOT/'tmp/bringup/capture-sleep-20261020/recovery-read-bridge-v1'
        _,boot_code=bridge.checked_bridge(boot)
        b=bridge.bootstrap(SimpleNamespace(recovery_build=a.recovery_build,bridge=boot),a.out,boot_code)
    b.call('-halt','-w',folder/'capture.bin',hex(LOAD),'-v',success='Download verified successfully')
    if b.upload(LOAD,len(code),'executable-readback.bin') != code:
        raise ValueError('Code readback mismatch')
    (b.output/'raw-request.bin').write_bytes(req); (b.output/'raw-clear.bin').write_bytes(bytes(384))
    b.call('-halt','-w',b.output/'raw-request.bin',hex(REQUEST),'-v',
        '-w',b.output/'raw-clear.bin',hex(PROOF),'-v',success='Download verified successfully')
    if b.upload(REQUEST,64,'raw-request-readback.bin') != req or b.upload(PROOF,384,'raw-clear-readback.bin') != bytes(384):
        raise ValueError('Request/proof readback mismatch')
    b.call('-halt','-coreReg',f"PC={hex(m['entry'])}",'XPSR=0x01000000','-run',success='Core run')
    deadline=time.monotonic()+(1200 if op==2 else 30); poll=0
    while True:
        p=decode(b.upload(PROOF,384,f'proof-{poll:04d}.bin'),names)
        if p['magic']==MAGIC and p['nonce']==nonce and p['terminal']==DONE: break
        if time.monotonic()>=deadline:
            dump(a.out/'incomplete.json',p)
            raise TimeoutError('No terminal; leave powered without retry')
        if poll%5==0: print(json.dumps(dict(state=p['state'],stage=p['stage'],formatted=p['formatted_slots'],sd_error=p['sd_error'])),flush=True)
        poll+=1; time.sleep(2 if op==2 else .2)
    dump(a.out/'proof.json',p)
    validate(p,m,words)
    card=card_snapshot(b,m,p,'completed')
    magic=magic_snapshot(b,m,p,'completed',card) if m.get('magic_format') else None
    # Live execution state is checked only after exact completed/idle proof.
    context=sd.context_proof(b,{m['park']},'completed')
    if b.upload(LOAD,m['immutable_bytes'],'completed-code.bin') != code[:m['immutable_bytes']]:
        raise ValueError('Immutable executable changed')
    clock,=struct.unpack('<I',b.upload(m['system_core_clock'],4,'system-clock.bin'))
    if clock!=400000000: raise ValueError('Clock differs from qualified profile')
    result=dict(passed=True,binary_sha256=sha(code),request_words=words,proof=p,context=context,card=card)
    if magic is not None: result['magic_format']=magic
    if op==1:
        result['whole_image']=frame_guards(b,m,p)
        if p['chunk_overflow'] or not 1 <= p['chunk_count'] <= 128:
            raise ValueError('Incomplete chunk trace')
        (a.out/'chunks.bin').write_bytes(b.upload(0x343FE000,p['chunk_count']*32,'chunks.bin'))
        if m.get('line_stream'):
            (a.out/'producer.bin').write_bytes(b.upload(m['producer'],416,'producer.bin'))
        if m.get('line_snapshots'):
            (a.out/'snapshots.bin').write_bytes(b.upload(0x343D0000,10240,'snapshots.bin'))
        if m.get('dma_sleep'):
            raw,stats=dma_wait_snapshot(b,m)
            (a.out/'dma-wait.bin').write_bytes(raw);result['dma_wait']=stats
        if a.download_frame:
            frame=b''.join(b.upload(m['frame']+off,min(READ_MAX,FRAME_BYTES-off),f'frame-{off:08x}.bin') for off in range(0,FRAME_BYTES,READ_MAX))
            (a.out/'frame.bin').write_bytes(frame); result['frame_sha256']=sha(frame)
    elif op==3:
        raw=b.upload(READ_BUFFER,p['read_bytes'],'sectors.bin')
        (a.out/'sectors.bin').write_bytes(raw); result['read_sha256']=sha(raw)
    if decode(b.upload(PROOF,384,'final-proof.bin'),names)!=p: raise ValueError('Terminal record changed')
    dump(a.out/'verified.json',result)
    print(json.dumps(result),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('operation',choices=OPS)
    p.add_argument('--build',type=Path,required=True); p.add_argument('--expected-sha',required=True)
    p.add_argument('--out',type=Path,required=True); p.add_argument('--prior',type=Path)
    p.add_argument('--bridge-proof',type=Path)
    p.add_argument('--recovery-build',type=Path,default=ROOT/'tmp/bringup/sd-normal-20261024/v66c-normal-standby/staged')
    p.add_argument('--execute',action='store_true'); p.add_argument('--download-frame',action='store_true')
    p.add_argument('--generation',type=lambda x:int(x,0)); p.add_argument('--slot-limit',type=int,default=0)
    p.add_argument('--lba',type=int,default=0); p.add_argument('--count',type=int,default=1)
    a=p.parse_args()
    if a.prior and a.bridge_proof: p.error('Select one initial-state proof')
    if a.generation is not None and not 0<a.generation<2**64: p.error('Generation must be nonzero64bits')
    run(a)


if __name__=='__main__': main()
