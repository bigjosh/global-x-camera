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
ALLOWED={
 '6c7a20b0ccd08f64079c250782eb3a1d30b3828ff098af0eb54689b5d282c5bc':(1,2700,0x343003A6),
 '8066f62577071218f00ace10fffcd0273f45728849639931149fc053585fe565':(2,3788,0x343003AA),
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
    if m['schema']==2:
        for key,start in (('rcc_before',96),('rcc_after',160)):
            p[key]=dict(zip(m['rcc_inventory_names'],words[start:]))
    return p

def validate(p,s):
    divider=s['request_words'][3]
    equal=(('IC1_BEFORE','IC1_AFTER'),('DBG_BEFORE','DBG_AFTER'),
        ('SCR_BEFORE','SCR_AFTER'),('APB5_BEFORE','APB5_AFTER'),('AHB5_BEFORE','AHB5_AFTER'),
        ('MEMENR_BEFORE','MEMENR_AFTER'))
    exact=dict(MAGIC=0x314F5349,VERSION=s['schema'],NONCE=s['nonce'],STATE=8,ERROR=0,FLAGS=s['request_words'][2],
        DIVIDER=divider,CONTROL=0,IPSR=0,PRIMASK=1,FAULTMASK=0,DEBUG_SAFE=1,
        CFGR1=0x33330000,CFGR2=0x100000,PLL1_1=0x404b00,PLL1_2=0,PLL1_3=0x49000005,
        NVIC_ENABLE_BEFORE=0,NVIC_PENDING_BEFORE=0,NVIC_ENABLE_AFTER=0,NVIC_PENDING_AFTER=0,
        SYSTICK_BEFORE=0,SYSTICK_FINAL=0,SYSTICK_RELOAD=4000000//divider-1,PREFLIGHT_TICKS=3,
        FINAL_PRIMASK=1,CFSR=0,HFSR=0,GPIO_SAFE=1,TERMINAL=0x454E4F44,VTOR_ACTIVE=s['load'])
    if any(p[k]!=v for k,v in exact.items()):raise ValueError('Isolated proof/context differs from expected success')
    wanted=(p['IC1_BEFORE']&~0xff0000)|((3*divider-1)<<16)
    if p['IC1_ACTIVE']!=wanted:raise ValueError('CPU divider did not take effect')
    if s['schema']==2:
        if p['CPU_HZ']!=400000000//divider or p['CLOCK_SAFE']!=1 or p['INVENTORY_COUNT']!=56:
            raise ValueError('Clock/inventory proof mismatch')
        if p['VTOR_BEFORE']!=s['vtor_before']:raise ValueError('Previous vector table differs')
        if any(p['rcc_before'][k]!=p['rcc_after'][k] for k in p['rcc_before'] if k!='SR'):
            raise ValueError('RCC inventory changed after restoration')
    if any(p[a]!=p[b] for a,b in equal):raise ValueError('Retained/restored state differs')
    if p['CCR']&0x30000 or p['FPCCR']&1 or p['SCR_ACTIVE']&0x16:raise ValueError('CPU state mismatch')
    if p['DBG_ACTIVE']!=p['DBG_BEFORE']&~(1 if p['FLAGS'] else 0):raise ValueError('Debug mode mismatch')
    if not 20<=p['BUSY_TICKS']<=21 or not 20<=p['SLEEP_TICKS']<=21:raise ValueError('Timer duration mismatch')
    if not 1<=p['WFI_RETURNS']==p['WFI_CALLS']<=1000:raise ValueError('No bounded WFI-return proof')
    if not p['BUSY_ITERATIONS'] or p['BUSY_ITERATIONS']%256:raise ValueError('No complete integer workload')
    if (p['LED_ODR_ACTIVE']&0x501)!=0x501 or p['LED_ODR_AFTER']!=p['LED_ODR_ACTIVE'] or p['PD12_ODR_AFTER']&0x1000:
        raise ValueError('LED/marker final state differs')

def prepare(build,out,flags=0,prior=None,divider=1):
    """Returns (Bench, session). First use bootstraps; repeats validate prior first."""
    if flags not in (0,1):raise ValueError('Only inherited or explicitly cleared DBG_SLEEP')
    build=Path(build).resolve();out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
    m,code=checked(build)
    if divider not in (1,2,4,8) or (m['schema']==1 and divider!=1):raise ValueError('Unreviewed divider')
    if prior is None:
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
        qualification='Caches-off integer/SRAM workload vs periodic100Hz SysTick/WFI at selected CPU divider. GPIO gives wall time. No camera/SD init. Expanded SRAM retained by trusted bridge. LEDs off in both windows; original400MHz/DBG_SLEEP restored before awake park. Not whole-MCU power isolation. Own vector remains installed at final park.')
    raw.dump(b.output/'verified.json',result);return result

if __name__=='__main__':
    m,c=checked(HERE/'probe-v2');print(json.dumps(dict(offline_checked=True,sha256=raw.sha(c),entry=hex(m['entry']),park=hex(m['park']))))
