"""Offline import is inert. Root alone calls prepare/launch/observe around JS logging.

Requires exact successful normal RAM capture/read terminal. No reset, power,
NOR, SD operation, or automatic retry. Observe only AFTER the measured window.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
spec = importlib.util.spec_from_file_location('sleep_raw_bench', ROOT/'firmware/capture-raw/bench.py')
raw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(raw)
NORMAL = '30c6a539a506a1b5ec963c382f190987aef6f8f68a0baa2e533c70a1a651b866'
PROBE = '186ae115cd0d8340f91c45bb779e3e72ca939415273cb0b4b767f7886dc813a3'

def checked_probe():
    m = json.loads((HERE/'manifest.json').read_text())
    code = (HERE/'probe.bin').read_bytes()
    if m['sha256'] != PROBE or raw.sha(code) != PROBE or len(code) != 1516:
        raise ValueError('Frozen sleep probe differs')
    if (m['load'],m['entry'],m['proof'],m['proof_words'],m['wfi'],m['after_wfi']) != (
            0x343C1000,0x343C1015,0x343C2000,128,0x343C14D6,0x343C14DE):
        raise ValueError('Sleep probe bounds differ')
    for name, digest in m['sources'].items():
        if raw.sha((HERE/name).read_bytes()) != digest:
            raise ValueError('Sleep probe source differs: '+name)
    if code[m['wfi']-m['load']:m['wfi']-m['load']+2] != b'\x30\xbf':
        raise ValueError('WFI instruction differs')
    return m,code

def prepare(build, prior_path, output):
    """Validate current successful terminal, load/readback isolated stub; do not run."""
    build,output=Path(build).resolve(),Path(output).resolve()
    m,code=raw.checked_build(build,NORMAL)
    prior=json.loads(Path(prior_path).read_text())
    if prior.get('passed') is not True or prior['proof']['operation'] not in (1,3):
        raise ValueError('Require a successful normal capture/read terminal')
    probe,payload=checked_probe()
    b=raw.sd.Bench(output)
    context=raw.terminal_gate(b,build,m,code,prior,'before-sleep')
    coreclock,=struct.unpack('<I',b.upload(m['system_core_clock'],4,'core-clock.bin'))
    if coreclock != 400000000:raise ValueError('Require 400MHz awake baseline')
    b.call('-halt','-w',HERE/'probe.bin',hex(probe['load']),'-v',success='Download verified successfully')
    if b.upload(probe['load'],len(payload),'probe-readback.bin') != payload:
        raise ValueError('Sleep probe RAM readback differs')
    raw.dump(output/'prepared.json',dict(build=str(build),prior=str(prior_path),context=context,probe=probe))
    return b,probe

def launch(b,m):
    """Call only after JS logging has started. No further STLINK call during trace."""
    b.call('-halt','-coreReg',f"PC={hex(m['entry'])}",'XPSR=0x01000000','-run',success='Core run')

def decode(data,m):
    if len(data)!=512:raise ValueError('Incomplete sleep proof')
    return dict(zip(m['fields'][:-1],struct.unpack('<128I',data)))

def observe(b,m):
    """Only after measurement. Read proof then halt PC/code; never reset/recover."""
    before=decode(b.upload(m['proof'],512,'sleep-proof-before-halt.bin'),m)
    registers=raw.sd.context_registers(b.call('-halt','-coreReg'))
    payload=b.upload(m['load'],m['bytes'],'sleep-code-after.bin')
    after=decode(b.upload(m['proof'],512,'sleep-proof-after-halt.bin'),m)
    cfsr,hfsr=struct.unpack('<II',b.upload(0xE000ED28,8,'fault-registers.bin'))
    clocks=(('APB5_CLOCK','APB5_AFTER'),('DIVIDERS','DIVIDERS_AFTER'),
            ('SD_CLOCKS','SD_CLOCKS_AFTER'),('BSEC_CLOCK','BSEC_AFTER'),('DEBUG_CR','DEBUG_CR_AFTER'))
    duration=(after['HOLD_END']-after['HOLD_BEGIN'])&0xffffffff
    passed=(after['MAGIC']==0x31504C53 and after['VERSION']==1 and after['STATE']==3 and
            after['ERROR']==0 and raw.sha(payload)==PROBE and cfsr==0 and hfsr==0 and
            m['wfi']<=registers.get('PC',0)<=m['after_wfi']+2 and
            80000000<=duration<=80400000 and not(after['DEBUG_CR']&1) and
            not(after['SCR_AFTER']&0x16) and after['SYSTICK']==0 and
            all(after[k]==0 for k in ('ENABLE_AFTER','PENDING_AFTER','NS_ENABLE_AFTER','NS_PENDING_AFTER')) and
            all(after[x]==after[y] for x,y in clocks) and
            all(before[k]==after[k] for k in before if k!='WFI_RETURNS'))
    result=dict(passed=passed,proof=after,proof_before_halt=before,registers=registers,
        cfsr=cfsr,hfsr=hfsr,hold_ms=duration/400000,wfi_loop_reached=passed,
        code_sha256=raw.sha(payload),
        qualification='Post-window debugger reads/halt may wake WFI. PC proves loop reached; external current trace qualifies actual sleeping interval. No clock, rail, SD or NOR change; IRQs masked/cleared and SCR made shallow. CLI disconnect may resume; no permanent-halt claim.')
    raw.dump(b.output/'observation.json',result)
    return result

if __name__=='__main__':
    m,c=checked_probe()
    print(json.dumps(dict(offline_checked=True,sha256=raw.sha(c),entry=hex(m['entry']),proof=hex(m['proof']))))
