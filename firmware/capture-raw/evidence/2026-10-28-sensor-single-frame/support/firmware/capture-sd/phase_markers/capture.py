"""API-only, bounded phase capture; no target stimulus or firmware writes.

Physical map: CH1=PD12/CN15.21, CH4=target5V/CN3.18,
CH0=NRST/CN3.14, CH6=PE6/CN15.2, GND=CN3.19.
Uses the existing Logic 2 server; never launches or stops that application.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
DEVICE = "6753424D9C96677D"
CHANNELS = [0, 1, 4, 6]
MAP = {"0":"NRST / CN3.14", "1":"PD12 / CN15.21 / Arduino D8",
       "4":"target 5 V / CN3.18", "6":"PE6 / CN15.2 / ST-LINK TX"}


def stamp():
    return dict(utc=datetime.now(timezone.utc).isoformat(), monotonic_ns=time.monotonic_ns())


def capture(output, *, probes_confirmed, seconds=10.0, analog_power=False, api=None):
    if probes_confirmed is not True:
        raise ValueError("Confirm the exact physical probe map before recording")
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not 1 <= seconds <= 10:
        raise ValueError("Capture duration must be 1..10 seconds")
    if type(analog_power) is not bool:
        raise ValueError("analog_power must be a boolean")
    if api is None:
        sys.path.insert(0, str(ROOT / "tmp/bringup/saleae-deps"))
        from saleae import automation as api
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    binary = output / "binary"
    binary.mkdir()
    meta = dict(schema=1, requested=stamp(), device_id=DEVICE, channel_map=MAP,
                ground="CN3.19", enabled_digital_channels=CHANNELS,
                digital_sample_rate=100000000, digital_threshold_family_volts=3.3,
                enabled_analog_channels=[4] if analog_power else [],
                analog_sample_rate=31250 if analog_power else None,
                duration_seconds=seconds, buffer_size_megabytes=256,
                target_stimulus="none", qualification="requested; capture not completed")

    def save_meta():
        (output / "capture-config.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    save_meta()
    try:
        with api.Manager.connect(port=10430, connect_timeout_seconds=5) as manager:
            if not any(d.device_id == DEVICE and not d.is_simulation for d in manager.get_devices()):
                raise RuntimeError("Required physical Logic Pro 8 was not found")
            meta["app_info"] = str(manager.get_app_info())
            dc = api.LogicDeviceConfiguration(enabled_digital_channels=CHANNELS,
                 digital_sample_rate=100000000, digital_threshold_volts=3.3,
                 enabled_analog_channels=[4] if analog_power else [],
                 analog_sample_rate=31250 if analog_power else None)
            cc = api.CaptureConfiguration(buffer_size_megabytes=256,
                 capture_mode=api.TimedCaptureMode(duration_seconds=seconds))
            with manager.start_capture(device_id=DEVICE, device_configuration=dc,
                                       capture_configuration=cc) as cap:
                meta["started"] = stamp()
                save_meta()
                (output / "started").write_text("Recording phase probes; no target stimulus issued.\n")
                print("CAPTURE_STARTED", str(output), flush=True)
                cap.wait()  # Timed mode: do not also call stop().
                meta["completed"] = stamp()
                cap.save_capture(str(output / "phase.sal"))
                meta["sal_saved"] = stamp()
                save_meta()
                cap.export_raw_data_binary(str(binary), digital_channels=CHANNELS,
                                          analog_channels=[4] if analog_power else [])
                meta["binary_exported"] = stamp()
                expected = [binary / f"digital_{ch}.bin" for ch in CHANNELS]
                if analog_power:
                    expected.append(binary / "analog_4.bin")
                if any(not p.is_file() for p in expected):
                    raise RuntimeError("Export returned without all requested channel files")
                meta["qualification"] = "recorded and exported; phase decoding and electrical state unqualified"
    except Exception as exc:
        meta["error"] = dict(type=type(exc).__name__, text=str(exc), **stamp())
        raise
    finally:
        save_meta()
    print("CAPTURE_SAVED", str(output), flush=True)
    return meta


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("output", type=Path)
    ap.add_argument("--seconds", type=float, default=10.0)
    ap.add_argument("--probes-confirmed", action="store_true")
    ap.add_argument("--analog-power", action="store_true",
                    help="Also request CH4 at31250 analog samples/s; no automatic rate fallback.")
    args = ap.parse_args()
    capture(args.output, probes_confirmed=args.probes_confirmed,
            seconds=args.seconds, analog_power=args.analog_power)
