"""Offline-only reproduction of the opt-debug auto/fixed JS110 comparison.

Run from the repository root. Reads saved CSV/JSONL only; uses no instrument API.
"""
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
SOURCE = BASE / "opt-current-voltage.jsonl"
CYCLES = [BASE / "opt-debug-auto-01", BASE / "opt-debug-fixed-01"]


def load_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def analog_timing(folder):
    digital = []
    with (folder / "digital.csv").open(newline="") as f:
        for row in csv.DictReader(f):
            digital.append({k: float(v) for k, v in row.items()})
    edges = {}
    for name, channel in [("nrst", 0), ("pd0", 1), ("pe0", 2)]:
        rises = [b["Time [s]"] for a, b in zip(digital, digital[1:])
                 if a[f"Channel {channel}"] == 0 and b[f"Channel {channel}"] == 1]
        assert len(rises) == 1, (folder, name, rises)
        edges[name] = rises[0]
    rows = []
    with (folder / "analog.csv").open(newline="") as f:
        for row in csv.DictReader(f):
            t = float(row["Time [s]"])
            if edges["pd0"] - .15 <= t <= edges["pd0"] + .1:
                rows.append({k: float(v) for k, v in row.items()})
    crossings = {}
    for channel, thresholds in [(3, [.33, 2.97]), (4, [.5, 4.5]), (5, [.33, 2.97])]:
        crossings[str(channel)] = {}
        for threshold in thresholds:
            up = [b["Time [s]"] for a, b in zip(rows, rows[1:])
                  if a[f"Channel {channel}"] < threshold <= b[f"Channel {channel}"]]
            crossings[str(channel)][str(threshold)] = up
    near = {}
    for edge in ["nrst", "pd0"]:
        before = max((r for r in rows if r["Time [s]"] <= edges[edge]), key=lambda r: r["Time [s]"])
        after = min((r for r in rows if r["Time [s]"] >= edges[edge]), key=lambda r: r["Time [s]"])
        near[edge] = {
            "edge_s": edges[edge],
            "sample_before_s": before["Time [s]"], "sample_after_s": after["Time [s]"],
            "main_vddio_ch5_before_v": before["Channel 5"], "main_vddio_ch5_after_v": after["Channel 5"],
            "aux_3v3_ch3_before_v": before["Channel 3"], "aux_3v3_ch3_after_v": after["Channel 3"],
            "target_5v_ch4_before_v": before["Channel 4"], "target_5v_ch4_after_v": after["Channel 4"],
        }
    def cross(channel, threshold):
        return max(t for t in crossings[str(channel)][str(threshold)] if t <= edges["pd0"])
    return {
        "source": "Direct recalculation from saved analog.csv and digital.csv",
        "analog_spacing_us": 32, "digital_spacing_us": .16,
        "edges_s": edges, "up_crossings_s": crossings,
        "target_5v_0_5_to_4_5_ms": (cross(4, 4.5)-cross(4, .5))*1000,
        "target_5v_0_5_to_pd0_ms": (edges["pd0"]-cross(4, .5))*1000,
        "target_5v_4_5_to_pd0_ms": (edges["pd0"]-cross(4, 4.5))*1000,
        "main_vddio_0_33_to_2_97_ms": (cross(5, 2.97)-cross(5, .33))*1000,
        "main_vddio_2_97_to_nrst_ms": (edges["nrst"]-cross(5, 2.97))*1000,
        "main_vddio_2_97_to_pd0_ms": (edges["pd0"]-cross(5, 2.97))*1000,
        "nrst_to_pd0_ms": (edges["pd0"]-edges["nrst"])*1000,
        "pd0_to_pe0_us": (edges["pe0"]-edges["pd0"])*1e6,
        "levels_bracketing_digital_edges": near,
    }


all_records = load_jsonl(SOURCE)
rows = [r for r in all_records if r["event"] == "stream_chunk"]
for row in rows:
    row["_t"] = datetime.fromisoformat(row["sample_utc"]).timestamp()
stop = next(r for r in reversed(all_records) if r["event"] == "stream_stop")
summaries = []
for folder in CYCLES:
    cycle = load_jsonl(folder / "cycle-log.jsonl")
    on = next(r for r in cycle if r.get("state") in ("auto", "2A"))
    t = datetime.fromisoformat(on["command_start"]["utc"]).timestamp()
    selected = [r for r in rows if r["_t"] <= t+.5 and r["_t"]+r["duration_s"] >= t-.2]

    def extreme(signal, field):
        candidates = [r for r in selected if r["signal"] == signal and r[field] is not None]
        row = (max if field == "max" else min)(candidates, key=lambda r:r[field])
        sid = row[field+"_sample_id"]
        at = row["_t"]+(sid-row["sample_id"])/row["sample_rate_hz"]
        return {"value":row[field], "units":row["units"], "sample_id":sid,
                "estimated_utc":datetime.fromtimestamp(at,timezone.utc).isoformat(),
                "ms_after_command_start":(at-t)*1000,
                "containing_chunk":{k:v for k,v in row.items() if not k.startswith("_")}}

    def window(signal, start, end):
        a = [r for r in rows if r["signal"] == signal and r["_t"] >= t+start
             and r["_t"]+r["duration_s"] <= t+end]
        finite = sum(r["finite_count"] for r in a)
        return {"relative_window_s":[start,end], "whole_chunks":len(a),
                "finite_samples":finite,
                "weighted_mean":sum(r["mean"]*r["finite_count"] for r in a
                                    if r["mean"] is not None)/finite if finite else None,
                "min":min((r["min"] for r in a if r["min"] is not None), default=None),
                "max":max((r["max"] for r in a if r["max"] is not None), default=None)}

    summary = {
        "cycle":folder.name, "on_state":on["state"],
        "reproduce":"python tmp/bringup/analyze_opt_stream_cycles.py",
        "input_sha256":{str(p.relative_to(BASE)):sha(p) for p in
                         [SOURCE, folder/"cycle-log.jsonl", folder/"analog.csv", folder/"digital.csv"]},
        "on_command":on, "analysis_window_s_relative_to_on_command":[-.2,.5],
        "saleae_timing":analog_timing(folder),
        "current_peak":extreme("current","max"),
        "upstream_voltage_minimum":extreme("voltage","min"),
        "baseline_upstream_voltage":window("voltage",-2,-.1),
        "settled_upstream_voltage":window("voltage",.1,1.5),
        "settled_current":window("current",.1,1.5),
        "capture_integrity":{
            "effective_sample_rates_hz":sorted(set(r["effective_sample_rate_hz"] for r in selected)),
            "decimate_factors":sorted(set(r["decimate_factor"] for r in selected)),
            "chunk_duration_s":sorted(set(r["duration_s"] for r in selected)),
            "nonfinite_samples_by_signal":{s:sum(r["nonfinite_count"] for r in selected if r["signal"]==s)
                                            for s in ["current","voltage"]},
            "sample_gap_records_in_window":sum(bool(r["gap_native_samples"]) for r in selected),
            "sample_gap_records_in_session":sum(bool(r["gap_native_samples"]) for r in rows),
            "abs_ge_2A_samples_in_window":sum(r.get("abs_ge_2A_count",0) for r in selected),
            "session_stop":stop},
        "limitations":[
            "One cycle per range; small differences are not statistical evidence of a speed improvement.",
            "Analog crossings are sampled at 32 us without interpolation; two-edge intervals have sampling and voltage-threshold uncertainty.",
            "CH5 is main VDDIO; CH3 is auxiliary 3.3 V. Neither identifies internal POR release, AON/core readiness or ROM entry.",
            "32.697 ms chunk summaries retain extrema and their sample positions, not complete waveforms.",
            "Current and voltage chunks have different boundaries; their native sample IDs share the instrument clock.",
            "Fixed 2 A is a measurement range, not current limiting; its startup peak is consistent with clipping and cannot establish actual inrush.",
            "Auto range is not an analog-peak guarantee; per-sample range codes and saturation flags were not recorded.",
            "Negative voltage minima may include ringing or measurement transients; do not assert a physical negative rail without corroboration.",
            "Low voltage chunk means support a substantial source-path disturbance, but the exact cause is not isolated.",
            "Driver-estimated UTC and host-command timestamps do not replace external rail/marker timing.",
        ]}
    (folder/"js110-summary.json").write_text(json.dumps(summary,indent=2,allow_nan=False)+"\n")
    summaries.append(summary)

comparison = {"cycles":[]}
for s in summaries:
    timing = s["saleae_timing"]
    compact = {"cycle":s["cycle"], "range":s["on_state"],
               **{k:v for k,v in timing.items() if k.endswith("_ms") or k.endswith("_us")},
               "reported_current_peak_A":s["current_peak"]["value"],
               "reported_upstream_min_V":s["upstream_voltage_minimum"]["value"],
               "settled_current_A":s["settled_current"]["weighted_mean"],
               "source_before_V":s["baseline_upstream_voltage"]["weighted_mean"],
               "source_after_V":s["settled_upstream_voltage"]["weighted_mean"],
               "levels_bracketing_digital_edges":timing["levels_bracketing_digital_edges"]}
    comparison["cycles"].append(compact)
comparison["conclusion"] = "Fixed 2 A did not materially shorten the observed target ramp or first-GPIO timing; source disturbance persisted. Current peaks are not directly comparable because fixed 2 A may clip; its recorded peak is consistent with clipping."
for folder in CYCLES:
    (folder/"range-comparison.json").write_text(json.dumps(comparison,indent=2,allow_nan=False)+"\n")
print(json.dumps(comparison,indent=2,allow_nan=False))
