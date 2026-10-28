"""Offline-only validation of sleep proof/code recovered after hardware reset.

Does not establish a live PC, pre-reset fault status, or time spent asleep.
The first live observation failed before reading any SRAM; retain that failure.
"""
import argparse
import importlib.util
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('sleep_run_retained',HERE/'run.py')
r=importlib.util.module_from_spec(s);s.loader.exec_module(r)

def validate(proof_path,code_path):
    m,_=r.checked_probe()
    p=r.decode(Path(proof_path).read_bytes(),m)
    code=Path(code_path).read_bytes()
    dt=(p['HOLD_END']-p['HOLD_BEGIN'])&0xffffffff
    clocks=(('APB5_CLOCK','APB5_AFTER'),('DIVIDERS','DIVIDERS_AFTER'),
        ('SD_CLOCKS','SD_CLOCKS_AFTER'),('BSEC_CLOCK','BSEC_AFTER'),('DEBUG_CR','DEBUG_CR_AFTER'))
    checks=dict(identity=p['MAGIC']==0x31504c53 and p['VERSION']==1,
        prepared_wfi_boundary=p['STATE']==3 and p['ERROR']==0,
        stub_survived=r.raw.sha(code)==r.PROBE,
        hold_200ms=80000000<=dt<=80400000,
        privileged_masked_context=not(p['CCR']&0x30000) and p['CONTROL']==0 and p['IPSR']==0 and
            p['PRIMASK']==1 and p['FAULTMASK']==0 and not(p['FPCCR']&1),
        no_systick=p['SYSTICK']==0,
        real_shallow_sleep_requested=not(p['DEBUG_CR']&1) and not(p['SCR_AFTER']&0x16),
        no_enabled_or_pending_interrupts=all(p[k]==0 for k in
            ('ENABLE_AFTER','PENDING_AFTER','NS_ENABLE_AFTER','NS_PENDING_AFTER')),
        unchanged_recorded_clocks=all(p[x]==p[y] for x,y in clocks),
        core_clock_matches=p['CFGR1']==0x33330000 and p['CFGR2']==0x100000 and
            p['PLL1_1']==0x404b00 and p['PLL1_2']==0 and p['PLL1_3']==0x49000005,
        stack_in_reserved_region=p['MSPLIM']==0x343af000 and 0x343af000<p['MSP']<=0x343b0000)
    return dict(retained_pre_wfi_checks_passed=all(checks.values()),checks=checks,proof=p,
        hold_ms=dt/400000,code_sha256=r.raw.sha(code),live_wfi_pc_proven=False,
        live_observation_failed=True,retention_scope='Observed bytes after reset only; general SRAM reset retention is not qualified.',
        qualification='STATE3 is stored immediately before DSB/ISB/WFI. It proves reaching that boundary, not execution duration or live WFI PC. Original HOTPLUG observation failed before SRAM read; hardware reset invalidated live PC/fault/clock state. Correlate external 11/12 markers and current trace separately. No nonce was stored: attribution is to this sole sleep-probe launch and its frozen measured session, not arbitrary future runs.')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('proof',type=Path);p.add_argument('code',type=Path);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();result=validate(a.proof,a.code)
    a.out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('retained_pre_wfi_checks_passed','hold_ms','live_wfi_pc_proven')}))
