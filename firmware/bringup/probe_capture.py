r"""Capture and verify the temporary PD0/PE0 wiring-test pattern with Logic 2.

Install Saleae's client without changing the system Python environment:
  python -m pip install --target tmp/bringup/saleae-deps logic2-automation==1.0.11
Start the already installed Logic app with its documented --automation flag.
Running this script without --capture only lists connected physical devices.

Example (run from the repository root; output directory must be new):
  python firmware/bringup/probe_capture.py --capture --duration 15 \
    --analog 0,1,2,3,4 --output tmp/bringup/probes-01 \
    --stimulus-command /absolute/path/to/gdb.exe -batch -x /path/to/test.gdb

--stimulus-command must be last; every following argument belongs to that
process. It is executed directly, without a shell, after capture starts.
Existing exports can be checked without a device using --analyze DIRECTORY.

Channels: 0=NRST, 1=PD0, 2=PE0, optional 3=3.3 V, optional 4=5 V.
Reset and GPIO activity do not establish that a power-on event occurred.
API: https://docs.saleae.com/automation/api/automation/Manager
"""

from array import array
from bisect import bisect_right
from collections import Counter
import argparse
import csv
import json
import math
from pathlib import Path
import re
import subprocess
import sys


REPO = Path(__file__).resolve().parents[2]
DEFAULT_DEPS = REPO / "tmp" / "bringup" / "saleae-deps"


def channels(value):
    result = [int(v) for v in value.split(",") if v]
    if len(result) != len(set(result)) or any(v < 0 or v > 7 for v in result):
        raise argparse.ArgumentTypeError("Channels must be unique integers 0 through 7.")
    return result


def columns(names):
    time_name = next((n for n in names if n.strip().lower().startswith("time")), None)
    channel_names = {}
    for name in names:
        match = re.fullmatch(r"\s*(?:channel|ch)\s*(\d+)(?:\s*\([^)]*\))?\s*", name, re.I)
        if match:
            channel_names[int(match.group(1))] = name
    if time_name is None:
        raise ValueError("CSV has no time column.")
    return time_name, channel_names


def read_digital(path):
    signals = {}
    start = end = None
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        time_name, names = columns(reader.fieldnames or [])
        for row in reader:
            time = float(row[time_name])
            if not math.isfinite(time) or (end is not None and time < end):
                raise ValueError("Digital timestamps must be finite and nondecreasing.")
            if start is None:
                start = time
            end = time
            for channel, name in names.items():
                level = int(row[name])
                if level not in (0, 1):
                    raise ValueError(f"Invalid digital level on channel {channel}.")
                if channel not in signals:
                    signals[channel] = {"initial": level, "final": level, "edges": []}
                signal = signals[channel]
                if signal["final"] != level:
                    signal["edges"].append([time, level])
                    signal["final"] = level
    if start is None:
        raise ValueError("Digital export is empty.")
    return {"start_s": start, "end_s": end, "channels": signals}


def high_pulses(signal):
    result = []
    rising = None
    for time, level in signal["edges"]:
        if level:
            rising = time
        elif rising is not None:
            result.append([rising, time])
            rising = None
    return result


def near(value, nominal):
    # Wiring identification, not oscillator or startup-performance qualification.
    return nominal * 0.65 <= value <= nominal * 1.6


def pulse_train_matches(pulses, nominal):
    return (all(near(fall - rise, nominal) for rise, fall in pulses)
            and all(near(b[0] - a[1], nominal) for a, b in zip(pulses, pulses[1:])))


def verify_pattern(digital):
    signals = digital["channels"]
    errors = []
    for channel in (0, 1, 2):
        if channel not in signals:
            errors.append(f"Required digital channel {channel} was not captured.")
    if errors:
        return {"passed": False, "errors": errors}
    reset = signals[0]
    lows = []
    falling = None
    for time, level in reset["edges"]:
        if level == 0:
            falling = time
        elif falling is not None:
            lows.append([falling, time])
            falling = None
    if reset["initial"] != 1 or reset["final"] != 1 or not lows:
        errors.append("NRST must start high, contain a complete low-to-high reset pulse, and finish high.")
    for channel in (1, 2):
        if signals[channel]["final"] != 0:
            errors.append(f"Marker channel {channel} did not finish low.")

    pd0 = high_pulses(signals[1])
    pe0 = high_pulses(signals[2])
    match = None
    # Ignore possible GPIO activity before firmware configures the pins. Match
    # the distinctive complete sequence and reject subsequent extra edges.
    for i in range(max(0, len(pd0) - 4)):
        p = pd0[i:i + 5]
        if not pulse_train_matches(p[:4], 0.050) or not near(p[4][1] - p[4][0], 0.200):
            continue
        for j in range(max(0, len(pe0) - 3)):
            q = pe0[j:j + 4]
            if not pulse_train_matches(q[:3], 0.100) or not near(q[3][1] - q[3][0], 0.200):
                continue
            if abs(p[4][0] - q[3][0]) > 0.005 or abs(p[4][1] - q[3][1]) > 0.005:
                continue
            # Each train includes its final low interval, followed by the
            # extra 100 ms delay in probe_smoke_run().
            gap1 = q[0][0] - p[3][1]
            gap2 = p[4][0] - q[2][1]
            if not (near(gap1, 0.150) and near(gap2, 0.200)):
                continue
            if any(t > p[4][1] + 0.005 for t, _ in signals[1]["edges"] + signals[2]["edges"]):
                continue
            if not any(end <= p[0][0] for _, end in lows):
                continue
            # GDB may reset the MCU again after the test to return it to ROM.
            # That cleanup reset is permitted; resets overlapping the marker
            # sequence would invalidate the observed waveform.
            pattern_end = max(p[4][1], q[3][1])
            if any(start < pattern_end and end > p[0][0] for start, end in lows):
                continue
            if any(p[0][0] <= rise < q[0][0] for rise, _ in pe0):
                continue
            match = {"pd0_pulses_s": p, "pe0_pulses_s": q,
                     "pd0_to_pe0_gap_s": gap1, "pe0_to_joint_gap_s": gap2,
                     "start_s": p[0][0], "end_s": max(p[4][1], q[3][1])}
            break
        if match:
            break
    if not match:
        errors.append("Did not find four PD0 50 ms pulses, then three PE0 100 ms pulses, then a joint 200 ms pulse after reset.")
    return {"passed": not errors, "errors": errors, "reset_low_intervals_s": lows,
            "pd0_complete_high_pulses": len(pd0), "pe0_complete_high_pulses": len(pe0),
            "matched_pattern": match,
            "note": "Pulse widths have broad tolerances. Capture start is not firmware entry or power-on."}


class VoltageStats:
    """Bounded-memory voltage summaries; median rounded to the nearest mV."""
    def __init__(self):
        self.count = 0
        self.histogram = Counter()
        self.minimum = math.inf
        self.maximum = -math.inf
        self.outside_expected = 0

    def add(self, voltage, expected=None):
        if not math.isfinite(voltage):
            raise ValueError("Non-finite analog voltage.")
        self.count += 1
        self.histogram[round(voltage * 1000)] += 1
        self.minimum = min(self.minimum, voltage)
        self.maximum = max(self.maximum, voltage)
        if expected is not None and not expected[0] <= voltage <= expected[1]:
            self.outside_expected += 1

    def result(self):
        if not self.count:
            return {"samples": 0, "median_v": None}
        middle = (self.count + 1) // 2
        cumulative = 0
        for value, count in sorted(self.histogram.items()):
            cumulative += count
            if cumulative >= middle:
                median = value / 1000
                break
        return {"samples": self.count, "median_v": median,
                "min_v": self.minimum, "max_v": self.maximum,
                "outside_expected_samples": self.outside_expected}


def analyze_analog(path, digital, pattern):
    totals = {}
    levels = {channel: [VoltageStats(), VoltageStats()] for channel in (1, 2)}
    edge_times = {c: array("d", (edge[0] for edge in digital["channels"].get(c, {}).get("edges", []))) for c in (1, 2)}
    match = pattern.get("matched_pattern")
    previous_time = None
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        time_name, names = columns(reader.fieldnames or [])
        totals = {channel: VoltageStats() for channel in names}
        for row in reader:
            time = float(row[time_name])
            if not math.isfinite(time) or (previous_time is not None and time < previous_time):
                raise ValueError("Analog timestamps must be finite and nondecreasing.")
            previous_time = time
            for channel, name in names.items():
                voltage = float(row[name])
                totals[channel].add(voltage)
                if channel not in levels or not match or not (match["start_s"] - 0.030 <= time <= match["end_s"] + 0.030):
                    continue
                times = edge_times[channel]
                index = bisect_right(times, time)
                # Exclude analog filtering/transition settling around each edge.
                if ((index and time - times[index - 1] < 0.001)
                        or (index < len(times) and times[index] - time < 0.001)):
                    continue
                signal = digital["channels"][channel]
                level = signal["edges"][index - 1][1] if index else signal["initial"]
                levels[channel][level].add(voltage, (-0.3, 0.5) if level == 0 else (2.7, 3.6))
    marker_results = {}
    warnings = []
    for channel, stats in levels.items():
        if channel not in totals:
            continue
        marker_results[channel] = {"low": stats[0].result(), "high": stats[1].result()}
        for level, item in marker_results[channel].items():
            if not item["samples"]:
                warnings.append(f"Channel {channel}: no stable {level} samples to assess.")
            elif item["outside_expected_samples"]:
                warnings.append(f"Channel {channel}: {item['outside_expected_samples']} stable {level} samples outside its expected voltage range.")
    return {"channels": {c: stats.result() for c, stats in totals.items()},
            "marker_levels": marker_results, "warnings": warnings,
            "median_resolution_v": 0.001, "edge_exclusion_s": 0.001,
            "low_expected_v": [-0.3, 0.5], "high_expected_v": [2.7, 3.6],
            "note": "Marker checks use the matched waveform window only. Rail channel statistics do not imply power-on was observed."}


def analyze(output):
    digital = read_digital(output / "digital.csv")
    pattern = verify_pattern(digital)
    result = {"digital": digital, "pattern": pattern}
    if (output / "analog.csv").exists():
        result["analog"] = analyze_analog(output / "analog.csv", digital, pattern)
    result["passed"] = pattern["passed"] and not result.get("analog", {}).get("warnings")
    (output / "probe-summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2), flush=True)
    return result["passed"]


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=10430)
    parser.add_argument("--capture", action="store_true")
    parser.add_argument("--analyze", type=Path)
    parser.add_argument("--duration", type=float, default=15.0)
    parser.add_argument("--digital", type=channels, default=[0, 1, 2])
    parser.add_argument("--analog", type=channels, default=[0, 1, 2])
    # Verified accepted together by the physical LP8 / Logic 2.4.46 with
    # digital and analog channels 0-4. Rates are constrained combinations,
    # not arbitrary values individually below the hardware maximum.
    parser.add_argument("--digital-rate", type=int, default=6_250_000)
    parser.add_argument("--analog-rate", type=int, default=31_250)
    parser.add_argument("--device")
    parser.add_argument("--deps", type=Path, default=DEFAULT_DEPS)
    parser.add_argument("--output", type=Path, default=REPO / "tmp" / "bringup" / "probe-smoke")
    parser.add_argument("--stimulus-command", nargs="+", help="Must be last; executable followed by its arguments, including flags.")
    argv = sys.argv[1:]
    # Keep arguments such as GDB's -batch/-x intact rather than parsing them as
    # this program's flags. There is deliberately no shell or command string.
    stimulus = None
    if "--stimulus-command" in argv:
        index = argv.index("--stimulus-command")
        stimulus = argv[index + 1:]
        argv = argv[:index]
        if not stimulus:
            parser.error("--stimulus-command requires an executable.")
    args = parser.parse_args(argv)
    args.stimulus_command = stimulus
    if args.duration <= 0:
        parser.error("--duration must be positive.")
    if args.capture and args.analyze:
        parser.error("Use either --capture or --analyze.")
    if stimulus and not args.capture:
        parser.error("--stimulus-command requires --capture.")
    return args


def main():
    args = parse_args()
    if args.analyze:
        return 0 if analyze(args.analyze.resolve()) else 1
    sys.path.insert(0, str(args.deps.resolve()))
    from saleae import automation

    with automation.Manager.connect(port=args.port, connect_timeout_seconds=5) as manager:
        print("APP", manager.get_app_info(), flush=True)
        devices = manager.get_devices()
        print("DEVICES", devices, flush=True)
        if not args.capture:
            return 0
        if not devices or (not args.device and len(devices) != 1):
            raise RuntimeError("Need one physical Saleae device, or an explicit --device selection.")
        output = args.output.resolve()
        output.mkdir(parents=True, exist_ok=False)
        config = automation.LogicDeviceConfiguration(
            enabled_digital_channels=args.digital,
            digital_sample_rate=args.digital_rate if args.digital else None,
            digital_threshold_volts=3.3,
            enabled_analog_channels=args.analog,
            analog_sample_rate=args.analog_rate if args.analog else None,
        )
        capture_config = automation.CaptureConfiguration(
            capture_mode=automation.TimedCaptureMode(duration_seconds=args.duration)
        )
        stimulus_status = None
        with manager.start_capture(device_id=args.device or devices[0].device_id,
                                   device_configuration=config,
                                   capture_configuration=capture_config) as capture:
            print("CAPTURE_STARTED", str(output), flush=True)
            with (output / "stimulus.stdout.log").open("w", encoding="utf-8") as stdout, \
                    (output / "stimulus.stderr.log").open("w", encoding="utf-8") as stderr:
                process = None
                try:
                    if args.stimulus_command:
                        process = subprocess.Popen(args.stimulus_command, stdout=stdout,
                                                   stderr=stderr, shell=False)
                    capture.wait()
                    capture.save_capture(str(output / "smoke.sal"))
                    capture.export_raw_data_csv(str(output), digital_channels=args.digital,
                                                analog_channels=args.analog)
                    if process:
                        try:
                            stimulus_status = process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            stimulus_status = "timeout: stimulus still running after capture"
                finally:
                    if process and process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=2)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()
            print("CAPTURE_SAVED", str(output), flush=True)
        (output / "capture-config.json").write_text(json.dumps({
            "duration_s": args.duration, "digital_channels": args.digital,
            "analog_channels": args.analog, "digital_sample_rate": args.digital_rate,
            "analog_sample_rate": args.analog_rate, "digital_threshold_volts": 3.3,
            "stimulus_command": args.stimulus_command, "stimulus_exit_status": stimulus_status,
        }, indent=2) + "\n", encoding="utf-8")
    passed = analyze(output)
    if stimulus_status not in (None, 0):
        print(f"STIMULUS_FAILED: {stimulus_status}; see saved stdout/stderr.", file=sys.stderr)
        return 1
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
