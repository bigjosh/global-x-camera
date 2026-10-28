"""Inert on import. Root may explicitly prepare/launch/observe this diagnostic.

prepare() requires the successful isolated-v4 sweep's fresh exact awake park,
enabled/non-reset AXISRAM banks and matching live code/proof before RAM loading.
The early recovery prefix alone does not enable this high SRAM and is rejected.
No reset, supply control, flash or SD commands; one BMCR powerdown write and one restore. Final PC is the checked
diagnostic branch-to-self; this does not claim persistent halt after disconnect.
"""
from pathlib import Path
import hashlib,importlib.util,json,re,struct,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
sys.path.insert(0,str(ROOT/'firmware/boot-timing'))
from nor_bench import Bench
ISOLATED_BUILD=HERE.parent.parent/'probe-v5'
sp=importlib.util.spec_from_file_location('mdio_isolated_gate',HERE.parent.parent/'run_v5.py')
isolated=importlib.util.module_from_spec(sp);sp.loader.exec_module(isolated)
SHA='d55a735bacfebfb9bd6efd1a35b7af2b0794c239794b42e79a84af95494ec828'
FIELDS=('magic version state error cleanup begin end dwt_hz '
        'rcc0 rcc1 rstr0 cfgr1 cfgr2 ic1 pll1a pll1b pll1c dwt_ctrl demcr '
        'mdio_high0 mdio_low mdio_high1 mdc_low mdc_high mdc_low2 '
        'clock_low_fail clock_high_fail bit_count scan_count match_count '
        'first_match restore_match').split()
TAIL=('control ipsr msp msplim old_msp old_msplim reserved2 reserved3').split()
PIN_FIELDS=('mode type speed pull af odr').split()
def sha(b):return hashlib.sha256(b).hexdigest()
def checked_probe():
 m=json.loads((HERE/'manifest.json').read_text());code=(HERE/'power_aba.bin').read_bytes()
 if m['sha256']!=SHA or sha(code)!=SHA or len(code)!=3312:raise ValueError('Frozen diagnostic differs')
 if (m['load'],m['entry'],m['park'],m['proof'],m['proof_words'])!=(0x343c4000,0x343c4cc5,0x343c4546,0x343c6000,512):
  raise ValueError('Diagnostic map differs')
 for name,digest in m['sources'].items():
  if sha((HERE/name).read_bytes())!=digest:raise ValueError('Source differs: '+name)
 if code[m['park']-m['load']:m['park']-m['load']+2]!=b'\xfe\xe7':raise ValueError('Park instruction differs')
 return m,code
def prepare(output,prior):
 """Root-only. prior is the main isolated-v4 sweep's successful verified.json.

 There is deliberately no early-prefix, recovery or automatic bootstrap route.
 RCC clocks/resets are checked before any high-SRAM read or write. A fresh exact
 main-probe context, proof and executable must match its successful result.
 """
 out=Path(output).resolve();out.relative_to(ROOT/'tmp');out.mkdir(parents=True,exist_ok=False)
 m,code=checked_probe()
 main,main_code=isolated.checked(ISOLATED_BUILD)
 previous=json.loads(Path(prior).read_text())
 if previous.get('passed') is not True:raise ValueError('Main sweep did not succeed')
 session=previous['session']
 if any(session[k]!=main[k] for k in ('sha256','load','bytes','park','proof','entry')):
  raise ValueError('Only frozen isolated-v4 final state is admitted')
 isolated.validate(previous['proof'],session)
 b=Bench(out/'debug')
 memenr,=struct.unpack('<I',b.upload(0x5602824c,4,'before-memenr.bin'))
 memrstr,=struct.unpack('<I',b.upload(0x5602820c,4,'before-memrstr.bin'))
 if memenr&0x18f!=0x18f or memrstr&0x18f:
  raise ValueError('Expanded AXISRAM is gated/reset; no high-SRAM access attempted')
 context=isolated.raw.sd.context_proof(b,{main['park']},'main-context')
 live=isolated.decode(b.upload(main['proof'],1024,'main-proof.bin'),main)
 if live!=previous['proof'] or memenr!=live['MEMENR_AFTER']:
  raise ValueError('Live main proof or memory clocks differ')
 isolated.validate(live,session)
 if b.upload(main['load'],len(main_code),'main-code.bin')!=main_code:
  raise ValueError('Main executable differs')
 faults=struct.unpack('<II',b.upload(0xe000ed28,8,'before-faults.bin'))
 if any(faults):raise ValueError('Live fault flags set')
 b.call('-halt','-w',HERE/'power_aba.bin',hex(m['load']),'-v',success='Download verified successfully')
 if b.upload(m['load'],len(code),'diagnostic-readback.bin')!=code:raise ValueError('RAM readback differs')
 (out/'prepared.json').write_text(json.dumps({'prior':str(Path(prior).resolve()),
   'main_context':context,'main_proof':live,'memenr':memenr,'memrstr':memrstr,'diagnostic':m},indent=2)+'\n')
 return b,m
def prepare_from_refused_v3(output,prepared,proof_file):
 """Root-only, one exact v3 sleep-clock guard refusal; never labels that sweep passed.

 Camera/SD are physically absent. ERROR7 preceded GPIO/debug/timer/workload
 changes: the required sleep-clock permission was absent. Its IRQ-masked awake park is
 admitted for this polling-only diagnostic, not as a generic failure override.
 """
 saved=Path(prepared).read_bytes();proof_bytes=Path(proof_file).read_bytes()
 if sha(saved)!='19040c36c5c265d4049cde295cd358bde2c6a9ba9ce50de426539a4e2517bdaf' or sha(proof_bytes)!='ba602591310bd9872b30391ec311e2aa45c18e130fa844975b4815d5b237172a':
  raise ValueError('Only the reviewed cpu400a/operation refusal is admitted')
 session=json.loads(saved);expected=json.loads(proof_bytes)
 sp3=importlib.util.spec_from_file_location('mdio_isolated_v3_gate',HERE.parent.parent/'run_v3.py')
 isolated3=importlib.util.module_from_spec(sp3);sp3.loader.exec_module(isolated3)
 main,main_code=isolated3.checked(HERE.parent.parent/'probe-v3');m,code=checked_probe()
 if main['sha256']!='c1ee79c7ecb6c005f71c06c8c1d6322026d38b42727a7874302d67a3e93666d1':raise ValueError('Exact v3 image required')
 if any(session[k]!=main[k] for k in ('sha256','load','bytes','park','proof','entry')):
  raise ValueError('Refusal executable identity differs')
 exact=dict(MAGIC=0x314f5349,VERSION=3,NONCE=36618274,STATE=15,ERROR=7,FLAGS=0,
  DIVIDER=1,CONTROL=0,IPSR=0,PRIMASK=1,FAULTMASK=0,DEBUG_SAFE=0,GPIO_SAFE=0,
  NVIC_ENABLE_BEFORE=0,NVIC_ENABLE_AFTER=0,NVIC_PENDING_BEFORE=64,NVIC_PENDING_AFTER=0,
  SYSTICK_BEFORE=0,SYSTICK_FINAL=0,TICKS=0,PREFLIGHT_TICKS=0,BUSY_ITERATIONS=0,
  WFI_CALLS=0,WFI_RETURNS=0,FINAL_PRIMASK=1,CFSR=0,HFSR=0,TERMINAL=0x454e4f44,
  IC1_AFTER=0x20000,VTOR_ACTIVE=0x34300000)
 if any(expected[k]!=v for k,v in exact.items()):raise ValueError('Guard refusal schema differs')
 out=Path(output).resolve();out.relative_to(ROOT/'tmp');out.mkdir(parents=True,exist_ok=False)
 b=Bench(out/'debug')
 memenr,=struct.unpack('<I',b.upload(0x5602824c,4,'before-memenr.bin'))
 memrstr,=struct.unpack('<I',b.upload(0x5602820c,4,'before-memrstr.bin'))
 if memenr&0x18f!=0x18f or memrstr&0x18f:
  raise ValueError('Expanded AXISRAM is gated/reset; no high-SRAM access attempted')
 context=isolated.raw.sd.context_proof(b,{main['park']},'main-refused-context')
 live=isolated3.decode(b.upload(main['proof'],1024,'main-refused-proof.bin'),main)
 if live!=expected or memenr!=live['MEMENR_AFTER']:raise ValueError('Live refusal differs')
 if b.upload(main['load'],len(main_code),'main-refused-code.bin')!=main_code:
  raise ValueError('Refused executable differs')
 cfgr=struct.unpack('<II',b.upload(0x56028020,8,'before-cfgr.bin'))
 pll=struct.unpack('<III',b.upload(0x56028080,12,'before-pll1.bin'))
 ic1,=struct.unpack('<I',b.upload(0x560280c4,4,'before-ic1.bin'))
 faults=struct.unpack('<II',b.upload(0xe000ed28,8,'before-faults.bin'))
 if cfgr!=(0x33330000,0x100000) or pll!=(0x404b00,0,0x49000005) or ic1!=0x20000 or any(faults):
  raise ValueError('Clock or fault state differs')
 b.call('-halt','-w',HERE/'power_aba.bin',hex(m['load']),'-v',success='Download verified successfully')
 if b.upload(m['load'],len(code),'diagnostic-readback.bin')!=code:raise ValueError('RAM readback differs')
 (out/'prepared.json').write_text(json.dumps({'source_run_passed':False,
  'refusal_reason':'v3 ERROR7: absent sleep-clock permissions; no workload run',
  'source_prepared':str(Path(prepared).resolve()),'source_proof':str(Path(proof_file).resolve()),
  'main_context':context,'main_refusal':live,'memenr':memenr,'memrstr':memrstr,
  'diagnostic':m},indent=2)+'\n')
 return b,m

def launch(b,m):
 b.call('-halt','-coreReg',f"PC={hex(m['entry'])}",'XPSR=0x01000000','-run',success='Core run')
EXTRA=('id1 id2 bmcr0 bmcr1 requested after0 after1 restored0 restored1 polls writes restore_writes restored failure_stage restore_error').split()
WINDOWS=('a_start a_end b_start b_end c_start c_end settle_cycles hold_cycles a_loops b_loops c_loops restore_id1 restore_id2 marker_error d_safe').split()

def decode(data):
 if len(data)!=2048:raise ValueError('Incomplete power A/B/A record')
 w=struct.unpack('<512I',data);d=dict(zip(FIELDS,w[:32]));d.update(zip(TAIL,w[56:64]))
 for name,pos in [('f_before',32),('g_before',38),('f_after',44),('g_after',50),('d_before',96),('d_after',102)]:
  d[name]=dict(zip(PIN_FIELDS,w[pos:pos+6]))
 d.update(zip(EXTRA,w[64:79]));d.update(zip(WINDOWS,w[80:95]))
 return d

def validate(d,pc,code,cfsr,hfsr,m):
 pads=[d[k] for k in ('mdio_high0','mdio_low','mdio_high1','mdc_low','mdc_high','mdc_low2')]
 exact=dict(magic=0x33414241,version=3,state=8,error=0,cleanup=0,dwt_hz=400000000,
  cfgr1=0x33330000,cfgr2=0x100000,ic1=0x20000,pll1a=0x404b00,pll1b=0,pll1c=0x49000005,
  clock_low_fail=0,clock_high_fail=0,restore_match=1,control=0,ipsr=0,msplim=0x343af000,
  id1=7,id2=0xc131,bmcr0=0x3000,bmcr1=0x3000,requested=0x3800,after0=0x3800,after1=0x3800,
  restored0=0x3000,restored1=0x3000,writes=1,restore_writes=1,restored=1,restore_error=0,
  failure_stage=0,restore_id1=7,restore_id2=0xc131,settle_cycles=40000000,hold_cycles=120000000,
  marker_error=0,d_safe=1)
 intervals={k:((d[k+'_end']-d[k+'_start'])&0xffffffff)/400000 for k in ('a','b','c')}
 complete=(all(d[k]==v for k,v in exact.items()) and pc==m['park'] and sha(code)==SHA
  and cfsr==hfsr==0 and pads==[1,0,1,0,1,0] and 1<=d['polls']<=100
  and d['f_before']==d['f_after'] and d['g_before']==d['g_after'] and d['d_before']==d['d_after']
  and d['rcc0']==d['rcc1'] and d['bit_count']>=780 and d['bit_count']%65==0
  and all(299.99<=v<=300.1 for v in intervals.values())
  and all(0<d[k+'_loops']<=100000000 for k in ('a','b','c')))
 return {'completed_and_restored':complete,'phy_restored_verified':d['restored']==1 and not d['restore_error'],
  'window_ms':intervals,'markers':{'11':'baseline_begin','12':'baseline_end','13':'powerdown_begin',
   '14':'powerdown_end','15':'restored_begin','16':'restored_end'},
  'scope':'Matched400MHz busy-loop PHY BMCR A/B/A. No MCU/camera/SD power attribution beyond measured difference.'}

def observe(b,m):
 """Call after at least 3 seconds; no automatic retry/recovery on failure."""
 first=decode(b.upload(m['proof'],2048,'proof-before.bin'))
 if first['state'] not in (8,15):raise ValueError('Power probe remains active; no halt or other operation issued')
 text=b.call('-halt','-coreReg')
 match=re.search(r'\bPC\s*[:=]\s*(?:0x)?([0-9a-fA-F]+)',text)
 if not match:raise ValueError('Cannot parse PC; keep diagnostic evidence')
 pc=int(match[1],16)
 code=b.upload(m['load'],m['bytes'],'diagnostic-after.bin')
 final=decode(b.upload(m['proof'],2048,'proof-after.bin'))
 cfsr,hfsr=struct.unpack('<II',b.upload(0xe000ed28,8,'faults.bin'))
 result=validate(final,pc,code,cfsr,hfsr,m)
 result.update(proof=final,proof_stable=first==final,pc=pc,cfsr=cfsr,hfsr=hfsr,code_sha256=sha(code))
 result['completed_and_restored'] &= result['proof_stable']
 (b.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
 return result
if __name__=='__main__':
 m,c=checked_probe();print(json.dumps({'offline_checked':True,'sha256':sha(c),'entry':hex(m['entry']),'park':hex(m['park'])}))
