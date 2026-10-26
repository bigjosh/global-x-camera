"""Bounded JS110 current/voltage pulse trace, without power or GPIO control.

The exclusive bench owner must stop any existing Joulescope client first.
This opens once with mode=restore; an ownership/open failure is not retried.
It requests 2 MHz i/v delivery, writes only aligned 1..5 ms summaries, then
restores stream settings and the starting current range on every handled exit.
No raw waveform, power stream or energy calculation is retained. Killing the
process, host failure or USB removal can prevent restoration.

Run this helper, wait for the ready JSON line/file, then start the RAM test.
Native sample ids are the timing authority within the received interval;
driver-estimated UTC is approximate and host receipt time is not sample time.
The voltage input is JS110 IN+/IN-, not the switched target rail. A current
step alone does not establish its LED cause, Standby entry, or analog limits.

--self-test runs a synthetic cross-packet/gap aggregation test without even
importing the instrument driver.
"""
import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import queue
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[3]
TOPICS = {"s/i/!data": ("current", "A"), "s/v/!data": ("voltage", "V")}
CONTROLS = ("h/fs", "s/i/ctrl", "s/v/ctrl")
RANGE = "s/i/range/select"


def stamp():
    return dict(utc=datetime.now(timezone.utc).isoformat(), monotonic_ns=time.monotonic_ns())


class BinLogger:
    def __init__(self, output, bin_ms):
        import numpy as np
        self.np = np
        self.output = output
        self.bin_ms = bin_ms
        self.queue = queue.Queue(maxsize=128)
        self.lock = threading.Lock()
        self.error = None
        self.dropped = 0
        self.closed = False
        self.pending = {}
        self.coverage = {name: dict(chunks=0, samples=0, finite=0, bins=0,
            first_sample_id=None, end_sample_id_exclusive=None, gap_native_samples=0,
            discontinuities=0, overlaps_or_resets=0, sample_rate_hz=None,
            decimate_factor=None) for name, _ in TOPICS.values()}
        self.callback = self.receive
        self.thread = threading.Thread(target=self.worker, daemon=True, name="led-trace-bins")
        self.thread.start()

    def emit(self, record):
        with self.lock:
            self.output.write(json.dumps(record, allow_nan=False) + "\n")
            self.output.flush()

    def receive(self, topic, value):
        # The device callback does no driver calls, reductions, or disk I/O.
        if self.closed:
            return
        try:
            payload = {k: value[k] for k in ("sample_id", "sample_rate", "decimate_factor", "utc")}
            payload["data"] = value["data"].copy()
            self.queue.put_nowait((topic, stamp(), payload))
        except queue.Full:
            self.dropped += 1
            self.error = self.error or "Summary queue overflow; samples were dropped"
        except Exception as exc:
            self.error = self.error or repr(exc)

    def flush(self, signal, reason):
        row = self.pending.pop(signal, None)
        if row is None:
            return
        row["mean"] = row.pop("sum") / row["finite_count"] if row["finite_count"] else None
        row["complete_bin"] = (row["sample_id"] == row["bin_start_sample_id"] and
                               row["sample_id_end_exclusive"] == row["bin_end_sample_id_exclusive"])
        row["flush_reason"] = reason
        row["duration_s"] = (row["sample_id_end_exclusive"] - row["sample_id"]) / row["sample_rate_hz"]
        self.coverage[signal]["bins"] += 1
        self.emit(row)

    def process(self, topic, received, packet):
        suffix = next(k for k in TOPICS if topic == k or topic.endswith("/" + k))
        signal, units = TOPICS[suffix]
        samples = self.np.asarray(packet["data"])
        rate, dec = int(packet["sample_rate"]), int(packet["decimate_factor"])
        sid, utc = int(packet["sample_id"]), int(packet["utc"])
        if samples.ndim != 1 or rate != 2000000 or dec != 1:
            raise ValueError("Require one-dimensional native 2 MHz i/v samples, decimate_factor=1")
        span = rate * self.bin_ms // 1000
        c = self.coverage[signal]
        previous = c["end_sample_id_exclusive"]
        if previous is not None and sid != previous:
            self.flush(signal, "discontinuity")
            c["discontinuities"] += 1
            c["gap_native_samples"] += max(0, sid - previous)
            c["overlaps_or_resets"] += int(sid < previous)
            self.emit(dict(event="gap", signal=signal, expected_sample_id=previous,
                           received_sample_id=sid, difference_native_samples=sid-previous,
                           received=received))
        if c["first_sample_id"] is None:
            c["first_sample_id"] = sid
        c["chunks"] += 1
        c["samples"] += int(samples.size)
        c["end_sample_id_exclusive"] = sid + int(samples.size)
        c["sample_rate_hz"], c["decimate_factor"] = rate, dec
        offset = 0
        while offset < samples.size:
            at = sid + offset
            boundary = (at // span + 1) * span
            n = min(boundary-at, int(samples.size)-offset)
            part = samples[offset:offset+n]
            finite = part[self.np.isfinite(part)]
            row = self.pending.get(signal)
            if row is None:
                row = dict(event="bin", signal=signal, units=units,
                    bin_start_sample_id=boundary-span, bin_end_sample_id_exclusive=boundary,
                    sample_id=at, sample_id_end_exclusive=at, sample_rate_hz=rate,
                    count=0, finite_count=0, nonfinite_count=0, sum=0.0, min=None, max=None,
                    utc_time64=utc + ((offset << 30) // rate), first_chunk_received=received)
                self.pending[signal] = row
            row["sample_id_end_exclusive"] += n
            row["count"] += n
            row["finite_count"] += int(finite.size)
            row["nonfinite_count"] += n-int(finite.size)
            c["finite"] += int(finite.size)
            if finite.size:
                minimum, maximum = float(finite.min()), float(finite.max())
                row["min"] = minimum if row["min"] is None else min(row["min"], minimum)
                row["max"] = maximum if row["max"] is None else max(row["max"], maximum)
                row["sum"] += float(finite.sum(dtype=self.np.float64))
            offset += n
            if at+n == boundary:
                self.flush(signal, "boundary")

    def worker(self):
        while True:
            item = self.queue.get()
            if item is None:
                break
            if self.error is None:
                try:
                    self.process(*item)
                except Exception as exc:
                    self.error = self.error or repr(exc)
        for signal in TOPICS.values():
            try:
                self.flush(signal[0], "stream_stop")
            except Exception as exc:
                self.error = self.error or repr(exc)

    def ready(self):
        return all(c["chunks"] > 0 for c in self.coverage.values())

    def close(self):
        if not self.closed:
            self.closed = True
            self.queue.put(None)
            self.thread.join(timeout=10)
            if self.thread.is_alive():
                self.error = self.error or "Summary worker did not terminate"
        checks = dict(both_signals_received=self.ready(), no_queue_drop=self.dropped==0,
            no_logger_error=self.error is None,
            contiguous_received_ids=all(c["discontinuities"]==0 for c in self.coverage.values()),
            all_received_samples_finite=all(c["finite"]==c["samples"] for c in self.coverage.values()))
        return dict(checks=checks, passed=all(checks.values()), signals=self.coverage,
                    dropped_chunks=self.dropped, logger_error=self.error,
                    scope="received intervals only; unobserved start/end not covered; no clipping or energy qualification")


def run(args, driver_factory, version):
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.ready and args.ready.exists():
        raise FileExistsError("Refusing an existing ready marker")
    rc, logger, cleanup_errors = 0, None, []
    final = dict(event="stopped", **stamp(), ok=False, device_opened=False,
                 device_context_close_attempted=False, device_context_closed=False,
                 driver_context_closed=False)
    with args.output.open("x", encoding="utf-8", buffering=1) as output:
        logger = BinLogger(output, args.bin_ms)
        logger.emit(dict(event="start", **stamp(), schema=1, driver_version=version,
            device=args.device, bin_ms=args.bin_ms, duration_s=args.duration,
            native_hz=2000000, raw_samples_retained=False, power_or_gpio_control=False,
            voltage_location="JS110 IN+ relative to IN-", energy_claim=False,
            utc_time64_units="2**-30 seconds since 2018-01-01 UTC"))
        try:
            with driver_factory() as driver:
                if args.device not in driver.device_paths():
                    raise RuntimeError("Requested JS110 is absent; no retry")
                with driver.open(args.device, mode="restore", timeout=5.0) as device:
                    final["device_opened"] = True
                    initial, subscriptions = {}, []
                    try:
                        # Read every restorable setting before the first write.
                        initial = {k: device.query(k, timeout=5.0) for k in (RANGE, *CONTROLS)}
                        for topic in TOPICS:
                            full = args.device + "/" + topic
                            driver.subscribe(full, "pub", logger.callback)
                            subscriptions.append(full)
                        for topic, target in (("h/fs", 2000000), ("s/i/ctrl", 1), ("s/v/ctrl", 1)):
                            if initial[topic] != target:
                                device.publish(topic, target, timeout=5.0)
                            if device.query(topic, timeout=5.0) != target:
                                raise RuntimeError("Stream setting readback mismatch: " + topic)
                        began = time.monotonic()
                        deadline = began + args.duration
                        ready = False
                        while time.monotonic() < deadline:
                            if logger.error:
                                raise RuntimeError(logger.error)
                            if not ready and logger.ready():
                                record = dict(event="ready", **stamp(), initial_settings=initial,
                                              output=str(args.output), remaining_s=deadline-time.monotonic())
                                logger.emit(record)
                                if args.ready:
                                    args.ready.parent.mkdir(parents=True, exist_ok=True)
                                    with args.ready.open("x", encoding="utf-8") as f:
                                        json.dump(record, f, indent=2)
                                print(json.dumps(record), flush=True)
                                ready = True
                            if not ready and time.monotonic()-began > 5:
                                raise RuntimeError("Both i/v streams did not arrive within five seconds")
                            time.sleep(0.02)
                        if not ready:
                            raise RuntimeError("Duration ended before both streams arrived")
                    finally:
                        # Try every restoration even if earlier USB or file I/O failed.
                        for topic in subscriptions:
                            try:
                                driver.unsubscribe(topic, logger.callback, timeout=5.0)
                            except Exception as exc:
                                cleanup_errors.append(dict(stage="unsubscribe", topic=topic, error=repr(exc)))
                        for topic in ("s/i/ctrl", "s/v/ctrl", "h/fs", RANGE):
                            if topic not in initial:
                                continue
                            try:
                                # Range is not changed during acquisition. Restore only
                                # on mismatch, so no redundant power-control command.
                                if device.query(topic, timeout=5.0) != initial[topic]:
                                    device.publish(topic, initial[topic], timeout=5.0)
                                if device.query(topic, timeout=5.0) != initial[topic]:
                                    raise RuntimeError("Restoration readback mismatch")
                            except Exception as exc:
                                cleanup_errors.append(dict(stage="restore", topic=topic, error=repr(exc)))
                        final["initial_settings"] = initial
                        final["device_context_close_attempted"] = True
                final["device_context_closed"] = True
            final["driver_context_closed"] = True
        except KeyboardInterrupt:
            rc = 130
            final["error"] = "Interrupted"
        except Exception as exc:
            rc = 1
            final["error"] = repr(exc)
        finally:
            coverage = logger.close()
            if cleanup_errors or not coverage["passed"]:
                rc = rc or 1
            final.update(stamp(), ok=rc==0, cleanup_errors=cleanup_errors, coverage=coverage,
                         returncode=rc)
            logger.emit(final)
            print(json.dumps(final), flush=True)
    return rc


def self_test():
    import io
    import numpy as np
    out = io.StringIO()
    log = BinLogger(out, 1)
    for topic, level in (("s/i/!data", .01), ("s/v/!data", 5.0)):
        for start, size in ((100, 1000), (1100, 3000), (4100, 1900)):
            log.receive(topic, dict(sample_id=start, sample_rate=2000000, decimate_factor=1,
                utc=start*(1<<30)//2000000, data=np.full(size, level, dtype=np.float32)))
    status = log.close()
    assert status["passed"], status
    rows = [json.loads(x) for x in out.getvalue().splitlines()]
    bins = [x for x in rows if x["signal"]=="current"]
    assert [(x["sample_id"], x["sample_id_end_exclusive"]) for x in bins]==[(100,2000),(2000,4000),(4000,6000)]
    assert [x["complete_bin"] for x in bins]==[False,True,True]
    assert all(abs(x["mean"]-.01)<1e-8 for x in bins)
    out = io.StringIO()
    log = BinLogger(out, 1)
    for start in (0, 3000):
        log.receive("s/i/!data", dict(sample_id=start, sample_rate=2000000,
            decimate_factor=1, utc=0, data=np.array([.01, float("nan")], dtype=np.float32)))
    status = log.close()
    assert not status["passed"]
    assert status["signals"]["current"]["gap_native_samples"]==2998
    assert not status["checks"]["all_received_samples_finite"]
    print("Synthetic aggregation self-test passed; no instrument driver imported")
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path)
    p.add_argument("--ready", type=Path)
    p.add_argument("--duration", type=float, default=40.0)
    p.add_argument("--bin-ms", type=int, choices=range(1,6), default=5)
    p.add_argument("--device", default="u/js110/000163")
    p.add_argument("--deps", type=Path, default=ROOT/"tmp/bringup/joulescope-deps")
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()
    if args.self_test:
        return self_test()
    if args.output is None:
        p.error("--output is required")
    if not math.isfinite(args.duration) or not 0 < args.duration <= 60:
        p.error("--duration must be >0 and <=60 seconds")
    if not args.device.startswith("u/js110/"):
        p.error("Only JS110 is supported")
    if args.ready and args.ready.resolve()==args.output.resolve():
        p.error("Ready and output paths must differ")
    sys.path.insert(0, str(args.deps.resolve()))
    from pyjoulescope_driver import Driver, __version__
    return run(args, Driver, __version__)


if __name__=="__main__":
    raise SystemExit(main())
