"""One guarded LBA0 PIO/IDMA read attempt; dry-run unless --execute.

No camera capture, card write/erase, NOR operation, power switch, UART stimulus
or automatic retry. Root performs recovery separately after any failed attempt.
The bench helper retains read diagnostics and the untrusted 512-byte destination
before rejecting a failed terminal; this script analyses those files offline.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import traceback

ROOT=Path(__file__).resolve().parents[3]
REFERENCE=ROOT/'tmp/bringup/raw-frontmeta-20261024/bench/preservation/payload-0000/verified.json'
IDENTITY=('sector_count','cid0','cid1','cid2','cid3')
TIMEOUTS=dict(park=90,read=120,final_idle=90)


def require(ok,message):
    if not ok:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def bound(path):
    path=Path(path).resolve()
    return dict(path=str(path),bytes=path.stat().st_size,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def save_new(path,value):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as file:
        json.dump(value,file,indent=2,allow_nan=False)
        file.write('\n')


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def reference_data(proof_path):
    proof_path=Path(proof_path).resolve()
    proof=read(proof_path)
    p=proof['proof']
    source=proof_path.parent/'sectors.bin'
    data=source.read_bytes()
    require(proof.get('passed') is True and p['operation']==3 and p['result']==0 and
            p['read_lba']==0 and p['read_count']*512==len(data) and len(data)>=512 and
            hashlib.sha256(data).hexdigest()==proof['read_sha256'],
            'Historical reference is not a complete hash-matching LBA0 read')
    require(data[:4]==b'GXRS','Expected the historical sensor-pattern slot header')
    return data[:512],dict(proof=bound(proof_path),full_payload=bound(source),
        included_offset=0,included_bytes=512,full_payload_hash_verified=True,
        card_identity={key:proof['card'][key] for key in IDENTITY},
        header_sha256=hashlib.sha256(data[:512]).hexdigest())


def admission(args):
    require(not args.out.exists(),'Refusing existing attempt/output folder')
    require(bool(args.prior)!=bool(args.recovery_build),
            'Select one successful same-build READ prior or explicit current recovery build')
    require((args.pair==0 and args.mode=='pio' and args.clock_hz==12500000) or
            (args.pair in (1,2,3) and args.clock_hz==25000000),
            'Pair0 is the12.5MHz PIO reference; pairs1..3 are25MHz comparisons')
    manifest=read(args.build/'manifest.json')
    bench=load('pio_dma_bench',ROOT/'firmware/capture-raw/bench.py')
    bench.checked_build(args.build,manifest['binary_sha256'])
    bench.diagnostic_layout(manifest,3)
    expected=dict(flash=False,standby=False,sd_clock_hz=args.clock_hz,sd_bus_width=4,
        sd_gpio_speed=3,sd_clk_gpio_speed=None,sd_clock_negedge=True,
        sd_clock_negedge_init=True,sd_review_profile=True,sd_startup_opt=True,
        sd_read_diagnostics=True,sd_read_diagnostics_proof_bytes=64,
        raw_read_camera_proof_bytes=64,
        sd_idma_read=args.mode=='idma',sd_high_speed=False,sd_early_run_clock=False,
        sd_fixed_compensation=False,sd_compensation_modified=False,
        sd_high_speed_mixed_slew=False,sd_high_speed_fixed_compensation=False,
        sd_high_speed_combined_electrical=False,raw_dma_tail_wait=False,
        dma_sleep=False,preinit=False)
    require(all(manifest.get(key)==value and type(manifest.get(key)) is type(value)
                for key,value in expected.items()),'Unexpected isolated READ profile')
    if args.prior:
        prior=read(args.prior)
        require(prior.get('passed') is True and prior['binary_sha256']==manifest['binary_sha256'] and
                prior['proof']['operation']==3,'Prior is not a successful same-build READ')
        bench.validate(prior['proof'],manifest,prior['request_words'])
    else:
        require((args.recovery_build/'manifest.json').is_file(),'Missing explicit recovery manifest')
    header,reference=reference_data(args.reference_proof)
    return manifest,bench,header,reference


def compare_bytes(actual,reference):
    require(len(actual)==len(reference)==512,'Comparison requires two complete512-byte buffers')
    differences=[dict(offset=i,expected=a,observed=b,xor=a^b)
        for i,(a,b) in enumerate(zip(reference,actual)) if a!=b]
    return dict(bytes=512,bytes_equal=not differences,differing_bytes=len(differences),
        first_difference=differences[0]['offset'] if differences else None,
        matching_prefix_bytes=differences[0]['offset'] if differences else 512,
        matching_words=sum(actual[i:i+4]==reference[i:i+4] for i in range(0,512,4)),
        actual_sha256=hashlib.sha256(actual).hexdigest(),
        reference_sha256=hashlib.sha256(reference).hexdigest(),differences=differences)


def analyze_retained(folder,manifest,reference,reference_info):
    """Offline only; helper artifact names are bound by host admission."""
    proof_path=folder/'read/proof.json'
    verified_path=folder/'read/verified.json'
    result=dict(proof=bound(proof_path) if proof_path.exists() else None,
        verified=bound(verified_path) if verified_path.exists() else None,
        diagnostic_record=None,buffer=None,comparison=None,
        full_buffer_retained=False,successful_idle_permission=False,camera_held_reset_proven=False,
        buffer_hash_verified=False)
    if proof_path.exists():
        p=read(proof_path)
        result.update(operation=p.get('operation'),result=p.get('result'),stage=p.get('stage'),
            sd_error=p.get('sd_error'),cleanup_error=p.get('cleanup_error'),
            read_lba=p.get('read_lba'),read_count=p.get('read_count'),
            camera_capture_entered=bool(p.get('arm') or p.get('camera_ready') or p.get('frames')),
            card_write_sectors=(p.get('card_write_hi',0)<<32)|p.get('card_write_lo',0))
        require(p.get('operation')==3 and result['card_write_sectors']==0,
                'Unexpected non-READ operation or sector writes')
        require(not result['camera_capture_entered'],'Camera activity recorded during isolated READ')
    # These files are produced before the bench helper applies normal successful
    # terminal validation, so CRC failures can retain their actual destination.
    diagnostic_path=folder/'read/read-diagnostics.json'
    buffer_path=folder/'read/read-buffer.bin'
    if diagnostic_path.exists():
        diagnostic=read(diagnostic_path)
        result['diagnostic_record']=bound(diagnostic_path)
        result['diagnostic']=diagnostic
        attribution=diagnostic['attribution']
        require(attribution['binary_sha256']==manifest['binary_sha256'] and
                attribution['nonce']==p['nonce'] and attribution['hardware_mutations'] is False and
                attribution['idle_permission'] is False,'Diagnostic attribution differs')
        result['attribution_valid']=bool(attribution['immutable_code_equal'] and
            attribution['final_proof_equal'] and
            attribution['expected_immutable_sha256']==attribution['observed_immutable_sha256'] and
            attribution['cfsr']==0 and attribution['hfsr']==0)
        telemetry=diagnostic['diagnostics']
        require(diagnostic['nonce']==p['nonce'] and diagnostic['operation_result']==p['result'],
                'Diagnostic nonce/result differs from attempted operation')
        card=diagnostic['card']
        require({key:card[key] for key in IDENTITY}==reference_info['card_identity'] and
                card['written_sectors']==0 and card['clock_hz']==manifest['sd_clock_hz'],
                'Retained card identity/write count/clock differs')
        camera=diagnostic['camera']
        require(camera['magic']==0x31504352 and camera['version']==1 and camera['phase']==2 and
                camera['held']==1 and camera['moder']&0xC00==0x400 and
                not camera['odr']&0x20 and not camera['idr']&0x20 and not camera['otyper']&0x20 and
                not camera['pupdr']&0xC00 and camera['sd_gpio_readable']==1 and
                camera['c_ospeed']&0xFF3==0xFF3 and camera['e_ospeed']&0x300==0x300 and
                ((camera['checked']-camera['assert_begin'])&0xFFFFFFFF)>=40800,
                'Camera held-reset/unchanged SD GPIO proof differs')
        result['camera_held_reset_proven']=True
        result['read_telemetry_captured']=telemetry.get('captured')==1
        if telemetry.get('captured')==1:
            expected=dict(magic=0x31445253,version=1,mode=int(manifest['sd_idma_read']),
                lba=0,count=1,destination=0x34200000,requested_bytes=512)
            require(all(telemetry.get(key)==value for key,value in expected.items()),
                    'Retained telemetry has wrong mode/LBA/count/destination')
            require(telemetry['clkcr']==(0x34000|150000000//(2*manifest['sd_clock_hz'])),
                    'Retained clock/phase/HWFC differs')
    if buffer_path.exists():
        payload=buffer_path.read_bytes()
        result['buffer']=bound(buffer_path)
        result['comparison']=compare_bytes(payload,reference)
        result['full_buffer_retained']=True
        if diagnostic_path.exists():
            require(diagnostic['buffer_bytes']==512 and
                    diagnostic['buffer_sha256']==result['buffer']['sha256'],
                    'Retained buffer hash differs from diagnostics record')
            result['buffer_hash_verified']=True
    if verified_path.exists():
        verified=read(verified_path)
        require(verified.get('passed') is True and verified['binary_sha256']==manifest['binary_sha256'],
                'Successful proof identity differs')
        require(result['camera_held_reset_proven'] and result['buffer_hash_verified'] and
                result.get('attribution_valid') is True,
                'Successful READ lacks camera/buffer diagnostic qualification')
        card=verified['card']
        require({key:card[key] for key in IDENTITY}==reference_info['card_identity'],
                'Current card differs from historical reference')
        require(card['clock_hz']==manifest['sd_clock_hz'] and card['written_sectors']==0 and
                card['read_sectors']==1 and card['error']==0 and card['cleanup_error']==0 and
                card['initialized']==card['controller_owned']==0 and card['media_idle']==1,
                'Successful READ card state differs')
        require(card['bus_width_proof']['configured_clkcr']==(0x34000|150000000//(2*manifest['sd_clock_hz'])) and
                card['bus_width_proof']['negotiated_width']==4,'Clock phase/width/HWFC differs')
        confirmed=(folder/'read/sectors.bin').read_bytes()
        require(len(confirmed)==512 and hashlib.sha256(confirmed).hexdigest()==verified['read_sha256'] and
                confirmed==buffer_path.read_bytes(),
                'Successful sector download differs from diagnostic destination snapshot')
        require(result['comparison']['bytes_equal'],'CRC-clean data differs from known historical pattern')
        result['successful_idle_permission']=True
        result['card']=card
    return result


def run(args):
    for field in ('build','out','prior','recovery_build','reference_proof'):
        value=getattr(args,field)
        if value is not None:
            setattr(args,field,value.resolve())
    manifest,bench,reference,reference_info=admission(args)
    plan=dict(schema=1,execute=args.execute,pair=args.pair,mode=args.mode,clock_hz=args.clock_hz,
        group='reference_control' if args.pair==0 else 'formal_25mhz',
        build=str(args.build),binary_sha256=manifest['binary_sha256'],lba=0,count=1,
        reference=reference_info,prior=bound(args.prior) if args.prior else None,
        recovery_build=str(args.recovery_build) if args.recovery_build else None,
        timeouts_seconds=TIMEOUTS,no_camera_capture=True,no_card_write=True,no_erase=True,
        no_nor_operation=True,uart_stimulus=False,power_switch=False,automatic_retry=False)
    if not args.execute:
        print(json.dumps(plan,indent=2))
        return plan
    args.out.mkdir(parents=True,exist_ok=False)
    save_new(args.out/'plan.json',plan)
    save_new(args.out/'reference.json',reference_info)
    (args.out/'reference-header.bin').write_bytes(reference)
    stage='not_started'

    def event(status,**extra):
        with (args.out/'events.jsonl').open('a',encoding='utf-8') as log:
            log.write(json.dumps(dict(utc=datetime.now(timezone.utc).isoformat(),stage=stage,
                status=status,**extra),allow_nan=False)+'\n')

    def execute(label,*command):
        nonlocal stage
        stage=label
        event('started')
        with (args.out/(label+'.log')).open('x',encoding='utf-8') as log:
            subprocess.run([sys.executable,*map(str,command)],cwd=ROOT,stdout=log,
                stderr=subprocess.STDOUT,timeout=TIMEOUTS[label],check=True)
        event('complete')

    try:
        if args.recovery_build:
            execute('park',ROOT/'firmware/capture-timing/recovery_gpio/check_park.py',
                '--build',args.recovery_build,'--out',args.out/'park')
        command=['read','--build',args.build,'--expected-sha',manifest['binary_sha256'],
            '--lba','0','--count','1','--out',args.out/'read','--execute']
        command+=['--prior',args.prior] if args.prior else ['--recovery-build',args.recovery_build]
        execute('read',ROOT/'firmware/capture-raw/bench.py',*command)
        stage='analyze'
        retained=analyze_retained(args.out,manifest,reference,reference_info)
        require(retained['successful_idle_permission'],'Read helper returned without verified idle terminal')
        execute('final_idle',ROOT/'tmp/bringup/sd-early-clock-20261026/fresh_idle.py',
            args.build,args.out/'read/verified.json',args.out/'final-idle')
        result=dict(passed=True,pair=args.pair,mode=args.mode,retained=retained,
            final_proof=bound(args.out/'read/verified.json'),
            final_idle=bound(args.out/'final-idle/verified.json'),automatic_retry=False)
        save_new(args.out/'result.json',result)
        return result
    except BaseException:
        error=traceback.format_exc()
        event('failed',error=error)
        try:
            retained=analyze_retained(args.out,manifest,reference,reference_info)
        except BaseException:
            retained=dict(analysis_error=traceback.format_exc(),successful_idle_permission=False)
        failure=dict(passed=False,pair=args.pair,mode=args.mode,stage=stage,error=error,
            retained=retained,automatic_retry=False,failed_attempt_not_idle_permission=True,
            target_state='Root diagnosis/recovery required before another operation',
            timeout_may_leave_programmer_child=True)
        save_new(args.out/'failed.json',failure)
        return failure


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--mode',choices=('pio','idma'),required=True)
    parser.add_argument('--pair',type=int,choices=(0,1,2,3),required=True)
    parser.add_argument('--clock-hz',type=int,choices=(12500000,25000000),default=25000000)
    source=parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--prior',type=Path)
    source.add_argument('--recovery-build',type=Path)
    parser.add_argument('--reference-proof',type=Path,default=REFERENCE)
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args()
    result=run(args)
    if args.execute:
        print(json.dumps(result,indent=2,allow_nan=False))
        raise SystemExit(0 if result['passed'] else 1)


if __name__=='__main__':
    main()
