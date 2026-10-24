"""Bounded inspection of one completed awake RAW flash capture.

Only SRAM uploads occur before exact successful proof, card/slot snapshots,
immutable code and late-loader validation. The sole execution-control command
is the existing halt/core-register query, issued only after those checks.
No reset, power switching, RAM writes, firmware writes, NOR or SD commands.
Nonce zero is explicitly a flash capture, never accepted as a RAM request.
"""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import re
import struct
import zlib

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
spec=importlib.util.spec_from_file_location('raw_flash_shared_bench',HERE/'bench.py')
bench=importlib.util.module_from_spec(spec);spec.loader.exec_module(bench)
sha=bench.sha


def checked_build(folder,receiver_sha,sector_sha):
    folder=Path(folder).resolve()
    if any(not re.fullmatch('[0-9a-f]{64}',s) for s in (receiver_sha,sector_sha)):
        raise ValueError('Explicit lowercase receiver and sector SHA256 required')
    m=json.loads((folder/'manifest.json').read_text())
    p=json.loads((folder/'staged/manifest.json').read_text())
    code=(folder/'capture.bin').read_bytes(); sector=(folder/'staged/capture_sector_0.bin').read_bytes()
    exact=dict(schema=1,kind='raw-slots',load=bench.LOAD,stack=0x343B0000,
        stack_floor=0x343AF000,request=bench.REQUEST,proof=bench.PROOF,proof_words=96,
        **bench.frame_layout(m),width=1120,height=1364,
        flash=True,standby=False,pattern=0,preinit=False,line_snapshots=False,line_poison=False)
    if any(m.get(k)!=v for k,v in exact.items()): raise ValueError('Only reviewed flash/awake scene layout accepted')
    if (sha(code)!=receiver_sha or m['binary_sha256']!=receiver_sha or len(code)!=m['binary_bytes'] or
        not 0<len(code)<0xE000 or len(code)%4 or struct.unpack_from('<II',code)!=(m['stack'],m['entry'])):
        raise ValueError('Receiver executable identity/layout differs')
    if (len(sector)!=65536 or sha(sector)!=sector_sha or p['program_sha256']!=sector_sha or
        p['stage2_manifest_sha256']!=sha((folder/'manifest.json').read_bytes()) or
        p['stage2_full_sha256']!=receiver_sha or p['stage2_full_bytes']!=len(code) or
        sector[0x2000:0x2000+len(code)]!=code or
        p.get('completion_policy')!='Awake RAW terminal park'):
        raise ValueError('Sector/prefix/receiver manifest binding differs')
    prefix=(folder/'staged/stage1.bin').read_bytes(); boot=(folder/'staged/stage1_boot.bin').read_bytes()
    if (sha(prefix)!=p['stage1_raw_sha256'] or len(prefix)!=p['stage1_raw_bytes'] or
        sector[:len(boot)]!=boot or not p.get('checked_recovery_literal_offsets')):
        raise ValueError('Recovery prefix binding differs')
    for name,want in m['source_hashes'].items():
        path=(folder/name).resolve();path.relative_to(folder)
        if sha(path.read_bytes())!=want: raise ValueError('Frozen receiver source changed: '+name)
    for rel,want in p['sources'].items():
        path=folder/'staged'/Path(rel).name
        if sha(path.read_bytes())!=want: raise ValueError('Frozen prefix source changed: '+str(rel))
    late=m['late_load']; begin,end=late['late_address'],bench.LOAD+len(code)
    early=late['early_bytes'];tail=code[early:]
    if (p['late_load']!=late or early!=15804 or begin!=bench.LOAD+early or
        late['late_bytes']!=len(tail) or late['late_flash_offset']!=0x2000+early or
        late['late_crc32']!=zlib.crc32(tail) or late['proof']!=0x343F9E00 or
        not late['after_arm'] or not late['interrupts_enabled'] or
        not late['layout_audit']['vectors_early'] or not late['layout_audit']['early_irq_symbols'] or
        p['stage2_bytes']!=early or p['stage2_sha256']!=sha(code[:early]) or
        int(p['stage2_crc32'],0)!=zlib.crc32(code[:early]) or
        (folder/'staged/stage2.bin').read_bytes()!=code[:early] or
        (folder/'staged/stage2-full.bin').read_bytes()!=code):
        raise ValueError('Split-load identity/layout differs')
    spans=[[bench.LOAD,m['data_start']],[begin,end]]
    if (late['immutable_ranges']!=spans or m['immutable_ranges']!=spans or
        not bench.LOAD<m['data_start']<=m['system_core_clock']<m['data_end']<=begin or
        not end<=m['bss_start']<=m['card']<=m['bss_end']-200<m['stack_floor'] or
        not m['bss_start']<=m['slots']<=m['bss_end']-640 or
        m['card']<m['slots']+640 and m['slots']<m['card']+200):
        raise ValueError('Code/data/BSS/card/slot overlap')
    for key in ('park','reject_park'):
        off=m[key]-bench.LOAD
        if not 0<=off<len(code)-1 or code[off:off+2]!=b'\xfe\xe7':
            raise ValueError('Missing exact terminal branch')
    flags=('async_stop','line_stream','preinit','line_snapshots','line_poison','dma_sleep','whole_image_preerase','magic_format')
    if m['expected_flags']!=sum(int(bool(m.get(k,False)))<<i for i,k in enumerate(flags)):
        raise ValueError('Feature flags differ')
    bench.whole_layout(m)
    bench.magic_layout(m)
    return m,p,code


def fresh_boot(path,receiver_sha,sector_sha,now=None):
    path=Path(path).resolve();p=json.loads(path.read_text())
    if (p.get('schema')!=1 or p.get('bench_owner')!='root' or
        p.get('kind')!='raw-flash-cold-boot' or p.get('cold_boot_confirmed') is not True or
        p.get('binary_sha256')!=receiver_sha or p.get('sector_sha256')!=sector_sha):
        raise ValueError('Root fresh cold-boot identity is required for nonce0')
    at=datetime.fromisoformat(p['observed_utc'].replace('Z','+00:00'))
    if at.tzinfo is None or not 0<=((now or datetime.now(timezone.utc))-at).total_seconds()<=600:
        raise ValueError('Cold-boot evidence is future-dated or older than10minutes')
    if not p.get('evidence'): raise ValueError('Cold-boot evidence hashes required')
    for item in p['evidence']:
        file=Path(item['path']);file=file if file.is_absolute() else path.parent/file
        if sha(file.read_bytes())!=item['sha256']: raise ValueError('Cold-boot evidence changed')
    return p


def validate_proof(p,m):
    exact=dict(magic=bench.MAGIC,schema=1,words=96,nonce=0,operation=1,state=3,result=0,
        stage=8,terminal=bench.DONE,frame=bench.frame_layout(m)['frame'],bytes=bench.FRAME_BYTES,
        width=1120,height=1364,card=m['card'],card_size=200,slots=m['slots'],slots_size=640,
        sd_error=0,media_idle=1,initialized=0,controller_owned=0,cleanup_error=0,
        control=0,ipsr=0,primask=1,cpacr=0,pattern=0,completion=0,
        transport=int(m['transport']=='idma'),chunk_sectors=m['chunk_sectors'],flags=m['expected_flags'],
        camera_ready=bench.FRAME_BYTES,dma_bytes=bench.FRAME_BYTES,frames=1,errors=0,
        canary=0,format=10,data_type=0x30,vc0cfgr1=0x201,written_sectors=3730,capture_error=0)
    if any(p.get(k)!=v for k,v in exact.items()): raise ValueError('Flash capture is not successful/complete/idle')
    if (p['ccr']&0x30000 or p['fpccr']&1 or p['systick']&3 or p['last_ready']&0x1F00!=0x900 or
        not p['slot_count']>p['slot'] or p['p0fctcr']&8 or p['cmsr1']&0x8000 or p['csi_sr0']&0x20000 or
        p['chunk_overflow'] or not 1<=p['chunk_count']<=128):
        raise ValueError('Flash camera/slot/terminal context differs')
    bench.capture_geometry(p,m)
    for field in ('begin','arm','frame_done','camera_stop','first_write','commit_done','deinit_done','end'):
        if not p[field]: raise ValueError('Missing completion timestamp: '+field)


def validate_loader(raw,m):
    w=list(struct.unpack('<16I',raw));late=m['late_load']
    if (w[0]!=0x524C4431 or w[2]!=late['late_address'] or w[3]!=late['late_bytes'] or
        not w[1] or w[4]&0x7F21 or not w[4]&2 or w[5]!=w[3] or
        w[6]!=late['late_crc32'] or w[7]!=w[6] or not w[8] or not w[9] or
        any(w[10:15]) or w[15]!=0x524C4F4B):
        raise ValueError('Late load is incomplete/failed/unbound; no maintenance permission')
    return w


def validate_slots(raw,p,m):
    if len(raw)!=640: raise ValueError('Incomplete slot object')
    u=struct.unpack_from('<16I',raw); generation=struct.unpack_from('<Q',raw,8)[0]
    if (u[0]!=m['card'] or not u[1]&1 or not m['late_load']['late_address']<=u[1]-1<bench.LOAD+m['binary_bytes'] or
        generation!=(p['generation_hi']<<32|p['generation_lo']) or
        list(u[4:8])!=[p['slot_count'],p['slot'],p['payload_lba'],3730] or
        list(u[8:12])!=[1,0,0,0] or u[12]!=p['scan_headers']):
        raise ValueError('Slot object ownership/state differs')
    header=raw[128:];h=struct.unpack('<128I',header)
    if (header[:8]!=b'GXRAWSL1' or h[2]!=1 or h[3]!=0x4C4C5546 or
        h[4]!=p['generation_lo'] or h[5]!=p['generation_hi'] or
        list(h[6:13])!=[p['slot'],bench.FRAME_BYTES,p['payload_lba'],1120,1364,1400,1] or
        h[22]!=bench.FRAME_BYTES or any(header[92:508]) or zlib.crc32(header[:508])!=h[127]):
        raise ValueError('Retained FULL header malformed; this is not SD readback')
    return dict(generation=generation,slot=p['slot'],payload_lba=p['payload_lba'],header_crc=h[127])


def profile_fields(folder):
    """Read names from the hash-bound build copy, never a live source revision."""
    text=(folder/'capture_profile.h').read_text()
    for name,value in [('ADDRESS','0x343F8A80'),('MAGIC','0x52435032'),('SCHEMA','2'),('WORDS','32')]:
        if not re.search(r'#define CAPTURE_PROFILE_'+name+r'\s+'+value+r'U\b',text):
            raise ValueError('Unreviewed capture-profile layout')
    body=text.split('enum capture_profile_word {',1)[1].split('};',1)[0]
    names=re.findall(r'\bCP_([A-Z0-9_]+)\b',body)
    if len(names)!=27 or len(set(names))!=27:raise ValueError('Unexpected capture-profile enum')
    return [n.lower() for n in names]+['reserved_'+str(n) for n in range(27,32)]


def camera_telemetry(b,folder,m):
    """SRAM records only, after the completion/identity/context gates passed."""
    raw=b.upload(0x343F8A80,128,'capture-profile.bin')
    (b.output.parent/'capture-profile.bin').write_bytes(raw)
    p=dict(zip(profile_fields(folder),struct.unpack('<32I',raw)))
    if p['magic']!=0x52435032 or p['schema']!=2 or p['words']!=32:
        raise ValueError('Capture-profile SRAM schema differs')
    pairs=dict(essential_checks=('post_frame_begin','essential_done'),
        pipe_stop=('pipe_stop_begin','pipe_stop_done'),
        data_disable=('pipe_stop_done','data_off_done'),
        sensor_stop=('data_off_done','sensor_stop_done'),
        optional_frame_scan=('scan_begin','scan_done'),
        optional_register_reads=('diagnostic_reads_begin','diagnostic_reads_done'),
        post_frame_to_handoff=('post_frame_begin','handoff_ready'))
    timing={name:((p[end]-p[start])&0xFFFFFFFF)/400000.0
            if p[start] and p[end] else None for name,(start,end) in pairs.items()}
    raw=b.upload(0x343F8000,544*4,'fast.bin');(b.output.parent/'fast.bin').write_bytes(raw)
    words=list(struct.unpack('<544I',raw));header=words[:32]
    if header[0]!=0x46505931 or header[8]!=1 or header[2]>32:
        raise ValueError('FAST SRAM schema/count differs')
    fields=('event cycles tick sr0 sr1 ier0 ier1 prcr pcr cr lmcfgr apb5rstr '
            'pa0 frames vsyncs strobe_ordinal').split()
    records=[dict(zip(fields,words[32+i*16:48+i*16])) for i in range(header[2])]
    return dict(capture_profile=p,capture_profile_intervals_ms=timing,
        interval_clock='400 MHz DWT active cycles; sensor_stop includes asynchronous polling gaps; skipped pairs are null',
        dma_sleep_enabled=bool(m.get('dma_sleep')),fast_header=header,fast_records=records,
        fast_unused_record_bytes_ignored=True)


def inspect(b,folder,m,code,*,download_frame=False):
    names=bench.fields(folder)
    p=bench.decode(b.upload(bench.PROOF,384,'proof-before.bin'),names)
    validate_proof(p,m)
    card=bench.card_snapshot(b,m,p,'before')
    slots=(bench.magic_snapshot(b,m,p,'before',card) if m.get('magic_format') else
           validate_slots(b.upload(m['slots'],640,'slots-before.bin'),p,m))
    loader=validate_loader(b.upload(m['late_load']['proof'],64,'late-loader.bin'),m)
    for index,(start,end) in enumerate(m['immutable_ranges']):
        if b.upload(start,end-start,f'code-{index}.bin')!=code[start-bench.LOAD:end-bench.LOAD]:
            raise ValueError('Immutable early/late receiver code changed')
    whole=bench.frame_guards(b,m,p)
    if struct.unpack('<I',b.upload(m['system_core_clock'],4,'clock.bin'))!=(400000000,):
        raise ValueError('CPU clock differs from qualified profile')
    if bench.decode(b.upload(bench.PROOF,384,'proof-before-halt.bin'),names)!=p:
        raise ValueError('Proof changed before halt; no execution-control command sent')
    # First execution-control command; all success/idle and identity gates passed.
    context=bench.sd.context_proof(b,{m['park']},'completed')
    result=dict(passed=True,kind='raw-flash-inspection',proof=p,context=context,card=card,
        slots=slots,loader_words=loader,sd_payload_integrity_verified=False,
        binary_sha256=sha(code),halt_after_success_idle_only=True,whole_image=whole)
    result['camera_telemetry']=camera_telemetry(b,folder,m)
    chunks=b.upload(m['chunk_trace'],p['chunk_count']*32,'chunks.bin')
    (b.output.parent/'chunks.bin').write_bytes(chunks)
    if m.get('line_stream'):
        if m.get('producer_bytes')!=416 or not m['bss_start']<=m['producer']<=m['bss_end']-416:
            raise ValueError('Producer telemetry outside BSS')
        data=b.upload(m['producer'],416,'producer.bin');(b.output.parent/'producer.bin').write_bytes(data)
    if m.get('dma_sleep'):
        data,stats=bench.dma_wait_snapshot(b,m)
        (b.output.parent/'dma-wait.bin').write_bytes(data)
        result['dma_wait']=stats
    if download_frame:
        frame=b''.join(b.upload(m['frame']+off,min(bench.READ_MAX,bench.FRAME_BYTES-off),
            f'frame-{off:08x}.bin') for off in range(0,bench.FRAME_BYTES,bench.READ_MAX))
        (b.output.parent/'frame.bin').write_bytes(frame);result['frame_sha256']=sha(frame)
    if bench.decode(b.upload(bench.PROOF,384,'proof-final.bin'),names)!=p:
        raise ValueError('Terminal proof changed during inspection')
    return result


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--build',type=Path,required=True);ap.add_argument('--expected-sha',required=True)
    ap.add_argument('--expected-sector-sha',required=True);ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--boot-proof',type=Path);ap.add_argument('--execute',action='store_true')
    ap.add_argument('--download-frame',action='store_true');a=ap.parse_args()
    m,p,code=checked_build(a.build,a.expected_sha,a.expected_sector_sha)
    if not a.execute:
        print(json.dumps(dict(plan_only=True,receiver_sha256=sha(code),sector_sha256=a.expected_sector_sha,
            limits='SRAM read only until exact success/idle; then halt/core context. No reset/write/NOR/SD/power commands.')))
        return
    if not a.boot_proof: ap.error('--execute requires recent root-bound --boot-proof for nonce0 freshness')
    fresh=fresh_boot(a.boot_proof,a.expected_sha,a.expected_sector_sha)
    a.out.mkdir(parents=True,exist_ok=False)
    bench.dump(a.out/'fresh-boot.json',fresh)
    result=inspect(bench.sd.Bench(a.out/'inspection'),a.build.resolve(),m,code,download_frame=a.download_frame)
    result.update(sector_sha256=a.expected_sector_sha,boot_proof_sha256=sha(a.boot_proof.read_bytes()))
    bench.dump(a.out/'verified.json',result);print(json.dumps(result),flush=True)


if __name__=='__main__':main()
