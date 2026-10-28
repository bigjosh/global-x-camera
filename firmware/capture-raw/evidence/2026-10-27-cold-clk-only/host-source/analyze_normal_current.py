"""Offline replay of the reviewed current-step algorithm, with normal-boot scope."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--trace',type=Path,required=True)
    p.add_argument('--analyzer',type=Path,required=True)
    p.add_argument('--reference',type=Path,required=True)
    p.add_argument('--observer',type=Path)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    rows=[json.loads(line) for line in a.trace.read_text().splitlines()]
    launch=next(r['utc'] for r in rows if r.get('event')=='power_on')
    spec=importlib.util.spec_from_file_location('reviewed_led_current',a.analyzer)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    result=module.analyze(a.trace,launch,4)
    reference=json.loads(a.reference.read_text())
    observation=json.loads(a.observer.read_text()) if a.observer else {}
    fresh=bool(observation.get('complete_core_observation') and observation.get('fresh_error_proof'))
    result['normal_boot_scope']={
        'hardware_access_by_analysis':False,
        'firmware':'Unchanged installed normal firmware; no injected error',
        'debug_status_obtained':fresh,
        'observer':str(a.observer) if a.observer else None,
        'observer_summary':observation.get('summary'),
        'interpretation':'Current changes are consistent with the existing four-blink error pattern if algorithm checks pass; no direct LED observation or command/error attribution.',
        'analyzer':str(a.analyzer),
        'analyzer_sha256':hashlib.sha256(a.analyzer.read_bytes()).hexdigest(),
        'reference':str(a.reference),
        'reference_sha256':hashlib.sha256(a.reference.read_bytes()).hexdigest(),
        'reference_measured':reference['measured'],
        'reference_timing_consistency':reference['timing_consistency'],
        'reference_complete_pattern_observed':reference['complete_pattern_observed'],
        'reference_plateau':reference['low_current_plateau'],
        'same_group_counts_as_reference':result['measured']['groups']==reference['measured']['groups'],
    }
    result['limits'][0]='LED/error-code association is inferred from characteristic current changes of normal uninjected firmware and a prior validated trace; no optical/GPIO probe.'
    if not fresh:result['limits'][0]+=' No fresh SRAM status was available.'
    result['limits'].append('The four-blink category cannot identify a command, CRC error, failed LBA, or electrical cause. No successful-save or Standby claim.')
    a.out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('complete_pattern_observed','timing_consistency','measured','low_current_plateau')},indent=2))


if __name__=='__main__':main()
