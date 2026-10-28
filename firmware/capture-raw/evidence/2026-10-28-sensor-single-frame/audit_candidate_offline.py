"""Independent file-only production single-frame audit; never opens instruments."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import sys
import zlib

ROOT=Path(__file__).resolve().parents[3]
HOME=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'firmware/capture-timing'))
sys.path.insert(0,str(ROOT/'firmware/capture-raw'))
import bench
import inspect_flash
import late_build

def sha(data):return hashlib.sha256(data).hexdigest()
def js(path):return json.loads(path.read_text())
def symbols(path):
    return {m[2]:int(m[1],16) for m in re.finditer(r'^([0-9a-f]+) [A-Za-z] (\S+)$',path.read_text(),re.M)}
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    obj=importlib.util.module_from_spec(spec);spec.loader.exec_module(obj);return obj


def audit(folder):
    m=js(folder/'manifest.json');p=folder/'staged';pm=js(p/'manifest.json')
    old=ROOT/'tmp/bringup/ethernet-normal-20261028/flash-candidate/staged'
    code=(folder/'capture.bin').read_bytes();prefix=(p/'stage1.bin').read_bytes()
    before=(old/'stage1.bin').read_bytes()
    unrel=(p/'stage1-unrelocated.bin').read_bytes()
    oldunrel=(old/'stage1-unrelocated.bin').read_bytes()
    assert m['sensor_single_frame'] and m['flash'] and m['error_blinks']
    assert m['sensor_autostop_proof_schema']==2
    assert sha(code)==m['binary_sha256'] and len(code)==m['binary_bytes']
    assert struct.unpack_from('<II',code)==(m['stack'],m['entry'])
    for name,digest in m['source_hashes'].items():assert sha((folder/name).read_bytes())==digest,name
    for name,digest in pm['sources'].items():assert sha((p/Path(name).name).read_bytes())==digest,name
    assert bench.sensor_autostop_layout(m,1) and bench.sensor_autostop_layout(m,3)
    bench.diagnostic_layout(m,1)
    try:bench.checked_build(folder,sha(code))
    except ValueError as exc:assert str(exc)=='Only reviewed RAM/awake layout is accepted'
    else:raise AssertionError('FLASH entered RAM-only runner')
    if not m['standby']:inspect_flash.checked_build(folder,sha(code),pm['program_sha256'])
    late=m['late_load'];begin=late['late_address'];end=begin+late['late_bytes']
    layout=late_build.audit_layout(code,(folder/'symbols.txt').read_text(),
        (folder/'capture.lst').read_text(),begin,end)
    assert late['early_bytes']==15804 and begin==0x34303DBC and end<=0x3430E000
    assert zlib.crc32(code[15804:])==late['late_crc32']
    syms=symbols(folder/'symbols.txt');ps=symbols(p/'symbols.txt');os=symbols(old/'symbols.txt')
    assert begin<=syms['rd16']<end and begin<=syms['raw_sensor_autostop_begin']<end

    # Frozen prefix review is stronger than an expanded arbitrary changed range.
    assert len(prefix)==len(before)==len(unrel)==6720
    assert sha(before)=='2b9724bc4b60af52b1c4ab45e1b232578e9640efc3a30a57772a810d99c3f344'
    assert prefix[:0x67A]==before[:0x67A]
    literal_offsets=list(range(0x67C,0x6CC,4));assert len(literal_offsets)==20
    for offset in literal_offsets:assert prefix[offset:offset+4]==before[offset:offset+4]
    assert pm['checked_recovery_literal_offsets']==literal_offsets
    # The entire wider historical prefix boundary has unchanged instruction
    # bytes; its only changes are these exact post-guard array pointers.
    assert [i for i in range(0xAFE) if prefix[i]!=before[i]]==[0x988,0x990]
    for offset,oldptr,newptr,size in ((0x988,0x341817F0,0x341817F8,16),
            (0x990,0x34181800,0x34181808,20)):
        assert struct.unpack_from('<I',before,offset)[0]==oldptr
        assert struct.unpack_from('<I',prefix,offset)[0]==newptr
        assert before[oldptr-0x34180400:oldptr-0x34180400+size]==prefix[newptr-0x34180400:newptr-0x34180400+size]
    assert prefix[ps['table.0']-0x34180400:ps['table.0']-0x34180400+64]==before[os['table.0']-0x34180400:os['table.0']-0x34180400+64]
    for name in ('recovery_gpio_park','stage1_fault','error_stage1_bridge',
            '_error_engine_start','_error_engine_end','_error_copy_end'):
        assert ps[name]==os[name],name
    assert ps['recovery_gpio_park']==0x3418078C
    assert prefix[0x1420:]==before[0x1420:]
    engine=prefix[0x1440:0x1A40]
    assert len(engine)==1536 and sha(engine)=='247ad0ddd76963039ed01a2e14beb3499ee9097a8df86f62ad5751047835454e'
    assert m['error_runtime_copy']['destination']==0x343C8000
    relocation=pm['prefix_crc_relocation'];offsets=[0xC9C,0x1358]
    assert relocation['literal_offsets']==offsets
    assert [i for i in range(len(unrel)) if unrel.startswith(struct.pack('<I',0x3E97C7F7),i)]==offsets
    crc=zlib.crc32(code[:15804]);wanted=bytearray(unrel)
    for offset in offsets:struct.pack_into('<I',wanted,offset,crc)
    assert prefix==wanted and relocation['unrelocated_sha256']==sha(unrel)
    assert int(pm['stage2_crc32'],0)==crc and pm['stage2_bytes']==15804
    # Reuse the old exact instruction/literal decoder on a normalized copy only
    # after independently validating the two changed literal targets above.
    normalized=bytearray(prefix)
    for offset in (0x988,0x990):normalized[offset:offset+4]=before[offset:offset+4]
    oldbuilder=module('singleframe_old_identity_builder',ROOT/'firmware/capture-sd/build.py')
    assert oldbuilder.check_recovery_identity(p,bytes(normalized),before,15804)==literal_offsets

    oldsensor=(old/'stage1_sensor.c').read_text();sensor=(p/'stage1_sensor.c').read_text()
    replacement=('static const uint8_t single_context[4]={1,0,4,0};\n'
        '    TRY(32,write_reg(0x048C,single_context,4)); /* repeat1, next4; MODE_SELECT already2 */')
    assert oldsensor.count('TRY(32,write_value(0x044C,2,1));')==1
    assert sensor==oldsensor.replace('TRY(32,write_value(0x044C,2,1));',replacement)
    manual=sensor.index('static const uint8_t manual[12]={2,0,')
    config=sensor.index('TRY(32,write_reg(0x048C,single_context,4));')
    start=sensor.index('TRY(36,write_value(0x0201,1,1));')
    assert manual<config<start and 'write_value(0x0201' not in sensor[manual:config]
    context=ps['single_context.0']-0x34180400
    assert prefix[context:context+4]==bytes((1,0,4,0))
    listing=(p/'stage1.lst').read_text()
    assert re.search(r'34181450:.*ldr\s+r1.*341816b0',listing)
    assert struct.unpack_from('<I',prefix,0x12B0)[0]==ps['single_context.0']
    assert re.search(r'34181452:.*movs\s+r2, #4',listing)
    assert re.search(r'34181454:.*movw\s+r0, #1164',listing)
    assert re.search(r'34181458:.*bl\s+34180598 <write_reg>',listing)
    assert re.search(r'341814b2:.*bl\s+341806d8 <write_value>',listing)

    capture=(folder/'capture.c').read_text();ast=(folder/'sensor_autostop.inc').read_text()
    runtime=(folder/'magic_runtime.inc').read_text()
    loader=capture.index('check(0xAF,raw_late_load());')
    astcall=capture.index('  raw_sensor_autostop_begin();')
    storage=capture.index('  raw_storage_execute();')
    assert loader<astcall<storage
    early=capture[:loader]
    assert not re.search(r'(?<!int )\brd16\(&',early)
    assert 'sensor.read16=rd16;' in early
    # No early sensor high-level driver invokes the installed late callback.
    assert not re.search(r'\bVD6G_\w+\(&sensor',early)
    assert capture.index('AST[32]=fast_strobes;')<capture.index('HAL_NVIC_EnableIRQ(EXTI0_IRQn)')
    assert capture.index('GPIOD->BSRR=1U<<16; AST[33]')<capture.index('HAL_NVIC_EnableIRQ(EXTI0_IRQn)')
    initializer=ast.split('void raw_sensor_autostop_begin(void)',1)[1].split('#endif',1)[0]
    for index in (12,18,32,33):assert not re.search(rf'AST\[{index}\]\s*=',initializer)
    assert 'repeat!=1U || next!=4U || count>1U' in initializer
    assert 'count!=1U || AST[17]!=1U' in ast
    for token in ('(uint32_t)(now-capture_stop_started)>AST[31]',
            'if(state!=2U) return;', 'if(!phase_gpio_emit(11U))',
            'count!=AST[15]', 'AST[26]!=AST[17]', 'AST[18] || frames!=1U || raw_capture_fault()'):
        assert token in ast,token
    assert 'wr8(' not in ast and 'write_value(' not in ast
    poll=capture[capture.index('void raw_capture_poll(void)'):]
    for token in ('if(frames!=1U || CPROF[CP_ERRORS])','raw_producer_complete(',
            'MAGIC_CHECK(32, HAL_DCMIPP_CSI_PIPE_Stop','MAGIC_CHECK(0xA5,fast_shutdown_data_off());'):
        assert token in poll,token
    assert 'MAGIC_CHECK(33,wr8(&sensor,0x0202,1U));' not in poll
    assert runtime.index('P[RP_PAYLOAD_DONE]=')<runtime.index('if(raw_sensor_autostop_finish())')<runtime.index('P[RP_COMMIT_DONE]=')
    sector=(p/'capture_sector_0.bin').read_bytes();boot=(p/'stage1_boot.bin').read_bytes()
    assert len(sector)==65536 and sha(sector)==pm['program_sha256']
    assert sector[:len(boot)]==boot and sector[0x2000:0x2000+len(code)]==code
    assert (p/'stage2.bin').read_bytes()==code[:15804] and (p/'stage2-full.bin').read_bytes()==code
    return dict(passed=True,hardware_access=False,build=str(folder.relative_to(ROOT)),
        receiver_sha256=sha(code),prefix_sha256=sha(prefix),sector_sha256=sha(sector),
        unrelocated_prefix_sha256=sha(unrel),bytes=dict(receiver=len(code),prefix=len(prefix),early=15804),
        recovery_guard_identical=True,recovery_literal_offsets=literal_offsets,
        changed_wider_boundary_literal_words=[0x988,0x990],changed_literal_targets_verified=True,
        crc_literal_offsets=offsets,error_engine_sha256=sha(engine),error_engine_identical=True,
        prefix_sensor_source_only_one_redundant_write_replaced=True,
        context_burst={'address':0x48C,'bytes':[1,0,4,0],'before_start':True},
        checked_late_load_before_readback=True,early_irqs_preserved=True,
        readback_semantics='post-START; no pre-START runtime readback claimed',
        sensor_counter_and_strobes_exact_one_required=True,no_explicit_stop_success_path=True,
        late_layout=layout,immutable_ranges=m['immutable_ranges'],
        normal_ram_runner_still_rejects_flash=True,host_sha256=sha((ROOT/'firmware/capture-raw/bench.py').read_bytes()),
        inspector_sha256=sha((ROOT/'firmware/capture-raw/inspect_flash.py').read_bytes()))


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--build',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args();result=audit(args.build.resolve())
    if args.out.exists():raise FileExistsError(args.out)
    args.out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
