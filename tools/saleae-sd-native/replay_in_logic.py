#!/usr/bin/env python3
"""Add the native SD analyzer to a saved Logic recording; never start acquisition."""

import argparse
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path, help="Existing .sal recording")
    parser.add_argument("output", type=Path, help="New/empty directory for the annotated recording and CSVs")
    parser.add_argument("--port", type=int, default=10430)
    parser.add_argument("--width", choices=("auto", "1", "4"), default="auto")
    parser.add_argument("--data-only", choices=("read", "write"))
    parser.add_argument("--falling", action="store_true")
    parser.add_argument("--offset", type=int, default=0, help="Sampling offset in acquisition samples")
    parser.add_argument("--close", action="store_true", help="Close only the recording opened by this script")
    for name, channel in (("clk", 2), ("cmd", 3), ("dat0", 7), ("dat1", 4), ("dat2", 5), ("dat3", 1)):
        parser.add_argument("--" + name, type=int, default=channel)
    args = parser.parse_args()
    if not args.capture.is_file():
        parser.error("capture does not exist")
    if args.data_only and args.width == "auto":
        parser.error("data-only replay requires --width 1 or --width 4")
    if args.output.exists() and any(args.output.iterdir()):
        parser.error("output directory must be empty; existing reports are never overwritten")
    if not 0 <= args.offset <= 1000:
        parser.error("offset must be between 0 and 1000 acquisition samples")
    # This project already has the Saleae Python client here. A normal installed
    # logic2-automation package is equally supported; no runtime installation.
    dependencies = Path(__file__).resolve().parents[2] / "tmp/bringup/saleae-deps"
    if dependencies.is_dir():
        sys.path.insert(0, str(dependencies))
    from saleae import automation

    args.output.mkdir(parents=True, exist_ok=True)
    destination = args.output.resolve()
    settings = {
        "CLK": args.clk, "CMD": args.cmd, "DAT0": args.dat0,
        "DAT1": args.dat1, "DAT2": args.dat2, "DAT3": args.dat3,
        "Bus width": {"auto": "Auto (start 1-bit)", "1": "1-bit", "4": "4-bit"}[args.width],
        "Clock edge": "Falling" if args.falling else "Rising",
        "Sample offset": args.offset,
        "Initial block bytes": 512,
        "Data-only mode": {None: "Off (decode CMD)", "read": "Read blocks (CMD missing)",
                           "write": "Write blocks (CMD missing)"}[args.data_only],
        "Capture mode": "Complete capture",
    }
    with automation.Manager.connect(port=args.port) as manager:
        capture = manager.load_capture(str(args.capture.resolve()))
        completed = False
        try:
            handles = []
            for view in (("Data and busy",) if args.data_only else ("Commands", "Data and busy")):
                handle = capture.add_analyzer("Global X Native SD", label="SD " + view,
                                              settings={**settings, "Waveform view": view})
                handles.append(handle)
            # The legacy exporter preserves real, overlapping intervals and
            # transfer summaries. One instance already has all decoded events.
            capture.legacy_export_analyzer(str(destination / "sd-all-events.csv"),
                                           handles[0], automation.RadixType.HEXADECIMAL)
            capture.export_data_table(str(destination / "sd-table.csv"), analyzers=handles)
            capture.save_capture(str(destination / "sd-analyzed.sal"))
            completed = True
        finally:
            if args.close or not completed:
                capture.close()
    print(f"Saved SD analyzer results to {destination}")


if __name__ == "__main__":
    main()
