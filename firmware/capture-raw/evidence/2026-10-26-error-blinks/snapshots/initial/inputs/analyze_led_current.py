"""Offline current-step evidence for an injected LED blink test.

Uses retained 5 ms (or other configured width) bin minima because this bench
has periodic positive load excursions which overlap the LED step in bin means.
A three-bin median rejects isolated minima outliers. Two thresholds distinguish
the off floor, LED-on floor, and higher startup load. This is an inferred LED
association with an injected firmware test, not a direct optical/GPIO trace.
Timing intervals include conservative +/- two-bin edge uncertainty; they are
not precision timing or energy claims. Raw observations and exclusions remain.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import numpy as np


def utc(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat()


def ranges(values):
    return None if not values else dict(count=len(values), minimum=min(values),
        median=float(np.median(values)), maximum=max(values))


def analyze(path, launch_utc, code):
    data = path.read_bytes()
    records = [json.loads(line) for line in data.decode("utf-8").splitlines()]
    start = next(r for r in records if r["event"]=="start")
    stops = [r for r in records if r["event"]=="stopped"]
    if not stops:
        raise ValueError("Recording has not completed; refusing partial-file analysis")
    stop = stops[-1]
    rows = [r for r in records if r["event"]=="bin" and r["signal"]=="current"]
    if not rows:
        raise ValueError("No current bins")
    hz = rows[0]["sample_rate_hz"]
    t = np.array([r["sample_id"]/hz for r in rows])
    end = rows[-1]["sample_id_end_exclusive"]/hz
    epoch = float(1514764800+rows[0]["utc_time64"]/(1<<30)-t[0])
    launch = datetime.fromisoformat(launch_utc.replace("Z", "+00:00"))
    if launch.tzinfo is None:
        raise ValueError("Launch time requires an explicit timezone")
    launch_t = launch.timestamp()-epoch
    width = start["bin_ms"]/1000
    raw = np.array([r["min"] if r["min"] is not None else np.nan for r in rows])
    filtered = np.median(np.lib.stride_tricks.sliding_window_view(
        np.pad(raw, (1,1), mode="edge"), 3), axis=1)
    calibration = (t>=launch_t+.3) & (t<launch_t+5)
    calibration_values = filtered[calibration & np.isfinite(filtered)]
    if len(calibration_values)<100:
        raise ValueError("Insufficient post-launch calibration coverage")
    off, on = np.quantile(calibration_values, [.2,.95])
    separation = float(on-off)
    if separation<.0005:
        raise ValueError("Current clusters are not separated by at least0.5mA")
    lower = float((off+on)/2)
    upper = float(on+.25*(on-off))
    high = (filtered>=lower) & (filtered<=upper) & (t>=launch_t)
    changes = np.flatnonzero(np.diff(np.r_[False,high,False].astype(int)))
    pulses, excluded = [], []
    edge_uncertainty = 2*width
    for a,b in zip(changes[::2], changes[1::2]):
        began, ended = float(t[a]), float(t[b] if b<len(t) else end)
        item = dict(start_sample_id=rows[a]["sample_id"],
            end_sample_id_exclusive=rows[b]["sample_id"] if b<len(t) else rows[-1]["sample_id_end_exclusive"],
            start_s=began, end_s=ended, start_utc_estimate=utc(epoch+began),
            end_utc_estimate=utc(epoch+ended), duration_s=ended-began,
            start_bounds_s=[began-edge_uncertainty,began+edge_uncertainty],
            end_bounds_s=[ended-edge_uncertainty,ended+edge_uncertainty],
            duration_bounds_s=[max(0,ended-began-2*edge_uncertainty),ended-began+2*edge_uncertainty],
            left_censored=bool(began<=launch_t+width),
            right_censored=bool(b==len(t)))
        if ended-began<.05:
            item["reason"]="shorter than50ms; not counted as a nominal100ms blink"
            excluded.append(item)
        else:
            pulses.append(item)
    groups = []
    for pulse in pulses:
        if not groups or pulse["start_s"]-groups[-1]["pulses"][-1]["end_s"]>1:
            groups.append(dict(index=len(groups)+1,pulses=[]))
        pulse["index"]=len(groups[-1]["pulses"])+1
        groups[-1]["pulses"].append(pulse)
    inner, between, periods = [], [], []
    for group in groups:
        group["count"] = len(group["pulses"])
        group["expected_count"] = code
        for left,right in zip(group["pulses"],group["pulses"][1:]):
            inner.append(right["start_s"]-left["end_s"])
            periods.append(right["start_s"]-left["start_s"])
    for left,right in zip(groups,groups[1:]):
        between.append(right["pulses"][0]["start_s"]-left["pulses"][-1]["end_s"])
    window = [r for r in rows if r["sample_id_end_exclusive"]/hz>=launch_t]
    scoped_nonfinite = sum(r["nonfinite_count"] for r in window)
    voltage = [r for r in records if r["event"]=="bin" and r["signal"]=="voltage"
               and r["sample_id_end_exclusive"]/hz>=launch_t]
    voltage_nonfinite = sum(r["nonfinite_count"] for r in voltage)
    last_pulse_end = pulses[-1]["end_s"] if pulses else end
    low = [r for r in rows if r["sample_id"]/hz>last_pulse_end and
           r["mean"] is not None and r["mean"]<float(off)*.5]
    low_plateau = None
    if low and low[-1]["sample_id_end_exclusive"]/hz-low[0]["sample_id"]/hz>.2:
        low_plateau = dict(start_s=low[0]["sample_id"]/hz,
            start_utc_estimate=utc(epoch+low[0]["sample_id"]/hz),
            duration_s=low[-1]["sample_id_end_exclusive"]/hz-low[0]["sample_id"]/hz,
            median_current_A=float(np.median([r["mean"] for r in low])),
            scope="observed current plateau only; not independent Standby attribution")
    checks = dict(no_queue_drop=stop["coverage"]["dropped_chunks"]==0,
        no_logger_error=stop["coverage"]["logger_error"] is None,
        continuous_current_ids=stop["coverage"]["signals"]["current"]["discontinuities"]==0,
        continuous_voltage_ids=stop["coverage"]["signals"]["voltage"]["discontinuities"]==0,
        fault_window_current_finite=scoped_nonfinite==0,
        fault_window_voltage_finite=voltage_nonfinite==0,
        five_groups=len(groups)==5,
        expected_blinks_per_group=bool(groups) and all(g["count"]==code for g in groups),
        expected_total_blinks=len(pulses)==5*code,
        no_censored_counted_pulses=bool(pulses) and not any(p["left_censored"] or p["right_censored"] for p in pulses),
        low_current_after_final_group=low_plateau is not None,
        cleanup_success=not stop["cleanup_errors"] and stop["device_context_closed"])
    def consistent(values,target):
        return bool(values) and all(abs(v-target)<=2*edge_uncertainty+1e-9 for v in values)
    timing = dict(on_100ms_consistent=consistent([p["duration_s"] for p in pulses],.1),
        between_blinks_400ms_consistent=consistent(inner,.4),
        between_sets_2000ms_consistent=consistent(between,2.0))
    return dict(schema=1, source=str(path), source_sha256=hashlib.sha256(data).hexdigest(),
        source_bytes=len(data), launch_host_utc=launch.isoformat(), launch_estimated_sample_s=launch_t,
        trace_first_utc_estimate=utc(epoch+t[0]), trace_end_utc_estimate=utc(epoch+end),
        fault_window_duration_s=end-launch_t, native_sample_rate_hz=hz, bin_width_s=width,
        method=dict(signal="current", statistic="bin minimum", median_filter_bins=3,
            calibration_s=[launch_t+.3,launch_t+5], lower_floor_A=float(off), upper_floor_A=float(on),
            cluster_separation_A=separation, led_on_thresholds_A=[lower,upper],
            edge_uncertainty_s=edge_uncertainty, interval_uncertainty_s=2*edge_uncertainty,
            reason="Positive periodic board-current spikes bias mean thresholds; minima separate the observed floor states. Higher startup current is a third state."),
        checks=checks, complete_pattern_observed=all(checks.values()), timing_consistency=timing,
        measured=dict(pulses=len(pulses), groups=[g["count"] for g in groups],
            on_s=ranges([p["duration_s"] for p in pulses]), interblink_off_s=ranges(inner),
            interset_off_s=ranges(between), rising_period_s=ranges(periods)),
        groups=groups, excluded_short_intervals=excluded, low_current_plateau=low_plateau,
        session_whole_coverage=stop["coverage"], fault_window_nonfinite_current=scoped_nonfinite,
        fault_window_nonfinite_voltage=voltage_nonfinite, whole_session_ok=stop["ok"],
        limits=["LED cause inferred from deliberately injected firmware and characteristic current changes; no optical/GPIO probe.",
                "Driver UTC and host launch are approximate; pulse spacings use native sample ids.",
                "Timing intervals include conservative bin/filter uncertainty, not precision calibration.",
                "Whole-session startup NaNs are retained; scoped finite fault-window evidence is separate.",
                "No energy, analog margin, general fault coverage, or independent Standby claim."])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("input",type=Path)
    p.add_argument("--launch-utc",required=True)
    p.add_argument("--code",type=int,choices=range(1,9),required=True)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    result=analyze(args.input,args.launch_utc,args.code)
    args.output.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:result[k] for k in ("complete_pattern_observed","checks","timing_consistency","measured","low_current_plateau")},indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
