"""Run the explicit RAM idle-card WFI diagnostic; never grant capture success.

No reset, power switching, NOR or explicit SD commands. Launch requires the
existing exact recovery/bridge proof. After launch this runner only uploads
RAM evidence; it does not halt, recover, retry or issue a subsequent request.
The diagnostic intentionally returns failure before CMD25, even when its
finite idle-WFI check passes. Results are not an idle permission token.
"""
import argparse
import json
from pathlib import Path
import secrets
import struct
import time
from types import SimpleNamespace

import bench

FIELDS=('magic version state result context_faults lifecycle_faults awake_tick_begin awake_tick_end '
    'awake_cycle_begin awake_cycle_end sleep_tick_begin sleep_tick_end sleep_cycle_begin sleep_cycle_end '
    'wfi_calls wfi_returns commands_before commands_after written_before written_after cfsr hfsr '
    'sd_sta_before sd_sta_after').split()


def decode(raw):
    if len(raw)!=96:raise ValueError('Incomplete DSP1 probe record')
    p=dict(zip(FIELDS,struct.unpack('<24I',raw)))
    p.update(awake_wall_ms=(p['awake_tick_end']-p['awake_tick_begin'])&0xFFFFFFFF,
        sleep_wall_ms=(p['sleep_tick_end']-p['sleep_tick_begin'])&0xFFFFFFFF,
        awake_active_cycles=(p['awake_cycle_end']-p['awake_cycle_begin'])&0xFFFFFFFF,
        sleep_active_cycles=(p['sleep_cycle_end']-p['sleep_cycle_begin'])&0xFFFFFFFF)
    return p


def validate_record(p):
    if (p['magic']!=0x31505344 or p['version']!=1 or p['state']!=4 or p['result'] or
        p['context_faults'] or p['lifecycle_faults'] or not 3<=p['awake_wall_ms']<=4 or
        not 20<=p['sleep_wall_ms']<=21 or not 1<=p['wfi_calls']==p['wfi_returns']<=1000 or
        not p['commands_before'] or p['commands_before']!=p['commands_after'] or
        p['written_before'] or p['written_after'] or p['cfsr'] or p['hfsr'] or
        p['sd_sta_before']&0x3000 or p['sd_sta_after']&0x3000):
        raise ValueError('Idle-card WFI probe did not pass its bounded context/no-command checks')


def retain(b,m,code,nonce,out,names):
    """Only reads after launch; failed/partial evidence is saved before validation."""
    raw=b.upload(m['dma_sleep_probe_address'],96,'probe.bin');probe=decode(raw)
    (out/'probe.bin').write_bytes(raw);bench.dump(out/'probe.json',probe)
    p=bench.decode(b.upload(bench.PROOF,384,'terminal.bin'),names)
    wait_raw,wait=bench.dma_wait_snapshot(b,m)
    clocks_raw,clocks=bench.dma_sleep_clocks_snapshot(b,m)
    card_raw=b.upload(m['card'],200,'probe-card.bin');card=bench.decode_card(card_raw)
    observed=b.upload(bench.LOAD,m['immutable_bytes'],'probe-code.bin')
    cfsr,hfsr=struct.unpack('<2I',b.upload(0xE000ED28,8,'probe-current-faults.bin'))
    final=bench.decode(b.upload(bench.PROOF,384,'probe-final-terminal.bin'),names)
    for name,data in (('terminal.bin',struct.pack('<96I',*[p[n] for n in names])),
            ('dma-wait.bin',wait_raw),('dma-sleep-clocks.bin',clocks_raw),('card.bin',card_raw)):
        (out/name).write_bytes(data)
    result=dict(kind='ram-idle-wfi-diagnostic',probe=probe,terminal=p,wait=wait,clocks=clocks,card=card,
        nonce=nonce,binary_sha256=bench.sha(code),immutable_code_equal=observed==code[:m['immutable_bytes']],
        terminal_unchanged=final==p,cfsr=cfsr,hfsr=hfsr,diagnostic_passed=False,
        capture_success=False,sd_payload_integrity_verified=False,idle_permission=False,
        sleep_entered_proven=False,post_launch_execution_control=False,
        scope='Finite WFI returns and SysTick progression on an idle initialized card; no CMD25 or image write',
        cycle_qualification='DWT deltas are active-clock cycles; external power measurements qualify actual savings')
    bench.dump(out/'retained.json',result)
    expected=dict(magic=bench.MAGIC,schema=1,words=96,nonce=nonce,operation=1,state=15,
        result=0x334,terminal=bench.DONE,stage=5,card_write_lo=0,card_write_hi=0,written_sectors=0,
        chunk_count=0,chunk_overflow=0,completion=0,flags=m['expected_flags'],
        card=m['card'],card_size=200,slots=m['slots'],slots_size=640)
    if any(p.get(k)!=v for k,v in expected.items()):
        raise ValueError('Probe did not reach the exact intentional failed-capture terminal')
    if not result['immutable_code_equal'] or not result['terminal_unchanged'] or cfsr or hfsr:
        raise ValueError('Probe executable/terminal identity changed or MCU fault flags set')
    if card['written_sectors'] or any(wait[k] for k in
            ('wait_calls','wall_ms','active_cycles','immediate_wakes','context_faults')):
        raise ValueError('Idle probe unexpectedly entered the DMA write path')
    bench.validate_dma_sleep_clocks(clocks)
    validate_record(probe)
    result['diagnostic_passed']=True
    bench.dump(out/'result.json',result)
    return result


def run(a):
    folder=a.build.resolve();m,code=bench.checked_build(folder,a.expected_sha,diagnostic_probe=True)
    names=bench.fields(folder);nonce=secrets.randbelow(0xFFFFFFFF)+1
    req=bench.request(1,nonce,magic_format=True)
    a.out.mkdir(parents=True,exist_ok=False)
    bench.dump(a.out/'plan.json',dict(execute=a.execute,build=str(folder),binary_sha256=bench.sha(code),
        request_words=list(struct.unpack('<16I',req)),kind='RAM-only idle WFI probe',
        reset=False,power_switch=False,nor_commands=False,expected_image_write=False,idle_permission=False))
    if not a.execute:
        print('Offline diagnostic admission passed; no hardware accessed');return
    boot=bench.ROOT/'tmp/bringup/capture-sleep-20261020/recovery-read-bridge-v1'
    _,boot_code=bench.bridge.checked_bridge(boot)
    if a.bridge_proof:
        b=bench.sd.Bench(a.out/'operation');prior=json.loads(a.bridge_proof.read_text())
        if prior['bridge_sha256']!=bench.bridge.BOOT_SHA:raise ValueError('Unknown bridge identity')
        live=bench.bridge.checked_boot(b.upload(bench.bridge.BOOT_PROOF,92,'bridge-proof.bin'),prior['proof']['nonce'])
        if live!=prior['proof'] or b.upload(bench.bridge.LOAD,len(boot_code),'bridge-code.bin')!=boot_code:
            raise ValueError('Bridge identity changed')
        bench.sd.context_proof(b,{bench.bridge.BOOT_PARK},'bridge-before')
    else:
        b=bench.bridge.bootstrap(SimpleNamespace(recovery_build=a.recovery_build,bridge=boot),a.out,boot_code)
    b.call('-halt','-w',folder/'capture.bin',hex(bench.LOAD),'-v',success='Download verified successfully')
    if b.upload(bench.LOAD,len(code),'executable-readback.bin')!=code:raise ValueError('Code readback mismatch')
    (b.output/'probe-request.bin').write_bytes(req);(b.output/'probe-clear.bin').write_bytes(bytes(384))
    b.call('-halt','-w',b.output/'probe-request.bin',hex(bench.REQUEST),'-v',
        '-w',b.output/'probe-clear.bin',hex(bench.PROOF),'-v',success='Download verified successfully')
    if (b.upload(bench.REQUEST,64,'probe-request-readback.bin')!=req or
        b.upload(bench.PROOF,384,'probe-clear-readback.bin')!=bytes(384)):
        raise ValueError('Request/proof readback mismatch')
    b.call('-halt','-coreReg',f"PC={hex(m['entry'])}",'XPSR=0x01000000','-run',success='Core run')
    deadline=time.monotonic()+30;poll=0
    while True:
        p=bench.decode(b.upload(bench.PROOF,384,f'proof-{poll:04d}.bin'),names)
        if p['magic']==bench.MAGIC and p['nonce']==nonce and p['terminal']==bench.DONE:break
        if time.monotonic()>=deadline:
            bench.dump(a.out/'incomplete.json',p)
            raw=b.upload(m['dma_sleep_probe_address'],96,'incomplete-probe.bin')
            (a.out/'incomplete-probe.bin').write_bytes(raw)
            bench.dump(a.out/'incomplete-probe.json',decode(raw))
            raise TimeoutError('Probe has no terminal; no halt/reset/retry was sent')
        poll+=1;time.sleep(.2)
    result=retain(b,m,code,nonce,a.out,names)
    print(json.dumps(result),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build',type=Path,required=True);p.add_argument('--expected-sha',required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--recovery-build',type=Path,required=True)
    p.add_argument('--bridge-proof',type=Path);p.add_argument('--execute',action='store_true')
    run(p.parse_args())


if __name__=='__main__':main()
