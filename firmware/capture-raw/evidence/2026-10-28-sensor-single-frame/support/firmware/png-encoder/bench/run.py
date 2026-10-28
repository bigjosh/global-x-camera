"""Exact-identity compute-only RAM trials; offline plan by default.

Only --execute accesses the bench. No NOR/SD commands, reset, power control,
fallback capture-proof fabrication, or retry on failure is provided.
"""
import argparse
import ctypes as C
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import secrets
import shutil
import struct
import subprocess
import sys
import tempfile
import time

import numpy as np
from PIL import Image
import protocol as p

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
spec=importlib.util.spec_from_file_location('frozen_readback_runner',
    ROOT/'firmware/capture-sd/low_power/readback_recovery/run.py')
bridge=importlib.util.module_from_spec(spec); spec.loader.exec_module(bridge)
sd=bridge.sd
LOAD=0x34320000
FIXTURE_SHA='ba0e69552271a93a743ebe0778c30fcdfc168532955129eae8312e3cbf7936d3'
RECOVERY_PREFIX='247f27c231e0053b7024af29914c6a0cb1b7decb1632ac0d6142a68b89e2da58'
RECOVERY_SECTOR='8129f9cc79e92c678207b4aee838810cc805d0b860c40b2f77b434ae746c8b61'

def sha(data):return hashlib.sha256(data).hexdigest()
def read(path):return json.loads(path.read_text(encoding='utf-8'))
def dump(path,value):path.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')

def checked_build(path,expected):
    m=read(path/'manifest.json'); code=(path/'bench.bin').read_bytes()
    if not re.fullmatch('[0-9a-f]{64}',expected) or sha(code)!=expected or m.get('binary_sha256')!=expected:
        raise ValueError('Explicit reviewed benchmark hash mismatch')
    exact=dict(schema=1,compute_only=True,scalar_only=True,sd_commands=False,nor_commands=False,
        sensor_commands=False,reset=False,power_switch=False,frame_bytes=p.FRAME_BYTES,
        report_bytes=512,request_bytes=64,chunk_bytes=32,chunk_capacity=100,max_output_bytes=3200000,cpu_hz=400000000)
    if any(m.get(k)!=v for k,v in exact.items()):raise ValueError('Unexpected benchmark policy/layout')
    addresses=dict(load_address=LOAD,prepare_entry=LOAD+1,ready_park=LOAD+0x16,
        run_entry=LOAD+0x19,done_park=LOAD+0x2e,stack_floor=0x343a0000,stack_top=0x343b0000,
        frame_address=p.FRAME,report_address=p.REPORT,request_address=p.REQUEST,chunks_address=p.CHUNKS)
    if any(sd.number(m.get(k,-1))!=v for k,v in addresses.items()):raise ValueError('Unexpected entry or reserved address')
    if not 0<len(code)<=0x20000 or len(code)%4 or m['binary_bytes']!=len(code):raise ValueError('Invalid code length')
    if not LOAD+len(code)<=sd.number(m['bss_start'])<=sd.number(m['bss_end'])<=0x343a0000:
        raise ValueError('Code/BSS overlaps the high stack')
    for key in ('ready_park','done_park'):
        offset=addresses[key]-LOAD
        if code[offset:offset+2]!=b'\xfe\xe7':raise ValueError('Unexpected exact park')
    for required in ('-mgeneral-regs-only','-mfloat-abi=soft','-mno-unaligned-access'):
        if required not in m['compile_flags']:raise ValueError('Scalar context/alignment flag missing')
    hashes=m.get('source_hashes')
    if not hashes or not {'bench_main.c','bench_protocol.h','bench_sink.c','bench_sink.h','entry.S','bench.ld',
                          'png16.c','png16.h','png16_miniz.c','miniz_config.h'}<=set(hashes):
        raise ValueError('Incomplete frozen source manifest')
    for relative,digest in hashes.items():
        source=(path/relative).resolve();source.relative_to(path.resolve())
        if sha(source.read_bytes())!=digest:raise ValueError('Frozen source mismatch: '+relative)
    return m,code

def checked_fixture(path):
    raw=path.read_bytes()
    if len(raw)!=p.FRAME_BYTES or sha(raw)!=FIXTURE_SHA or np.any(np.frombuffer(raw,dtype='<u2')>1023):
        raise ValueError('Only the exact qualified awake02 RAW10 fixture is supported')
    return raw

def host_golden(build,raw,modes):
    """Compile frozen encoder sources, independently decode, retain only metadata."""
    testspec=importlib.util.spec_from_file_location('png_bench_host_tests',HERE.parent/'test_png16.py')
    tests=importlib.util.module_from_spec(testspec);testspec.loader.exec_module(tests)
    cc=shutil.which('clang') or shutil.which('gcc')
    if not cc:raise RuntimeError('Native compiler required for independent source-bound output expectations')
    results=[]
    with tempfile.TemporaryDirectory(prefix='png-compute-golden-') as tmp:
        library=Path(tmp)/'encoder.dll'
        command=[cc,'-shared','-O2','-std=c11','-Wall','-Wextra','-Werror','-ffunction-sections','-fdata-sections',
                 str(build/'png16.c'),str(build/'png16_miniz.c'),'-Wl,--gc-sections','-o',str(library)]
        subprocess.run(command,check=True,capture_output=True)
        lib=C.CDLL(str(library))
        lib.png16_workspace_size.restype=C.c_size_t
        lib.png16_encode.argtypes=[C.c_void_p,C.c_size_t,C.c_uint32,C.c_uint32,C.c_size_t,C.c_int,
                                  C.c_void_p,C.c_size_t,tests.WRITE,C.c_void_p,C.POINTER(tests.Stats)]
        lib.png16_encode.restype=C.c_int
        try:
            size=lib.png16_workspace_size();workspace=(C.c_uint64*((size+7)//8))()
            source=C.create_string_buffer(raw);expected=np.frombuffer(raw,dtype='<u2').astype(np.uint32)<<6
            for mode in modes:
                pieces=[]
                @tests.WRITE
                def sink(user,data,n):pieces.append(C.string_at(data,n));return 1
                stats=tests.Stats()
                status=lib.png16_encode(source,len(raw),1120,1364,2240,mode,workspace,size,sink,None,C.byref(stats))
                if status:raise ValueError(f'Host encode failed in mode {mode}: {status}')
                encoded=b''.join(pieces)
                w,h,pixels,*_=tests.parse_png(encoded)
                if (w,h)!=(1120,1364) or not np.array_equal(pixels,expected):raise ValueError('Host parser pixel mismatch')
                with Image.open(io.BytesIO(encoded)) as image:
                    if not np.array_equal(np.asarray(image).ravel(),expected):raise ValueError('Independent PNG decode mismatch')
                if C.string_at(source,len(raw))!=raw:raise ValueError('Host encoder modified fixture')
                if not 0<len(encoded)<=3200000:raise ValueError('Encoded output exceeds target sink bound')
                results.append(dict(mode=mode,bytes=len(encoded),fnv=p.fnv(encoded),sha256=sha(encoded),
                    exact_pixel_roundtrip=True,independent_decode=True,workspace_bytes=size))
        finally:tests.close_library(lib)
    return results

def exact_code_context(b,code,park,label):
    # Caller has already proved a fresh terminal result; these reads may halt.
    registers=b.call('-halt','-coreReg')
    context=sd.context_registers(registers)
    sd.validate_context(context,{park})
    stack={key:int(value,16) for key,value in re.findall(
        r'^(SP|MSP)\s*=\s*0x([0-9a-fA-F]+)',registers,re.M)}
    if park in (LOAD+0x16,LOAD+0x2e) and (stack.get('SP')!=0x343b0000 or stack.get('MSP')!=0x343b0000):
        raise ValueError('High benchmark park must use the exact high MSP before RAW upload/reuse')
    ccr,=struct.unpack('<I',b.upload(0xe000ed14,4,label+'-ccr.bin'))
    fpccr,=struct.unpack('<I',b.upload(0xe000ef34,4,label+'-fpccr.bin'))
    if ccr&0x30000 or fpccr&1:raise ValueError('Caches/lazy FP must be inactive')
    context=dict(registers=context,stack=stack,ccr=ccr,fpccr=fpccr)
    if b.upload(LOAD,len(code),label+'-code.bin')!=code:raise ValueError('Live benchmark code mismatch')
    return context

def wait_terminal(b,command,terminal,timeout):
    nonce=struct.unpack_from('<I',command,12)[0]
    deadline=time.monotonic()+timeout
    for poll in range(60):
        raw=b.upload(p.REPORT,512,f'report-{poll:02d}.bin')
        report=p.decode(raw)
        if report['magic']==p.MAGIC and report['nonce']==nonce and report['terminal']==terminal:
            dump(b.output/'terminal.json',report)
            return p.validate(report,command)
        if time.monotonic()>deadline:break
        time.sleep(.1)
    raise TimeoutError('No fresh compute terminal; no halt/reset/retry issued')

def dispatch(b,command,entry,terminal,timeout,prior_park,code):
    context=exact_code_context(b,code,prior_park,'before')
    (b.output/'request.bin').write_bytes(command);(b.output/'clear.bin').write_bytes(bytes(512))
    b.call('-halt','-w',b.output/'clear.bin',hex(p.REPORT),'-v',
           '-w',b.output/'request.bin',hex(p.REQUEST),'-v',success='Download verified successfully')
    if (b.upload(p.REQUEST,64,'request-readback.bin')!=command or
        b.upload(p.REPORT,512,'cleared-report.bin')!=bytes(512)):
        raise ValueError('Compute request/clear readback mismatch')
    timing=dict(scope='Host command brackets, not electrical synchronization',run_before=sd.host_stamp())
    dump(b.output/'host-timing.json',timing)
    b.call('-halt','-coreReg','PC='+hex(entry),'XPSR=0x01000000','-run',success='Core run')
    timing['run_after']=sd.host_stamp()
    report=wait_terminal(b,command,terminal,timeout)
    timing['terminal_observed']=sd.host_stamp();dump(b.output/'host-timing.json',timing)
    final_park=LOAD+0x16 if terminal==p.READY else LOAD+0x2e
    final=exact_code_context(b,code,final_park,'final')
    if b.upload(p.REQUEST,64,'completed-request.bin')!=command:raise ValueError('Completed request differs')
    result=dict(report=report,initial_context=context,final_context=final,
        module_sha256=sha(code),request_words=list(struct.unpack('<16I',command)),
        sd_commands=False,nor_commands=False,reset_sent=False,power_changed=False)
    if terminal==p.DONE:
        result['chunks']=p.chunks(b.upload(p.CHUNKS,report['chunk_count']*32,'chunks.bin'),report['chunk_count'])
        if (result['chunks'][-1]['bytes']!=report['output_bytes'] or
            result['chunks'][-1]['fnv']!=report['output_fnv'] or
            result['chunks'][-1]['elapsed_cycles']>report['encode_cycles'] or
            result['chunks'][-1]['sink_body_cycles']>report['sink_body_cycles'] or
            report['chunk_count']!=(report['output_bytes']+32767)//32768):
            raise ValueError('Final interval does not bind output digest/timing')
    dump(b.output/'verified.json',result)
    return result

def execute(a,m,code,boot,raw,golden,out):
    # This repeated exact early guard is inside bootstrap immediately before RAM writes.
    bootstrap=bridge.bootstrap(a,out,boot)
    bootstrap.call('-halt','-w',(a.build/'bench.bin').resolve(),hex(LOAD),'-v',success='Download verified successfully')
    if bootstrap.upload(LOAD,len(code),'benchmark-readback.bin')!=code:raise ValueError('Benchmark RAM readback differs')
    ready_b=sd.Bench(out/'prepare')
    command=p.request(1,secrets.randbelow(0xffffffff)+1)
    ready=dispatch(ready_b,command,LOAD+1,p.READY,a.timeout,bridge.BOOT_PARK,code)
    # Critical lifetime boundary: CPU and SP now lie above the RAW upload.
    fixture=sd.Bench(out/'fixture')
    exact_code_context(fixture,code,LOAD+0x16,'high-park-before-raw')
    guard=struct.pack('<8I',*[0x504e4700+i for i in range(8)])
    (fixture.output/'guard.bin').write_bytes(guard)
    fixture.call('-halt','-w',a.raw.resolve(),hex(p.FRAME),'-v',
        '-w',fixture.output/'guard.bin',hex(p.FRAME+p.FRAME_BYTES),'-v',success='Download verified successfully')
    actual=fixture.upload(p.FRAME,len(raw),'raw-readback.bin')
    if actual!=raw or fixture.upload(p.FRAME+p.FRAME_BYTES,32,'guard-readback.bin')!=guard:
        raise ValueError('Exact fixture/guard upload mismatch; no encoding started')
    exact_code_context(fixture,code,LOAD+0x16,'high-park-after-raw')
    dump(fixture.output/'verified.json',dict(raw_sha256=sha(actual),raw_bytes=len(actual),
        high_park_verified_before_and_after=True,raw_upload_overwrites_retired_low_bridge=True))
    prior=ready;prior_command=command;park=LOAD+0x16;results=[]
    input_fnv=p.fnv(raw)
    for item in golden:
        for repeat in range(1,a.repeats+1):
            b=sd.Bench(out/f'mode-{item["mode"]}-run-{repeat:02d}')
            # Require fresh live terminal/nonce proof before any halt or write.
            live=p.decode(b.upload(p.REPORT,512,'prior-report.bin'))
            p.validate(live,prior_command)
            if live!=prior['report']:raise ValueError('Prior terminal changed since verification')
            command=p.request(2,secrets.randbelow(0xffffffff)+1,item['mode'],input_fnv,item['fnv'],item['bytes'])
            result=dispatch(b,command,LOAD+0x19,p.DONE,a.timeout,park,code)
            result['golden']=item;result['repeat']=repeat
            dump(b.output/'verified.json',result)
            results.append(result);prior=result;prior_command=command;park=LOAD+0x2e
    dump(out/'verified.json',dict(compute_only=True,hardware_access=True,source_frame_sha256=sha(raw),
        module_sha256=sha(code),runs=len(results),results=results,
        expected_png_metadata_from_host=True,full_target_png_bytes_downloaded=False,
        nor_unchanged_by_design=True,sd_commands_sent=False,final_exact_park=hex(park),
        production_timing_qualified=False))
    print(json.dumps(dict(passed=True,runs=len(results),final_exact_park=hex(park)),indent=2))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build',type=Path,required=True)
    parser.add_argument('--expected-sha256',required=True)
    parser.add_argument('--bridge',type=Path,required=True)
    parser.add_argument('--recovery-build',type=Path,required=True)
    parser.add_argument('--raw',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--mode',type=int,choices=(0,1,2,3),action='append')
    parser.add_argument('--repeats',type=int,default=3)
    parser.add_argument('--timeout',type=float,default=90)
    parser.add_argument('--execute',action='store_true')
    a=parser.parse_args()
    if not 1<=a.repeats<=10 or not 5<=a.timeout<=180:parser.error('Invalid repeat count or timeout')
    a.mode=a.mode or [0,1,2,3]
    if len(set(a.mode))!=len(a.mode):parser.error('Duplicate modes')
    a.build=a.build.resolve();a.bridge=a.bridge.resolve();a.recovery_build=a.recovery_build.resolve()
    m,code=checked_build(a.build,a.expected_sha256)
    _,boot=bridge.checked_bridge(a.bridge)
    identity=bridge.checked_recovery(a.recovery_build)
    if identity['prefix_sha256']!=RECOVERY_PREFIX or identity['sector_sha256']!=RECOVERY_SECTOR:
        raise ValueError('This compute path accepts only the current exact v66c recovery')
    raw=checked_fixture(a.raw.resolve())
    golden=host_golden(a.build,raw,a.mode)
    out=a.out.resolve();out.relative_to((ROOT/'tmp').resolve());out.mkdir(parents=True,exist_ok=False)
    dump(out/'plan.json',dict(execute=a.execute,compute_only=True,build=str(a.build),
        module_sha256=sha(code),recovery_identity=identity,bridge_sha256=sha(boot),
        frame_sha256=sha(raw),input_fnv=p.fnv(raw),modes=a.mode,repeats=a.repeats,
        goldens=golden,nor_commands=False,sd_commands=False,reset=False,power_switch=False))
    if not a.execute:
        print(json.dumps(dict(offline_plan_passed=True,plan=str(out/'plan.json'),goldens=golden),indent=2));return
    execute(a,m,code,boot,raw,golden,out)

if __name__=='__main__':main()
