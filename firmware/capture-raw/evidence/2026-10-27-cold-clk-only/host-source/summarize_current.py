"""Offline summary of a root-owned cold_led_trace recording; no hardware API."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path


EPOCH2018 = datetime(2018, 1, 1, tzinfo=timezone.utc).timestamp()


def describe(rows):
    finite = [r for r in rows if r.get('complete_bin') and r.get('nonfinite_count') == 0 and
              isinstance(r.get('mean'), (int, float)) and math.isfinite(r['mean'])]
    if not finite:return dict(complete_finite_bins=0)
    count = sum(r['finite_count'] for r in finite)
    return dict(complete_finite_bins=len(finite), samples=count,
        weighted_mean=sum(r['mean']*r['finite_count'] for r in finite)/count,
        min_bin_mean=min(r['mean'] for r in finite),max_bin_mean=max(r['mean'] for r in finite),
        min_sample=min(r['min'] for r in finite),max_sample=max(r['max'] for r in finite),
        first_utc=datetime.fromtimestamp(EPOCH2018+finite[0]['utc_time64']/2**30, timezone.utc).isoformat(),
        last_bin_end_utc=datetime.fromtimestamp(EPOCH2018+finite[-1]['utc_time64']/2**30+
                                              finite[-1]['duration_s'], timezone.utc).isoformat(),
        complete_finite_bins_contiguous=all(a['sample_id_end_exclusive']==b['sample_id']
                                           for a,b in zip(finite,finite[1:])),
        excluded_partial_or_nonfinite_bins=len(rows)-len(finite),
        last_bin_mean=finite[-1]['mean'])


def summarize(trace, observer):
    raw = trace.read_bytes()
    rows = [json.loads(line) for line in raw.decode().splitlines()]
    power = next(r for r in rows if r.get('event')=='power_on')
    stopped = next(r for r in reversed(rows) if r.get('event')=='stopped')
    power_utc = datetime.fromisoformat(power['utc']).timestamp()
    post = [r for r in rows if r.get('event')=='bin' and
            EPOCH2018+r['utc_time64']/2**30 >= power_utc+.1]
    observation = json.loads(observer.read_text())
    coverage = stopped['coverage']
    current = describe([r for r in post if r['signal']=='current'])
    voltage = describe([r for r in post if r['signal']=='voltage'])
    final_range_events = [r for r in rows if r.get('event') in ('power_off','power_on')]
    nonfinite = coverage['signals']['current']['samples']-coverage['signals']['current']['finite']
    load_observed = current.get('max_bin_mean',0)>.02
    core_observed = bool(observation.get('complete_core_observation') and observation.get('fresh_error_proof'))
    conclusion = ('Input supply was present and post-ON target-path load was observed. '
        'No program state, SD command, failure cause or saved image was read; any blink association needs separate current-pattern analysis.'
        if load_observed else
        'Input supply was present but there was essentially no measured load after ON. '
        'The observer skipped all debug reads. No powered normal cold boot, four-blink cause, image save, or probe-effect qualification was established.')
    if core_observed:
        conclusion='Post-ON load and a fresh retained normal-cycle failure were observed. The attached observer summary attributes the failing operation; current alone does not. No successful image save or independent Standby attribution.'
    return dict(schema=1,hardware_access=False,trace=str(trace),trace_sha256=hashlib.sha256(raw).hexdigest(),
        observer=str(observer),power_on=power,post_on_guard_s=.1,
        time_selection='Device UTC bin starts at least100ms after the host power_on timestamp; complete finite bins only',
        post_on_current_A=current,post_on_js_input_voltage_V=voltage,
        voltage_location='JS110 IN+ relative to IN-; this is NOT a target-board rail measurement',
        coverage=coverage,
        total_nonfinite_current_samples=nonfinite,
        whole_session_valid=coverage['passed'],logger_returncode=stopped['returncode'],
        cleanup_errors=stopped['cleanup_errors'],device_context_closed=stopped['device_context_closed'],
        driver_context_closed=stopped['driver_context_closed'],initial_settings=stopped['initial_settings'],
        restoration_events=[r for r in rows if r.get('event')=='cleanup_setting_restore'],
        last_logged_power_range=final_range_events[-1]['range'],
        expected_final_range=stopped['initial_settings']['s/i/range/select'],
        range_evidence='Last power command128; reviewed logger queries/restores initial128 during clean cleanup. No independent final DUT voltage measurement.',
        observer_debug_reads=observation['debug_reads'],observer_reason=observation.get('stopped_reason',observation.get('error')),
        post_on_load_observed=load_observed,
        powered_cold_boot_established=core_observed and load_observed,
        error_diagnosis_established=core_observed,
        observer_summary=observation.get('summary'),
        conclusion=conclusion,
        limits=[f'{nonfinite} startup current samples are nonfinite; whole-session validity remains false.',
                'Post-ON finite contiguous windows are described separately; no energy or clipping qualification.',
                'A software ON/range command does not establish power reached the target.',
                ('Fresh retained SRAM status was read; no target rail or saved image was read.' if core_observed else
                 'No target rail, program state, fault record or image was read in this attempt.')])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--trace',type=Path,required=True)
    p.add_argument('--observer',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();result=summarize(a.trace,a.observer)
    a.out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('post_on_current_A','post_on_js_input_voltage_V',
        'total_nonfinite_current_samples','whole_session_valid','observer_debug_reads','conclusion')},indent=2))


if __name__=='__main__':main()
