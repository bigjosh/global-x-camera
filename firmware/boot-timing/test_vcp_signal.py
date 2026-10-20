"""Observe ST-LINK VCP TX and NRST through Saleae, without target-memory writes.

Requires exclusive bench ownership and confirmed probe wiring:
CH6 -> CN15.2 (PE6), CH0 -> CN3.14 (NRST), ground -> CN5.6.
BREAK may reset some ST-LINK-connected targets. Do not use during a storage
operation. This tests electrical behavior, not a firmware recovery detector.
Uses the existing Logic automation backend. Never switches target power.
"""
import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
SERIAL = "002100203335511035383531"
SALEAE = "6753424D9C96677D"


def summarize(folder):
    with (folder / "analog.csv").open(newline="") as stream:
        reader = csv.DictReader(stream)
        fields = [x for x in reader.fieldnames if x != "Time [s]"]
        counts = {x: 0 for x in fields}
        totals = {x: 0.0 for x in fields}
        lows = {x: float("inf") for x in fields}
        highs = {x: -float("inf") for x in fields}
        for row in reader:
            for key in fields:
                value = float(row[key])
                counts[key] += 1
                totals[key] += value
                lows[key] = min(lows[key], value)
                highs[key] = max(highs[key], value)
    analog = {key: dict(min=lows[key], max=highs[key],
                        avg=totals[key] / counts[key], samples=counts[key])
              for key in fields if counts[key]}
    with (folder / "digital.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    digital = {}
    for key in ("Channel 0", "Channel 6"):
        intervals = []
        if rows:
            start = float(rows[0]["Time [s]"])
            state = int(rows[0][key])
            for row in rows[1:]:
                end, new = float(row["Time [s]"]), int(row[key])
                if new != state:
                    intervals.append(dict(start_s=start, end_s=end, level=state))
                    start, state = end, new
            intervals.append(dict(start_s=start,
                                  end_s=float(rows[-1]["Time [s]"]), level=state))
        digital[key] = intervals
    result = dict(analog=analog, digital_intervals=digital,
                  limitations=["No firmware detector or cold-boot test.",
                               "Host stimulus times are not hardware timestamps.",
                               "UART BREAK API success does not prove a LOW level."])
    (folder / "signal-summary.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--mode", choices=("passive", "open", "break", "bytes", "reset-bytes"),
                        default="passive")
    parser.add_argument("--probes-confirmed", action="store_true")
    parser.add_argument("--baud", type=int, choices=(115200, 1000000), default=115200)
    args = parser.parse_args()
    if not args.probes_confirmed:
        parser.error("Confirm the stated physical probe map before running.")
    if args.mode == "reset-bytes" and args.baud != 115200:
        parser.error("reset-bytes timing is defined for the 115200-baud burst only.")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    sys.path[:0] = [str(ROOT / "tmp/bringup/saleae-deps"),
                    str(ROOT / "tmp/bringup/vcp-deps")]
    from saleae import automation
    import serial
    from serial.tools import list_ports
    ports = [p for p in list_ports.comports()
             if p.vid == 0x0483 and p.pid == 0x3754 and p.serial_number == SERIAL]
    if args.mode != "passive" and len(ports) != 1:
        raise RuntimeError("Expected exactly one matching ST-LINK VCP.")
    events = []

    def event(name, **data):
        item = dict(name=name, utc=datetime.now(timezone.utc).isoformat(),
                    monotonic_ns=time.monotonic_ns(), **data)
        events.append(item)
        (output / "events.json").write_text(json.dumps(events, indent=2) + "\n")
        print(json.dumps(item), flush=True)

    with automation.Manager.connect(port=10430, connect_timeout_seconds=5) as manager:
        if not any(d.device_id == SALEAE and not d.is_simulation
                   for d in manager.get_devices()):
            raise RuntimeError("Expected physical Saleae not found.")
        config = dict(mode=args.mode, baud=args.baud, stlink_serial=SERIAL,
                      saleae=SALEAE, channel_map={"0": "NRST", "6": "PE6 / VCP TX"},
                      digital_sample_rate=6250000, analog_sample_rate=31250,
                      digital_threshold_family_volts=3.3,
                      app_info=str(manager.get_app_info()))
        (output / "config.json").write_text(json.dumps(config, indent=2) + "\n")
        device_config = automation.LogicDeviceConfiguration(
            enabled_digital_channels=[0, 6], digital_sample_rate=6250000,
            digital_threshold_volts=3.3, enabled_analog_channels=[0, 6],
            analog_sample_rate=31250)
        capture_config = automation.CaptureConfiguration(
            capture_mode=automation.ManualCaptureMode())
        with manager.start_capture(device_id=SALEAE, device_configuration=device_config,
                                   capture_configuration=capture_config) as capture:
            uart = None
            try:
                event("capture_started")
                time.sleep(.3)
                if args.mode == "passive":
                    time.sleep(.7)
                else:
                    uart = serial.Serial()
                    uart.port, uart.baudrate = ports[0].device, args.baud
                    uart.timeout, uart.write_timeout = .5, 2
                    uart.rts, uart.dtr = False, False
                    uart.open()
                    event("uart_opened", port=uart.port, settings=uart.get_settings())
                    time.sleep(.3)
                    if args.mode == "open":
                        time.sleep(.75)
                    elif args.mode == "break":
                        uart.break_condition = True
                        event("break_api_asserted")
                        time.sleep(.75)
                        uart.break_condition = False
                        event("break_api_released")
                    elif args.mode == "reset-bytes":
                        payload = bytes(4096)
                        result = {}

                        def writer():
                            try:
                                result["count"] = uart.write(payload)
                            except Exception as exc:
                                result["error"] = repr(exc)

                        thread = threading.Thread(target=writer, daemon=True)
                        event("write_begin", bytes=len(payload))
                        thread.start()
                        try:
                            time.sleep(.05)
                            uart.break_condition = True
                            event("break_api_asserted")
                            time.sleep(.1)
                            uart.break_condition = False
                            event("break_api_released")
                            thread.join(timeout=3)
                            if thread.is_alive():
                                raise TimeoutError("Concurrent serial write did not finish.")
                            if result.get("count") != len(payload):
                                raise RuntimeError(f"Concurrent write failed: {result}")
                            time.sleep(len(payload) * 10 / args.baud + .1)
                            event("write_completed", **result)
                        finally:
                            if thread.is_alive():
                                uart.cancel_write()
                                thread.join(timeout=2)
                    else:
                        # A bounded payload; do not depend on host scheduling per byte.
                        payload = bytes(4096)
                        event("write_begin", bytes=len(payload))
                        count = uart.write(payload)
                        if count != len(payload):
                            raise RuntimeError("Incomplete serial write.")
                        # Wait a bounded time instead of an unbounded flush call.
                        deadline = time.monotonic() + 2
                        while uart.out_waiting and time.monotonic() < deadline:
                            time.sleep(.01)
                        if uart.out_waiting:
                            raise TimeoutError("VCP transmit queue did not drain.")
                        time.sleep(len(payload) * 10 / args.baud + .1)
                        event("write_queue_drained", bytes=count)
                    time.sleep(.4)
            finally:
                try:
                    if uart is not None and uart.is_open:
                        try:
                            uart.break_condition = False
                            uart.reset_output_buffer()
                        finally:
                            uart.close()
                            event("uart_closed")
                finally:
                    capture.stop()
                    capture.save_capture(str(output / "signal.sal"))
                    capture.export_raw_data_csv(str(output), digital_channels=[0, 6],
                                                analog_channels=[0, 6])
                    event("capture_saved")
    result = summarize(output)
    print(json.dumps(dict(analog=result["analog"],
                          interval_counts={k: len(v) for k, v in
                                           result["digital_intervals"].items()})), flush=True)


if __name__ == "__main__":
    main()
