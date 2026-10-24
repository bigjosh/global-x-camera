"""Read PNG files using exact early recovery, a RAM bridge and frozen v8b READ.

Offline validation is the default. Only the exclusive bench owner may use
--execute. There is no reset, power control, NOR command, FORMAT, SAVE, delete,
or retry interface. Any unexpected result stops with the target left powered.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import secrets
import struct
import subprocess
import sys
import time
import zlib

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
spec=importlib.util.spec_from_file_location("capture_sd_bench",ROOT/"firmware/capture-sd/bench.py")
sd=importlib.util.module_from_spec(spec)
spec.loader.exec_module(sd)
BOOT_SHA="9d0a4553845dbf033264bde3629e2601aac561799cac9e34ed841f32485abdb6"
MODULE_SHA="91e1edfa43f95a9608b94457cfbf900c6f51d5ecd10d2b3b7667c84d40cd3844"
MODULE_MANIFEST_SHA="09685b857c2e2fd8d3ea01a614edb8d097131b0a7f941eec443d29ec69759b4d"
RECOVERY_SHA="9a6c498a94c9415ec3dc39933bae2e958ceb0a43b53a1b2c8b931ef26475d071"
SECTOR_SHA="7fda9d00cc7ffb3fbb9e6aac6695cf18545754b5dbfce1520cf30b2da39c4e63"
# Each entry requires an independent exact-prefix/sector review. There is no
# command-line opt-in for unknown firmware. This table does not broaden the
# bridge or READ-module identities, and check_park still verifies live code.
APPROVED_RECOVERY={
    # RAW v16 preerase: exact unchanged early recovery, two CRC literal changes.
    '31b8a97eb8a68e574c1adab17e44b838044277bd95f81f5b22c30b9fdaaccd2e':
        dict(name="raw-v16-preerase-standby",sector_sha256=
             '285fba4951f88deb12033e7b3c2948c802371862982da5a8e304c6cae35fb58f'),
    '2bafcb1a4d2fe20d2ae6ae9a04d3a43416a5ed7f50bbea7e0e29959aa13094eb':
        dict(name="raw-v16-preerase-awake",sector_sha256=
             '52edac834cc8aebd649c8d35a8f3fd6ef20e2e6c12dc99bcf0944a636d445508'),
    # RAW v15 Standby: fresh receiver RLOK guard; exact early recovery unchanged.
    # Admission supports qualification and is not evidence of installation.
    'db234498a9b347f6cb9f41daf22da1fb0f9266dba264b9ca203ef33d1b1711df':
        dict(name="raw-v15-standby",sector_sha256=
             'efb3c440e008e448a1682285034fe30b77bdbb5834024da9de787f3f51f42629'),
    # RAW v12 Standby; phase-v2 timing and CRC relocation do not change recovery.
    '82ce8c0411a0990c7a5081633cb358012bbd081fcb7368241010091f7d1f913b':
        dict(name="raw-v12-standby",sector_sha256=
             '03cbd89553944838922bbcd7e2b21813297f3466db64730c5e3e2903a7942424'),
    # RAW v9 awake, independently checked identical early recovery guard.
    # Only the existing READ-only bridge is admitted from this exact pair.
    '55525083edf15a7961d6ad27eb2bb3b54063fc9e597bde5a6008c94d760adcf5':
        dict(name="raw-v9-awake",sector_sha256=
             'dd4db5228d3a4fe9c352630201bacfe1dfd08888725e6f5a63be2a4fb82392bc'),
    RECOVERY_SHA:dict(name="v59",sector_sha256=SECTOR_SHA),
    # Historical v65 early recovery remains usable for READ. Its later
    # schema-1 loader gate refused shutdown; this is not Standby approval.
    "6f07ee096565b43a8d5c1f09a0dc28e300599667bda4b025868cb278288baefb":
        dict(name="v65-normal-standby",sector_sha256=
             "409628f664b41b39b8a6397d9098a7bd3420d23c9d8441538e11e59ae9ee593c"),
    # v66c fixes the late-loader schema/profile gate. Exact early recovery,
    # SRAM initializer, complete region map and fixed loader reviewed.
    "247f27c231e0053b7024af29914c6a0cb1b7decb1632ac0d6142a68b89e2da58":
        dict(name="v66c-normal-standby",sector_sha256=
             "8129f9cc79e92c678207b4aee838810cc805d0b860c40b2f77b434ae746c8b61"),
}
LOAD,BOOT_REQUEST,BOOT_PROOF=0x341E0000,0x341B4000,0x341B4100
BOOT_PARK=0x341E0016
MAX_BYTES=3100000
BOOT_FIELDS="""magic schema words nonce result stage ccr control ipsr primask
faultmask fpccr mpu cfgr1 cfgr2 ahb5enr ahb5rstr xspi_sr memory_result memenr
dwt_ctrl dwt_delta terminal""".split()


def checked_bridge(path):
    m=json.loads((path/"manifest.json").read_text())
    code=(path/"boot.bin").read_bytes()
    exact=dict(schema=1,load=LOAD,entry=LOAD|1,park=BOOT_PARK,
        stack_floor=0x341B6000,stack_top=0x341B8000,request=BOOT_REQUEST,
        proof=BOOT_PROOF,proof_words=23,binary_bytes=1324,binary_sha256=BOOT_SHA,
        sd_commands=False,nor_commands=False,reset=False,power_switch=False)
    if any(m.get(k)!=v for k,v in exact.items()) or sd.sha(code)!=BOOT_SHA:
        raise ValueError("Bridge is not the exact reviewed executable/layout")
    if code[BOOT_PARK-LOAD:BOOT_PARK-LOAD+2]!=b"\xfe\xe7":
        raise ValueError("Bridge park instruction differs")
    if set(m.get("source_hashes",{}))!={"boot.c","entry.S","boot.ld","raw10_memory.c"}:
        raise ValueError("Bridge source manifest incomplete")
    for name,want in m["source_hashes"].items():
        if sd.sha((path/name).read_bytes())!=want:
            raise ValueError("Frozen bridge source changed: "+name)
    return m,code


def checked_module(path):
    if sd.sha((path/"manifest.json").read_bytes())!=MODULE_MANIFEST_SHA:
        raise ValueError("Only the frozen qualified v8b manifest is supported")
    m,code=sd.checked_build(path,MODULE_SHA)
    if (m["binary_bytes"]!=27420 or sd.number(m["bench_entry_address"])!=0x34320051
            or sd.number(m["park_address"])!=0x3432006E
            or sd.module_buffer(m,3)!=(0x3432EB40,262144)):
        raise ValueError("Frozen module READ layout differs")
    return m,code


def checked_recovery(path):
    prefix=(path/"stage1.bin").read_bytes()
    sector=(path/"capture_sector_0.bin").read_bytes()
    digest=sd.sha(prefix)
    approved=APPROVED_RECOVERY.get(digest)
    if (approved is None or len(prefix)!=5140 or len(sector)!=65536 or
            sd.sha(sector)!=approved["sector_sha256"]):
        raise ValueError("Unreviewed recovery prefix/sector pair")
    return dict(approved,prefix_sha256=digest)


def checked_recovery_result(result,identity):
    if (result.get("passed") is not True or
            result.get("prefix_sha256")!=identity["prefix_sha256"]):
        raise ValueError("Fresh guard did not prove the selected recovery image")


def checked_names(names):
    if not 1<=len(names)<=16 or len(set(names))!=len(names):
        raise ValueError("Specify 1..16 distinct known PNG names")
    if any(not re.fullmatch(r"IMG[0-9]{5}\.PNG",n) for n in names):
        raise ValueError("Only known IMGnnnnn.PNG names are accepted")
    return names


def read_request(name,offset,nonce):
    checked_names([name])
    if offset%262144 or not 0<=offset<MAX_BYTES:
        raise ValueError("READ offset is outside the bounded file walk")
    # Operation and mode are constants, never caller-controlled.
    return sd.make_request(3,1,25000000,offset,262144,name,nonce,262144)


def checked_boot(raw,nonce):
    if len(raw)!=92:
        raise ValueError("Incomplete bridge proof")
    p=dict(zip(BOOT_FIELDS,struct.unpack("<23I",raw)))
    exact=dict(magic=0x52425231,schema=1,words=23,nonce=nonce,result=0,stage=3,
        control=0,ipsr=0,primask=1,faultmask=0,cfgr1=0x33330000,
        cfgr2=0x00100000,memory_result=0,terminal=0x5242444E)
    if (any(p[k]!=v for k,v in exact.items()) or p["ccr"]&0x30000
            or p["fpccr"]&1 or p["mpu"]&1 or p["xspi_sr"]&0x7F20
            or not p["dwt_ctrl"]&1 or not p["dwt_delta"]):
        raise ValueError("Bridge did not complete the exact guarded SRAM setup")
    return p


def read_only_success(report,card,fs,manifest,request):
    sd.validate_success(report,manifest,request)
    sd.successful_snapshots(card,fs,report)
    if (report["operation"]!=3 or card["written_sectors"] or card["write_cycles"]
            or fs["bytes_written"] or fs["completed"] or report["png_bytes"]
            or report["fnv_before"] or report["fnv_after"]
            or report["postclean_validated"]):
        raise ValueError("READ unexpectedly reports a write or capture operation")


def verify_png(path,expected_sha=None):
    """Independent PNG integrity/decode check; no lost-RAW-frame claim."""
    from PIL import Image
    raw=path.read_bytes()
    if not 0<len(raw)<=MAX_BYTES or raw[:8]!=b"\x89PNG\r\n\x1a\n":
        raise ValueError("Invalid PNG size/signature")
    offset=8; kinds=[]; significant=None; idat=False
    while offset<len(raw):
        if offset+12>len(raw):
            raise ValueError("Truncated PNG chunk")
        count,=struct.unpack_from(">I",raw,offset)
        end=offset+count+12
        if end>len(raw):
            raise ValueError("PNG chunk exceeds file")
        kind=raw[offset+4:offset+8]; data=raw[offset+8:end-4]
        crc,=struct.unpack_from(">I",raw,end-4)
        if zlib.crc32(kind+data)&0xFFFFFFFF!=crc:
            raise ValueError("PNG chunk CRC mismatch")
        kinds.append(kind.decode("ascii"))
        if kind==b"IHDR" and struct.unpack(">IIBBBBB",data)!=(1120,1364,16,0,0,0,0):
            raise ValueError("Unexpected PNG format")
        if kind==b"sBIT": significant=data
        if kind==b"IDAT": idat=True
        if kind==b"IEND" and (count or end!=len(raw)):
            raise ValueError("IEND is not empty/final")
        offset=end
    if (not kinds or kinds[0]!="IHDR" or kinds[-1]!="IEND" or
            kinds.count("IHDR")!=1 or kinds.count("IEND")!=1 or
            significant!=b"\x0a" or not idat):
        raise ValueError("Required PNG structure missing")
    minimum,maximum,count=65535,0,0
    with Image.open(path) as image:
        image.load()
        if image.size!=(1120,1364):
            raise ValueError("Decoded size differs")
        for value in (image.get_flattened_data() if hasattr(image,"get_flattened_data")
                      else image.getdata()):
            if not isinstance(value,int) or not 0<=value<=65535 or value&63:
                raise ValueError("Decoded sample does not match 10-bit left-aligned format")
            minimum=min(minimum,value); maximum=max(maximum,value); count+=1
    digest=sd.sha(raw)
    if expected_sha is not None and digest!=expected_sha:
        raise ValueError("File differs from the separately supplied known SHA-256")
    return dict(bytes=len(raw),sha256=digest,all_png_chunk_crcs_valid=True,
        complete_independent_decode=True,pixels=count,width=1120,height=1364,
        format="PNG grayscale16",sBIT=10,all_samples_10bit_left_aligned=True,
        pixel_min=minimum,pixel_max=maximum,discernible_dynamic_range=maximum>minimum,
        exact_capture_pixel_comparison=False,
        reason="The pre-Standby RAW frame is unavailable",
        known_file_hash_matched=expected_sha is not None)


def wait_boot(bench,nonce):
    for poll in range(12):
        raw=bench.upload(BOOT_PROOF,92,f"boot-proof-{poll:02d}.bin")
        words=struct.unpack("<23I",raw)
        if words[0]==0x52425231 and words[3]==nonce and words[22]==0x5242444E:
            return checked_boot(raw,nonce)
        time.sleep(.1)
    raise TimeoutError("No bridge terminal proof; no further write/reset/retry")


def bootstrap(args,out,boot_code):
    identity=checked_recovery(args.recovery_build.resolve())
    b=sd.Bench(out/"bootstrap")
    guard=ROOT/"firmware/capture-timing/recovery_gpio/check_park.py"
    proc=subprocess.run([sys.executable,str(guard),"--build",
        str(args.recovery_build.resolve()),"--out",str(b.output/"early-guard")],
        capture_output=True,timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
    (b.output/"early-guard.log").write_bytes(proc.stdout+proc.stderr)
    if proc.returncode:
        raise RuntimeError("Fresh exact early-recovery guard failed; no bridge write")
    result=json.loads((b.output/"early-guard/result.json").read_text())
    checked_recovery_result(result,identity)
    nonce=secrets.randbelow(0xFFFFFFFF)+1
    request=struct.pack("<4I",0x52425231,nonce,0,0)
    (b.output/"request.bin").write_bytes(request)
    (b.output/"clear.bin").write_bytes(bytes(92))
    b.call("-halt","-w",(args.bridge/"boot.bin").resolve(),hex(LOAD),"-v",
           success="Download verified successfully")
    if b.upload(LOAD,len(boot_code),"bridge-readback.bin")!=boot_code:
        raise ValueError("Bridge RAM differs; not executed")
    b.call("-halt","-w",b.output/"clear.bin",hex(BOOT_PROOF),"-v",
        "-w",b.output/"request.bin",hex(BOOT_REQUEST),"-v",
        success="Download verified successfully")
    if (b.upload(BOOT_PROOF,92,"cleared.bin")!=bytes(92) or
            b.upload(BOOT_REQUEST,16,"request-readback.bin")!=request):
        raise ValueError("Bridge request/status readback differs")
    b.call("-halt","-coreReg","PC=0x341E0001","XPSR=0x01000000",
           "-run",success="Core run")
    proof=wait_boot(b,nonce)
    context=sd.context_proof(b,{BOOT_PARK},"bridge-final")
    memory=b.upload(0x341F5000,128,"memory-proof.bin")
    if struct.unpack_from("<2I",memory)!=(0x5231304D,0):
        raise ValueError("Expanded memory initializer did not succeed")
    sd.json_file(b.output/"verified.json",dict(proof=proof,context=context,
        early_recovery=result,recovery_identity=identity,bridge_sha256=BOOT_SHA))
    return b


def exact_prior_read(b,manifest,code,prior):
    raw=b.upload(sd.REPORT,512,"prior-report.bin")
    report=sd.decode_report(raw)
    card,fs=sd.snapshots(b,report,"prior")
    read_only_success(report,card,fs,manifest,prior)
    expected,_=read_request(prior["name"],prior["offset"],prior["nonce"])
    if b.upload(sd.REQUEST,64,"prior-request.bin")!=expected:
        raise ValueError("Prior READ request differs")
    if b.upload(sd.LOAD,len(code),"prior-code.bin")!=code:
        raise ValueError("Prior module code differs")
    sd.context_proof(b,{0x3432006E},"prior")


def chunk(out,manifest,code,name,offset,prior):
    b=sd.Bench(out)
    if prior is not None:
        exact_prior_read(b,manifest,code,prior)
    else:
        sd.context_proof(b,{BOOT_PARK},"initial")
        if b.upload(sd.LOAD,len(code),"initial-code.bin")!=code:
            raise ValueError("Initial module readback differs")
    command,request=read_request(name,offset,secrets.randbelow(0xFFFFFFFF)+1)
    (b.output/"request.bin").write_bytes(command)
    (b.output/"clear.bin").write_bytes(bytes(512))
    b.call("-halt","-w",b.output/"clear.bin",hex(sd.REPORT),"-v",
           "-w",b.output/"request.bin",hex(sd.REQUEST),"-v",
           success="Download verified successfully")
    if (b.upload(sd.REQUEST,64,"request-readback.bin")!=command or
            b.upload(sd.REPORT,512,"cleared-report.bin")!=bytes(512)):
        raise ValueError("READ request/clear differs; not executed")
    sd.context_proof(b,{BOOT_PARK if prior is None else 0x3432006E},"ready")
    b.call("-halt","-coreReg","PC=0x34320051","XPSR=0x01000000",
           "-run",success="Core run")
    deadline=time.monotonic()+90
    for poll in range(60):
        report=sd.decode_report(b.upload(sd.REPORT,512,f"report-{poll:02d}.bin"))
        if (report["magic"]==0x53564431 and report["nonce"]==request["nonce"] and
                report["terminal"]==0x444F4E45):
            break
        if time.monotonic()>deadline:
            raise TimeoutError("READ did not terminate; no halt/reset/retry")
        time.sleep(.1)
    else:
        raise TimeoutError("READ poll bound exceeded; no halt/reset/retry")
    card,fs=sd.snapshots(b,report,"result")
    result=dict(report=report,card=card,filesystem=fs,request=request,
        module_sha256=MODULE_SHA,reset_sent=False,power_changed=False,
        nor_commands_sent=False)
    sd.json_file(b.output/"result.json",result)
    read_only_success(report,card,fs,manifest,request)
    if b.upload(sd.REQUEST,64,"completed-request.bin")!=command:
        raise ValueError("Completed READ request differs from the selected filename/offset")
    result["context"]=sd.context_proof(b,{0x3432006E},"final")
    count=report["read_bytes"]
    data=b.upload(report["buffer_address"],count,"data.bin") if count else b""
    if not count: (b.output/"data.bin").write_bytes(b"")
    result["data_sha256"]=sd.sha(data)
    sd.json_file(b.output/"verified.json",result)
    return data,request


def execute(args,manifest,code,boot_code):
    identity=checked_recovery(args.recovery_build.resolve())
    out=args.out.resolve()
    out.relative_to((ROOT/"tmp").resolve())
    out.mkdir(parents=True,exist_ok=False)
    sd.json_file(out/"plan.json",dict(names=args.name,module_sha256=MODULE_SHA,
        bridge_sha256=BOOT_SHA,recovery_identity=identity,
        raw_frame_available=False,read_only=True))
    b=bootstrap(args,out,boot_code)
    frozen=b.output/"frozen-save.bin"; frozen.write_bytes(code)
    b.call("-halt","-w",frozen,hex(sd.LOAD),"-v",success="Download verified successfully")
    if b.upload(sd.LOAD,len(code),"module-readback.bin")!=code:
        raise ValueError("Frozen module RAM readback differs")
    # Old LPL/LPM records are deliberately retained; ordinary maintenance stays
    # blocked. This separate path follows only the fresh bootstrap/READ proofs.
    prior=None; results=[]
    for name in args.name:
        folder=out/name.removesuffix(".PNG")
        folder.mkdir()
        image=bytearray()
        for index in range(12):
            data,prior=chunk(folder/f"chunk-{index:02d}",manifest,code,
                             name,len(image),prior)
            image.extend(data)
            if len(image)>MAX_BYTES:
                raise ValueError("File exceeds the prototype PNG bound")
            if len(data)<262144:
                break
        else:
            raise ValueError("No EOF within bounded file walk")
        path=folder/name; path.write_bytes(image)
        result=verify_png(path,args.known_sha.get(name))
        result.update(name=name,read_chunks=index+1,readonly_card_writes=0)
        sd.json_file(folder/"verified.json",result)
        results.append(result)
        print(json.dumps(result),flush=True)
    sd.json_file(out/"verified.json",dict(files=results,read_only=True,
        target_state="Exact v8b READ terminal park; SD deinitialized; caches off",
        nor_image_changed=False,raw_frame_comparison=False))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--bridge",type=Path,required=True)
    p.add_argument("--module",type=Path,required=True)
    p.add_argument("--recovery-build",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--name",action="append",required=True)
    p.add_argument("--known-sha",action="append",default=[],metavar="NAME=SHA256")
    p.add_argument("--execute",action="store_true")
    a=p.parse_args()
    checked_names(a.name)
    known={}
    for item in a.known_sha:
        name,sep,digest=item.partition("=")
        if not sep or name not in a.name or name in known or not re.fullmatch("[0-9a-f]{64}",digest):
            p.error("--known-sha needs a selected unique NAME=lowercase SHA256")
        known[name]=digest
    a.known_sha=known
    identity=checked_recovery(a.recovery_build.resolve())
    _,boot=checked_bridge(a.bridge.resolve())
    manifest,code=checked_module(a.module.resolve())
    if not a.execute:
        print(json.dumps(dict(offline_valid=True,bridge_sha256=BOOT_SHA,
            module_sha256=MODULE_SHA,recovery_identity=identity,
            names=a.name,read_only=True),indent=2))
        return
    execute(a,manifest,code,boot)


if __name__=="__main__":
    main()
