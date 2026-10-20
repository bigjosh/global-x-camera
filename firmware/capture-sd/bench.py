"""Guarded RAM-only save-module runner. No reset, power control, or NOR commands.

Only the exclusive bench owner may execute this script. Start in the exact
raw10 prepare_maintenance cache park after a completed frame, or the exact
successful save-module park. A failed/unknown operation is never retried here.
An automatic SAVE with nonce zero is accepted only after successful loader
return and the exact cache-maintenance park; it is never a bench-park token.
"""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import re
import secrets
import struct
import sys
import time
import zlib

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"firmware"/"boot-timing"))
from nor_bench import Bench

LOAD=0x34320000
REQUEST=0x343F9F00
LOADER=0x343F9E00
REPORT=0x343FA000
CARD=0x343FA200
FS=0x343FA400
FRAME=0x34000000
FRAME_BYTES=3055360
CACHE=0x343C0000
CACHE_STATUS=0x343C0400
CACHE_BYTES=148
CACHE_SHA="59427aa1c107a24378a35c3f85eb7f7d4fc1209115a319f05d3322646f62943d"
OPERATIONS={"save":1,"format":2,"read":3,"mount":4}
MODES={"stored":0,"fast-none":1,"fast-sub":2}
FIELDS="""magic schema words state operation mode result stage begin end cpu_hz
buffer_address buffer_bytes read_bytes sd_hz ccr total_lo total_hi encode_lo
encode_hi callback_lo callback_hi finish_lo finish_hi init_lo init_hi mount_lo
mount_hi validate_lo validate_hi stack_used stack_canary rows idat_chunks
callbacks buffer_flushes png_bytes_lo png_bytes_hi fnv_before fnv_after width
height frame_bytes media_idle card_error fs_result fs_stage png_result card_size
fs_size nonce initial_msplim""".split()
CARD_QWORDS="sector_count read_sectors written_sectors read_cycles write_cycles ready_cycles".split()
CARD_WORDS="""initialized controller_owned media_idle clock_hz ocr rca cid0 cid1
cid2 cid3 csd0 csd1 csd2 csd3 error error_stage error_command error_sta stage
last_command last_argument last_sta last_r1 command_count last_ready_r1
last_stop_r1 cleanup_error transfer_words transfer_sta transfer_cycles
init_cycles gpioc_idr gpioe_idr vddio5_control saved_sdmmc_mux saved_demcr
saved_dwt timer_owned""".split()
FS_WORDS="""state stage fat_result bytes_written expected_max_bytes file_number
cluster_bytes free_clusters completed""".split()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def number(value):
    if isinstance(value,bool):
        raise ValueError("Boolean is not an address/count")
    return int(value,0) if isinstance(value,str) else int(value)


def signed(value):
    return value if value<0x80000000 else value-0x100000000


def json_file(path,value):
    path.write_text(json.dumps(value,indent=2)+"\n",encoding="utf-8")


def host_stamp():
    return dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                monotonic_ns=time.monotonic_ns())


def validate_layout(manifest,code,expected_sha):
    if not re.fullmatch(r"[0-9a-f]{64}",expected_sha):
        raise ValueError("An explicit lowercase reviewed module SHA-256 is required")
    if sha(code)!=expected_sha or manifest.get("binary_sha256")!=expected_sha:
        raise ValueError("Module does not match the explicitly selected reviewed hash")
    exact={"schema":1,"load_address":LOAD,"entry_address":LOAD|1,
           "stack_floor":0x343A0000,"stack_top":0x343B0000,
           "request_address":REQUEST,"report_address":REPORT,"buffer_bytes":32768}
    for key,value in exact.items():
        if number(manifest.get(key,-1))!=value:
            raise ValueError("Unexpected module layout: "+key)
    if not 0<len(code)<=40960 or len(code)%4 or manifest.get("binary_bytes")!=len(code):
        raise ValueError("Module code length exceeds the frozen window")
    start,end=[number(manifest[k]) for k in ("bss_start","bss_end")]
    buffer=number(manifest["buffer_address"])
    entry,park=[number(manifest[k]) for k in ("bench_entry_address","park_address")]
    if not LOAD+len(code)<=start<=buffer<buffer+32768<=end<=0x343A0000:
        raise ValueError("Module BSS/buffer overlaps code, stack, or diagnostics")
    if start%4 or end%8 or buffer%32:
        raise ValueError("Unaligned BSS or buffer")
    if not entry&1 or not LOAD<=entry-1<LOAD+len(code) or park%2:
        raise ValueError("Invalid bench entry or park")
    offset=park-LOAD
    if (not 0<=offset<len(code)-1 or
            (code[offset:offset+2]!=b"\xfe\xe7" and code[offset:offset+4]!=b"\xff\xf7\xfe\xbf")):
        raise ValueError("Park must be the exact Thumb branch-to-self instruction")


def checked_build(build,expected_sha):
    manifest=json.loads((build/"manifest.json").read_text(encoding="utf-8-sig"))
    code=(build/"save.bin").read_bytes()
    validate_layout(manifest,code,expected_sha)
    sources=manifest.get("sources")
    if not isinstance(sources,dict) or not sources:
        raise ValueError("A frozen source manifest is required")
    for relative,want in sources.items():
        path=(ROOT/relative).resolve()
        if not path.is_relative_to(ROOT) or sha(path.read_bytes())!=want:
            raise ValueError("Frozen module source changed: "+relative)
    return manifest,code


def decode_report(raw):
    if len(raw)!=512:
        raise ValueError("Incomplete module report")
    words=struct.unpack("<128I",raw)
    result=dict(zip(FIELDS,words))
    result["result_signed"]=signed(result["result"])
    result["png_result_signed"]=signed(result["png_result"])
    result["terminal"]=words[63]
    result["name"]=raw[256:272].split(b"\0",1)[0].decode("ascii",errors="replace")
    for field in ("total","encode","callback","finish","init","mount","validate","png_bytes"):
        result[field]=result[field+"_lo"] | result[field+"_hi"]<<32
    for field in ("total","encode","callback","finish","init","mount","validate"):
        result[field+"_ms"]=result[field]*1000/400000000
    result["raw_words"]=list(words)
    return result


def validate_success(report,manifest,request=None,allow_auto=False):
    exact={"magic":0x53564431,"schema":1,"words":128,"state":2,"result":0,
           "terminal":0x444F4E45,"cpu_hz":400000000,"media_idle":1,
           "card_error":0,"fs_result":0,"width":1120,"height":1364,
           "frame_bytes":FRAME_BYTES,"buffer_bytes":32768,
           "buffer_address":number(manifest["buffer_address"]),
           "stack_canary":0x5354414B,"initial_msplim":0x343A0000}
    for key,want in exact.items():
        if report.get(key)!=want:
            raise ValueError("No successful terminal storage proof: "+key)
    auto=allow_auto and report["nonce"]==0 and report["operation"]==OPERATIONS["save"]
    if (report["operation"] not in OPERATIONS.values() or report["mode"] not in MODES.values()
            or (not auto and not 0<report["nonce"]<2**32) or report["stack_used"]>65536
            or report["ccr"]&0x30000 or report["read_bytes"]>32768):
        raise ValueError("Invalid terminal storage context")
    if request:
        for key in ("operation","mode","nonce"):
            if report[key]!=request[key]:
                raise ValueError("Stale terminal report: "+key)
        if report["read_bytes"]>request["length"]:
            raise ValueError("Read result exceeds the requested chunk")
    if report["operation"]==OPERATIONS["save"]:
        if (report["fnv_before"]!=report["fnv_after"] or report["rows"]!=1364
                or report["png_result"] or not 0<report["png_bytes"]<=3100000):
            raise ValueError("Completed PNG/frame-integrity proof is missing")


def decode_card(raw):
    expected=6*8+len(CARD_WORDS)*4
    if len(raw)!=expected:
        raise ValueError("SD-card snapshot ABI changed")
    values=struct.unpack("<6Q"+str(len(CARD_WORDS))+"I",raw)
    return dict(zip(CARD_QWORDS+CARD_WORDS,values))


def decode_fs(raw):
    if len(raw)!=80:
        raise ValueError("Filesystem report ABI changed")
    result=dict(zip(FS_WORDS,struct.unpack_from("<9I",raw)))
    result["sector_count"]=struct.unpack_from("<Q",raw,40)[0]
    result["final_name"]=raw[48:61].split(b"\0",1)[0].decode("ascii",errors="replace")
    result["temporary_name"]=raw[61:74].split(b"\0",1)[0].decode("ascii",errors="replace")
    return result


def context_registers(text):
    return {name:int(value,16) for name,value in re.findall(
        r"^(PC|XPSR|CONTROL|PRIMASK|FAULTMASK)\s*=\s*0x([0-9A-Fa-f]+)",text,re.M)}


def validate_context(context,parks):
    if (context.get("PC") not in parks or context.get("CONTROL")!=0
            or context.get("PRIMASK")!=1 or context.get("FAULTMASK")!=0
            or context.get("XPSR",511)&511 or not context.get("XPSR",0)&0x01000000):
        raise ValueError("Core is not in the exact privileged IRQ-masked terminal park")


def context_proof(bench,parks,label):
    context=context_registers(bench.call("-halt","-coreReg"))
    validate_context(context,parks)
    ccr,=struct.unpack("<I",bench.upload(0xE000ED14,4,label+"-ccr.bin"))
    fpccr,=struct.unpack("<I",bench.upload(0xE000EF34,4,label+"-fpccr.bin"))
    if ccr&0x30000 or fpccr&1:
        raise ValueError("Caches must be disabled and no lazy FP save may be pending")
    return dict(registers=context,ccr=ccr,fpccr=fpccr)


def frame_proof(bench):
    trace=struct.unpack("<64I",bench.upload(0x343F0000,256,"capture-trace.bin"))
    raw=struct.unpack("<10I",bench.upload(0x343F6000,40,"raw10-proof.bin"))
    guard=struct.unpack("<8I",bench.upload(FRAME+FRAME_BYTES,32,"frame-guard.bin"))
    if (trace[0]!=0x43545031 or trace[1]!=40 or trace[3] or trace[4] or trace[7]
            or tuple(trace[12:16])!=(FRAME,FRAME_BYTES,1120,1364)
            or raw[0]!=0x52313046 or raw[1]!=FRAME_BYTES or raw[7]
            or guard!=tuple(0xA15A1000+i for i in range(8))):
        raise ValueError("Require an intact completed RAW10 capture before maintenance")
    return dict(trace_words=list(trace),raw10_words=list(raw),guard_words=list(guard))


def snapshots(bench,report,label):
    if not 0<report["card_size"]<=512 or not 0<report["fs_size"]<=512:
        raise ValueError("Snapshot lengths exceed their reserved windows")
    card=decode_card(bench.upload(CARD,report["card_size"],label+"-card.bin"))
    fs=decode_fs(bench.upload(FS,report["fs_size"],label+"-fs.bin"))
    return card,fs


def successful_snapshots(card,fs,report):
    if (card["error"] or card["media_idle"]!=1 or card["initialized"]
            or card["controller_owned"] or fs["fat_result"]):
        raise ValueError("Card snapshot does not prove successful deinitialization")
    if report["operation"]==OPERATIONS["save"]:
        if (fs["completed"]!=1 or fs["bytes_written"]!=report["png_bytes"]
                or fs["final_name"]!=report["name"]):
            raise ValueError("Filesystem completion does not match the PNG report")


def validate_storage_activity(loader,report):
    """Reject recognized partial/error records before any halt or RAM write."""
    if len(loader)!=16:
        raise ValueError("Incomplete storage-loader proof")
    loader_known=loader[0]==0x534C4431
    module_known=report["magic"]==0x53564431
    if loader_known and (not loader[11] or loader[10] or not loader[8] or not loader[9]):
        raise ValueError("Storage loader is active/failed/unknown; no halt, retry or reset")
    if module_known and (report["schema"]!=1 or report["words"]!=128
            or report["terminal"]!=0x444F4E45 or report["state"]!=2
            or report["result"] or report["media_idle"]!=1 or report["card_error"]
            or report["fs_result"]):
        raise ValueError("Storage module is active/failed/nonidle; no halt, retry or reset")
    if loader_known and not module_known:
        raise ValueError("Recognized loader has no completed storage-module proof")
    if module_known and report["nonce"]==0 and not loader_known:
        raise ValueError("Automatic SAVE has no completed loader proof")
    return loader_known or module_known


def validate_loader_completion(loader,code):
    if (loader[0]!=0x534C4431 or not loader[11] or loader[10]
            or loader[8]!=len(code) or not loader[9]
            or loader[7]!=zlib.crc32(code)):
        raise ValueError("Loader did not completely load and successfully return from this exact module")


def exact_storage_proof(bench,manifest,code,loader,raw,label):
    """Read-only proof usable by prepare_maintenance before its first halt."""
    report=decode_report(raw)
    if not validate_storage_activity(loader,report):
        raise ValueError("No recognized completed storage operation")
    auto=report["nonce"]==0
    validate_success(report,manifest,allow_auto=auto)
    if loader[0]==0x534C4431:
        validate_loader_completion(loader,code)
    if not auto:
        request_raw=bench.upload(REQUEST,64,label+"-request.bin")
        request_words=struct.unpack("<16I",request_raw)
        if (request_words[0]!=0x53525131 or request_words[1]!=report["operation"]
                or request_words[2]!=report["mode"] or request_words[10]!=report["nonce"]):
            raise ValueError("Terminal report is stale relative to its request")
    live=bench.upload(LOAD,len(code),label+"-module.bin")
    if live!=code:
        raise ValueError("Live module differs from the exact approved module")
    card,fs=snapshots(bench,report,label)
    successful_snapshots(card,fs,report)
    return dict(automatic_save=auto,report=report,card=card,fs=fs,
                loader_words=list(loader),module_sha256=sha(code))


def maintenance_park_proof(bench):
    frame=frame_proof(bench)
    cache=bench.upload(CACHE,CACHE_BYTES,"maintenance-code.bin")
    status=struct.unpack("<5I",bench.upload(CACHE_STATUS,20,"maintenance-status.bin"))
    if sha(cache)!=CACHE_SHA or status[0]!=0x43414348 or status[3] or status[4]&0x30000:
        raise ValueError("Exact completed raw10 prepare_maintenance cache helper is required")
    context=context_proof(bench,{CACHE+0x72,CACHE+0x74},"preflight")
    return dict(frame=frame,cache_status=list(status),cache_sha256=sha(cache),context=context)


def preflight(bench,manifest,code):
    """No halt/write before terminal evidence; no retry path for an SD error."""
    loader=struct.unpack("<16I",bench.upload(LOADER,64,"prior-loader.bin"))
    raw=bench.upload(REPORT,512,"prior-report.bin")
    prior=decode_report(raw)
    if validate_storage_activity(loader,prior):
        proof=exact_storage_proof(bench,manifest,code,loader,raw,"prior")
        if proof["automatic_save"]:
            return dict(path="automatic_save_maintenance",**proof,
                        **maintenance_park_proof(bench),module_already_identical=True)
        context=context_proof(bench,{number(manifest["park_address"])},"preflight")
        return dict(path="successful_save_park",**proof,context=context,module_already_identical=True)
    return dict(path="completed_capture_maintenance",**maintenance_park_proof(bench),
                module_already_identical=False)


def make_request(operation,mode,sd_hz,offset,length,name,nonce):
    if operation not in OPERATIONS.values() or mode not in MODES.values():
        raise ValueError("Unsupported operation/mode")
    if sd_hz not in (100000,12500000,25000000) or not 0<nonce<2**32:
        raise ValueError("Unsupported clock or invalid nonce")
    if not 0<=offset<=0xffffffff or not 0<=length<=32768:
        raise ValueError("Read chunk exceeds bounded ABI")
    if operation==OPERATIONS["read"]:
        if not re.fullmatch(r"IMG[0-9]{5}\.(PNG|TMP)",name) or not length:
            raise ValueError("READ requires a generated filename and nonempty bounded chunk")
    elif offset or length or name:
        raise ValueError("Read parameters are only valid for READ")
    encoded=name.encode("ascii").ljust(16,b"\0")
    raw=struct.pack("<6I16s6I",0x53525131,operation,mode,sd_hz,offset,length,
                    encoded,nonce,0,0,0,0,0)
    return raw,dict(operation=operation,mode=mode,sd_clock_hz=sd_hz,offset=offset,
                    length=length,name=name,nonce=nonce)


def run_request(build,out,expected_sha,operation,mode,sd_hz=25000000,
                offset=0,length=0,name="",format_card=False,timeout=180):
    """Execute one bounded request; READ writes only its returned chunk to data.bin."""
    if operation==OPERATIONS["format"] and not format_card:
        raise ValueError("Destructive FORMAT requires explicit --format-card")
    if format_card and operation!=OPERATIONS["format"]:
        raise ValueError("--format-card is only valid for FORMAT")
    if not 1<=timeout<=1800:
        raise ValueError("Timeout must be 1..1800 seconds")
    manifest,code=checked_build(build.resolve(),expected_sha)
    command,request=make_request(operation,mode,sd_hz,offset,length,name,
                                 secrets.randbelow(0xffffffff)+1)
    bench=Bench(out)
    frozen=bench.output/"frozen-save.bin"
    frozen.write_bytes(code)
    json_file(bench.output/"manifest.json",manifest)
    json_file(bench.output/"request.json",dict(request,reviewed_sha256=expected_sha,
              format_explicit=format_card,reset_permitted=False,power_control_permitted=False))
    proof=preflight(bench,manifest,code)
    json_file(bench.output/"preflight.json",proof)
    if not proof["module_already_identical"]:
        bench.call("-halt","-w",frozen,hex(LOAD),"-v",
                   success="Download verified successfully")
    live=bench.upload(LOAD,len(code),"loaded-module.bin")
    if live!=code or sha(frozen.read_bytes())!=expected_sha:
        raise ValueError("Exact module readback failed before execution")
    command_path=bench.output/"request.bin"
    command_path.write_bytes(command)
    clear=bench.output/"clear-report.bin"
    clear.write_bytes(bytes(512))
    bench.call("-halt","-w",clear,hex(REPORT),"-v","-w",command_path,hex(REQUEST),"-v",
               success="Download verified successfully")
    if bench.upload(REQUEST,64,"request-readback.bin")!=command:
        raise ValueError("Request readback mismatch; nothing executed")
    context_proof(bench,{CACHE+0x72,CACHE+0x74,number(manifest["park_address"])},"ready")
    timing={"scope":"Host command/status brackets, not electrical synchronization",
            "run_before":host_stamp(),"polls":[]}
    json_file(bench.output/"host-timing.json",timing)
    bench.call("-halt","-coreReg","CONTROL=0","PRIMASK=1",
               "PC="+hex(number(manifest["bench_entry_address"])),"XPSR=0x01000000",
               "-run",success="Core run")
    timing["run_after"]=host_stamp()
    json_file(bench.output/"host-timing.json",timing)
    deadline=time.monotonic()+timeout
    report=None
    for poll in range(600):
        poll_timing={"index":poll,"before":host_stamp()}
        raw=bench.upload(REPORT,512,f"report-{poll:03d}.bin")
        poll_timing["after"]=host_stamp()
        report=decode_report(raw)
        poll_timing.update(state=report["state"],stage=report["stage"],
                           nonce=report["nonce"],terminal=report["terminal"])
        timing["polls"].append(poll_timing)
        json_file(bench.output/"host-timing.json",timing)
        if (report["magic"]==0x53564431 and report["schema"]==1
                and report["nonce"]==request["nonce"] and report["terminal"]==0x444F4E45):
            break
        if time.monotonic()>=deadline:
            json_file(bench.output/"last-report.json",report)
            raise TimeoutError("No fresh terminal report; target left running, no reset/retry")
        time.sleep(.2)
    else:
        raise TimeoutError("Poll limit reached; target left running, no reset/retry")
    card,fs=snapshots(bench,report,"result")
    result=dict(report=report,card=card,filesystem=fs,request=request,
                module_sha256=expected_sha,reset_sent=False,power_changed=False,
                nor_commands_sent=False,host_timing=timing)
    timing["target"]=dict(total_cycles=report["total"],cpu_hz=report["cpu_hz"],
                          mode=report["mode"],frame_fnv_before=report["fnv_before"],
                          frame_fnv_after=report["fnv_after"])
    json_file(bench.output/"host-timing.json",timing)
    json_file(bench.output/"result.json",result)
    # Failure records are saved, but no halt/retry/power change follows failure.
    validate_success(report,manifest,request)
    successful_snapshots(card,fs,report)
    result["final_context"]=context_proof(bench,{number(manifest["park_address"])},"final")
    if operation==OPERATIONS["read"]:
        count=report["read_bytes"]
        data=bench.upload(number(manifest["buffer_address"]),count,"data.bin") if count else b""
        if not count:
            (bench.output/"data.bin").write_bytes(b"")
        result["readback"]=dict(bytes=count,sha256=sha(data),offset=offset,name=name)
    json_file(bench.output/"result.json",result)
    return result


def self_test():
    """Pure host guards; no Bench instance, debugger, or instrument access."""
    import unittest

    class Guards(unittest.TestCase):
        def test_request_roundtrip(self):
            raw,request=make_request(3,2,25000000,123,32768,"IMG00001.PNG",44)
            words=struct.unpack("<16I",raw)
            self.assertEqual((len(raw),words[10],words[4],words[5]),(64,44,123,32768))
            self.assertEqual(request["nonce"],44)

        def test_request_rejections(self):
            for args in ((3,0,25000000,0,32769,"IMG00001.PNG",1),
                         (3,0,25000000,0,20,"../bad",1),
                         (1,0,25000000,0,20,"IMG00001.PNG",1),
                         (3,0,25000000,0,20,"IMG00001.PNG",0)):
                with self.assertRaises(ValueError):
                    make_request(*args)

        def test_exact_context(self):
            context=dict(PC=CACHE+0x72,CONTROL=0,PRIMASK=1,FAULTMASK=0,XPSR=0x01000000)
            validate_context(context,{CACHE+0x72})
            for key,value in (("PC",CACHE),("PRIMASK",0),("CONTROL",4),
                              ("FAULTMASK",1),("XPSR",0x01000003)):
                with self.assertRaises(ValueError):
                    validate_context(dict(context,**{key:value}),{CACHE+0x72})

        def test_decode_and_terminal_rejections(self):
            words=[0]*128
            values=dict(magic=0x53564431,schema=1,words=128,state=2,operation=4,
                        mode=1,cpu_hz=400000000,media_idle=1,width=1120,height=1364,
                        frame_bytes=FRAME_BYTES,buffer_bytes=32768,buffer_address=LOAD+4096,
                        stack_canary=0x5354414B,initial_msplim=0x343A0000,nonce=77)
            for key,value in values.items():
                words[FIELDS.index(key)]=value
            words[63]=0x444F4E45
            report=decode_report(struct.pack("<128I",*words))
            manifest={"buffer_address":hex(LOAD+4096)}
            validate_success(report,manifest,dict(operation=4,mode=1,nonce=77,length=0))
            for key,value in (("nonce",0),("state",3),("result",1),("media_idle",0),
                              ("ccr",0x20000),("terminal",0),("card_error",1)):
                with self.assertRaises(ValueError):
                    validate_success(dict(report,**{key:value}),manifest)
            with self.assertRaises(ValueError):
                validate_success(report,manifest,dict(operation=4,mode=1,nonce=78,length=0))

        def test_failed_or_active_prior_operation_never_halts(self):
            class ReadOnlyPrior:
                def __init__(self,raw):
                    self.raw=raw
                    self.reads=0
                def upload(self,address,length,name):
                    self.reads+=1
                    if (address,length)==(LOADER,64):
                        return bytes(64)
                    assert (address,length)==(REPORT,512)
                    return self.raw
                def call(self,*args,**kwargs):
                    raise AssertionError("A failed/active storage operation must not be halted")
            for state,terminal,result in ((1,0,0),(3,0x444F4E45,1),(2,0x444F4E45,1)):
                words=[0]*128
                for key,value in (("magic",0x53564431),("state",state),("result",result)):
                    words[FIELDS.index(key)]=value
                words[63]=terminal
                fake=ReadOnlyPrior(struct.pack("<128I",*words))
                with self.assertRaises(ValueError):
                    preflight(fake,{},b"")
                self.assertEqual(fake.reads,2)

        def test_loader_activity_refuses_even_before_module_magic(self):
            report=decode_report(bytes(512))
            loader=[0]*16
            self.assertFalse(validate_storage_activity(loader,report))
            loader[0]=0x534C4431
            with self.assertRaisesRegex(ValueError,"loader is active"):
                validate_storage_activity(loader,report)
            loader[8]=128; loader[9]=10; loader[11]=20
            with self.assertRaisesRegex(ValueError,"no completed storage-module"):
                validate_storage_activity(loader,report)
            loader[10]=0xffffffff
            with self.assertRaisesRegex(ValueError,"loader is active"):
                validate_storage_activity(loader,report)

        def test_format_flag_required_before_any_build_or_bench_access(self):
            with self.assertRaisesRegex(ValueError,"explicit --format-card"):
                run_request(Path("nonexistent"),Path("unused"),"0"*64,2,1)

        def test_layout_hash_bounds_and_park(self):
            code=b"\xfe\xe7"+bytes(126)
            manifest=dict(schema=1,load_address=hex(LOAD),entry_address=hex(LOAD|1),
                          stack_floor="0x343a0000",stack_top="0x343b0000",
                          request_address=hex(REQUEST),report_address=hex(REPORT),
                          buffer_bytes=32768,binary_bytes=len(code),binary_sha256=sha(code),
                          bss_start=hex(LOAD+128),bss_end=hex(LOAD+65536),
                          buffer_address=hex(LOAD+4096),bench_entry_address=hex(LOAD+3),
                          park_address=hex(LOAD))
            validate_layout(manifest,code,sha(code))
            for key,value in (("buffer_address",hex(FRAME)),("park_address",hex(LOAD+2)),
                              ("bss_end",hex(0x343B0000)),("request_address",hex(FRAME))):
                with self.assertRaises(ValueError):
                    validate_layout(dict(manifest,**{key:value}),code,sha(code))
            with self.assertRaises(ValueError):
                validate_layout(manifest,code,"0"*64)

    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Guards))
    if not result.wasSuccessful():
        raise SystemExit(1)


def main():
    if sys.argv[1:]==["--self-test"]:
        self_test()
        return
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation",choices=OPERATIONS)
    parser.add_argument("--build",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--expected-sha256",required=True)
    parser.add_argument("--mode",choices=MODES,default="fast-none")
    parser.add_argument("--sd-clock-hz",type=int,choices=(100000,12500000,25000000),default=25000000)
    parser.add_argument("--format-card",action="store_true")
    parser.add_argument("--name",default="")
    parser.add_argument("--offset",type=int,default=0)
    parser.add_argument("--length",type=int,default=0)
    parser.add_argument("--timeout",type=float,default=180)
    parser.add_argument("--execute",action="store_true",help="Explicitly execute the guarded RAM request")
    args=parser.parse_args()
    if not args.execute:
        parser.error("Use --execute only after exclusive bench ownership is established")
    result=run_request(args.build,args.out,args.expected_sha256,OPERATIONS[args.operation],
                       MODES[args.mode],args.sd_clock_hz,args.offset,args.length,args.name,
                       args.format_card,args.timeout)
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    main()
