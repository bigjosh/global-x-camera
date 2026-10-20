"""Offline integration of js110_session --power-stream-log JSONL.

Never opens instruments or changes settings. A window JSON uses native sample
IDs, or ISO UTC strings plus an explicitly assumed clock-alignment uncertainty:

  {"start_sample_id": 2000000, "end_sample_id": 4000000,
   "boundary_uncertainty_samples": 0,
   "baseline": {"start_sample_id": 0, "end_sample_id": 1000000}}

  {"start_utc": "...+00:00", "end_utc": "...+00:00",
   "boundary_uncertainty_s": 0.05}

Native sample IDs are preferred when external markers establish the interval.
UTC uses the driver's estimated mapping; receipt timestamps are never used.
Optional target_duration_s is a consistency check, not electrical alignment.
Bounds cover chunk aggregation and the supplied boundary uncertainty only.
They do not include calibration, clipping, bypass current, or unknown clock
alignment error. Baseline subtraction assumes the baseline remains applicable.
"""
import argparse
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path


class EvidenceError(ValueError):
    pass


def finite(value, name):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise EvidenceError(f"Invalid finite {name}")
    return float(value)


def integer(value, name):
    if isinstance(value, bool) or not isinstance(value, int):
        raise EvidenceError(f"Invalid integer {name}")
    return value


def utc_seconds(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.utcoffset() is None:
            raise ValueError("timezone missing")
        return parsed.timestamp()
    except (TypeError, AttributeError, ValueError) as exc:
        raise EvidenceError("UTC must be an ISO timestamp with timezone") from exc


@dataclass(frozen=True)
class Chunk:
    start: int
    end: int
    rate: int
    decimation: int
    count: int
    minimum: float
    maximum: float
    total_j: float
    utc: float
    time_map: dict

    def part(self, start, end):
        """Tight extrema/sum bounds without inventing within-chunk ordering."""
        a, b = max(start, self.start), min(end, self.end)
        if b <= a:
            return 0., 0., 0.
        duration = (b - a) / self.rate
        total_duration = (self.end - self.start) / self.rate
        if a == self.start and b == self.end:
            return self.total_j, self.total_j, self.total_j
        outside = total_duration - duration
        low = max(self.minimum * duration, self.total_j - self.maximum * outside)
        high = min(self.maximum * duration, self.total_j - self.minimum * outside)
        estimate = self.total_j * duration / total_duration
        return low, high, min(high, max(low, estimate))


def load_chunks(records):
    starts = [r for r in records if r.get("event") == "stream_start"]
    stops = [r for r in records if r.get("event") == "stream_stop"]
    if len(starts) != 1 or starts[0].get("schema") != 2 or len(stops) > 1:
        raise EvidenceError("Expected one schema2 power-stream session")
    if stops and (stops[0].get("error") or stops[0].get("dropped_chunks", 0) or
                  stops[0].get("complete") is not True):
        raise EvidenceError("Recording reports an error or dropped chunks")
    chunks = []
    for record in records:
        if record.get("event") != "stream_chunk" or record.get("signal") != "power":
            continue
        if record.get("units") != "W":
            raise EvidenceError("Power units must be W")
        start = integer(record.get("sample_id"), "sample_id")
        end = integer(record.get("sample_id_end_exclusive"), "end sample_id")
        rate = integer(record.get("sample_rate_hz"), "sample rate")
        decimation = integer(record.get("decimate_factor"), "decimation")
        count = integer(record.get("count"), "sample count")
        if min(start, rate, decimation, count) < 0 or not rate or not decimation or not count:
            raise EvidenceError("Invalid sample extent")
        if end != start + count * decimation:
            raise EvidenceError("Inconsistent sample extent")
        if record.get("nonfinite_count") != 0 or record.get("finite_count") != count:
            raise EvidenceError("Power contains nonfinite or missing samples")
        low = finite(record.get("min"), "minimum power")
        high = finite(record.get("max"), "maximum power")
        total = finite(record.get("sum"), "power sample sum")
        mean = finite(record.get("mean"), "mean power")
        tolerance = 1e-6 * max(1., abs(mean), abs(low), abs(high))
        if low > high or mean < low-tolerance or mean > high+tolerance:
            raise EvidenceError("Inconsistent power extrema")
        if not math.isclose(total / count, mean, rel_tol=1e-6, abs_tol=1e-9):
            raise EvidenceError("Power sum disagrees with mean/count")
        expected_duration = count * decimation / rate
        if not math.isclose(finite(record.get("duration_s"), "duration"),
                            expected_duration, rel_tol=1e-9, abs_tol=1e-12):
            raise EvidenceError("Duration disagrees with sample extent")
        if chunks:
            previous = chunks[-1]
            if start != previous.end:
                raise EvidenceError("Power sample IDs contain a gap, overlap, or reset")
            if rate != previous.rate or decimation != previous.decimation:
                raise EvidenceError("Sample rate/decimation changed within recording")
            if record.get("gap_native_samples") != 0:
                raise EvidenceError("Logger reports discontinuous power samples")
        elif record.get("gap_native_samples") not in (None, 0):
            raise EvidenceError("First power chunk reports a preceding gap")
        utc = utc_seconds(record.get("sample_utc"))
        time_map = record.get("time_map", {})
        if not isinstance(time_map, dict):
            raise EvidenceError("Invalid time map")
        chunks.append(Chunk(start, end, rate, decimation, count, low, high,
                            total * decimation / rate, utc, time_map))
    if not chunks:
        raise EvidenceError("No power samples; old i/v means cannot establish energy")
    return chunks, bool(stops)


def integrate(chunks, start, end):
    if not (chunks[0].start <= start < end <= chunks[-1].end):
        raise EvidenceError("Requested interval is not completely covered")
    low = high = estimate = 0.
    for chunk in chunks:
        a, b, c = chunk.part(start, end)
        low += a
        high += b
        estimate += c
    return low, high, estimate


def uncertain_band(chunks, start, end):
    """Allow any amount of a boundary band, including negative power."""
    low = high = 0.
    for chunk in chunks:
        duration = max(0., min(end, chunk.end) - max(start, chunk.start)) / chunk.rate
        low += min(0., chunk.minimum) * duration
        high += max(0., chunk.maximum) * duration
    return low, high


def resolve_window(chunks, spec):
    rate = chunks[0].rate
    native = "start_sample_id" in spec or "end_sample_id" in spec
    utc = "start_utc" in spec or "end_utc" in spec
    if native == utc:
        raise EvidenceError("Select native sample IDs or UTC, never both")
    if native:
        if "boundary_uncertainty_s" in spec:
            raise EvidenceError("Native sample windows require uncertainty in samples")
        start = integer(spec.get("start_sample_id"), "window start")
        end = integer(spec.get("end_sample_id"), "window end")
        uncertainty = integer(spec.get("boundary_uncertainty_samples", 0), "boundary uncertainty")
        source = "caller-selected native sample interval"
    else:
        if "boundary_uncertainty_samples" in spec:
            raise EvidenceError("UTC windows require uncertainty in seconds")
        anchor = chunks[0]
        start = anchor.start + (utc_seconds(spec.get("start_utc")) - anchor.utc) * rate
        end = anchor.start + (utc_seconds(spec.get("end_utc")) - anchor.utc) * rate
        uncertainty = finite(spec.get("boundary_uncertainty_s"), "explicit UTC uncertainty") * rate
        source = "driver UTC estimate; supplied alignment uncertainty is an assumption"
    if uncertainty < 0 or start >= end or 2 * uncertainty >= end - start:
        raise EvidenceError("Invalid or overlapping boundary-uncertainty intervals")
    if start - uncertainty < chunks[0].start or end + uncertainty > chunks[-1].end:
        raise EvidenceError("Coverage does not include boundary uncertainty")
    return start, end, uncertainty, source


def measure(chunks, spec):
    start, end, uncertainty, source = resolve_window(chunks, spec)
    rate = chunks[0].rate
    low, high, estimate = integrate(chunks, start, end)
    if uncertainty:
        low, high, _ = integrate(chunks, start + uncertainty, end - uncertainty)
        for a, b in ((start-uncertainty, start+uncertainty),
                     (end-uncertainty, end+uncertainty)):
            extra_low, extra_high = uncertain_band(chunks, a, b)
            low += extra_low
            high += extra_high
    duration = (end - start) / rate
    target = spec.get("target_duration_s")
    if target is not None:
        target = finite(target, "target duration")
        if target <= 0 or abs(target-duration) > 2*uncertainty/rate + 1/rate:
            raise EvidenceError("Target duration is inconsistent with the selected interval")
    anchor = chunks[0]
    residuals = [c.utc - (anchor.utc+(c.start-anchor.start)/rate) for c in chunks
                 if c.end >= start-uncertainty and c.start <= end+uncertainty]
    drift = max(map(abs, residuals), default=0.)
    if "start_utc" in spec and drift > uncertainty/rate + 2/rate:
        raise EvidenceError("Driver UTC map variation exceeds supplied uncertainty")
    durations = [duration-2*uncertainty/rate, duration+2*uncertainty/rate]
    powers = [e/t for e in (low, high) for t in durations]
    return {
        "start_sample_id": start, "end_sample_id": end,
        "duration_s": duration,
        "duration_bounds_s": durations,
        "boundary_uncertainty_samples": uncertainty,
        "boundary_source": source,
        "energy_bounds_j": [low, high],
        "uniform_partial_chunk_estimate_j": estimate,
        "mean_power_bounds_w": [min(powers), max(powers)],
        "driver_utc_mapping_max_residual_s": drift,
        "target_duration_s": target,
    }


def analyze(records, window):
    chunks, finalized = load_chunks(records)
    result = measure(chunks, window)
    baseline = window.get("baseline")
    if baseline is not None:
        reference = measure(chunks, baseline)
        ru, bu = result["boundary_uncertainty_samples"], reference["boundary_uncertainty_samples"]
        if not (reference["end_sample_id"]+bu <= result["start_sample_id"]-ru or
                reference["start_sample_id"]-bu >= result["end_sample_id"]+ru):
            raise EvidenceError("Baseline overlaps operation")
        powers = reference["mean_power_bounds_w"]
        durations = result["duration_bounds_s"]
        offsets = [p*t for p in powers for t in durations]
        result["baseline"] = reference
        result["baseline_subtracted_conditional_bounds_j"] = [
            result["energy_bounds_j"][0]-max(offsets),
            result["energy_bounds_j"][1]-min(offsets)]
        result["baseline_assumption"] = "Measured baseline mean remains applicable throughout the operation"
    result.update(
        schema=1, status="delivered-sample integration qualified",
        recording_finalized=finalized,
        sample_rate_hz=chunks[0].rate, decimate_factor=chunks[0].decimation,
        coverage_sample_ids=[chunks[0].start, chunks[-1].end],
        first_time_map=chunks[0].time_map,
        voltage_boundary="JS110 IN+ relative to IN-; current through JS110",
        physical_alignment_verified=False,
        exclusions=[
            "No absolute calibration or analog clipping bound",
            "No proof that every DUT supply path passes through JS110",
            "UTC estimates and supplied uncertainty are not externally synchronized markers",
            "Raw sample order within a chunk was not retained",
            "Baseline subtraction is a conditional estimate, not total measured board energy",
        ])
    for key in ("mode", "frame_sha256", "run_id"):
        if key in window:
            result[key] = window[key]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stream-log", required=True, type=Path)
    parser.add_argument("--window", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    if args.out.resolve() in {args.stream_log.resolve(), args.window.resolve()}:
        parser.error("Output must differ from inputs")
    raw = args.stream_log.read_bytes()
    try:
        records = [json.loads(line) for line in raw.decode("utf-8-sig").splitlines() if line.strip()]
        result = analyze(records, json.loads(args.window.read_text(encoding="utf-8-sig")))
        code = 0
    except (EvidenceError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        result = {"schema": 1, "status": "unqualified", "error": str(exc)}
        code = 2
    result["stream_log_sha256"] = hashlib.sha256(raw).hexdigest()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps(result, allow_nan=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
