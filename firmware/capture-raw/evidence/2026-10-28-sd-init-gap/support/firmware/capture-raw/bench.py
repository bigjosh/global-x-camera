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
    width_layout(m)
    gpio_layout(m)
    compensation_layout(m)
    diagnostic_layout(m)
    return m, code


def startup_flash_profile(m):
    """Narrow flash admission after separate RAM source/readback tests."""
    true_keys=('flash','sd_startup_opt','sd_review_profile','sd_clock_negedge','sd_clock_negedge_init',
               'magic_format','line_stream','async_stop')
    false_keys=('sd_high_speed','sd_fixed_compensation','sd_compensation_modified','sd_high_speed_mixed_slew',
                'sd_high_speed_fixed_compensation','sd_high_speed_combined_electrical','sd_idma_read',
                'raw_dma_tail_wait','dma_sleep','preinit','line_snapshots','line_poison','whole_image_preerase',
                'sd_early_run_clock','sd_read_diagnostics')
    return (all(m.get(k) is True for k in true_keys) and
            all(m.get(k,False) is False for k in false_keys) and
            m.get('sd_clock_hz') in (12500000,25000000) and m.get('sd_bus_width')==4 and m.get('sd_gpio_speed')==3 and
            m.get('transport')=='idma' and m.get('pattern')==0 and m.get('exposure_coarse')==1428 and
            not m.get('cycle_trace') and m.get('sd_clk_gpio_speed') is None)


def diagnostic_layout(m,operation=None):
    """Bind the separate RAM-only receive and capture-tail experiments."""
    board_eth_layout(m,operation)
    sd_init_gap_layout(m,operation)
    power_probe_layout(m,operation)
    clk_gpio_layout(m,operation)
    read_diagnostics_layout(m,operation)
    for key,macro in (('sd_idma_read','SD_IDMA_READ'),('raw_dma_tail_wait','RAW_DMA_TAIL_WAIT'),
                      ('sd_startup_opt','SD_STARTUP_OPT'),('sd_early_run_clock','SD_EARLY_RUN_CLOCK')):
        value=m.get(key,False)
        selected=[f for f in m.get('flags',[]) if f.startswith('-D'+macro+'=')]
        if type(value) is not bool or ((key in m or selected) and selected!=[f'-D{macro}={int(value)}']):
            raise ValueError('Diagnostic manifest/compiler flag differs')
        if value and (m.get('flash') or m.get('standby')) and not (key=='sd_startup_opt' and startup_flash_profile(m)):
            raise ValueError('Diagnostic requires RAM awake profile')
    if m.get('sd_idma_read') and (not m.get('sd_review_profile') or m.get('raw_dma_tail_wait') or
            operation is not None and operation!=3):
        raise ValueError('IDMA receive is a reviewed read-only diagnostic')
    if m.get('sd_startup_opt'):
        if not m.get('sd_review_profile') or m.get('sd_bus_width')!=4 or operation==2:
            raise ValueError('Startup optimization requires reviewed four-bit capture/read')
        address=m.get('sd_startup_proof')
        if (type(address) is not int or address%4 or m.get('sd_startup_proof_bytes')!=64 or
                not m['bss_start']<=address<=m['bss_end']-64):
            raise ValueError('Startup proof bounds differ')
        for key,size in (('card',200),('slots',640),('producer',416),('magic_slots',576),('sd_stream',44),
                         ('raw_dma_tail_wait_proof',64),('sd_high_speed_proof',184),('sd_clock_profile_proof',128),
                         ('sd_early_clock_proof',64)):
            other=m.get(key)
            if other is not None and address<other+size and other<address+64:
                raise ValueError('Startup proof overlaps another owner')
    elif m.get('sd_startup_proof') is not None or m.get('sd_startup_proof_bytes',0):
        raise ValueError('Unexpected startup telemetry')
    if m.get('raw_dma_tail_wait'):
        if (not m.get('magic_format') or not m.get('line_stream') or not m.get('async_stop') or
                m.get('transport')!='idma' or m.get('dma_sleep') or
                operation is not None and operation!=1):
            raise ValueError('DMA tail wait requires a RAM magic LINE/IDMA capture')
        address=m.get('raw_dma_tail_wait_proof')
        if (type(address) is not int or address%4 or m.get('raw_dma_tail_wait_proof_bytes')!=64 or
                not m['bss_start']<=address<=m['bss_end']-64):
            raise ValueError('DMA tail wait proof bounds differ')
        for key,size in (('card',200),('slots',640),('producer',416),('magic_slots',576),('sd_stream',44)):
            other=m.get(key)
            if other is not None and address<other+size and other<address+64:
                raise ValueError('DMA tail wait proof overlaps another owner')
    elif m.get('raw_dma_tail_wait_proof') is not None or m.get('raw_dma_tail_wait_proof_bytes',0):
        raise ValueError('Unexpected DMA tail wait telemetry')
    if m.get('sd_early_run_clock'):
        true_keys=('sd_review_profile','sd_startup_opt','sd_clock_negedge','sd_clock_negedge_init',
                   'magic_format','line_stream','async_stop')
        false_keys=('flash','standby','sd_high_speed','sd_fixed_compensation','sd_compensation_modified',
                    'sd_high_speed_mixed_slew','sd_high_speed_fixed_compensation','sd_high_speed_combined_electrical',
                    'sd_idma_read','raw_dma_tail_wait','dma_sleep','preinit','line_snapshots','line_poison','whole_image_preerase')
        if (not all(m.get(k) is True for k in true_keys) or not all(m.get(k,False) is False for k in false_keys) or
                m.get('sd_clock_hz')!=12500000 or m.get('sd_bus_width')!=4 or m.get('sd_gpio_speed')!=3 or
                m.get('transport')!='idma' or m.get('pattern')!=0 or m.get('exposure_coarse')!=1428 or
                operation not in (None,1,3)):
            raise ValueError('Early run clock requires the exact reviewed startup 12.5 MHz no-tail RAM scene profile')
        address=m.get('sd_early_clock_proof')
        if (type(address) is not int or address%4 or m.get('sd_early_clock_proof_bytes')!=64 or
                not m['bss_start']<=address<=m['bss_end']-64):
            raise ValueError('Early clock proof bounds differ')
        for key,size in (('card',200),('slots',640),('producer',416),('magic_slots',576),('magic_proof',32),
                         ('sd_stream',44),('sd_scr',16),('sd_erase',32),('sd_width_proof',24),
                         ('sd_startup_proof',64),('raw_dma_tail_wait_proof',64),
                         ('sd_high_speed_proof',184),('sd_clock_profile_proof',128)):
            other=m.get(key)
            if other is not None and address<other+size and other<address+64:
                raise ValueError('Early clock proof overlaps another owner')
    elif m.get('sd_early_clock_proof') is not None or m.get('sd_early_clock_proof_bytes',0):
        raise ValueError('Unexpected early clock telemetry')


def early_clock_snapshot(b,m,label,operation,card):
    """Retain the CSD-to-CMD7 clock transition; this is not an idle proof."""
    diagnostic_layout(m,operation)
    if not m.get('sd_early_run_clock'):return None
    raw=b.upload(m['sd_early_clock_proof'],64,label+'-sd-early-clock.bin')
    if len(raw)!=64:raise ValueError('Incomplete early clock proof')
    names=('magic version requested_hz csd_tran_speed csd_max_hz csd_command_count '
           'switch_command_count select_command_count clock_before clock_after timer_before timer_after '
           'switch_begin_cycles switch_end_cycles select_begin_cycles result').split()
    p=dict(zip(names,struct.unpack('<16I',raw)))
    rate=p['csd_tran_speed'];units=(100000,1000000,10000000,100000000)
    multipliers=(0,10,12,13,15,20,25,30,35,40,45,50,55,60,70,80)
    if rate>0x7f or (rate&7)>3 or not multipliers[(rate>>3)&15]:
        raise ValueError('Reserved CSD transfer speed encoding')
    max_hz=units[rate&7]*multipliers[(rate>>3)&15]//10
    if ((p['magic'],p['version'],p['requested_hz'])!=(0x314B4345,1,12500000) or
            rate!=(card['csd0']&255) or p['csd_max_hz']!=max_hz or max_hz<p['requested_hz'] or
            not 0<p['csd_command_count']==p['switch_command_count'] or
            p['select_command_count']!=p['switch_command_count']+1 or
            p['clock_before']!=(0x30000|750) or p['clock_after']!=(0x30000|6) or
            p['timer_before']!=200000 or p['timer_after']!=25000000 or p['result'] or
            (p['switch_end_cycles']-p['switch_begin_cycles'])&0xffffffff>=0x80000000 or
            (p['select_begin_cycles']-p['switch_end_cycles'])&0xffffffff>=0x80000000):
        raise ValueError('Early run clock/CSD/timer/order proof differs')
    p['switch_cycles']=(p['switch_end_cycles']-p['switch_begin_cycles'])&0xffffffff
    return p


def dma_tail_snapshot(b,m,label,stream):
    diagnostic_layout(m,1)
    names=('magic version outcome start end elapsed limit available_before available_after polls '
           'result frame_before stopped_before reserved0 reserved1 reserved2').split()
    raw=b.upload(m['raw_dma_tail_wait_proof'],64,label+'-dma-tail-wait.bin')
    if len(raw)!=64:raise ValueError('Incomplete DMA tail wait proof')
    p=dict(zip(names,struct.unpack('<16I',raw)))
    if ((p['magic'],p['version'],p['limit'])!=(0x31575444,1,4000000) or
            p['result'] or any(p[k] for k in ('reserved0','reserved1','reserved2')) or
            p['outcome'] not in (1,2,3,4,5) or p['frame_before'] not in (0,1) or
            p['stopped_before'] not in (0,1) or
            p['elapsed']!=(p['end']-p['start'])&0xffffffff or
            not 512<=p['available_before']<=p['available_after']<=SLOT_BYTES or
            p['available_before']%512 or p['available_after']%512):
        raise ValueError('DMA tail wait proof is inconsistent')
    outcome=p['outcome']
    if outcome in (1,2,3):
        if p['polls'] or p['elapsed'] or p['available_before']!=p['available_after']:
            raise ValueError('Skipped DMA tail wait changed publication')
        if ((outcome==1 and (p['available_before']!=SLOT_BYTES or
                            p['frame_before']!=1 or p['stopped_before']!=1)) or
                (outcome==2 and (p['frame_before'] or p['available_before']==SLOT_BYTES)) or
                (outcome==3 and (not p['frame_before'] or p['available_before']>=SLOT_BYTES-512))):
            raise ValueError('DMA tail wait skip reason differs')
    else:
        if p['frame_before']!=1 or p['available_before']!=SLOT_BYTES-512:
            raise ValueError('DMA tail wait lacked validated near-complete frame')
        if outcome==4 and (not p['polls'] or p['available_after']!=SLOT_BYTES):
            raise ValueError('DMA tail wait completion lacks full publication')
        if outcome==5 and (p['elapsed']<p['limit'] or p['available_after']==SLOT_BYTES):
            raise ValueError('DMA tail wait timeout did not retain PIO prefix')
    # The transport calls publication again, so a timeout may subsequently
    # become IDMA; a successful/full wait must always choose complete IDMA.
    if outcome in (1,4) and stream['mode']!=1:
        raise ValueError('Complete DMA tail wait did not select IDMA')
    if stream['initial_available_bytes']<p['available_after']:
        raise ValueError('DMA publication regressed after tail wait')
    return p


def startup_snapshot(b,m,label,operation):
    diagnostic_layout(m,operation)
    if not m.get('sd_startup_opt'):return None
    raw=b.upload(m['sd_startup_proof'],64,label+'-sd-startup.bin')
    if len(raw)!=64:raise ValueError('Incomplete startup proof')
    names=('magic version gpio_settle_cycles train_cycles train_hz train_min_cycles run_settle_cycles '
           'run_hz scr_reads scr_hits scr_valid cache_owner result reserved0 reserved1 reserved2').split()
    p=dict(zip(names,struct.unpack('<16I',raw)))
    if ((p['magic'],p['version'],p['train_hz'],p['train_min_cycles'])!=(0x31504F53,1,100000,400000) or
            p['gpio_settle_cycles']<400000 or p['train_cycles']<400000 or p['run_settle_cycles']<400 or
            p['run_hz']!=(25000000 if m.get('sd_high_speed') else clock_layout(m)) or
            p['scr_reads']!=1 or p['scr_hits']!=int(operation==1 and bool(m.get('magic_format'))) or
            any(p[k] for k in ('scr_valid','cache_owner','result','reserved0','reserved1','reserved2'))):
        raise ValueError('Startup timing/cache proof differs')
    return p


def clock_layout(m):
    """Bind the compile-time SD frequency; frozen old builds are 25 MHz."""
    hz=m.get('sd_clock_hz',25000000)
    if type(hz) is not int or hz not in (12500000,25000000,50000000):
        raise ValueError('Unsupported native SD clock')
    flags=[f for f in m.get('flags',[]) if f.startswith('-DRAW_SD_CLOCK_HZ=')]
    if 'sd_clock_hz' in m or flags:
        if flags!=[f'-DRAW_SD_CLOCK_HZ={hz}U']:
            raise ValueError('SD clock manifest/compiler flag differs')
    review=m.get('sd_review_profile',False);high=m.get('sd_high_speed',False)
    mixed=m.get('sd_high_speed_mixed_slew',False)
    high_fixed=m.get('sd_high_speed_fixed_compensation',False)
    combined=m.get('sd_high_speed_combined_electrical',False)
    for key,value,macro in (('sd_review_profile',review,'SD_REVIEW_PROFILE'),('sd_high_speed',high,'SD_HIGH_SPEED'),
            ('sd_high_speed_mixed_slew',mixed,'SD_HIGH_SPEED_MIXED_SLEW'),
            ('sd_high_speed_fixed_compensation',high_fixed,'SD_HIGH_SPEED_FIXED_COMPENSATION'),
            ('sd_high_speed_combined_electrical',combined,'SD_HIGH_SPEED_COMBINED_ELECTRICAL')):
        if type(value) is not bool:raise ValueError('Invalid reviewed SD profile flag')
        selected=[f for f in m.get('flags',[]) if f.startswith('-D'+macro+'=')]
        if (key in m or selected) and selected!=[f'-D{macro}={int(value)}']:
            raise ValueError('Reviewed SD manifest/compiler flag differs')
    if combined and (not mixed or not high_fixed):
        raise ValueError('Combined electrical trial requires both explicit High Speed experiments')
    if high_fixed and (not high or (mixed and not combined) or m.get('flash') or m.get('standby')):
        raise ValueError('High Speed fixed compensation requires isolated uniform-slew RAM50')
    if mixed and (not high or m.get('flash') or m.get('standby')):
        raise ValueError('Mixed High Speed slew is a RAM50 diagnostic only')
    if mixed or 'sd_high_speed_gpio_values' in m:
        values=dict(c=0x10 if mixed else 0xFF3,e=0 if mixed else 0x300) if high else None
        if m.get('sd_high_speed_gpio_values')!=values:raise ValueError('High Speed GPIO pin values differ')
    if high!=(hz==50000000):raise ValueError('50 MHz requires explicit High Speed protocol')
    if high and (not review or m.get('sd_clock_negedge_init') is not True or
            m.get('sd_clock_negedge') is not True or m.get('sd_bus_width')!=4 or
            m.get('sd_gpio_speed')!=3 or m.get('sd_fixed_compensation') is not high_fixed):
        raise ValueError('Unreviewed 50 MHz electrical/protocol profile')
    if m.get('sd_kernel_hz',150000000)!=(100000000 if high else 150000000):
        raise ValueError('SD kernel clock differs from reviewed topology')
    if high and (m.get('sd_identification_clock_negedge') is not True or
            m.get('sd_transfer_clock_negedge') is not False or m.get('sd_switch_clock_hz')!=25000000):
        raise ValueError('High Speed launch-phase transition differs')
    return hz


def width_layout(m):
    clock_layout(m)
    phase_layout(m)
    width=m.get('sd_bus_width',1)
    if type(width) is not int or width not in (1,4):
        raise ValueError('Unsupported native SD width')
    if width==4:
        address=m.get('sd_width_proof')
        if (type(address) is not int or m.get('sd_width_proof_bytes')!=24 or
                not m['bss_start']<=address<=m['bss_end']-24 or
                '-DSD_BUS_WIDTH=4' not in m.get('flags',[])):
            raise ValueError('Four-bit width proof layout/build differs')
    elif m.get('sd_width_proof') is not None or m.get('sd_width_proof_bytes',0):
        raise ValueError('Unexpected width telemetry in one-bit build')
    if m.get('sd_high_speed'):
        for key,size in (('sd_high_speed_proof',184),('sd_clock_profile_proof',128)):
            address=m.get(key)
            if type(address) is not int or m.get(key+'_bytes')!=size or not m['bss_start']<=address<=m['bss_end']-size:
                raise ValueError('High Speed proof bounds differ')


def width_snapshot(b,m,label):
    width_layout(m)
    if m.get('sd_bus_width',1)==1:
        return None
    raw=b.upload(m['sd_width_proof'],24,label+'-sd-width.bin')
    names=('requested_width','scr_widths','acmd6_r1','acmd6_accepted',
           'configured_clkcr','negotiated_width')
    proof=dict(zip(names,struct.unpack('<6I',raw)))
    if (proof['requested_width']!=4 or proof['scr_widths']&5!=5 or
            proof['acmd6_r1']&0xFDFFE008 or not proof['acmd6_r1']&0x20 or
            proof['acmd6_accepted']!=1 or
            proof['configured_clkcr']!=(m.get('sd_kernel_hz',150000000)//(2*clock_layout(m))|0x24000|phase_layout(m)) or
            proof['negotiated_width']!=4):
        raise ValueError('Four-bit negotiation proof incomplete or inconsistent')
    if m.get('sd_high_speed'):proof['high_speed']=high_speed_snapshot(b,m,label)
    return proof


def high_speed_snapshot(b,m,label):
    raw=b.upload(m['sd_high_speed_proof'],184,label+'-sd-high-speed.bin')
    names=('requested_hz kernel_hz check_done switch_done check_r1 switch_r1 check_sta switch_sta '
           'configured_clkcr qualified gpio_c_before gpio_c_after gpio_e_before gpio_e_after').split()
    proof=dict(zip(names,struct.unpack('<14I',raw[:56])))
    if (proof['requested_hz'],proof['kernel_hz'],proof['check_done'],proof['switch_done'],proof['qualified'])!=(50000000,100000000,1,1,1):
        raise ValueError('Incomplete High Speed negotiation')
    if proof['configured_clkcr']!=(0x24001|phase_layout(m)):
        raise ValueError('High Speed receive/transmit/divider differs')
    for name,offset in (('check_status',56),('switch_status',120)):
        data=raw[offset:offset+64];current=int.from_bytes(data[:2],'big')
        if not 0<current<=200 or data[17]>1 or not data[13]&2 or data[16]&15!=1 or data[17]==1 and data[29]&2:
            raise ValueError('Invalid High Speed switch-function status')
        if any((v&15)==15 or v>>4==15 for v in data[14:17]):
            raise ValueError('A switch-function group canceled selection')
        proof[name]=data.hex()
    for name in ('check_r1','switch_r1'):
        if proof[name]&0xFDFFE008:raise ValueError('High Speed command reported card error')
    for name in ('check_sta','switch_sta'):
        if not proof[name]&0x100 or proof[name]&0x103A:raise ValueError('High Speed status data not CRC-clean/inactive')
    for bank,mask in (('c',0xFF3),('e',0x300)):
        before=proof[f'gpio_{bank}_before'];after=proof[f'gpio_{bank}_after']
        wanted=(0x10 if bank=='c' else 0) if m.get('sd_high_speed_mixed_slew') else mask
        if after&mask!=wanted or (before^after)&~mask:raise ValueError('High Speed GPIO profile differs')
    clockraw=b.upload(m['sd_clock_profile_proof'],128,label+'-sd-clock-profile.bin')
    fields=('magic version state result owned stage enable_polls disable_polls cr sr cfgr1 cfgr2 hsicfgr '
            'pll1cfgr1 pll1cfgr2 pll1cfgr3 ic1cfgr ic2cfgr ic5_before divenr_before ccipr5_before '
            'ccipr7_before ccipr8_before ahb5_before ic5_after divenr_after ccipr8_after ahb5_after '
            'kernel_hz cleanup_error reserved0 reserved1').split()
    clock=dict(zip(fields,struct.unpack('<32I',clockraw)))
    if (clock['magic'],clock['version'],clock['state'],clock['result'],clock['owned'],clock['kernel_hz'],clock['cleanup_error'])!=(0x5344434B,1,5,0,0,100000000,0):
        raise ValueError('Clock profile was not successfully restored')
    if (clock['ic5_after']!=clock['ic5_before'] or clock['divenr_after']!=clock['divenr_before'] or
            clock['ccipr8_after']!=clock['ccipr8_before'] or clock['ahb5_after']!=clock['ahb5_before']):
        raise ValueError('Clock profile restoration changed unrelated state')
    proof['clock_profile']=clock
    return proof


def phase_layout(m):
    """Bind explicit launch phase; flash allows only speed3/default compensation."""
    enabled=m.get('sd_clock_negedge',False)
    if type(enabled) is not bool:
        raise ValueError('Unsupported SD clock phase selection')
    flags=[f for f in m.get('flags',[]) if f.startswith('-DSD_CLOCK_NEGEDGE=')]
    if 'sd_clock_negedge' in m or flags:
        if flags!=[f'-DSD_CLOCK_NEGEDGE={int(enabled)}']:
            raise ValueError('Clock phase manifest/compiler flag differs')
    initial=m.get('sd_clock_negedge_init',False)
    if type(initial) is not bool:
        raise ValueError('Unsupported initial SD clock phase selection')
    initial_flags=[f for f in m.get('flags',[]) if f.startswith('-DSD_CLOCK_NEGEDGE_INIT=')]
    if 'sd_clock_negedge_init' in m or initial_flags:
        if initial_flags!=[f'-DSD_CLOCK_NEGEDGE_INIT={int(initial)}']:
            raise ValueError('Initial clock phase manifest/compiler flag differs')
    speed=m.get('sd_gpio_speed',3)
    high_fixed=m.get('sd_high_speed_fixed_compensation',False)
    if initial and (not enabled or speed!=3):
        raise ValueError('Initial clock phase requires falling-edge run phase and speed3')
    if enabled and clock_layout(m)==12500000 and not initial:
        raise ValueError('12.5 MHz clock phase requires explicit falling-edge identification')
    if enabled and (m.get('sd_bus_width',1)!=4 or type(speed) is not int or speed not in (1,2,3) or
            clock_layout(m)==12500000 and speed!=3 or
            m.get('sd_fixed_compensation',False) is not high_fixed or
            m.get('sd_compensation_modified',False) is not high_fixed):
        raise ValueError('Clock phase requires four-bit mode without compensation changes; 12.5 MHz requires speed3')
    if enabled and ((m.get('flash') or m.get('standby')) and speed!=3 or
            m.get('standby') and not m.get('flash')):
        raise ValueError('Flash clock phase requires speed3; Standby requires flash')
    return 0 if m.get('sd_high_speed') else (0x10000 if enabled else 0)


def gpio_layout(m):
    speed=m.get('sd_gpio_speed',3)
    if type(speed) is not int or speed not in (0,1,2,3):
        raise ValueError('Unsupported SD GPIO speed')
    flags=[f for f in m.get('flags',[]) if f.startswith('-DSD_GPIO_SPEED=')]
    if 'sd_gpio_speed' in m or flags:
        if flags!=[f'-DSD_GPIO_SPEED={speed}']:
            raise ValueError('GPIO speed manifest/compiler flag differs')
        masks=dict(c=0xFF3 if m.get('sd_bus_width',1)==4 else 0x3F0,
                   e=0x300 if m.get('sd_bus_width',1)==4 else 0)
        comp=m.get('sd_fixed_compensation',False)
        if (type(comp) is not bool or (comp and speed!=3) or m.get('sd_gpio_masks')!=masks or
                m.get('sd_compensation_modified') is not comp):
            raise ValueError('GPIO speed experiment mask/compensation scope differs')
    if speed in (1,2) and (clock_layout(m)!=25000000 or m.get('sd_bus_width',1)!=4 or
            m.get('sd_fixed_compensation',False) is not False or
            m.get('sd_compensation_modified',False) is not False):
        raise ValueError('Intermediate GPIO speed must be an isolated 25 MHz four-bit diagnostic')
    if speed!=3:
        address=m.get('sd_gpio_proof')
        if (m.get('flash') or m.get('standby') or type(address) is not int or
                m.get('sd_gpio_proof_bytes')!=32 or
                not m['bss_start']<=address<=m['bss_end']-32):
            raise ValueError('GPIO speed diagnostic layout/build differs')
    elif m.get('sd_gpio_proof') is not None or m.get('sd_gpio_proof_bytes',0):
        raise ValueError('Unexpected GPIO speed telemetry in default build')
    return speed


def gpio_snapshot(b,m,label):
    speed=gpio_layout(m)
    if speed==3:
        return None
    raw=b.upload(m['sd_gpio_proof'],32,label+'-sd-gpio.bin')
    if len(raw)!=32:raise ValueError('Incomplete GPIO speed telemetry')
    names=('requested_speed','c_mask','c_before','c_after','e_mask','e_before','e_after','applied')
    proof=dict(zip(names,struct.unpack('<8I',raw)))
    masks=m['sd_gpio_masks']
    if (proof['requested_speed']!=speed or proof['applied']!=1 or
            proof['c_mask']!=masks['c'] or proof['e_mask']!=masks['e'] or
            (proof['c_after']&masks['c'])!=masks['c']//3*speed or
            (proof['e_after']&masks['e'])!=masks['e']//3*speed or
            (proof['c_before']^proof['c_after'])&~masks['c'] or
            (proof['e_before']^proof['e_after'])&~masks['e']):
        raise ValueError('GPIO speed application proof incomplete or inconsistent')
    return proof


POWER_PROBE_FIELDS=('magic version mode state wait_begin camera_ready hold_begin hold_end '
    'gpio_mode gpio_odr_before gpio_idr_before gpio_odr_after gpio_idr_after faults preconditions hold_cycles').split()


def board_eth_layout(m,operation=None):
    """Optional board power saving has separate admission from RAM experiments."""
    enabled=m.get('board_eth_powerdown',False)
    selected=[f for f in m.get('flags',[]) if f.startswith('-DRAW_BOARD_ETH_POWERDOWN=')]
    if type(enabled) is not bool:
        raise ValueError('Board Ethernet selector type differs')
    if not enabled:
        if selected or m.get('board_eth_proof') is not None or m.get('board_eth_proof_bytes',0):
            raise ValueError('Unexpected board Ethernet feature or telemetry')
        return False
    if selected!=['-DRAW_BOARD_ETH_POWERDOWN=1']:
        raise ValueError('Board Ethernet manifest/compiler flag differs')
    true_keys=('sd_review_profile','sd_startup_opt','sd_clock_negedge','sd_clock_negedge_init',
               'magic_format','line_stream','async_stop')
    false_keys=('sd_high_speed','sd_fixed_compensation','sd_compensation_modified',
        'sd_high_speed_mixed_slew','sd_high_speed_fixed_compensation','sd_high_speed_combined_electrical',
        'sd_early_run_clock','sd_idma_read','sd_read_diagnostics','raw_dma_tail_wait','dma_sleep',
        'preinit','line_snapshots','line_poison','whole_image_preerase','error_test_code',
        'error_after_frame_test','power_probe','cycle_trace')
    flash=m.get('flash',False);standby=m.get('standby',False)
    if (type(flash) is not bool or type(standby) is not bool or standby and not flash or
        not all(m.get(k) is True for k in true_keys) or any(m.get(k,False) for k in false_keys) or
        m.get('sd_bus_width')!=4 or m.get('sd_clock_hz')!=25000000 or m.get('sd_gpio_speed')!=3 or
        m.get('sd_clk_gpio_speed') is not None or m.get('transport')!='idma' or m.get('pattern')!=0 or
        m.get('exposure_coarse')!=1428 or operation is not None and operation not in (1,3)):
        raise ValueError('Board Ethernet requires the reviewed startup 25 MHz capture/read profile')
    required=dict(RAW_FLASH=str(int(flash)),RAW_STANDBY=str(int(standby)),
        SD_REVIEW_PROFILE='1',SD_STARTUP_OPT='1',SD_BUS_WIDTH='4',RAW_SD_CLOCK_HZ='25000000U',
        SD_GPIO_SPEED='3',SD_CLOCK_NEGEDGE='1',SD_CLOCK_NEGEDGE_INIT='1',RAW_MAGIC_FORMAT='1',
        RAW_LINE_STREAM='1',RAW_ASYNC_STOP='1',RAW_DMA='1',RAW_PREINIT='0',RAW_LINE_SNAPSHOTS='0',
        RAW_LINE_POISON='0',RAW_WHOLE_IMAGE_PREERASE='0',RAW_DMA_SLEEP='0',RAW_DMA_TAIL_WAIT='0',
        SD_EARLY_RUN_CLOCK='0',SD_IDMA_READ='0',SD_FIXED_COMPENSATION='0',SD_HIGH_SPEED='0',
        RAW_PATTERN='0',RAW_EXPOSURE_COARSE='1428U')
    for key,value in required.items():
        if [f for f in m.get('flags',[]) if f.startswith('-D'+key+'=')]!=[f'-D{key}={value}']:
            raise ValueError('Board Ethernet profile compiler flag differs: '+key)
    address=m.get('board_eth_proof')
    if (type(address) is not int or address%32 or m.get('board_eth_proof_bytes')!=256 or
        not LOAD<=m['bss_start']<=address<=m['bss_end']-256 or
        m['bss_end']>m.get('stack_floor',0x343AF000)):
        raise ValueError('Board Ethernet telemetry bounds differ')
    for key,size in (('card',200),('slots',640),('producer',416),('magic_slots',576),('sd_scr',16),
            ('sd_stream',44),('magic_proof',32),('sd_startup_proof',64),('sd_width_proof',24),
            ('power_probe_proof',64),('power_phy_proof',256),('power_csi_proof',128),
            ('sd_init_gap_proof',64)):
        other=m.get(key)
        if other is not None and address<other+size and other<address+256:
            raise ValueError('Board Ethernet telemetry overlaps '+key)
    return True


def board_eth_snapshot(b,m,p,label):
    """An optional power warning never changes a successful image result."""
    if not board_eth_layout(m,p['operation']):return None
    raw=b.upload(m['board_eth_proof'],256,label+'-board-eth.bin')
    if len(raw)!=256:raise ValueError('Incomplete board Ethernet telemetry')
    w=list(struct.unpack('<64I',raw))
    if p['operation']==3:
        if any(w):raise ValueError('READ unexpectedly entered board Ethernet helper')
        return dict(words=w,attempted=False,qualified_powerdown=False,
            scope='READ does not change Ethernet; retained PHY power state is not inferred')
    if (w[0]!=0x31485445 or w[1]!=1 or w[2] not in (6,0xE1) or
        w[3]>9 or w[4]>9 or w[5]&~255 or w[15]>1 or w[16]>6 or
        w[30]>1 or w[31] or any(w[61:64])):
        raise ValueError('Malformed board Ethernet terminal telemetry')
    flags=w[5]
    if bool(flags&8)!=bool(w[15]) or flags&4 and w[15]:
        raise ValueError('Board Ethernet write-attempt flags differ')
    for at in (32,38,44,50):
        if any(w[at+i]>limit for i,limit in enumerate((3,1,3,3,15,1))):
            raise ValueError('Board Ethernet GPIO field out of range')
    if flags&1 and (w[8]!=7 or w[9]&0xFFF0!=0xC130):
        raise ValueError('Board Ethernet identity flag is unsupported')
    if flags&32 and (w[32:38]!=w[44:50] or w[38:44]!=w[50:56]):
        raise ValueError('Board Ethernet GPIO restoration flag differs')
    if flags&64 and w[17]!=w[18]:
        raise ValueError('Board Ethernet clock restoration flag differs')
    # The gap experiment intentionally moves SD initialization later. Bind its
    # complete separate proof instead of relaxing the normal 10 ms adjacency.
    gap=sd_init_gap_snapshot(b,m,p,label+'-eth-order') if m.get('sd_init_gap_ms',0) else None
    qualified=w[2]==6
    if qualified:
        already=bool(flags&4)
        wanted=w[10]|0x800
        if (w[3] or w[4] or flags!=(119 if already else 123) or
            w[8]!=7 or w[9]&0xFFF0!=0xC130 or w[10]!=w[11] or
            w[10]&~0x2900!=0x1000 or bool(w[10]&0x800)!=already or w[12]!=wanted or
            (w[13:15]!=[0,0] if already else w[13:15]!=[wanted,wanted]) or
            w[15]!=(0 if already else 1) or w[16]!=(4 if already else 6) or
            w[17]!=w[18] or w[19]&0x60 or w[20]!=(0x60&~w[17]) or w[21]!=1 or
            w[22:30]!=[0x33330000,0x100000,0x20000,0x404B00,0,0x49000005,400000000,2000] or
            # Cortex-M55 CONTROL FPCA/SFPA (bits 2/3) can be set by the
            # privileged camera path. Still require MSP, privilege and no
            # reserved bits; these FP context flags do not select PSP.
            w[30] or w[56] or w[57]&~0xC or not w[58]&1 or not w[59]&0x1000000 or w[60]&0x10000):
            raise ValueError('Board Ethernet power-down success proof differs')
        next_begin=gap['entry'] if gap is not None else p['sd_begin']
        if (not p['arm'] or not next_begin or
            (w[6]-p['arm'])&0xFFFFFFFF>400000000 or
            not 0<(w[7]-w[6])&0xFFFFFFFF<=400000000 or
            (next_begin-w[7])&0xFFFFFFFF>4000000):
            raise ValueError('Board Ethernet did not run after arm and before the next pre-SD stage')
    elif not (w[3] or w[4]):
        raise ValueError('Board Ethernet warning has no diagnostic error')
    return dict(words=w,attempted=True,qualified_powerdown=qualified,
        warning=None if qualified else dict(error=w[3],cleanup_error=w[4],flags=flags),
        already_powered_down=bool(flags&4),write_attempts=w[15],read_attempts=w[16],
        outcome_unknown=bool(flags&128),id1=w[8],id2=w[9],original_bmcr=w[10],
        requested_bmcr=w[12],gpio_restored=bool(flags&32),clock_restored=bool(flags&64),
        elapsed_ms=((w[7]-w[6])&0xFFFFFFFF)/400000,
        scope='Optional LAN8742 power-down after receiver arm; no PHY restore before shutdown. '
              'A warning preserves capture/save success but does not qualify a power saving.')


SD_INIT_GAP_FIELDS=('magic version state error entry frame_done stop_done gap_begin gap_end '
    'target_cycles commands_before commands_after frame_valid stopped clock_hz reserved').split()


def sd_init_gap_layout(m,operation=None):
    """One opt-in 200 ms separation diagnostic; legacy/default builds stay inert."""
    duration=m.get('sd_init_gap_ms',0)
    selected=[f for f in m.get('flags',[]) if f.startswith('-DRAW_SD_INIT_GAP_MS=')]
    if type(duration) is not int or duration not in (0,200):
        raise ValueError('SD initialization gap selector differs')
    if not duration:
        if selected or m.get('sd_init_gap_proof') is not None or m.get('sd_init_gap_proof_bytes',0):
            raise ValueError('Unexpected SD initialization gap feature or telemetry')
        return False
    if selected!=['-DRAW_SD_INIT_GAP_MS=200U'] or not board_eth_layout(m,operation):
        raise ValueError('SD initialization gap requires the exact Ethernet-down normal profile')
    events=m.get('phase_markers',{}).get('events',{})
    if events.get('11')!='sd_init_gap_begin' or events.get('12')!='sd_init_gap_end':
        raise ValueError('SD initialization gap marker declaration differs')
    address=m.get('sd_init_gap_proof')
    if (type(address) is not int or address%32 or m.get('sd_init_gap_proof_bytes')!=64 or
        not LOAD<=m['bss_start']<=address<=m['bss_end']-64 or
        m['bss_end']>m.get('stack_floor',0x343AF000)):
        raise ValueError('SD initialization gap telemetry bounds differ')
    for key,size in (('card',200),('slots',640),('producer',416),('magic_slots',576),('sd_scr',16),
            ('sd_stream',44),('magic_proof',32),('sd_startup_proof',64),('sd_width_proof',24),
            ('board_eth_proof',256),('power_probe_proof',64),('power_phy_proof',256),('power_csi_proof',128)):
        other=m.get(key)
        if other is not None and address<other+size and other<address+64:
            raise ValueError('SD initialization gap telemetry overlaps '+key)
    return True


def sd_init_gap_snapshot(b,m,p,label):
    if not sd_init_gap_layout(m,p['operation']):return None
    raw=b.upload(m['sd_init_gap_proof'],64,label+'-sd-init-gap.bin')
    if len(raw)!=64:raise ValueError('Incomplete SD initialization gap telemetry')
    values=struct.unpack('<16I',raw);g=dict(zip(SD_INIT_GAP_FIELDS,values))
    if p['operation']==3:
        if any(values):raise ValueError('READ unexpectedly entered SD initialization gap')
        return dict(attempted=False,completed=False,
            scope='READ bypasses the capture-only separation diagnostic')
    if ((g['magic'],g['version'],g['state'],g['error'],g['target_cycles'],g['clock_hz'])!=
            (0x31504147,1,3,0,80000000,400000000) or
            g['commands_before'] or g['commands_after'] or g['reserved'] or
            g['frame_valid']!=1 or g['stopped']!=1 or
            not p.get('arm') or not p.get('frame_done') or not p.get('camera_stop') or not p.get('sd_begin') or
            g['frame_done']!=p['frame_done'] or g['stop_done']!=p['camera_stop']):
        raise ValueError('SD initialization gap completion/preconditions differ')
    elapsed=lambda end,start:(end-start)&0xFFFFFFFF
    if (elapsed(g['entry'],p['arm'])>400000000 or
            elapsed(g['stop_done'],g['frame_done'])>1200000000 or
            elapsed(g['gap_begin'],g['entry'])>1200000000 or
            elapsed(g['gap_begin'],g['stop_done'])>4000000 or
            not 80000000<=elapsed(g['gap_end'],g['gap_begin'])<100000000 or
            elapsed(p['sd_begin'],g['gap_end'])>4000000):
        raise ValueError('SD initialization gap timing/order differs')
    g.update(attempted=True,completed=True,
        wait_for_stop_ms=elapsed(g['gap_begin'],g['entry'])/400000,
        elapsed_ms=elapsed(g['gap_end'],g['gap_begin'])/400000,
        scope='Validated FRAME and acknowledged STOP precede the 200 ms gap; zero SD commands before/after. '
              'Card is electrically powered: this separates firmware phases, not individual device rails.')
    return g


def power_probe_layout(m,operation=None):
    """Bind a RAM-only pre-SD hold experiment; never expands idle admission."""
    mode=m.get('power_probe')
    selected=[f for f in m.get('flags',[]) if f.startswith('-DRAW_POWER_PROBE=')]
    if mode is None:
        if (selected or m.get('power_probe_proof') is not None or m.get('power_probe_proof_bytes',0) or
            m.get('power_phy_proof') is not None or m.get('power_phy_proof_bytes',0) or
            m.get('power_csi_proof') is not None or m.get('power_csi_proof_bytes',0)):
            raise ValueError('Unexpected power-probe telemetry')
        return None
    modes={'hold-after-stop':1,'reset-after-stop':2,'ethernet-control':3,'ethernet-powerdown':4,'receiver-off':5}
    if mode not in modes or selected!=[f'-DRAW_POWER_PROBE={modes[mode]}']:
        raise ValueError('Power-probe mode/compiler flag differs')
    true_keys=('sd_review_profile','sd_startup_opt','sd_clock_negedge','sd_clock_negedge_init',
               'magic_format','line_stream','async_stop')
    false_keys=('flash','standby','sd_high_speed','sd_fixed_compensation','sd_compensation_modified',
        'sd_high_speed_mixed_slew','sd_high_speed_fixed_compensation','sd_high_speed_combined_electrical',
        'sd_early_run_clock','sd_idma_read','sd_read_diagnostics','raw_dma_tail_wait','dma_sleep',
        'preinit','line_snapshots','line_poison','whole_image_preerase','error_blinks','error_test_code','error_after_frame_test')
    if (not all(m.get(k) is True for k in true_keys) or any(m.get(k,False) for k in false_keys) or
        m.get('sd_bus_width')!=4 or m.get('sd_clock_hz')!=25000000 or m.get('sd_gpio_speed')!=3 or
        m.get('sd_clk_gpio_speed') is not None or m.get('transport')!='idma' or m.get('pattern')!=0 or
        m.get('exposure_coarse')!=1428 or operation is not None and operation!=1):
        raise ValueError('Power probe requires the reviewed startup 25 MHz RAM capture profile')
    required=dict(RAW_FLASH='0',RAW_STANDBY='0',SD_REVIEW_PROFILE='1',SD_STARTUP_OPT='1',
        SD_BUS_WIDTH='4',RAW_SD_CLOCK_HZ='25000000U',SD_GPIO_SPEED='3',SD_CLOCK_NEGEDGE='1',
        SD_CLOCK_NEGEDGE_INIT='1',RAW_MAGIC_FORMAT='1',RAW_LINE_STREAM='1',RAW_ASYNC_STOP='1',
        RAW_DMA='1',RAW_PREINIT='0',RAW_LINE_SNAPSHOTS='0',RAW_LINE_POISON='0',
        RAW_WHOLE_IMAGE_PREERASE='0',RAW_DMA_SLEEP='0',RAW_DMA_TAIL_WAIT='0',
        SD_EARLY_RUN_CLOCK='0',SD_IDMA_READ='0',SD_FIXED_COMPENSATION='0',SD_HIGH_SPEED='0',
        RAW_PATTERN='0',RAW_EXPOSURE_COARSE='1428U')
    for key,value in required.items():
        if [f for f in m.get('flags',[]) if f.startswith('-D'+key+'=')]!=[f'-D{key}={value}']:
            raise ValueError('Power-probe profile compiler flag differs: '+key)
    address=m.get('power_probe_proof')
    if (type(address) is not int or address%4 or m.get('power_probe_proof_bytes')!=64 or
        not m['bss_start']<=address<=m['bss_end']-64):
        raise ValueError('Power-probe telemetry bounds differ')
    for key,size in (('card',200),('slots',640),('producer',416),('magic_slots',576),('sd_scr',16),
                     ('sd_stream',44),('sd_startup_proof',64),('sd_width_proof',24)):
        other=m.get(key)
        if other is not None and address<other+size and other<address+64:
            raise ValueError('Power-probe telemetry overlaps '+key)
    events=m.get('phase_markers',{}).get('events',{})
    if events.get('11')!='power_probe_hold_begin' or events.get('12')!='power_probe_hold_end':
        raise ValueError('Power-probe marker declaration differs')
    phy_address=m.get('power_phy_proof')
    if modes[mode] not in (3,4):
        if phy_address is not None or m.get('power_phy_proof_bytes',0):
            raise ValueError('Unexpected Ethernet power telemetry')
    else:
        if (type(phy_address) is not int or phy_address%32 or m.get('power_phy_proof_bytes')!=256 or
            not m['bss_start']<=phy_address<=m['bss_end']-256):
            raise ValueError('Ethernet power telemetry bounds differ')
        for key,size in (('power_probe_proof',64),('card',200),('slots',640),('producer',416),
                ('magic_slots',576),('sd_scr',16),('sd_stream',44),('sd_startup_proof',64),('sd_width_proof',24)):
            other=m.get(key)
            if other is not None and phy_address<other+size and other<phy_address+256:
                raise ValueError('Ethernet power telemetry overlaps '+key)
    csi_address=m.get('power_csi_proof')
    if modes[mode]!=5:
        if csi_address is not None or m.get('power_csi_proof_bytes',0):
            raise ValueError('Unexpected receiver power telemetry')
    else:
        if (type(csi_address) is not int or csi_address%32 or m.get('power_csi_proof_bytes')!=128 or
            not m['bss_start']<=csi_address<=m['bss_end']-128):
            raise ValueError('Receiver power telemetry bounds differ')
        for key,size in (('power_probe_proof',64),('card',200),('slots',640),('producer',416),
                ('magic_slots',576),('sd_scr',16),('sd_stream',44),('sd_startup_proof',64),('sd_width_proof',24)):
            other=m.get(key)
            if other is not None and csi_address<other+size and other<csi_address+128:
                raise ValueError('Receiver power telemetry overlaps '+key)
    return modes[mode]


def power_probe_snapshot(b,m,p,label):
    mode=power_probe_layout(m,p['operation'])
    if mode is None:return None
    raw=b.upload(m['power_probe_proof'],64,label+'-power-probe.bin')
    if len(raw)!=64:raise ValueError('Incomplete power-probe telemetry')
    v=dict(zip(POWER_PROBE_FIELDS,struct.unpack('<16I',raw)))
    expected=0 if mode in (2,5) else 1<<5
    if (v['magic']!=0x31505750 or v['version']!=1 or v['mode']!=mode or v['state']!=3 or
        v['faults'] or v['preconditions']!=15 or v['hold_cycles']!=80000000 or
        (v['gpio_mode']&(3<<10))!=1<<10 or not v['gpio_odr_before']&(1<<5) or
        not v['gpio_idr_before']&(1<<5) or (v['gpio_odr_after']&(1<<5))!=expected or
        (v['gpio_idr_after']&(1<<5))!=expected or
        (v['gpio_odr_before']^v['gpio_odr_after'])&~(1<<5)):
        raise ValueError('Power-probe preconditions or GPIO result differ')
    elapsed=(v['hold_end']-v['hold_begin'])&0xffffffff
    if (not 80000000<=elapsed<=80400000 or
        (v['camera_ready']-v['wait_begin'])&0xffffffff>1200400000 or
        (v['hold_begin']-v['camera_ready'])&0xffffffff>(400000000 if mode>=3 else 4000000) or
        (p['sd_begin']-v['hold_end'])&0xffffffff>4000000):
        raise ValueError('Power-probe time bounds/order differ')
    for field in ('frame_done','camera_stop'):
        if not p[field] or (v['camera_ready']-p[field])&0xffffffff>1200400000:
            raise ValueError('Power hold preceded completed camera: '+field)
    v.update(hold_ms=elapsed/400000,scope='Stopped sensor, live receiver clocks, CPU busy hold; before SD initialization')
    return v


def power_phy_snapshot(b,m,p,label):
    mode=power_probe_layout(m,p['operation'])
    if mode not in (3,4):return None
    raw=b.upload(m['power_phy_proof'],256,label+'-power-phy.bin')
    if len(raw)!=256:raise ValueError('Incomplete Ethernet power telemetry')
    w=list(struct.unpack('<64I',raw))
    original=w[12];requested=original|(0x800 if mode==4 else 0)
    if (w[0]!=0x31594850 or w[1]!=1 or w[2]!=mode or w[3]!=6 or w[4] or w[5] or
        w[10]!=7 or w[11]&0xfff0!=0xc130 or original!=w[13] or original&~0x2100!=0x1000 or
        w[14]!=requested or w[15]!=requested or w[16]!=requested or w[17]!=requested or
        w[18]!=original or w[19]!=original or not 1<=w[20]<=100 or w[21] or w[22] or w[23]!=2 or
        w[24]!=w[25] or w[26]&0x60 or w[27]!=w[28] or w[29]&0x60 or
        w[30]!=1 or w[31]!=1 or w[32:38]!=w[44:50] or w[38:44]!=w[50:56] or
        w[56]!=1 or w[57]!=w[10] or w[58]!=w[11] or w[59]!=3 or
        w[60]!=400000000 or w[61]!=2000 or w[62] or w[63]):
        raise ValueError('Ethernet identity, mutation or restoration proof differs')
    for at in (32,38,44,50):
        limits=(3,1,3,3,15,1)
        if any(w[at+i]>limit for i,limit in enumerate(limits)):
            raise ValueError('Ethernet GPIO proof field out of range')
    if ((w[7]-w[6])&0xffffffff>400000000 or
        (w[9]-w[8])&0xffffffff>400000000 or
        not p['deinit_done'] or (w[8]-p['deinit_done'])&0xffffffff>4000000):
        raise ValueError('Ethernet probe sequence timing differs')
    return dict(words=w,mode=mode,phy_address=0,id1=w[10],id2=w[11],original_bmcr=original,
        requested_bmcr=requested,restored_bmcr=w[19],gpio_restored=True,
        begin_ms=((w[7]-w[6])&0xffffffff)/400000,
        restore_ms=((w[9]-w[8])&0xffffffff)/400000,
        scope='LAN8742 BMCR power-down through hold/save; exact original BMCR and pins restored after SD deinit; other PHY registers not qualified')


def power_csi_snapshot(b,m,p,label):
    mode=power_probe_layout(m,p['operation'])
    if mode!=5:return None
    raw=b.upload(m['power_csi_proof'],128,label+'-power-csi.bin')
    if len(raw)!=128:raise ValueError('Incomplete receiver power telemetry')
    w=list(struct.unpack('<32I',raw))
    if (w[0]!=0x31595043 or w[1]!=1 or w[2]!=2 or w[3] or
        w[6]&0x44!=0x44 or w[7]&0x44 or w[8]&0x30000!=0x30000 or
        not w[9]&1 or not w[10]&2 or w[11]!=3 or w[12]&0x1e0000 or w[14]&0x80808000 or
        any(w[i]&8 for i in (15,17,19)) or any(w[i]&0x80000000 for i in (16,18,20)) or
        w[21]!=(w[9]&~1) or w[22]!=(w[10]&~2) or w[23] or
        w[24]!=w[6] or w[25]!=w[7] or w[26]!=w[8] or w[29] or w[30] or w[31]):
        raise ValueError('Receiver idle, power-off or retained-clock proof differs')
    if ((w[5]-w[4])&0xffffffff>4000000 or not p['camera_stop'] or
        (w[4]-p['camera_stop'])&0xffffffff>4000000):
        raise ValueError('Receiver power-off did not follow bounded completed STOP')
    return dict(words=w,receiver_off=True,apb_and_kernel_clocks_retained=True,
        mutation_us=((w[5]-w[4])&0xffffffff)/400,
        scope='Sensor held reset; CSI/PHY disabled and camera IRQs masked after idle checks; APB/kernel clocks retained')


READ_DIAGNOSTIC_FIELDS=('magic version mode lba count destination requested_bytes words sta dcount '
                        'fifo_flags idmactrl dctrl clkcr captured result').split()


def read_diagnostics_layout(m,operation=None):
    """Bind a single-sector receive observation; never an idle/success gate."""
    enabled=m.get('sd_read_diagnostics',False)
    selected=[f for f in m.get('flags',[]) if f.startswith('-DSD_READ_DIAGNOSTICS=')]
    if type(enabled) is not bool:
        raise ValueError('Receive diagnostic selector type differs')
    if not enabled:
        if (selected or m.get('sd_read_diagnostics_proof') is not None or m.get('sd_read_diagnostics_proof_bytes',0) or
                m.get('raw_read_camera_proof') is not None or m.get('raw_read_camera_proof_bytes',0)):
            raise ValueError('Unexpected receive diagnostics')
        return False
    true_keys=('sd_review_profile','sd_startup_opt','sd_clock_negedge','sd_clock_negedge_init',
               'magic_format','line_stream','async_stop')
    false_keys=('flash','standby','sd_high_speed','sd_fixed_compensation','sd_compensation_modified',
                'sd_high_speed_mixed_slew','sd_high_speed_fixed_compensation','sd_high_speed_combined_electrical',
                'sd_early_run_clock','raw_dma_tail_wait','dma_sleep','preinit','line_snapshots',
                'line_poison','whole_image_preerase','error_blinks','error_after_frame_test')
    if (selected!=['-DSD_READ_DIAGNOSTICS=1'] or
            not all(m.get(k) is True for k in true_keys) or
            not all(m.get(k,False) is False for k in false_keys) or
            m.get('sd_clock_hz') not in (12500000,25000000) or m.get('sd_bus_width')!=4 or
            m.get('sd_gpio_speed')!=3 or m.get('sd_clk_gpio_speed') is not None or
            m.get('transport')!='idma' or m.get('pattern')!=0 or m.get('exposure_coarse')!=1428 or
            m.get('error_test_code',0) or type(m.get('sd_idma_read')) is not bool or
            operation not in (None,3)):
        raise ValueError('Receive diagnostics require the exact single-sector RAM READ profile')
    expected=dict(SD_READ_DIAGNOSTICS='1',SD_REVIEW_PROFILE='1',SD_STARTUP_OPT='1',
        SD_CLOCK_NEGEDGE='1',SD_CLOCK_NEGEDGE_INIT='1',SD_BUS_WIDTH='4',SD_GPIO_SPEED='3',
        RAW_SD_CLOCK_HZ=str(m['sd_clock_hz'])+'U',SD_IDMA_READ=str(int(m['sd_idma_read'])),
        RAW_FLASH='0',RAW_STANDBY='0',SD_FIXED_COMPENSATION='0',SD_HIGH_SPEED='0',
        SD_HIGH_SPEED_MIXED_SLEW='0',SD_HIGH_SPEED_FIXED_COMPENSATION='0',
        SD_HIGH_SPEED_COMBINED_ELECTRICAL='0',SD_EARLY_RUN_CLOCK='0',RAW_DMA_TAIL_WAIT='0',
        RAW_DMA_SLEEP='0',RAW_MAGIC_FORMAT='1',RAW_LINE_STREAM='1',RAW_ASYNC_STOP='1',RAW_DMA='1',
        RAW_PREINIT='0',RAW_LINE_SNAPSHOTS='0',RAW_LINE_POISON='0',RAW_WHOLE_IMAGE_PREERASE='0',
        RAW_PATTERN='0',RAW_EXPOSURE_COARSE='1428U')
    for macro,value in expected.items():
        flags=[f for f in m.get('flags',[]) if f.startswith('-D'+macro+'=')]
        if flags!=['-D'+macro+'='+value]:
            raise ValueError('Receive diagnostic compiler flag differs: '+macro)
    if any(f.startswith('-DSD_CLK_GPIO_SPEED=') for f in m.get('flags',[])):
        raise ValueError('Receive diagnostics refuse CLK slew experiment')
    address=m.get('sd_read_diagnostics_proof')
    if (type(address) is not int or address%4 or m.get('sd_read_diagnostics_proof_bytes')!=64 or
            not m['bss_start']<=address<=m['bss_end']-64):
        raise ValueError('Receive diagnostic bounds differ')
    for key,size in (('card',200),('slots',640),('producer',416),('magic_slots',576),('magic_proof',32),
                     ('sd_stream',44),('sd_scr',16),('sd_erase',32),('sd_width_proof',24),
                     ('sd_gpio_proof',32),('sd_clk_gpio_proof',48),('sd_compensation_proof',32),
                     ('sd_startup_proof',64),('raw_dma_tail_wait_proof',64),('sd_early_clock_proof',64),
                     ('sd_high_speed_proof',184),('sd_clock_profile_proof',128),('raw_read_camera_proof',64)):
        other=m.get(key)
        if other is not None and address<other+size and other<address+64:
            raise ValueError('Receive diagnostics overlap another owner')
    camera=m.get('raw_read_camera_proof')
    if (type(camera) is not int or camera%4 or m.get('raw_read_camera_proof_bytes')!=64 or
            not m['bss_start']<=camera<=m['bss_end']-64):
        raise ValueError('Read camera proof bounds differ')
    for key,size in (('card',200),('slots',640),('producer',416),('magic_slots',576),('magic_proof',32),
                     ('sd_stream',44),('sd_scr',16),('sd_erase',32),('sd_width_proof',24),
                     ('sd_startup_proof',64),('sd_read_diagnostics_proof',64)):
        other=m.get(key)
        if other is not None and camera<other+size and other<camera+64:
            raise ValueError('Read camera proof overlaps another owner')
    return True


def read_diagnostics_snapshot(b,m,label,*,lba,count):
    """Read retained SRAM after terminal, including failed/untrusted reads.

    This checks attribution and bounds only. Hardware/result/cleanup errors are
    preserved for diagnosis and cannot authorize another operation.
    """
    if not read_diagnostics_layout(m,3):return None
    if count!=1:raise ValueError('Receive diagnostics require one sector')
    raw=b.upload(m['sd_read_diagnostics_proof'],64,label+'-sd-read-diagnostics.bin')
    d=dict(zip(READ_DIAGNOSTIC_FIELDS,struct.unpack('<16I',raw)))
    expected_clkcr=0x34000|(3 if m['sd_clock_hz']==25000000 else 6)
    if (d['magic']!=0x31445253 or d['version']!=1 or d['captured']!=1 or
            d['mode']!=int(m['sd_idma_read']) or d['lba']!=lba or d['count']!=count or
            d['destination']!=READ_BUFFER or d['requested_bytes']!=512 or d['words']>128 or
            d['dcount']>512 or d['fifo_flags']!=(d['sta']&0xA8000) or d['clkcr']!=expected_clkcr):
        raise ValueError('Receive diagnostic record differs from request/profile')
    if (not m['sd_idma_read'] and d['idmactrl']) or (m['sd_idma_read'] and d['idmactrl']!=1):
        raise ValueError('Receive diagnostic IDMA ownership differs')
    return d


def read_camera_snapshot(b,m,label):
    if not read_diagnostics_layout(m,3):return None
    raw=b.upload(m['raw_read_camera_proof'],64,label+'-read-camera.bin')
    keys=('magic version phase rcc_ahb4enr svmcr3 moder odr idr otyper pupdr '
          'assert_begin checked c_ospeed e_ospeed sd_gpio_readable held').split()
    d=dict(zip(keys,struct.unpack('<16I',raw)))
    if (d['magic']!=0x31504352 or d['version']!=1 or d['phase']!=2 or d['held']!=1 or
            d['rcc_ahb4enr']&0x44014!=0x44014 or not d['svmcr3']&0x100 or
            d['moder']&0xC00!=0x400 or d['odr']&0x20 or d['idr']&0x20 or
            d['otyper']&0x20 or d['pupdr']&0xC00 or d['sd_gpio_readable']!=1 or
            d['c_ospeed']&0xFF3!=0xFF3 or d['e_ospeed']&0x300!=0x300 or
            (d['checked']-d['assert_begin'])&0xFFFFFFFF<40800):
        raise ValueError('Camera reset hold or unchanged SD GPIO speed proof differs')
    return d


def clk_gpio_layout(m,operation=None):
    """Admit only the isolated PC2 slew trial; this record never proves idle."""
    speed=m.get('sd_clk_gpio_speed')
    flags=m.get('flags',[])
    selected=[f for f in flags if f.startswith('-DSD_CLK_GPIO_SPEED=')]
    if speed is None:
        if selected or m.get('sd_clk_gpio_proof') is not None or m.get('sd_clk_gpio_proof_bytes',0):
            raise ValueError('Unexpected CLK-only speed telemetry or compiler flag')
        return None
    true_keys=('sd_review_profile','sd_startup_opt','sd_clock_negedge','sd_clock_negedge_init',
               'magic_format','line_stream','async_stop')
    false_keys=('flash','standby','sd_high_speed','sd_fixed_compensation','sd_compensation_modified',
                'sd_high_speed_mixed_slew','sd_high_speed_fixed_compensation','sd_high_speed_combined_electrical',
                'sd_early_run_clock','sd_idma_read','raw_dma_tail_wait','dma_sleep','preinit',
                'line_snapshots','line_poison','whole_image_preerase','error_after_frame_test')
    if (type(speed) is not int or speed not in (1,2,3) or
            selected!=[f'-DSD_CLK_GPIO_SPEED={speed}'] or
            not all(m.get(k) is True for k in true_keys) or
            not all(m.get(k,False) is False for k in false_keys) or
            m.get('error_test_code',0)!=0 or m.get('sd_clock_hz')!=25000000 or
            m.get('sd_bus_width')!=4 or m.get('sd_gpio_speed')!=3 or
            m.get('transport')!='idma' or operation not in (None,1,3)):
        raise ValueError('CLK-only slew requires the reviewed startup 25 MHz no-tail RAM capture/read profile')
    macros=dict(SD_BUS_WIDTH='4',RAW_SD_CLOCK_HZ='25000000U',SD_GPIO_SPEED='3',
        SD_REVIEW_PROFILE='1',SD_STARTUP_OPT='1',SD_CLOCK_NEGEDGE='1',SD_CLOCK_NEGEDGE_INIT='1',
        RAW_FLASH='0',RAW_STANDBY='0',RAW_DMA='1',RAW_MAGIC_FORMAT='1',RAW_LINE_STREAM='1',RAW_ASYNC_STOP='1',
        SD_FIXED_COMPENSATION='0',SD_HIGH_SPEED='0',SD_HIGH_SPEED_MIXED_SLEW='0',
        SD_HIGH_SPEED_FIXED_COMPENSATION='0',SD_HIGH_SPEED_COMBINED_ELECTRICAL='0',
        SD_EARLY_RUN_CLOCK='0',SD_IDMA_READ='0',RAW_DMA_TAIL_WAIT='0',RAW_DMA_SLEEP='0',
        RAW_PREINIT='0',RAW_LINE_SNAPSHOTS='0',RAW_LINE_POISON='0',RAW_WHOLE_IMAGE_PREERASE='0')
    for macro,value in macros.items():
        if [f for f in flags if f.startswith('-D'+macro+'=')]!=[f'-D{macro}={value}']:
            raise ValueError('CLK-only profile compiler flags differ: '+macro)
    address=m.get('sd_clk_gpio_proof')
    if (type(address) is not int or address%4 or m.get('sd_clk_gpio_proof_bytes')!=48 or
            not m['bss_start']<=address<=m['bss_end']-48):
        raise ValueError('CLK-only proof bounds differ')
    for key,size in (('card',200),('slots',640),('producer',416),('magic_slots',576),('magic_proof',32),
                     ('sd_stream',44),('sd_scr',16),('sd_erase',32),('sd_width_proof',24),
                     ('sd_startup_proof',64),('sd_gpio_proof',32),('sd_compensation_proof',32),
                     ('raw_dma_tail_wait_proof',64),('sd_high_speed_proof',184),
                     ('sd_clock_profile_proof',128),('sd_early_clock_proof',64)):
        other=m.get(key)
        if other is not None and address<other+size and other<address+48:
            raise ValueError('CLK-only proof overlaps another owner')
    return speed


def clk_gpio_snapshot(b,m,label,operation=None):
    speed=clk_gpio_layout(m,operation)
    if speed is None:return None
    raw=b.upload(m['sd_clk_gpio_proof'],48,label+'-sd-clk-gpio.bin')
    if len(raw)!=48:raise ValueError('Incomplete CLK-only speed telemetry')
    names=('magic','version','requested_speed','clk_mask','c_mask','c_before','c_configured',
           'c_after','e_mask','e_before','e_after','applied')
    proof=dict(zip(names,struct.unpack('<12I',raw)))
    expected_c=(0xFF3&~0x30)|(speed<<4)
    if (proof['magic']!=0x314B4C43 or proof['version']!=1 or proof['requested_speed']!=speed or
            proof['clk_mask']!=0x30 or proof['c_mask']!=0xFF3 or proof['e_mask']!=0x300 or
            proof['applied']!=1 or (proof['c_configured']&0xFF3)!=0xFF3 or
            (proof['c_after']&0xFF3)!=expected_c or (proof['e_after']&0x300)!=0x300 or
            (proof['c_before']^proof['c_configured'])&~0xFF3 or
            (proof['c_configured']^proof['c_after'])&~0x30 or
            (proof['e_before']^proof['e_after'])&~0x300):
        raise ValueError('CLK-only speed readback or unrelated-pin preservation differs')
    return proof


def compensation_layout(m):
    enabled=m.get('sd_fixed_compensation',False)
    if type(enabled) is not bool:
        raise ValueError('Unsupported SD compensation selection')
    flags=[f for f in m.get('flags',[]) if f.startswith('-DSD_FIXED_COMPENSATION=')]
    if 'sd_fixed_compensation' in m or flags:
        if flags!=[f'-DSD_FIXED_COMPENSATION={int(enabled)}']:
            raise ValueError('Compensation manifest/compiler flag differs')
        if m.get('sd_compensation_modified') is not enabled:
            raise ValueError('Compensation scope differs')
    if enabled:
        address=m.get('sd_compensation_proof')
        if (m.get('flash') or m.get('standby') or
                (clock_layout(m)!=25000000 and not m.get('sd_high_speed_fixed_compensation')) or
                m.get('sd_gpio_speed',3)!=3 or type(address) is not int or
                m.get('sd_compensation_proof_bytes')!=32 or
                not m['bss_start']<=address<=m['bss_end']-32):
            raise ValueError('Fixed compensation diagnostic layout/build differs')
    elif m.get('sd_compensation_proof') is not None or m.get('sd_compensation_proof_bytes',0):
        raise ValueError('Unexpected compensation proof in default build')
    return enabled


def compensation_snapshot(b,m,label):
    if not compensation_layout(m):
        return None
    raw=b.upload(m['sd_compensation_proof'],32,label+'-sd-compensation.bin')
    if len(raw)!=32:raise ValueError('Incomplete compensation telemetry')
    names=('clock_before','clock_after','reset','svmcr2','svmcr3','before','after','applied')
    proof=dict(zip(names,struct.unpack('<8I',raw)))
    if (proof['clock_after']!=(proof['clock_before']|1) or proof['reset']&1 or
            not proof['svmcr2']&0x100 or not proof['svmcr3']&0x200 or
            proof['after']!=0x287 or proof['applied']!=1):
        raise ValueError('Fixed compensation application proof incomplete or inconsistent')
    return proof


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
    diagnostic_layout(m,words[2])
    exact = dict(magic=MAGIC, schema=1, words=96, nonce=words[1],operation=words[2],
        state=3, result=0, stage=8, terminal=DONE, frame=frame_layout(m)['frame'], bytes=FRAME_BYTES,
        width=1120,height=1364,card=m['card'],card_size=200,slots=m['slots'],slots_size=640,
        sd_error=0,media_idle=1,initialized=0,controller_owned=0,cleanup_error=0,
        control=0,ipsr=0,primask=1,cpacr=0,pattern=m['pattern'],
        transport=int(m['transport']=='idma'),chunk_sectors=m['chunk_sectors'],completion=0,
        flags=m.get('expected_flags',0),clock_hz=clock_layout(m))
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
        if m.get('raw_dma_tail_wait'):
            result['dma_tail_wait']=dma_tail_snapshot(b,m,label,stream)
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


def decode_card(raw):
    values=struct.unpack('<6Q38I',raw)
    names=('sector_count read_sectors written_sectors read_cycles write_cycles ready_cycles '
        'initialized controller_owned media_idle clock_hz ocr rca cid0 cid1 cid2 cid3 '
        'csd0 csd1 csd2 csd3 error error_stage error_command error_sta stage last_command '
        'last_argument last_sta last_r1 command_count last_ready_r1 last_stop_r1 cleanup_error '
        'transfer_words transfer_sta transfer_cycles init_cycles gpioc_idr gpioe_idr '
        'vddio5_control saved_sdmmc_mux saved_demcr saved_dwt timer_owned').split()
    return dict(zip(names,values))


def card_snapshot(b,m,p,label):
    c=decode_card(b.upload(m['card'],200,label+'-card.bin'))
    if c['clock_hz']!=clock_layout(m) or p.get('clock_hz')!=c['clock_hz']:
        raise ValueError('Live card, terminal proof, and requested SD clock differ')
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
    width=width_snapshot(b,m,label)
    if width is not None:c['bus_width_proof']=width
    gpio=gpio_snapshot(b,m,label)
    if gpio is not None:c['gpio_speed_proof']=gpio
    clk_gpio=clk_gpio_snapshot(b,m,label,p['operation'])
    if clk_gpio is not None:c['clk_gpio_speed_proof']=clk_gpio
    comp=compensation_snapshot(b,m,label)
    if comp is not None:c['compensation_proof']=comp
    startup=startup_snapshot(b,m,label,p['operation'])
    if startup is not None:c['startup_proof']=startup
    early=early_clock_snapshot(b,m,label,p['operation'],c)
    if early is not None:c['early_clock_proof']=early
    return c


def run(a):
    folder=a.build.resolve(); m,code=checked_build(folder,a.expected_sha)
    names=fields(folder); op=OPS[a.operation]; nonce=secrets.randbelow(0xffffffff)+1
    diagnostic_layout(m,op)
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
    if m.get('sd_read_diagnostics') and (op!=3 or args[1]!=1):
        raise ValueError('Receive diagnostics require one-sector READ')
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
    read_diagnostics=None
    if m.get('sd_read_diagnostics'):
        # Retain failed receive evidence before ordinary success validation.
        # These are SRAM reads only, never accesses to clock-gated SD registers.
        raw=b.upload(READ_BUFFER,512,'read-buffer.bin')
        (a.out/'read-buffer.bin').write_bytes(raw)
        retained_card=decode_card(b.upload(m['card'],200,'read-card.bin'))
        retained_code=b.upload(LOAD,m['immutable_bytes'],'read-immutable-code.bin')
        final_proof=decode(b.upload(PROOF,384,'read-final-proof.bin'),names)
        cfsr,hfsr=struct.unpack('<2I',b.upload(0xE000ED28,8,'read-fault-status.bin'))
        attribution=dict(binary_sha256=sha(code),expected_immutable_sha256=sha(code[:m['immutable_bytes']]),
            observed_immutable_sha256=sha(retained_code),immutable_code_equal=retained_code==code[:m['immutable_bytes']],
            final_proof_equal=final_proof==p,nonce=nonce,cfsr=cfsr,hfsr=hfsr,
            hardware_mutations=False,idle_permission=False)
        dump(a.out/'read-attribution.json',attribution)
        read_diagnostics=read_diagnostics_snapshot(b,m,'completed',lba=args[0],count=args[1])
        camera=read_camera_snapshot(b,m,'completed')
        dump(a.out/'read-diagnostics.json',dict(diagnostics=read_diagnostics,
            camera=camera,card=retained_card,attribution=attribution,
            buffer_sha256=sha(raw),buffer_bytes=512,operation_result=p['result'],
            nonce=nonce,read_data_valid=False,
            caveat='Diagnostic retention only; ordinary success/idle validation is still required.'))
        if not attribution['immutable_code_equal'] or not attribution['final_proof_equal'] or cfsr or hfsr:
            raise ValueError('Retained receive attribution differs or MCU fault flags are set')
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
    board_eth=board_eth_snapshot(b,m,p,'completed')
    if board_eth is not None:result['board_eth']=board_eth
    sd_init_gap=sd_init_gap_snapshot(b,m,p,'completed')
    if sd_init_gap is not None:result['sd_init_gap']=sd_init_gap
    power_probe=power_probe_snapshot(b,m,p,'completed')
    if power_probe is not None:result['power_probe']=power_probe
    power_phy=power_phy_snapshot(b,m,p,'completed')
    if power_phy is not None:result['power_phy']=power_phy
    power_csi=power_csi_snapshot(b,m,p,'completed')
    if power_csi is not None:result['power_csi']=power_csi
    if read_diagnostics is not None:result['read_diagnostics']=read_diagnostics
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
