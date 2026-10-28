"""Independent file-only RAM experiment audit; never opens bench instruments."""
from pathlib import Path
import hashlib
import json
import re
import struct
import sys

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'firmware/capture-raw'))
import bench

def sha(b):return hashlib.sha256(b).hexdigest()
p=HERE/'design/ram-auto-v2'
m=json.loads((p/'manifest.json').read_text());code=(p/'capture.bin').read_bytes()
accepted,_=bench.checked_build(p,m['binary_sha256']);assert accepted==m
assert bench.sensor_autostop_layout(m,1) and bench.sensor_autostop_layout(m,3)
sensor=(p/'stage1_sensor.c').read_text();capture=(p/'capture.c').read_text()
ast=(p/'sensor_autostop.inc').read_text();runtime=(p/'magic_runtime.inc').read_text()
required=[
    'TRY(40,write_value(0x048C,1U,2));','TRY(41,write_value(0x048E,4U,2));',
    'TRY(42,read_reg(0x048C,2,&ast_repeat));','TRY(43,read_reg(0x048E,2,&ast_next));',
    'TRY(44,read_reg(0x0050,2,&ast_count));',
    'if(ast_repeat!=1U || ast_next!=4U || ast_count!=0U)',
    'SENSOR[30]=1U;','event(109);','TRY(36,write_value(0x0201,1,1));']
offsets=[sensor.index(token) for token in required]
assert offsets==sorted(offsets)
poll=capture[capture.index('void raw_capture_poll(void)'):]
assert 'MAGIC_CHECK(33,wr8(&sensor,0x0202,1U));' not in poll
assert 'MAGIC_CHECK(32, HAL_DCMIPP_CSI_PIPE_Stop' in poll
assert 'MAGIC_CHECK(0xA5,fast_shutdown_data_off());' in poll
for token in ('if(frames!=1U || CPROF[CP_ERRORS])','raw_producer_complete(',
              'raw_capture_data_ready();','AST[16]=FAST[31]; AST[28]=frames;'):
    assert token in poll
assert 'if(a==0x0202U && v==1U) AST[18]++;' in capture
for token in ('(uint32_t)(now-capture_stop_started)>AST[31]',
              '(uint32_t)(now-capture_stop_poll)<400000U','if(state!=2U) return;',
              'if(!phase_gpio_emit(11U))','rd16(&sensor,0x0050,&count)',
              '(count!=1U && count!=2U)','(AST[17]!=1U && AST[17]!=2U)',
              'count!=AST[15]','AST[26]!=AST[17]','frames!=1U || raw_capture_fault()',
              'AST[3]=4U; AST[30]|=8U;'):
    assert token in ast
assert 'wr8(' not in ast and 'write_value(' not in ast
assert runtime.index('P[RP_PAYLOAD_DONE]=')<runtime.index('if(raw_sensor_autostop_finish())')<runtime.index('P[RP_COMMIT_DONE]=')
assert capture.index('GPIOD->BSRR=1U<<16; AST[33]')<capture.index('HAL_NVIC_EnableIRQ(EXTI0_IRQn)')
normal=HERE/'design/ram-default'
old=ROOT/'tmp/bringup/ethernet-normal-20261028/ram-candidate'
disabled=HERE/'design/flash-default'
installed=ROOT/'tmp/bringup/ethernet-normal-20261028/flash-candidate'
for name in ('capture.bin','staged/stage1.bin','staged/capture_sector_0.bin'):
    assert (disabled/name).read_bytes()==(installed/name).read_bytes()
report=dict(passed=True,scope='Independent offline file/source review only; not a hardware qualification',
    build=str(p.relative_to(ROOT)),binary_sha256=sha(code),binary_bytes=len(code),
    checked_build_passed=True,source_hashes_match=True,header=struct.unpack_from('<II',code),
    configured_readback_before_start=True,config_register_writes={'0x048C':1,'0x048E':4},
    initial_sensor_counter_required_zero=True,normal_frame_gates_and_receiver_stop_retained=True,
    success_path_explicit_stop_removed=True,explicit_stop_write_counter_retained=True,
    bounded_autonomous_fsm2_poll=True,independent_counter_and_strobe_counts=True,
    stable_recheck_after_payload_before_commit=True,mirror_enabled_before_irq=True,
    normal_disabled_flash_receiver_prefix_sector_identical=True,
    normal_disabled_ram_binary_identical=(normal/'capture.bin').read_bytes()==(old/'capture.bin').read_bytes(),
    normal_disabled_ram_comparison_note='The generated disabled RAM control omits error_blinks; '
        'the older Ethernet RAM candidate includes them, so these are not the same build profile.',
    normal_binary_sha256=sha((normal/'capture.bin').read_bytes()),
    host_sha256=sha((ROOT/'firmware/capture-raw/bench.py').read_bytes()),
    caution='Receiver completion is one image; independent sensor observations can be one or two. '
            'No FLASH recovery-prefix or hardware audit is implied by this RAM-only report.')
out=HERE/'ram-v2-offline-audit.json'
if out.exists():raise FileExistsError(out)
out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
