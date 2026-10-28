"""Offline native-sample analysis; never imports a hardware-access module.

Usage: analyze_isolated.py RUN --proof RUN/proof.bin --manifest BUILD/manifest.json
RUN/trace must have a complete result.json. All output is written in this analysis folder.
"""
from pathlib import Path
import argparse, json, struct, sys
import numpy as np

HERE = Path(__file__).resolve().parent
CAMPAIGN = HERE.parent
sys.path.insert(0, str(CAMPAIGN.parent/'power-ablation-20261028'))
from analyze_warm_ablations import load
from analyze_existing_baseline import FS, metrics, sha

def analyze(run, proof_path, manifest_path):
    manifest = json.loads(manifest_path.read_text())
    assert manifest['kind'] == 'isolated-nucleo-power'
    preparation = proof_path.parent
    if not (preparation/'probe-readback.bin').exists():
        preparation = run/'operation'
        assert proof_path.parent.name == 'reobserve'
        assert (preparation/'completed-proof.bin').read_bytes() == proof_path.read_bytes(), 'Reobserved proof must match original completed run'
    readback = preparation/'probe-readback.bin'
    assert readback.exists() and sha(readback) == manifest['sha256'], 'Exact loaded probe readback must match build manifest'
    raw = proof_path.read_bytes()
    assert len(raw) == manifest['proof_words']*4
    words = struct.unpack('<'+'I'*manifest['proof_words'], raw)
    p = dict(zip(manifest['fields'], words))
    verification_path = proof_path.parent/'verified.json'
    verification = json.loads(verification_path.read_text())
    assert verification['passed'] and verification['qualified_timed_wfi_returns']
    assert verification['session']['sha256'] == manifest['sha256']
    assert all(verification['proof'][k] == v for k, v in p.items())
    request_raw = (preparation/'isolated-request-readback.bin').read_bytes()
    request = struct.unpack('<8I', request_raw)
    assert request == (0x31514552, p['NONCE'], p['FLAGS'], p['DIVIDER'], 0, 0, 0, 0)
    assert request == tuple(verification['session']['request_words'])
    assert (proof_path.parent/'after-context-proof.bin').read_bytes() == raw
    assert sha(proof_path.parent/'completed-code.bin') == manifest['sha256']
    assert (proof_path.parent/'faults.bin').read_bytes() == bytes(8)
    context = verification['context']
    assert context['registers']['PC'] == manifest['park'] and context['registers']['PRIMASK'] == 1
    assert context['registers']['CONTROL'] == context['registers']['FAULTMASK'] == 0
    assert context['ccr'] & 0x30000 == 0 and context['fpccr'] & 1 == 0
    assert p['MAGIC'] == 0x314F5349 and p['VERSION'] == manifest['schema'] and p['VERSION'] in (1, 2, 3, 4, 5, 6) and p['NONCE']
    assert p['STATE'] == 8 and p['ERROR'] == 0 and p['TERMINAL'] == 0x454E4F44
    assert p['CFSR'] == p['HFSR'] == p['SYSTICK_FINAL'] == 0
    assert p['FINAL_PRIMASK'] == 1 and p['DBG_AFTER'] == p['DBG_BEFORE']
    assert p['SCR_AFTER'] == p['SCR_BEFORE'] and p['SCR_ACTIVE'] & 6 == 0
    assert p['PREFLIGHT_TICKS'] == 3 and 20 <= p['BUSY_TICKS'] <= 21
    assert 20 <= p['SLEEP_TICKS'] <= 21 and 0 < p['WFI_RETURNS'] == p['WFI_CALLS'] <= 1000
    assert p['GPIO_SAFE'] and p['LED_ODR_ACTIVE'] & 0x501 == 0x501
    assert p['LED_ODR_AFTER'] & 0x501 == 0x501 and p['PD12_ODR_AFTER'] & (1 << 12) == 0
    assert p['IC1_AFTER'] == p['IC1_BEFORE']
    cpu_hz = p.get('CPU_HZ', 400_000_000)
    if p['VERSION'] >= 2:
        assert p['CLOCK_SAFE'] and cpu_hz == 400_000_000//p['DIVIDER']
        assert p['SYSTICK_RELOAD'] == cpu_hz//100-1
    if p['VERSION'] >= 3:
        assert p['NVIC_ENABLE_BEFORE'] == 0 and p['PENDING_CLEARED'] == p['NVIC_PENDING_BEFORE']
    if p['VERSION'] >= 4:
        assert p['LP_SAFE']
        for active, before, after, mask in [('MEMLP_ACTIVE','MEMLPENR','MEMLP_AFTER',0xe),('AHB3LP_ACTIVE','AHB3LPENR','AHB3LP_AFTER',0x4200),('BUSLP_ACTIVE','BUSLPENR','BUSLP_AFTER',3),('BSECLP_ACTIVE','BSEC_LPCLOCK','BSECLP_AFTER',2)]:
            assert p[active] == p[before] | mask and p[after] == p[before]
    if p['VERSION'] >= 5:
        mask = 0x181 if p['FLAGS'] & 2 else 0
        assert p['MEM_RUN_ACTIVE'] == p['MEMENR_BEFORE'] & ~mask
        assert p['MEMENR_AFTER'] == p['MEMENR_BEFORE']
        if mask:
            assert p['RUN_TRIM_SAFE'] and p['MEM_RUN_ACTIVE'] & 0xe == 0xe
            assert 0x343af000 < p['RUN_MSP'] <= 0x343b0000 and 0x34300000 <= p['RUN_CODE'] < 0x34310000
    if p['VERSION'] >= 6:
        assert p['CCR_ACTIVE'] == p['CCR'] | (0x20000 if p['FLAGS'] & 4 else 0)
        assert p['CCR_AFTER'] == p['CCR']
        if p['FLAGS'] & 4: assert p['CACHE_SAFE']
    inventory = {}
    if 'rcc_inventory_names' in manifest:
        names = manifest['rcc_inventory_names']
        assert p['INVENTORY_COUNT'] == len(names)
        for label in ('before', 'after'):
            offset = manifest['rcc_inventory_'+label+'_word']
            inventory[label] = dict(zip(names, words[offset:offset+len(names)]))
            assert inventory[label] == verification['proof']['rcc_'+label]
        assert inventory['before'] == inventory['after'], 'Diagnostic must restore every recorded RCC register'
    signals, checks = load(run/'trace')
    start, gpi = signals['gpi0']
    changes = np.flatnonzero(gpi[1:] != gpi[:-1])+1
    edges = [{'sample_id': int(start+x), 'level': int(gpi[x])} for x in changes]
    pulses = []
    expected = [11, 12, 13, 14]
    for a, b in zip(edges, edges[1:]):
        if a['level'] == 1 and b['level'] == 0:
            width = (b['sample_id']-a['sample_id'])/FS*1e6
            candidates = [i for i in expected if abs(width-(2*i+.24)) <= .80]
            pulses.append(dict(sample_id=a['sample_id'], end_sample_id=b['sample_id'], width_us=width, candidates=candidates))
    trains = []
    for k in range(len(pulses)-3):
        train = pulses[k:k+4]
        # Instruction overhead changes with the CPU divider. Decode the entire
        # four-pulse signature jointly, with a bounded common width offset.
        offsets = [x['width_us']-2*i for x, i in zip(train, expected)]
        overhead = float(np.median(offsets))
        if not (-.25 <= overhead <= 3 and max(abs(x-overhead) for x in offsets) <= .75): continue
        busy = (train[1]['sample_id']-train[0]['sample_id'])/FS
        sleep = (train[3]['sample_id']-train[2]['sample_id'])/FS
        busy_dwt = ((p['BUSY_END']-p['BUSY_START']) & 0xffffffff)/cpu_hz
        if .18 < busy < .24 and .18 < sleep < .24 and abs(busy/busy_dwt-1) < .02 and abs(sleep/(p['SLEEP_TICKS']*.01)-1) < .02: trains.append((train, overhead))
    assert len(trains) == 1, ('unique bounded marker train', trains, pulses)
    train, width_overhead = trains[0]
    markers = dict(zip(expected, train))
    origin = markers[11]['sample_id']
    intervals = {}
    for name, a, b in [('busy', 11, 12), ('sleep', 13, 14)]:
        begin, end = markers[a]['sample_id'], markers[b]['sample_id']
        intervals[name+'_full'] = metrics(signals, begin, end, origin)
        intervals[name+'_middle'] = metrics(signals, begin+int(.025*FS), end-int(.025*FS), origin)
    busy, sleep = intervals['busy_middle'], intervals['sleep_middle']
    gpi1_start, gpi1 = signals['gpi1']
    gpi1_changes = np.flatnonzero(gpi1[1:] != gpi1[:-1])+1
    report = dict(run=run.name, scope='Camera and SD physically disconnected per root; warm RAM diagnostic, not a capture or cold boot.',
        proof_sha256=sha(proof_path), manifest_sha256=sha(manifest_path), binary_sha256=manifest['sha256'], proof=p,
        exact_probe_readback_sha256=sha(readback),
        measurement_proof=dict(verification_path=str(verification_path), proof_path=str(proof_path), preparation_path=str(preparation), verification_sha256=sha(verification_path), context=context, request=list(request), rcc_inventory=inventory,
            independent_checks=['Raw proof matches parsed proof','Exact pre/post probe code readback','Request nonce/flags/divider match','Proof unchanged after context read','No fault registers','Awake terminal PC and masks','Clocks/debug/LP masks restored','All recorded RCC inventory values restored']),
        markers=[dict(id=i, name=manifest['markers'][str(i)], **markers[i]) for i in expected],
        interval_boundary='Rising marker edges; middle windows discard 25 ms from both ends. Native JS sample IDs define wall time, not DWT across sleep.',
        marker_rule='Unique ordered 11,12,13,14 signature; fit common offset to width_us - 2*ID, allowed -0.25..3 us with residual <=0.75 us at 0.5 us sample grid. Both windows180..240ms; busy agrees with DWT and sleep with SysTick count within2%.',
        fitted_marker_overhead_us=width_overhead,
        checks=checks, intervals=intervals,
        reduction=dict(current_mA=busy['current_mean_mA']-sleep['current_mean_mA'], power_mW=(busy['power_mean']-sleep['power_mean'])*1000,
            fraction_percent=100*(1-sleep['power_mean']/busy['power_mean'])),
        all_gpi0_edges=edges, unclassified_gpi0_edges=len(edges)-8,
        all_gpi1_edges=[dict(sample_id=int(gpi1_start+x), level=int(gpi1[x])) for x in gpi1_changes],
        caveats=['Busy uses sustained LFSR/SRAM workload, not an SD polling loop.',
                 'Sleep includes periodic 100-Hz SysTick IRQs and WFI re-entry.',
                 'Current is the complete powered Nucleo rail, not a measurement of the MCU alone.',
                 'Final packed-GPI chunks are excluded because padding length is unresolved.',
                 'Any startup nonfinite samples remain invalid in whole-session checks; bounded intervals independently require finite samples and continuity.'])
    out = HERE/(run.name+'-analysis.json')
    out.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(dict(run=run.name, busy_ms=intervals['busy_full']['duration_ms'], sleep_ms=intervals['sleep_full']['duration_ms'],
        busy_mA=busy['current_mean_mA'], sleep_mA=sleep['current_mean_mA'], reduction=report['reduction'], output=str(out)), indent=2))
    return report

if __name__ == '__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('run', type=Path); ap.add_argument('--proof', type=Path, required=True); ap.add_argument('--manifest', type=Path, required=True)
    a=ap.parse_args(); analyze(a.run, a.proof, a.manifest)
