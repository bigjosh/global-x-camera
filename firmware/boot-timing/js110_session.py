r"""Keep one JS110 connection open for reversible bench power control.

Release the device in the Joulescope GUI before starting this program. From
the repository root, using the same Python as the isolated driver install:

  python firmware/boot-timing/js110_session.py \
    --control tmp/bringup/js110-control.json \
    --response tmp/bringup/js110-response.json \
    --log tmp/bringup/js110-session.jsonl

After the response says "ready", replace the control file with a JSON object
such as {"id": "off-1", "state": "off"}. States are off, auto, query, and stop.
Use a new string/integer id for every request and wait for its response before
sending another. This is a one-request mailbox, not a queue. A control file
already present at startup is ignored. UTF-8 with or without a BOM is accepted.

The current range at session start is restored on stop, timeout, Ctrl-C, or a
handled error. Killing the process, unplugging the instrument, or host failure
can prevent restoration. Closing the session does not guarantee continued DUT
power. No automatic off/on cycle is performed by this script.

Sensor statistics arrive at about 2 Hz and may precede the latest command.
Voltage is measured at JS110 IN+/IN-, not the switched DUT output. Host command
timestamps are diagnostic; use the Saleae rail waveform for physical timing.
Driver reference: https://github.com/jetperch/joulescope_driver
"""

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import sys
import threading
import time


REPO = Path(__file__).resolve().parents[2]
DEFAULT_DEPS = REPO / "tmp" / "bringup" / "joulescope-deps"
RANGE_TOPIC = "s/i/range/select"
STATS_TOPIC = "s/sstats/value"


def stamp():
    return {"utc": datetime.now(timezone.utc).isoformat(),
            "monotonic_ns": time.monotonic_ns()}


def number(value):
    """Keep NaN/Inf out of otherwise portable JSON statistics."""
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


class Statistics:
    def __init__(self):
        self.lock = threading.Lock()
        self.latest = None
        self.sequence = 0

    def receive(self, topic, value):
        # The driver invokes this on its own thread: no device calls or file I/O.
        signals = value.get("signals", {})
        result = {"received": stamp(), "voltage_location": "IN+ relative to IN-"}
        for signal, unit in (("voltage", "V"), ("current", "A"), ("power", "W")):
            result[signal] = {"units": unit}
            for field in ("avg", "min", "max"):
                result[signal][field] = number(
                    signals.get(signal, {}).get(field, {}).get("value"))
        with self.lock:
            self.sequence += 1
            result["sequence"] = self.sequence
            self.latest = result

    def snapshot(self):
        with self.lock:
            result = None if self.latest is None else dict(self.latest)
        if result is not None:
            result["age_s"] = (time.monotonic_ns() - result["received"]["monotonic_ns"]) / 1e9
        return result


class Reporter:
    def __init__(self, response, log):
        self.response = response
        self.log = log

    def emit(self, event, *, response=False, **values):
        record = {"event": event, **stamp(), **values}
        encoded = json.dumps(record, allow_nan=False)
        self.log.write(encoded + "\n")
        self.log.flush()
        if response:
            temporary = self.response.with_name(self.response.name + ".tmp")
            temporary.write_text(encoded + "\n", encoding="utf-8")
            # Windows readers can briefly prevent replacement. Retry without
            # performing the hardware command a second time.
            for attempt in range(5):
                try:
                    os.replace(temporary, self.response)
                    break
                except PermissionError:
                    if attempt == 4:
                        raise
                    time.sleep(0.02)
            print(encoded, flush=True)


def read_control(path):
    try:
        with path.open("rb") as stream:
            return stream.read(65537)
    except (FileNotFoundError, PermissionError):
        return None


def run_session(args, driver_factory, driver_version):
    """Run the mailbox; driver_factory is injectable for hardware-free checks."""
    previous_content = read_control(args.control)
    seen_ids = set()
    stats = Statistics()
    removed = threading.Event()
    stop_id = None
    exit_code = 0
    deadline = time.monotonic() + args.duration
    for path in (args.response, args.log):
        path.parent.mkdir(parents=True, exist_ok=True)

    with args.log.open("a", encoding="utf-8", buffering=1) as log:
        report = Reporter(args.response, log)
        try:
            with driver_factory() as driver:
                paths = driver.device_paths()
                if args.device not in paths:
                    raise RuntimeError(f"Required device not found; available={paths}")
                with driver.open(args.device, mode="restore", timeout=5.0) as device:
                    starting_range = device.query(RANGE_TOPIC, timeout=5.0)
                    starting_stats = None
                    reason = "timeout"
                    try:
                        device.subscribe(STATS_TOPIC, "pub", stats.receive)
                        # Enable only native sensor statistics, preserving their
                        # previous setting. No i/v/p stream or range-mode change.
                        starting_stats = device.query("s/sstats/ctrl", timeout=5.0)
                        if not starting_stats:
                            device.publish("s/sstats/ctrl", 1, timeout=5.0)
                        driver.subscribe("@/!remove", "pub",
                                         lambda topic, value: removed.set()
                                         if value == args.device else None)
                        report.emit("ready", response=True, device=args.device,
                                    driver_version=driver_version, open_mode="restore",
                                    starting_range=starting_range, range=starting_range,
                                    voltage_range=device.query("s/v/range/select", timeout=5.0),
                                    duration_s=args.duration, statistics=stats.snapshot())
                        last_stats = 0
                        while time.monotonic() < deadline:
                            if removed.is_set():
                                raise RuntimeError("JS110 disconnected during session")
                            snapshot = stats.snapshot()
                            if snapshot and snapshot["sequence"] != last_stats:
                                last_stats = snapshot["sequence"]
                                report.emit("statistics", statistics=snapshot)
                            content = read_control(args.control)
                            if content is None or content == previous_content:
                                time.sleep(0.1)
                                continue
                            previous_content = content
                            try:
                                if len(content) > 65536:
                                    raise ValueError("Control file exceeds 64 KiB")
                                request = json.loads(content.decode("utf-8-sig"))
                                if not isinstance(request, dict):
                                    raise ValueError("Control request must be a JSON object")
                                request_id = request.get("id")
                                if type(request_id) not in (str, int) or request_id == "":
                                    raise ValueError("Request id must be a nonempty string or integer")
                            except (ValueError, UnicodeError) as exc:
                                # A writer may be midway through replacing the
                                # file. A later, complete version is still read.
                                report.emit("invalid_control", error=str(exc))
                                time.sleep(0.1)
                                continue
                            id_key = (type(request_id), request_id)
                            if id_key in seen_ids:
                                continue
                            seen_ids.add(id_key)
                            state = request.get("state")
                            if state not in ("off", "auto", "query", "stop"):
                                report.emit("response", response=True, id=request_id,
                                            ok=False, error="State must be off, auto, query, or stop")
                                continue
                            command_start = stamp()
                            if state in ("off", "auto"):
                                device.publish(RANGE_TOPIC, state, timeout=5.0)
                            command_end = stamp()
                            current_range = device.query(RANGE_TOPIC, timeout=5.0)
                            report.emit("response", response=True, id=request_id, state=state,
                                        ok=True, range=current_range,
                                        command_start=command_start, command_end=command_end,
                                        statistics=stats.snapshot())
                            if state == "stop":
                                stop_id = request_id
                                reason = "stop"
                                break
                    except KeyboardInterrupt:
                        reason = "interrupt"
                        exit_code = 130
                    except Exception as exc:
                        reason = "error"
                        exit_code = 1
                        report.emit("error", error=str(exc))
                    finally:
                        # Always attempt restoration before reporting or
                        # cleaning up subscriptions, even when file I/O failed.
                        restore_error = None
                        restored_range = None
                        try:
                            device.publish(RANGE_TOPIC, starting_range, timeout=5.0)
                            restored_range = device.query(RANGE_TOPIC, timeout=5.0)
                            if restored_range != starting_range:
                                raise RuntimeError("Restored range does not match starting range")
                        except Exception as exc:
                            restore_error = str(exc)
                            exit_code = 1
                        if starting_stats is not None:
                            try:
                                device.publish("s/sstats/ctrl", starting_stats, timeout=5.0)
                            except Exception as exc:
                                report.emit("statistics_restore_error", error=str(exc))
                                exit_code = 1
                        report.emit("stopped", response=True, id=stop_id, reason=reason,
                                    ok=exit_code == 0, starting_range=starting_range,
                                    range=restored_range, restore_error=restore_error,
                                    statistics=stats.snapshot())
        except Exception as exc:
            report.emit("fatal", response=True, ok=False, error=str(exc))
            exit_code = 1
    return exit_code


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--device", default="u/js110/000163")
    parser.add_argument("--deps", type=Path, default=DEFAULT_DEPS)
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--response", type=Path, required=True)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--duration", type=float, default=1800,
                        help="Maximum session seconds, >0 and <=1800 (default 1800).")
    args = parser.parse_args()
    if not math.isfinite(args.duration) or not 0 < args.duration <= 1800:
        parser.error("--duration must be >0 and <=1800 seconds")
    if len({path.resolve() for path in (args.control, args.response, args.log)}) != 3:
        parser.error("Control, response, and log paths must be distinct")
    if not args.device.startswith("u/js110/"):
        parser.error("This helper supports JS110 devices only")
    sys.path.insert(0, str(args.deps.resolve()))
    from pyjoulescope_driver import Driver, __version__
    return run_session(args, Driver, __version__)


if __name__ == "__main__":
    raise SystemExit(main())
