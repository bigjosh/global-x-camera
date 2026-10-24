"""Integrate complete-cycle JS110 raw recordings on their native sample clock.

Offline only. Explicit cycle windows can share one recording. Each starts in
an observed off-current baseline and ends in a sustained plateau. Independent
terminal qualification is required by default; an explicit opt-in permits
signature-only results with completion claims marked false. No host
UTC/command-to-sample alignment is used.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import zlib

import numpy as np


def sha_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for data in iter(lambda: source.read(4 * 1024**2), b""):
            digest.update(data)
    return digest.hexdigest()


class Archive:
    """Validate identity, coverage and layout before exposing memory maps."""
    def __init__(self, directory):
        self.directory = Path(directory)
        self.manifest = json.loads((self.directory / "manifest.json").read_text())
        m = self.manifest
        if (m.get("schema") != 1 or m.get("dtype") != "<f4" or not m.get("finalized")
                or not m["status"]["complete"] or not m["status"]["coverage"]["passed"]):
            raise ValueError("Raw recording is not finalized with complete coverage")
        path = self.directory / "chunks.jsonl"
        if sha_file(path) != m["chunks_sha256"]:
            raise ValueError("Chunk index hash mismatch")
        records = [json.loads(line) for line in path.read_text().splitlines()]
        starts = [r for r in records if r.get("event") == "stream_start"]
        stops = [r for r in records if r.get("event") == "stream_stop"]
        if len(starts) != 1 or len(stops) != 1 or starts[0].get("raw_schema") != 1:
            raise ValueError("Missing/ambiguous raw stream boundaries")
        if (not stops[0]["complete"] or stops[0].get("dropped_chunks") != 0
                or not stops[0]["coverage"]["passed"]):
            raise ValueError("Incomplete stream stop")
        self.signals = {}
        try:
            for name in ("current", "voltage", "power"):
                info = m["files"][name]
                if info["path"] != name + ".f32":
                    raise ValueError("Unexpected raw signal path")
                path = self.directory / info["path"]
                if path.stat().st_size != info["bytes"] or sha_file(path) != info["sha256"]:
                    raise ValueError("Raw signal length/hash mismatch: " + name)
                chunks = [r for r in records
                          if r.get("event") == "stream_chunk" and r.get("signal") == name]
                if not chunks:
                    raise ValueError("Empty raw signal")
                offset, next_id = 0, chunks[0]["sample_id"]
                rate, decimation = chunks[0]["sample_rate_hz"], chunks[0]["decimate_factor"]
                if (type(rate) is not int or type(decimation) is not int
                        or rate <= 0 or decimation <= 0):
                    raise ValueError("Invalid sample geometry")
                with path.open("rb") as source:
                    for r in chunks:
                        if (r["sample_id"] != next_id or r["raw_byte_offset"] != offset
                                or r["sample_rate_hz"] != rate or r["decimate_factor"] != decimation
                                or r["raw_file"] != info["path"]
                                or r["count"] <= 0 or r["raw_byte_count"] != r["count"] * 4
                                or r["sample_id_end_exclusive"] != next_id + r["count"] * decimation):
                            raise ValueError("Discontinuous/inconsistent raw signal")
                        payload = source.read(r["raw_byte_count"])
                        if f"{zlib.crc32(payload):08x}" != r["raw_crc32"]:
                            raise ValueError("Raw chunk CRC mismatch")
                        offset += len(payload)
                        next_id = r["sample_id_end_exclusive"]
                if offset != info["bytes"]:
                    raise ValueError("Unindexed waveform tail")
                self.signals[name] = dict(data=np.memmap(path, dtype="<f4", mode="r"),
                                          start=chunks[0]["sample_id"], end=next_id,
                                          rate=rate, decimation=decimation)
            geometry = {(s["rate"], s["decimation"], s["start"] % s["decimation"])
                        for s in self.signals.values()}
            if len(geometry) != 1:
                raise ValueError("Signals do not share an aligned sample clock")
            self.rate, self.decimation, _ = geometry.pop()
            self.start = max(s["start"] for s in self.signals.values())
            self.end = min(s["end"] for s in self.signals.values())
            if self.start >= self.end:
                raise ValueError("No common waveform coverage")
        except BaseException:
            self.close()
            raise

    def close(self):
        for signal in self.signals.values():
            signal["data"]._mmap.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def get(self, signal, start, end):
        s = self.signals[signal]
        d = s["decimation"]
        if (type(start) is not int or type(end) is not int or start >= end
                or start < s["start"] or end > s["end"]
                or (start - s["start"]) % d or (end - s["start"]) % d):
            raise ValueError("Window lacks aligned, complete waveform coverage")
        return s["data"][(start-s["start"])//d:(end-s["start"])//d]


def analyze_cycle(archive, window, criteria, *, allow_unqualified_plateau=False):
    """Require explicit thresholds; unqualified levels need a separate opt-in."""
    if type(allow_unqualified_plateau) is not bool:
        raise ValueError("Unqualified plateau opt-in must be an explicit Boolean")
    start, end = window["start_sample_id"], window["end_sample_id"]
    current = archive.get("current", start, end)
    voltage = archive.get("voltage", start, end)
    power = archive.get("power", start, end)
    for name, data in (("current", current), ("voltage", voltage), ("power", power)):
        if not np.isfinite(data).all():
            raise ValueError("Nonfinite " + name + " samples in cycle window")
    required = ("bin_s", "off_baseline_s", "off_abs_max_a", "onset_a",
                "pretrigger_s", "plateau_min_s", "plateau_mean_min_a",
                "plateau_mean_max_a", "plateau_peak_abs_max_a",
                "plateau_mean_span_a", "current_valid_abs_max_a")
    for key in required:
        if key not in criteria or type(criteria[key]) not in (int, float) or not math.isfinite(criteria[key]):
            raise ValueError("Missing/invalid criterion: " + key)
    c = criteria
    if (any(c[k] <= 0 for k in required if k != "plateau_mean_min_a")
            or c["plateau_mean_min_a"] < 0
            or c["plateau_mean_min_a"] >= c["plateau_mean_max_a"]
            or c["onset_a"] <= c["off_abs_max_a"]
            or c["plateau_mean_max_a"] >= c["onset_a"]
            or c["plateau_peak_abs_max_a"] > c["current_valid_abs_max_a"]):
        raise ValueError("Inconsistent current/plateau criteria")
    if float(np.abs(current).max()) >= c["current_valid_abs_max_a"]:
        raise ValueError("Current reaches the caller's measurement-validity limit")
    fs = archive.rate / archive.decimation
    count = len(current)
    baseline_n = math.ceil(c["off_baseline_s"] * fs)
    pretrigger_n = math.ceil(c["pretrigger_s"] * fs)
    bin_n = max(1, math.ceil(c["bin_s"] * fs))
    plateau_n = max(bin_n, math.ceil(c["plateau_min_s"] * fs))
    if baseline_n + plateau_n >= count:
        raise ValueError("Cycle too short for baseline and plateau")
    if float(np.abs(current[:baseline_n]).max()) > c["off_abs_max_a"]:
        raise ValueError("Window does not begin in an observed off-current baseline")
    candidates = np.flatnonzero(current[baseline_n:] >= c["onset_a"])
    if not len(candidates):
        raise ValueError("No positive current onset")
    onset = baseline_n + int(candidates[0])
    if onset < pretrigger_n or onset - pretrigger_n < baseline_n:
        raise ValueError("Insufficient pretrigger after the verified baseline")
    # Reject any earlier excursion above the off criterion rather than silently
    # calling a slow precharge or an earlier cycle part of the off baseline.
    earlier = np.flatnonzero(np.abs(current[baseline_n:onset]) > c["off_abs_max_a"])
    first_activity = baseline_n + int(earlier[0]) if len(earlier) else onset
    integration_start = onset - pretrigger_n
    if first_activity < integration_start:
        raise ValueError("Activity precedes the requested pretrigger; enlarge it")
    # Work backwards from the explicit window end. This rules out a transient
    # quiet gap followed by renewed work as the terminal plateau.
    plateau_start = count
    means, peaks = [], []
    mean_low, mean_high = math.inf, -math.inf
    while plateau_start - bin_n >= onset:
        a = plateau_start - bin_n
        block = current[a:plateau_start]
        mean = float(block.mean(dtype=np.float64))
        peak = float(np.abs(block).max())
        if (not c["plateau_mean_min_a"] <= mean <= c["plateau_mean_max_a"]
                or peak > c["plateau_peak_abs_max_a"]):
            break
        next_low, next_high = min(mean_low, mean), max(mean_high, mean)
        if next_high - next_low > c["plateau_mean_span_a"]:
            break
        mean_low, mean_high = next_low, next_high
        means.append(mean)
        peaks.append(peak)
        plateau_start = a
    if count - plateau_start < plateau_n:
        raise ValueError("No sustained terminal plateau within the configured limits")
    if plateau_start <= onset:
        raise ValueError("No distinguishable activity before the terminal plateau")
    # Do not infer sleep/shutdown from low current alone.
    evidence = Path(window["terminal_evidence"])
    qualified = window.get("terminal_state_qualified")
    if not evidence.is_file() or (qualified is not True and not (
            allow_unqualified_plateau and qualified is False)):
        raise ValueError("Fresh external terminal-state qualification is required")
    evidence_hash = sha_file(evidence)
    settle_end = plateau_start + plateau_n
    dt = 1 / fs

    def energy(a, b):
        return float(power[a:b].sum(dtype=np.float64)) * dt

    def sid(i):
        return start + int(i) * archive.decimation

    baseline_power = float(power[:baseline_n].mean(dtype=np.float64))
    return {
        "name": window.get("name"),
        "terminal_evidence": str(evidence), "terminal_evidence_sha256": evidence_hash,
        "terminal_state_qualified": qualified,
        **({} if qualified else dict(completion_boundary_qualified=False,
                                     onset_to_plateau_energy_is_complete_cycle=False)),
        "terminal_state_qualification": (
            "caller attestation; analyzer does not interpret firmware proof" if qualified else
            "Unqualified current plateau only; evidence records context, not firmware completion, SBF or file verification."),
        "window": {"start_sample_id": start, "end_sample_id": end},
        "boundaries": {"current_onset_sample_id": sid(onset),
                       "first_activity_above_off_threshold_sample_id": sid(first_activity),
                       "integration_start_sample_id": sid(integration_start),
                       "terminal_plateau_start_sample_id": sid(plateau_start),
                       "integration_end_sample_id": sid(settle_end),
                       "sample_interval_s": dt, "plateau_boundary_bin_s": bin_n * dt},
        "onset_to_plateau_s": (plateau_start - onset) * dt,
        "integration_duration_s": (settle_end - integration_start) * dt,
        "pretrigger_energy_j": energy(integration_start, onset),
        "onset_to_plateau_energy_j": energy(onset, plateau_start),
        "plateau_confirmation_energy_j": energy(plateau_start, settle_end),
        "pretrigger_through_confirmed_plateau_energy_j": energy(integration_start, settle_end),
        "whole_window_energy_j": energy(0, count),
        "baseline_power_w": baseline_power,
        "conditional_baseline_subtracted_energy_j": energy(integration_start, settle_end)
            - baseline_power * (settle_end - integration_start) * dt,
        "peak_current_a": float(current.max()), "minimum_source_voltage_v": float(voltage.min()),
        "plateau": {"observed_s": (count-plateau_start)*dt, "mean_current_a": float(
            current[plateau_start:].mean(dtype=np.float64)),
                    "mean_power_w": float(power[plateau_start:].mean(dtype=np.float64)),
                    "bin_mean_span_a": max(means)-min(means),
                    "peak_abs_current_a": max(peaks)},
        "criteria": dict(criteria),
        "limits": [
            "Boundaries are measured-current thresholds, not physical target-rail edges.",
            "Pretrigger includes measured startup charge only if activity begins inside its window.",
            "Subthreshold charge before pretrigger is not proven absent; whole-window energy is also reported.",
            "Plateau classification and firmware completion require the external qualification.",
            *([] if qualified else [
                "Explicit unqualified-plateau mode: energy/time describe the observed signature only; do not label them a verified complete capture/save cycle or Standby entry."]),
            "Baseline subtraction assumes stationary background; raw energy is the primary result.",
            "No analog calibration, saturation detection, suppression interpolation, or CN8 bypass correction is inferred.",
        ],
    }


def analyze(directory, spec, *, allow_unqualified_plateau=False):
    with Archive(directory) as archive:
        cycles = [analyze_cycle(archive, window, spec["criteria"],
                               allow_unqualified_plateau=allow_unqualified_plateau)
                  for window in spec["cycles"]]
        spans = sorted((v["window"]["start_sample_id"], v["window"]["end_sample_id"]) for v in cycles)
        if any(a[1] > b[0] for a, b in zip(spans, spans[1:])):
            raise ValueError("Repeated cycle windows overlap")
        return {"schema": 1, "recording": str(directory),
                "manifest_sha256": sha_file(Path(directory) / "manifest.json"),
                "sample_rate_hz": archive.rate, "decimate_factor": archive.decimation,
                "starting_measurement_settings": archive.manifest.get("starting_measurement_settings"),
                "range_commands": archive.manifest.get("range_commands"),
                "uses_host_utc_alignment": False,
                "unqualified_plateau_mode_enabled": allow_unqualified_plateau,
                "cycles": cycles}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recording", type=Path, required=True)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--allow-unqualified-plateau", action="store_true",
                        help="Opt in to signature-only results for explicitly unqualified windows; never establishes completion or Standby")
    args = parser.parse_args()
    spec = json.loads(args.spec.read_text())
    for window in spec["cycles"]:
        path = Path(window["terminal_evidence"])
        if not path.is_absolute():
            window["terminal_evidence"] = str(args.spec.parent / path)
    result = analyze(args.recording, spec,
                     allow_unqualified_plateau=args.allow_unqualified_plateau)
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
