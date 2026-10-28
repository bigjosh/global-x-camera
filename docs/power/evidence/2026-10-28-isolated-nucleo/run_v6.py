"""Root-only prepare/launch/observe; importing performs no hardware access.

First prepare uses the exact installed early guard and unchanged SRAM bridge.
Repeats require this same binary's fresh successful awake proof and exact PC.
No camera/SD/NOR command, reset or power switch exists in this wrapper.
"""
import importlib.util,json,secrets,struct
from pathlib import Path
from types import SimpleNamespace
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sp=importlib.util.spec_from_file_location('isolated_raw_bench',ROOT/'firmware/capture-raw/bench.py')
raw=importlib.util.module_from_spec(sp);sp.loader.exec_module(raw)
# Cortex-M55 CMSIS core_cm55.h: CCR.IC is bit17, DC is bit16.
CCR_IC=1<<17
CCR_DC=1<<16
ALLOWED={
 '6c7a20b0ccd08f64079c250782eb3a1d30b3828ff098af0eb54689b5d282c5bc':(1,2700,0x343003A6),
 '8066f62577071218f00ace10fffcd0273f45728849639931149fc053585fe565':(2,3788,0x343003AA),
 'c1ee79c7ecb6c005f71c06c8c1d6322026d38b42727a7874302d67a3e93666d1':(3,3924,0x343003AA),
 '04d688d07a3e988c6cb0549490e0f38a16965226bece6936da4872eed239a2cd':(4,4120,0x343003AA),
 'e82ed59ddc1345e26ba54a697cf26326b9627393d9f1c3643b861f3ede921a74':(5,4340,0x343003AA),
 '19350ad4ba0d64942e5e3faf9bfce866525b1b486012c084494dac173d58a019':(6,4544,0x343003AA),
}

def checked(build):
    build=Path(build).resolve();m=json.loads((build/'manifest.json').read_text());code=(build/'probe.bin').read_bytes()
    exact=ALLOWED.get(m['sha256'])
    if exact is None or raw.sha(code)!=m['sha256'] or (m['schema'],len(code),m['park'])!=exact:
        raise ValueError('Only frozen isolated probe-v1/v2 admitted')
    if (m['load'],m['entry'],m['park'],m['request'],m['proof']) != (
            0x34300000,0x34300381,exact[2],0x343C1F00,0x343C2000):
        raise ValueError('Unexpected isolated layout')
    if code[m['park']-m['load']:m['park']-m['load']+2]!=b'\xfe\xe7':raise ValueError('Park is not exact self-branch')
    for n,digest in m['sources'].items():
        if raw.sha((build/n).read_bytes())!=digest:raise ValueError('Frozen source changed: '+n)
    return m,code

def decode(data,m):
    if len(data)!=1024:raise ValueError('Incomplete isolated proof')
    words=struct.unpack('<256I',data);p=dict(zip(m['fields'],words))
    if m['schema']>=2:
        for key,start in (('rcc_before',96),('rcc_after',160)):
            p[key]=dict(zip(m['rcc_inventory_names'],words[start:]))
    if m['schema']>=3:
        p['nvic_pending_banks_before']=list(words[224:240])
        p['nvic_pending_banks_after_clear']=list(words[240:256])
    return p

def validate(p,s):
    divider=s['request_words'][3]
    equal=(('IC1_BEFORE','IC1_AFTER'),('DBG_BEFORE','DBG_AFTER'),
        ('SCR_BEFORE','SCR_AFTER'),('APB5_BEFORE','APB5_AFTER'),('AHB5_BEFORE','AHB5_AFTER'),
        ('MEMENR_BEFORE','MEMENR_AFTER'))
    exact=dict(MAGIC=0x314F5349,VERSION=s['schema'],NONCE=s['nonce'],STATE=8,ERROR=0,FLAGS=s['request_words'][2],
        DIVIDER=divider,CONTROL=0,IPSR=0,PRIMASK=1,FAULTMASK=0,DEBUG_SAFE=1,
        CFGR1=0x33330000,CFGR2=0x100000,PLL1_1=0x404b00,PLL1_2=0,PLL1_3=0x49000005,
        NVIC_ENABLE_BEFORE=0,NVIC_ENABLE_AFTER=0,
        SYSTICK_BEFORE=0,SYSTICK_FINAL=0,SYSTICK_RELOAD=4000000//divider-1,PREFLIGHT_TICKS=3,
        FINAL_PRIMASK=1,CFSR=0,HFSR=0,GPIO_SAFE=1,TERMINAL=0x454E4F44,VTOR_ACTIVE=s['load'])
    if any(p[k]!=v for k,v in exact.items()):raise ValueError('Isolated proof/context differs from expected success')
    wanted=(p['IC1_BEFORE']&~0xff0000)|((3*divider-1)<<16)
    if p['IC1_ACTIVE']!=wanted:raise ValueError('CPU divider did not take effect')
    if s['schema']>=2:
        if p['CPU_HZ']!=400000000//divider or p['CLOCK_SAFE']!=1 or p['INVENTORY_COUNT']!=56:
            raise ValueError('Clock/inventory proof mismatch')
        if p['VTOR_BEFORE']!=s['vtor_before']:raise ValueError('Previous vector table differs')
        if any(p['rcc_before'][k]!=p['rcc_after'][k] for k in p['rcc_before'] if k!='SR'):
            raise ValueError('RCC inventory changed after restoration')
    if s['schema']>=3:
        # Exact observed exception: disabled TCM_ECC can be pending. Record
        # clearing/reassertion, without making a memory-health claim.
        if not 1<=p['NVIC_BANKS']<=16 or p['PENDING_CLEARED']!=p['NVIC_PENDING_BEFORE']:
            raise ValueError('Disabled IRQ clearing proof differs')
        for key in ('NVIC_PENDING_BEFORE','PENDING_AFTER_CLEAR','NVIC_PENDING_AFTER'):
            if p[key] not in (0,64):raise ValueError('Unreviewed pending interrupt')
        for key in ('nvic_pending_banks_before','nvic_pending_banks_after_clear'):
            if p[key][0] not in (0,64) or any(p[key][1:]):raise ValueError('Pending source is not isolated TCM_ECC')
    elif p['NVIC_PENDING_BEFORE'] or p['NVIC_PENDING_AFTER']:
        raise ValueError('Earlier profile requires no pending external IRQ')
    if s['schema']>=4:
        if p['LP_SAFE']!=1:raise ValueError('Sleep-clock setup not qualified')
        for before,active,after,mask in (
                ('MEMLPENR','MEMLP_ACTIVE','MEMLP_AFTER',0xE),
                ('AHB3LPENR','AHB3LP_ACTIVE','AHB3LP_AFTER',0x4200),
                ('BUSLPENR','BUSLP_ACTIVE','BUSLP_AFTER',3),
                ('BSEC_LPCLOCK','BSECLP_ACTIVE','BSECLP_AFTER',2)):
            if p[active]!=(p[before]|mask) or p[after]!=p[before]:raise ValueError('Sleep-clock setup/restoration differs')
    if s['schema']>=5:
        trim=bool(p['FLAGS']&2)
        if p['RUN_TRIM_SAFE']!=int(trim) or p['MEM_RUN_ACTIVE']!=p['MEMENR_BEFORE']&~(0x181 if trim else 0):
            raise ValueError('Unused SRAM RUN clock control differs')
        if p['MEM_RUN_ACTIVE']&0xE!=0xE or not 0x343AF000<p['RUN_MSP']<=0x343B0000 or not 0x34300000<=p['RUN_CODE']<0x34310000:
            raise ValueError('Executable/work/stack SRAM retention differs')
    if s['schema']>=6:
        if p['CACHE_SAFE']!=int(bool(p['FLAGS']&4)) or p['CCR_ACTIVE']!=(p['CCR']|(CCR_IC if p['FLAGS']&4 else 0)) or p['CCR_AFTER']!=p['CCR'] or p['CCR_ACTIVE']&CCR_DC:
            raise ValueError('I-cache active/final state mismatch')
    if any(p[a]!=p[b] for a,b in equal):raise ValueError('Retained/restored state differs')
    if p['CCR']&0x30000 or p['FPCCR']&1 or p['SCR_ACTIVE']&0x16:raise ValueError('CPU state mismatch')
    if p['DBG_ACTIVE']!=p['DBG_BEFORE']&~(1 if p['FLAGS']&1 else 0):raise ValueError('Debug mode mismatch')
    if not 20<=p['BUSY_TICKS']<=21 or not 20<=p['SLEEP_TICKS']<=21:raise ValueError('Timer duration mismatch')
    if not 1<=p['WFI_RETURNS']==p['WFI_CALLS']<=1000:raise ValueError('No bounded WFI-return proof')
    if not p['BUSY_ITERATIONS'] or p['BUSY_ITERATIONS']%256:raise ValueError('No complete integer workload')
    if (p['LED_ODR_ACTIVE']&0x501)!=0x501 or p['LED_ODR_AFTER']!=p['LED_ODR_ACTIVE'] or p['PD12_ODR_AFTER']&0x1000:
        raise ValueError('LED/marker final state differs')

def prepare(build,out,flags=0,prior=None,divider=1,refusal=None):
    """Returns (Bench, session). First use bootstraps; repeats validate prior first."""
    if flags not in range(8):raise ValueError('Unreviewed diagnostic flags')
    build=Path(build).resolve();out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
    m,code=checked(build)
    if m['schema']<6 and flags&4:raise ValueError('I-cache control requires exact v6')
    if m['schema']<5 and flags>1:raise ValueError('SRAM trim requires exact v5')
    if divider not in (1,2,4,8) or (m['schema']==1 and divider!=1):raise ValueError('Unreviewed divider')
    if refusal is not None:
        if prior is not None or m['schema']!=4:raise ValueError('Refusal upgrade is only into reviewed v4')
        directory=Path(refusal).resolve();old=json.loads((directory/'prepared.json').read_text())
        saved=json.loads((directory/'proof.json').read_text());pm,pc=checked(old['build'])
        if (pm['schema'],saved['ERROR']) not in ((1,4),(3,7)):
            raise ValueError('Unreviewed refusal, not a generic failure override')
        expected=dict(MAGIC=0x314F5349,VERSION=pm['schema'],NONCE=old['nonce'],STATE=15,FLAGS=0,DIVIDER=1,
            CONTROL=0,IPSR=0,PRIMASK=1,FAULTMASK=0,VTOR_ACTIVE=pm['load'],SCR_BEFORE=0,SCR_AFTER=0,
            DEBUG_SAFE=0,NVIC_ENABLE_BEFORE=0,NVIC_ENABLE_AFTER=0,
            SYSTICK_BEFORE=0,SYSTICK_FINAL=0,FINAL_PRIMASK=1,CFSR=0,HFSR=0,GPIO_SAFE=0,TERMINAL=0x454E4F44)
        if any(saved[k]!=v for k,v in expected.items()) or saved['CCR']&0x30000 or saved['FPCCR']&1:
            raise ValueError('Not the exact awake pre-measurement refusal')
        if any(saved[k] for k in ('BUSY_START','BUSY_END','BUSY_TICKS','BUSY_ITERATIONS','SLEEP_START','SLEEP_END','SLEEP_TICKS','WFI_CALLS','WFI_RETURNS')):
            raise ValueError('A measurement already ran; requires separate diagnosis')
        if saved['NVIC_PENDING_BEFORE'] not in (0,64) or saved['NVIC_PENDING_AFTER'] not in (0,64):
            raise ValueError('Unknown pending source')
        if pm['schema']==3 and (saved['IC1_BEFORE']!=0x20000 or saved['IC1_AFTER']!=0x20000 or saved['MEMLPENR']!=0):
            raise ValueError('Not the observed restored400MHz/missingRAMsleepclock refusal')
        b=raw.sd.Bench(out/'operation')
        live=decode(b.upload(pm['proof'],1024,'refusal-proof.bin'),pm)
        if live!=saved:raise ValueError('Refusal proof changed')
        if b.upload(pm['load'],len(pc),'refusal-code.bin')!=pc:raise ValueError('Refusal executable differs')
        request_path=directory/('request-readback.bin' if pm['schema']==1 else 'isolated-request-readback.bin')
        old_request=request_path.read_bytes()
        if old_request!=struct.pack('<8I',0x31514552,old['nonce'],0,1,0,0,0,0):
            raise ValueError('Saved refusal request differs from exact initial control')
        if b.upload(pm['request'],32,'refusal-request.bin')!=old_request:
            raise ValueError('Refusal request differs')
        raw.sd.context_proof(b,{pm['park']},'refusal-context')
        if any(struct.unpack('<II',b.upload(0xE000ED28,8,'refusal-faults.bin'))):raise ValueError('Live fault flags set')
        apb5,=struct.unpack('<I',b.upload(0x5602827C,4,'refusal-apb5.bin'))
        ahb5,=struct.unpack('<I',b.upload(0x56028260,4,'refusal-ahb5.bin'))
        if apb5&0x44 or ahb5&0x80:raise ValueError('Camera/SD peripheral clocks unexpectedly enabled')
        raw.dump(b.output/'refusal-admission.json',dict(prior_directory=str(directory),proof=saved,
            qualification='Exact known awake pre-measurement refusal only, with no enabled camera/SD, immutable code, no CPU faults and restored400MHz. Failure remains failure; this is a reviewed diagnostic replacement, not a successful-measurement claim.'))
    elif prior is None:
        boot=ROOT/'tmp/bringup/capture-sleep-20261020/recovery-read-bridge-v1'
        _,boot_code=raw.bridge.checked_bridge(boot)
        args=SimpleNamespace(recovery_build=ROOT/'tmp/bringup/error-relocate-20261026/flash-normal-v2/staged',bridge=boot)
        b=raw.bridge.bootstrap(args,out,boot_code)
    else:
        previous=json.loads(Path(prior).read_text());b=raw.sd.Bench(out/'operation')
        if previous.get('passed') is not True or previous['session']['sha256'] not in ALLOWED:raise ValueError('Prior operation not valid')
        pm,pc=checked(previous['session']['build'])
        live=decode(b.upload(pm['proof'],1024,'prior-proof.bin'),pm)
        if live!=previous['proof']:raise ValueError('Live proof differs from prior')
        validate(live,previous['session'])
        if b.upload(pm['load'],len(pc),'prior-code.bin')!=pc:raise ValueError('Prior executable differs')
        raw.sd.context_proof(b,{pm['park']},'prior-context')
    b.call('-halt','-w',build/'probe.bin',hex(m['load']),'-v',success='Download verified successfully')
    if b.upload(m['load'],len(code),'probe-readback.bin')!=code:raise ValueError('Probe readback mismatch')
    vtor,=struct.unpack('<I',b.upload(0xE000ED08,4,'isolated-vtor-before.bin'))
    nonce=secrets.randbelow(0xffffffff)+1;words=[0x31514552,nonce,flags,divider,0,0,0,0]
    data=struct.pack('<8I',*words);(b.output/'isolated-request.bin').write_bytes(data)
    (b.output/'isolated-clear.bin').write_bytes(bytes(1024))
    b.call('-halt','-w',b.output/'isolated-request.bin',hex(m['request']),'-v',
        '-w',b.output/'isolated-clear.bin',hex(m['proof']),'-v',success='Download verified successfully')
    if b.upload(m['request'],32,'isolated-request-readback.bin')!=data or b.upload(m['proof'],1024,'isolated-clear-readback.bin')!=bytes(1024):
        raise ValueError('Request/clear mismatch')
    s=dict(m,nonce=nonce,request_words=words,build=str(build),vtor_before=vtor);raw.dump(b.output/'prepared.json',s)
    return b,s

def launch(b,s):
    """Root starts logger first; no other STLINK calls until measured window ends."""
    b.call('-halt','-coreReg',f"PC={hex(s['entry'])}",'XPSR=0x01000000','-run',success='Core run')

def observe(b,s):
    p=decode(b.upload(s['proof'],1024,'completed-proof.bin'),s)
    raw.dump(b.output/'proof.json',p)
    # No halt on an unexpected incomplete result. A diagnosed failure stays explicit.
    validate(p,s)
    context=raw.sd.context_proof(b,{s['park']},'completed-context')
    code=b.upload(s['load'],s['bytes'],'completed-code.bin')
    after=decode(b.upload(s['proof'],1024,'after-context-proof.bin'),s)
    if raw.sha(code)!=s['sha256'] or after!=p:raise ValueError('Code/proof changed')
    cfgr=b.upload(0x56028020,8,'rcc-cfgr.bin')
    faults=struct.unpack('<II',b.upload(0xE000ED28,8,'faults.bin'))
    if any(faults):raise ValueError('Live CPU fault flags set')
    result=dict(passed=True,session=s,proof=p,context=context,
        busy_nominal_ms=p['BUSY_TICKS']*10,sleep_nominal_ms=p['SLEEP_TICKS']*10,
        qualified_timed_wfi_returns=True,clock_inventory_cfgr_hex=cfgr.hex(),
        cpu_hz=400000000//s['request_words'][3],
        disabled_tcm_ecc_pending_observed=bool(p['NVIC_PENDING_BEFORE']&64),
        qualification='Integer/SRAM workload with selected I-cache flag (D-cache always off) vs periodic100Hz SysTick/WFI at selected CPU divider. GPIO gives wall time. No camera/SD init. Expanded SRAM retained by trusted bridge. LEDs off in both windows; original400MHz/DBG_SLEEP restored before awake park. Disabled TCM_ECC pending/clear/reassert values retained, origin unresolved; no memory-health claim. Not whole-MCU power isolation. Own vector remains installed at final park.')
    raw.dump(b.output/'verified.json',result);return result

if __name__=='__main__':
    m,c=checked(HERE/'probe-v6');print(json.dumps(dict(offline_checked=True,sha256=raw.sha(c),entry=hex(m['entry']),park=hex(m['park']))))
