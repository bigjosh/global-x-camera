"""Offline power-on/current signature; no firmware, energy or Standby inference."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics

EPOCH=datetime(2018,1,1,tzinfo=timezone.utc).timestamp()


def analyze(path):
    raw=path.read_bytes();rows=[json.loads(line) for line in raw.decode().splitlines()]
    power=next(r for r in rows if r.get('event')=='power_on')
    stopped=next(r for r in reversed(rows) if r.get('event')=='stopped')
    origin=datetime.fromisoformat(power['utc']).timestamp()
    bins=[r for r in rows if r.get('event')=='bin' and r.get('signal')=='current' and
          r['complete_bin'] and not r['nonfinite_count'] and EPOCH+r['utc_time64']/2**30>=origin]
    assert bins
    threshold=.020
    last_high=max(i for i,r in enumerate(bins) if r['mean']>=threshold)
    tail=bins[last_high+1:];assert tail
    t=lambda r:EPOCH+r['utc_time64']/2**30-origin
    stable_start=t(tail[0]);last_high_end=t(bins[last_high])+bins[last_high]['duration_s']
    stable_end=t(tail[-1])+tail[-1]['duration_s']
    late=[r for r in tail if t(r)>=stable_end-2.0]
    mean=lambda seq:sum(r['mean']*r['finite_count'] for r in seq)/sum(r['finite_count'] for r in seq)
    return dict(schema=1,hardware_access=False,trace=str(path),trace_sha256=hashlib.sha256(raw).hexdigest(),
        power_on=power,threshold_A=threshold,bin_width_s=.005,
        sustained_below_threshold_start_s=stable_start,
        last_above_threshold_bin_start_s=t(bins[last_high]),
        last_above_threshold_bin_end_s=last_high_end,
        transition_scope='Boundary between retained5ms mean-current bins; host/device time alignment and transition within a bin limit precision',
        low_tail_duration_s=stable_end-stable_start,
        low_tail_mean_A=mean(tail),low_tail_median_bin_A=statistics.median(r['mean'] for r in tail),
        low_tail_min_bin_mean_A=min(r['mean'] for r in tail),low_tail_max_bin_mean_A=max(r['mean'] for r in tail),
        low_tail_min_sample_A=min(r['min'] for r in tail),low_tail_max_sample_A=max(r['max'] for r in tail),
        final_two_seconds_mean_A=mean(late),
        transient_max_bin_mean_A=max(r['mean'] for r in bins[:last_high+1]),
        transient_max_retained_sample_A=max(r['max'] for r in bins[:last_high+1]),
        finite_complete_bins_contiguous=all(a['sample_id_end_exclusive']==b['sample_id'] for a,b in zip(bins,bins[1:])),
        whole_session_valid=stopped['coverage']['passed'],
        startup_current_nan_count=stopped['coverage']['signals']['current']['samples']-stopped['coverage']['signals']['current']['finite'],
        interpretation='A transient followed by a sustained low-current signature; no saved-image, correct shutdown or independent Standby proof.',
        error_pattern_claim=False,energy_claim=False)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--trace',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();result=analyze(a.trace);a.out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
