r"""Keep one JS110 connection open for reversible bench power control.

Release the device in the Joulescope GUI before starting this program. From
the repository root, using the same Python as the isolated driver install:

  python firmware/boot-timing/js110_session.py \
    --control tmp/bringup/js110-control.json \
    --response tmp/bringup/js110-response.json \
    --log tmp/bringup/js110-session.jsonl

After the response says "ready", replace the control file with a JSON object
such as {"id": "off-1", "state": "off"}. States are off, auto, 2A, query, and stop.
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

Optional --stream-log PATH records full-rate i/v chunk summaries on a separate
worker: min/mean/max, extrema sample positions, nonfinite counts and gaps. It
temporarily selects 2 MHz host sampling and enables i/v streams, then restores
those settings. It retains no raw waveform. Chunk UTC is the driver's estimate;
receipt/command UTC is host time. Neither replaces external rail timing.
The legacy stream "complete" flag describes logging only. Separate coverage
checks require samples from both signals and contiguous native sample ids;
session success requires both. These checks cover received intervals, not the
unobserved stream boundaries, and do not establish finite or unclipped readings.

Optional --power-stream-log PATH selects a new schema with i/v/p summaries and
float64 sample sums. Power comes from the driver's s/p/!data stream, not the
product of separate current/voltage means. This option preserves and restores
the additional s/p/ctrl setting. It is mutually exclusive with --stream-log.
Use capture-sd/energy.py for offline interval integration and coverage checks.

Optional --cycle-raw-dir DIR retains exact full-rate i/v/p float32 samples and
their native sample IDs, using the same single device owner and restore path.
It requires a new directory and is mutually exclusive with the summary flags.
At 2 MHz it writes about 24 MB/s; --raw-max-mib bounds total sample-file bytes.
Exceeding that budget fails the recording and follows normal settings cleanup.
Use capture-sd/cycle_energy.py offline. This adds no power cycles or GPIO access.

The 2A state selects a fixed measurement range, NOT a 2 A current limit. Inrush
can exceed the range and clip the reported current. This helper changes no
source voltage, protection threshold, voltage range, or range-suppression mode.

Optional --recovery-output owns OUT0 for an active-high NMOS recovery interface.
Use --recovery-interface diode for a PE1-anode/OUT0-cathode diode sink instead.
It initially releases recovery (NMOS OUT0=0; diode OUT0=1) and accepts
state=recovery with a strict JSON boolean asserted. It preserves the initial
OUT0 and shared I/O voltage on exit, never writes OUT1, and reports retained GPIO
settings (not measured pins).
See js110-recovery-output.md for wiring, shared-voltage guards and limitations.
"""

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import queue
import sys
import threading
import time


REPO = Path(__file__).resolve().parents[2]
DEFAULT_DEPS = REPO / "tmp" / "bringup" / "joulescope-deps"
RANGE_TOPIC = "s/i/range/select"
STATS_TOPIC = "s/sstats/value"
STREAM_TOPICS = {"s/i/!data": ("current", "A"),
                 "s/v/!data": ("voltage", "V")}
RANGE_STATES = {"off": 0, "auto": 128, "2A": 2}
SUPPORTED_STATES = [*RANGE_STATES, "query", "stop"]
EXTIO_TOPIC = "s/extio/voltage"
GPO_TOPICS = ("s/gpo/0/value", "s/gpo/1/value")


class RecoveryOutput:
    """Opt-in OUT0 ownership. No calls occur for legacy power-only sessions."""

    def __init__(self, device, interface="nmos"):
        if interface not in ("nmos", "diode"):
            raise ValueError("Recovery interface must be nmos or diode")
        self.device = device
        self.interface = interface
        self.released_level = int(interface == "diode")
        self.starting = {}
        self.changed = set()

    def query(self):
        values = {topic: self.device.query(topic, timeout=5.0)
                  for topic in (EXTIO_TOPIC, *GPO_TOPICS)}
        for topic in GPO_TOPICS:
            if type(values[topic]) not in (bool, int) or values[topic] not in (0, 1):
                raise RuntimeError(f"Invalid retained GPIO value: {topic}={values[topic]!r}")
        if type(values[EXTIO_TOPIC]) is not int or values[EXTIO_TOPIC] < 0:
            raise RuntimeError("Invalid retained external-I/O voltage")
        return values

    def snapshot(self):
        values = self.query()
        if self.starting and values[GPO_TOPICS[1]] != self.starting[GPO_TOPICS[1]]:
            raise RuntimeError("OUT1 changed unexpectedly; helper does not own OUT1")
        return {"scope": "retained_settings_not_measured_pins",
                "interface": "active_low_diode" if self.interface == "diode" else "active_high_nmos",
                "extio_voltage_mv": values[EXTIO_TOPIC],
                "gpo0": int(values[GPO_TOPICS[0]]), "gpo1": int(values[GPO_TOPICS[1]]),
                "asserted": int(values[GPO_TOPICS[0]]) != self.released_level}

    def _write(self, topic, value):
        # A failed USB call may still have changed hardware; restore it anyway.
        self.changed.add(topic)
        self.device.publish(topic, value, timeout=5.0)
        if self.device.query(topic, timeout=5.0) != value:
            raise RuntimeError(f"Retained setting mismatch after writing {topic}")

    def start(self):
        self.starting = self.query()
        voltage = self.starting[EXTIO_TOPIC]
        if voltage not in (0, 3300):
            raise RuntimeError("Recovery output requires existing I/O voltage 3300 mV or off")
        if voltage == 0:
            # This supply serves both outputs and both input thresholds. Even
            # OUT1=0 changes from unpowered to driven-low when it is enabled.
            # The CLI flag also requires other rear GPIO pins disconnected.
            live = self.starting[GPO_TOPICS[1]] != 0
            for topic in ("s/gpi/0/ctrl", "s/gpi/1/ctrl", "s/i/lsb_src", "s/v/lsb_src"):
                if self.device.query(topic, timeout=5.0) != 0:
                    live = True
            if live:
                raise RuntimeError("Cannot enable shared I/O voltage while another GPIO route is active")
        # Release before enabling the shared supply: low for NMOS, high for
        # diode. This ordering does not establish the actual unpowered pin state.
        if self.starting[GPO_TOPICS[0]] != self.released_level:
            self._write(GPO_TOPICS[0], self.released_level)
        if voltage != 3300:
            self._write(EXTIO_TOPIC, 3300)
        return self.snapshot()

    def set_asserted(self, asserted):
        if type(asserted) is not bool:
            raise ValueError("Recovery asserted must be a JSON boolean")
        before = self.snapshot()
        if before["extio_voltage_mv"] != 3300:
            raise RuntimeError("Recovery I/O voltage changed unexpectedly")
        self._write(GPO_TOPICS[0], self.released_level ^ int(asserted))
        after = self.snapshot()
        if after["asserted"] != asserted or after["extio_voltage_mv"] != 3300:
            raise RuntimeError("Recovery output retained state did not match request")
        return after

    def restore(self):
        """Try every owned setting even if an earlier restoration fails."""
        errors = []
        order = (EXTIO_TOPIC, GPO_TOPICS[0]) if self.starting.get(EXTIO_TOPIC) == 0 else (
            GPO_TOPICS[0], EXTIO_TOPIC)
        for topic in order:
            if topic not in self.changed:
                continue
            try:
                if topic == EXTIO_TOPIC:
                    # Never disable a shared supply if an unowned output has
                    # changed during the session. Do not overwrite that pin.
                    if self.device.query(GPO_TOPICS[1], timeout=5.0) != self.starting[GPO_TOPICS[1]]:
                        raise RuntimeError("OUT1 changed; refusing shared-voltage restoration")
                self.device.publish(topic, self.starting[topic], timeout=5.0)
                if self.device.query(topic, timeout=5.0) != self.starting[topic]:
                    raise RuntimeError("Restored recovery setting does not match starting value")
            except Exception as exc:
                errors.append(("recovery_restore_error", topic, str(exc)))
        current = None
        if self.starting:
            try:
                current = self.snapshot()
                if self.interface == "diode" and self.starting[GPO_TOPICS[0]] == 0:
                    current["restore_warning"] = (
                        "Restored OUT0=0 is the diode interface's recovery polarity; "
                        "the next boot may enter recovery. Retained settings are not measured pin levels.")
                if self.query() != self.starting:
                    raise RuntimeError("Recovery settings differ from starting values")
            except Exception as exc:
                errors.append(("recovery_restore_error", "verification", str(exc)))
        return current, errors


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


class StreamLog:
    """Log off the USB thread, distinguishing logging from signal coverage."""

    def __init__(self, path, include_power=False, *, queue_chunks=64):
        if type(queue_chunks) is not int or not 1 <= queue_chunks <= 1024:
            raise ValueError("Stream queue size must be an integer between 1 and 1024")
        import numpy as np
        self.np = np
        self.include_power = include_power
        self.topics = dict(STREAM_TOPICS)
        if include_power:
            self.topics["s/p/!data"] = ("power", "W")
        path.parent.mkdir(parents=True, exist_ok=True)
        self.file = path.open("a", encoding="utf-8", buffering=1)
        self.queue = queue.Queue(maxsize=queue_chunks)
        self.lock = threading.Lock()
        self.error = None
        self.dropped_chunks = 0
        self.chunks = 0
        self.next_samples = {}
        self.coverage = {
            signal: {"chunks": 0, "samples": 0, "nonfinite_samples": 0,
                     "first_sample_id": None, "last_sample_id_end_exclusive": None,
                     "discontinuities": 0, "missing_native_samples": 0,
                     "overlap_or_reset_events": 0}
            for signal, _ in self.topics.values()}
        self.callback = self.receive
        self.closed = False
        self._write({"event": "stream_start", **stamp(), "schema": 2 if include_power else 1,
                     "aggregation": "one record per driver chunk, no raw samples retained",
                     "complete_scope": "logging_only; see coverage checks separately",
                     "voltage_location": "IN+ relative to IN-",
                     "requested_output_sample_rate_hz": 2000000,
                     "sample_id_units": "native sample ticks; advance by decimate_factor",
                     "utc_time64_units": "2**-30 seconds since 2018-01-01T00:00:00Z",
                     "limits": {
                         "range_selection_is_current_limit": False,
                         "fixed_2A_may_clip_above_range": True,
                         "abs_ge_2A_count_is_not_a_clipping_detector": True,
                         "range_suppression_remains_unchanged": True,
                         "min_max_are_of_delivered_samples_not_analog_peak_guarantees": True}})
        self.thread = threading.Thread(target=self._worker, name="js110-stream-log", daemon=True)
        self.thread.start()

    def _write(self, record):
        self.file.write(json.dumps(record, allow_nan=False) + "\n")

    def receive(self, topic, value):
        # Copy driver-owned samples before returning; never block for disk/queue.
        try:
            if self.closed:
                return
            packet = {key: value[key] for key in
                      ("sample_id", "sample_rate", "decimate_factor", "utc")}
            packet["time_map"] = dict(value.get("time_map", {}))
            packet["data"] = value["data"].copy()
            self.queue.put_nowait((topic, stamp(), packet))
        except queue.Full:
            with self.lock:
                self.dropped_chunks += 1
        except Exception as exc:
            with self.lock:
                self.error = self.error or str(exc)

    def summarize(self, topic, received, value):
        """Driver sample ids use native ticks, even for decimated samples."""
        np = self.np
        suffix = next(key for key in self.topics if topic.endswith("/" + key) or topic == key)
        signal, units = self.topics[suffix]
        samples = np.asarray(value["data"])
        if samples.ndim != 1:
            raise ValueError("Expected a one-dimensional float stream")
        sample_id = int(value["sample_id"])
        rate = int(value["sample_rate"])
        decimation = int(value["decimate_factor"])
        if rate <= 0 or decimation <= 0:
            raise ValueError("Invalid sample rate or decimation")
        count = int(samples.size)
        finite_indices = np.flatnonzero(np.isfinite(samples))
        finite = samples[finite_indices]
        minimum = maximum = mean = None
        min_id = max_id = None
        if finite.size:
            minimum, maximum = number(finite.min()), number(finite.max())
            mean = number(finite.mean(dtype=np.float64))
            min_id = sample_id + int(finite_indices[finite.argmin()]) * decimation
            max_id = sample_id + int(finite_indices[finite.argmax()]) * decimation
        next_sample = sample_id + count * decimation
        previous = self.next_samples.get(signal)
        self.next_samples[signal] = next_sample
        utc64 = int(value["utc"])
        time_map = value.get("time_map", {})
        result = {"event": "stream_chunk", "received": received,
                  "signal": signal, "units": units,
                  "sample_id": sample_id, "sample_id_end_exclusive": next_sample,
                  "sample_rate_hz": rate, "decimate_factor": decimation,
                  "effective_sample_rate_hz": rate / decimation,
                  "duration_s": count * decimation / rate,
                  "utc_time64": utc64,
                  "sample_utc": datetime.fromtimestamp(
                      1514764800 + utc64 / (1 << 30), timezone.utc).isoformat(),
                  "time_map": {key: (int(time_map[key]) if key != "counter_rate"
                                      else number(time_map[key]))
                               for key in ("offset_time", "offset_counter", "counter_rate")
                               if key in time_map},
                  "count": count, "finite_count": int(finite.size),
                  "nonfinite_count": count - int(finite.size),
                  "min": minimum, "mean": mean, "max": maximum,
                  "min_sample_id": min_id, "max_sample_id": max_id,
                  "gap_native_samples": None if previous is None else sample_id - previous}
        if signal == "current":
            result["abs_ge_2A_count"] = int(np.count_nonzero(np.abs(finite) >= 2.0))
        if self.include_power:
            result["sum"] = number(finite.sum(dtype=np.float64)) if finite.size else None
            result["sum_scope"] = "finite delivered samples; invalid for total energy if any are nonfinite"
        return result

    def _worker(self):
        try:
            while True:
                item = self.queue.get()
                if item is None:
                    break
                if self.error is None:
                    try:
                        record = self.summarize(*item)
                        self._write(record)
                        with self.lock:
                            self.chunks += 1
                            signal = self.coverage[record["signal"]]
                            signal["chunks"] += 1
                            signal["samples"] += record["count"]
                            signal["nonfinite_samples"] += record["nonfinite_count"]
                            if signal["first_sample_id"] is None:
                                signal["first_sample_id"] = record["sample_id"]
                            signal["last_sample_id_end_exclusive"] = record["sample_id_end_exclusive"]
                            gap = record["gap_native_samples"]
                            if gap is not None and gap != 0:
                                signal["discontinuities"] += 1
                                signal["missing_native_samples"] += max(0, gap)
                                signal["overlap_or_reset_events"] += int(gap < 0)
                    except Exception as exc:
                        with self.lock:
                            self.error = str(exc)
            self._write({"event": "stream_stop", **stamp(), **self.status()})
        except Exception as exc:
            with self.lock:
                self.error = str(exc)
        finally:
            self.file.close()

    def status(self):
        with self.lock:
            signals = {name: dict(values) for name, values in self.coverage.items()}
            checks = {}
            for name, values in signals.items():
                checks[name + "_samples_present"] = values["samples"] > 0
                checks[name + "_sample_ids_contiguous"] = values["discontinuities"] == 0
            return {"chunks": self.chunks, "dropped_chunks": self.dropped_chunks,
                    "error": self.error,
                    "complete": self.error is None and self.dropped_chunks == 0,
                    "complete_scope": "logging_only; see coverage checks separately",
                    "coverage": {
                        "passed": all(checks.values()), "checks": checks,
                        "signals": signals,
                        "scope": "Received sample intervals only; stream boundaries, "
                                 "nonfinite samples and clipping are not validated."}}

    def check(self):
        if self.error is not None:
            raise RuntimeError("Stream recording failed: " + self.error)

    def close(self):
        if not self.closed:
            self.closed = True
            # Subscriptions have already been removed; finish the bounded queue.
            deadline = time.monotonic() + 5.0
            while self.thread.is_alive() and time.monotonic() < deadline:
                try:
                    self.queue.put(None, timeout=0.1)
                    break
                except queue.Full:
                    continue
            self.thread.join(timeout=max(0, deadline - time.monotonic()))
            if self.thread.is_alive():
                with self.lock:
                    self.error = self.error or "Stream worker did not finish within 5 seconds"
        return self.status()


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
    stream = None
    recovery_enabled = bool(getattr(args, "recovery_output", False))
    supported_states = SUPPORTED_STATES + (["recovery"] if recovery_enabled else [])
    exit_code = 0
    deadline = time.monotonic() + args.duration
    for path in (args.response, args.log):
        path.parent.mkdir(parents=True, exist_ok=True)

    with args.log.open("a", encoding="utf-8", buffering=1) as log:
        report = Reporter(args.response, log)
        try:
            stream_path = getattr(args, "stream_log", None)
            power_path = getattr(args, "power_stream_log", None)
            raw_path = getattr(args, "cycle_raw_dir", None)
            if sum(p is not None for p in (stream_path, power_path, raw_path)) > 1:
                raise ValueError("Select only one stream log")
            if raw_path is not None:
                from js110_raw import make_raw_stream
                stream = make_raw_stream(StreamLog, raw_path,
                    max_bytes=getattr(args, "raw_max_mib", 4096) * 1024**2,
                    queue_chunks=getattr(args, "raw_queue_chunks", 64))
            elif power_path is not None:
                stream = StreamLog(power_path, include_power=True)
            elif stream_path is not None:
                stream = StreamLog(stream_path)
            with driver_factory() as driver:
                paths = driver.device_paths()
                if args.device not in paths:
                    raise RuntimeError(f"Required device not found; available={paths}")
                with driver.open(args.device, mode="restore", timeout=5.0) as device:
                    starting_range = device.query(RANGE_TOPIC, timeout=5.0)
                    recovery = RecoveryOutput(device, getattr(args, "recovery_interface", "nmos")) if recovery_enabled else None
                    starting_stats = None
                    starting_stream_settings = {}
                    stream_subscriptions = []
                    reason = "timeout"
                    try:
                        raw_settings = (stream.snapshot_measurement_settings(device)
                                        if raw_path is not None else None)
                        if recovery is not None:
                            recovery.start()
                        device.subscribe(STATS_TOPIC, "pub", stats.receive)
                        # Without --stream-log, enable only native statistics.
                        starting_stats = device.query("s/sstats/ctrl", timeout=5.0)
                        if not starting_stats:
                            device.publish("s/sstats/ctrl", 1, timeout=5.0)
                        if stream is not None:
                            stream_controls = ["s/i/ctrl", "s/v/ctrl"]
                            if stream.include_power:
                                stream_controls.append("s/p/ctrl")
                            for topic in ("h/fs", *stream_controls):
                                starting_stream_settings[topic] = device.query(topic, timeout=5.0)
                            for topic in stream.topics:
                                absolute_topic = args.device + "/" + topic
                                driver.subscribe(absolute_topic, "pub", stream.callback)
                                stream_subscriptions.append(absolute_topic)
                            for topic, value in [("h/fs", 2000000), *[(t, 1) for t in stream_controls]]:
                                if starting_stream_settings[topic] != value:
                                    device.publish(topic, value, timeout=5.0)
                        driver.subscribe("@/!remove", "pub",
                                         lambda topic, value: removed.set()
                                         if value == args.device else None)
                        report.emit("ready", response=True, device=args.device,
                                    driver_version=driver_version, open_mode="restore",
                                    supported_states=supported_states,
                                    starting_range=starting_range, range=starting_range,
                                    voltage_range=device.query("s/v/range/select", timeout=5.0),
                                    stream_log=None if stream is None else str(raw_path or power_path or stream_path),
                                    starting_stream_settings=starting_stream_settings,
                                    **({} if raw_settings is None else {
                                        "starting_raw_measurement_settings": raw_settings}),
                                    duration_s=args.duration, statistics=stats.snapshot(),
                                    **({} if recovery is None else {
                                        "starting_recovery_settings": recovery.starting,
                                        "recovery_output": recovery.snapshot()}))
                        last_stats = 0
                        while time.monotonic() < deadline:
                            if removed.is_set():
                                raise RuntimeError("JS110 disconnected during session")
                            if stream is not None:
                                stream.check()
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
                            if state not in supported_states:
                                report.emit("response", response=True, id=request_id,
                                            supported_states=supported_states,
                                            ok=False, error=("Recovery control requires --recovery-output"
                                                if state == "recovery" else
                                                "State must be one of: " + ", ".join(supported_states)))
                                continue
                            if state == "recovery" and type(request.get("asserted")) is not bool:
                                report.emit("response", response=True, id=request_id, state=state,
                                            supported_states=supported_states, ok=False,
                                            error="Recovery asserted must be a JSON boolean")
                                continue
                            command_start = stamp()
                            if state in RANGE_STATES:
                                device.publish(RANGE_TOPIC, RANGE_STATES[state], timeout=5.0)
                            elif state == "recovery":
                                recovery.set_asserted(request["asserted"])
                            command_end = stamp()
                            current_range = device.query(RANGE_TOPIC, timeout=5.0)
                            if raw_path is not None and state in RANGE_STATES:
                                stream.note_range_command(state, current_range,
                                                          command_start, command_end)
                            report.emit("response", response=True, id=request_id, state=state,
                                        supported_states=supported_states,
                                        ok=True, range=current_range,
                                        command_start=command_start, command_end=command_end,
                                        statistics=stats.snapshot(),
                                        **({} if recovery is None else {
                                            "recovery_output": recovery.snapshot()}))
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
                        restored_recovery = None
                        recovery_errors = []
                        if recovery is not None:
                            restored_recovery, recovery_errors = recovery.restore()
                            if recovery_errors:
                                exit_code = 1
                        try:
                            device.publish(RANGE_TOPIC, starting_range, timeout=5.0)
                            restored_range = device.query(RANGE_TOPIC, timeout=5.0)
                            if restored_range != starting_range:
                                raise RuntimeError("Restored range does not match starting range")
                        except Exception as exc:
                            restore_error = str(exc)
                            exit_code = 1
                        cleanup_errors = list(recovery_errors)
                        for topic in stream_subscriptions:
                            try:
                                driver.unsubscribe(topic, stream.callback, timeout=5.0)
                            except Exception as exc:
                                cleanup_errors.append(("stream_unsubscribe_error", topic, str(exc)))
                                exit_code = 1
                        for topic in ("s/i/ctrl", "s/v/ctrl", "s/p/ctrl", "h/fs"):
                            if topic in starting_stream_settings:
                                try:
                                    device.publish(topic, starting_stream_settings[topic], timeout=5.0)
                                    if device.query(topic, timeout=5.0) != starting_stream_settings[topic]:
                                        raise RuntimeError("Restored stream setting does not match starting value")
                                except Exception as exc:
                                    cleanup_errors.append(("stream_restore_error", topic, str(exc)))
                                    exit_code = 1
                        stream_status = None if stream is None else stream.close()
                        if stream_status is not None and not (
                                stream_status["complete"] and stream_status["coverage"]["passed"]):
                            exit_code = 1
                        if starting_stats is not None:
                            try:
                                device.publish("s/sstats/ctrl", starting_stats, timeout=5.0)
                            except Exception as exc:
                                cleanup_errors.append(("statistics_restore_error", "s/sstats/ctrl", str(exc)))
                                exit_code = 1
                        # A full/broken log must not prevent remaining hardware
                        # restoration attempts. Report only after those attempts.
                        for event, topic, error in cleanup_errors:
                            report.emit(event, topic=topic, error=error)
                        report.emit("stopped", response=True, id=stop_id, reason=reason,
                                    ok=exit_code == 0, starting_range=starting_range,
                                    range=restored_range, restore_error=restore_error,
                                    stream=stream_status,
                                    statistics=stats.snapshot(),
                                    **({} if recovery is None else {
                                        "starting_recovery_settings": recovery.starting,
                                        "recovery_output": restored_recovery,
                                        "recovery_restore_errors": [
                                            {"topic": topic, "error": error}
                                            for _, topic, error in recovery_errors]}))
        except Exception as exc:
            report.emit("fatal", response=True, ok=False, error=str(exc))
            exit_code = 1
        finally:
            if stream is not None:
                stream.close()
    return exit_code


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--device", default="u/js110/000163")
    parser.add_argument("--deps", type=Path, default=DEFAULT_DEPS)
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--response", type=Path, required=True)
    parser.add_argument("--log", type=Path, required=True)
    streams = parser.add_mutually_exclusive_group()
    streams.add_argument("--stream-log", type=Path,
                        help="Optional JSONL full-rate i/v chunk summaries; no raw samples retained.")
    streams.add_argument("--power-stream-log", type=Path,
                         help="Optional schema2 i/v/p summaries and sums for offline energy bounds.")
    streams.add_argument("--cycle-raw-dir", type=Path,
                         help="New directory for native-rate raw i/v/p samples and summary index.")
    parser.add_argument("--raw-max-mib", type=int, default=4096,
                        help="Raw sample byte budget in MiB (default 4096; about 179 s at 2 MHz).")
    parser.add_argument("--raw-queue-chunks", type=int, default=64,
                        help="Raw logging queue capacity, 1..1024 packets (default 64). "
                             "1024 uses about 256 MiB / 11 s at the observed packet size; "
                             "requires --cycle-raw-dir when nondefault.")
    parser.add_argument("--recovery-output", action="store_true",
                        help="Own OUT0 for recovery; release initially and restore on exit. "
                             "If shared I/O voltage starts off, other rear GPIO pins must be disconnected.")
    parser.add_argument("--recovery-interface", choices=("nmos", "diode"),
                        help="OUT0 polarity: nmos active high (default), diode active low. Requires --recovery-output.")
    parser.add_argument("--duration", type=float, default=1800,
                        help="Maximum session seconds, >0 and <=1800 (default 1800).")
    args = parser.parse_args()
    if args.recovery_interface is not None and not args.recovery_output:
        parser.error("--recovery-interface requires --recovery-output")
    args.recovery_interface = args.recovery_interface or "nmos"
    if not math.isfinite(args.duration) or not 0 < args.duration <= 1800:
        parser.error("--duration must be >0 and <=1800 seconds")
    if not 1 <= args.raw_max_mib <= 16384:
        parser.error("--raw-max-mib must be between 1 and 16384")
    if not 1 <= args.raw_queue_chunks <= 1024:
        parser.error("--raw-queue-chunks must be between 1 and 1024")
    if args.raw_queue_chunks != 64 and args.cycle_raw_dir is None:
        parser.error("Nondefault --raw-queue-chunks requires --cycle-raw-dir")
    paths = [args.control, args.response, args.log]
    if args.stream_log is not None:
        paths.append(args.stream_log)
    if args.power_stream_log is not None:
        paths.append(args.power_stream_log)
    if args.cycle_raw_dir is not None:
        paths.append(args.cycle_raw_dir)
        raw_root = args.cycle_raw_dir.resolve()
        if any(p.resolve().is_relative_to(raw_root) for p in paths[:-1]):
            parser.error("Control, response and session logs must be outside the new raw directory")
    if len({path.resolve() for path in paths}) != len(paths):
        parser.error("Control, response, log, and stream log paths must be distinct")
    if not args.device.startswith("u/js110/"):
        parser.error("This helper supports JS110 devices only")
    sys.path.insert(0, str(args.deps.resolve()))
    from pyjoulescope_driver import Driver, __version__
    return run_session(args, Driver, __version__)


if __name__ == "__main__":
    raise SystemExit(main())
