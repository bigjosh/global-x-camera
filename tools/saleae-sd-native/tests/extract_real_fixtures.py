"""Extract bounded native-SD edge fixtures from an existing Saleae export.

Offline only: this module never connects to Logic, ST-LINK, or the DUT.  The
private source capture is not distributed.  Existing committed fixtures are
sufficient for regression tests; regeneration additionally needs that capture.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import struct
from pathlib import Path

import numpy as np


RATE = 250_000_000
CHANNELS = {"clk": 2, "cmd": 3, "d0": 7, "d1": 4, "d2": 5, "d3": 1}
WINDOWS = {
    # Ends after the first busy release and before the second block starts.
    "first-write": (0.422550000, 0.423062900),
    # Excludes the preceding last block's pattern payload.
    "final-stop": (0.639660000, 0.640800000),
}


def sha256(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def read_channel(path: Path) -> tuple[int, np.ndarray]:
    with path.open("rb") as source:
        header = source.read(44)
    magic, version, kind, initial, start, end, count = struct.unpack(
        "<8siiIddQ", header
    )
    if (magic, version, kind) != (b"<SALEAE>", 0, 0):
        raise ValueError(f"Unsupported Saleae binary header: {path.name}")
    if initial not in (0, 1) or path.stat().st_size != 44 + count * 8:
        raise ValueError(f"Invalid Saleae digital data: {path.name}")
    edges = np.memmap(path, dtype="<f8", offset=44, shape=(count,), mode="r")
    return initial, edges


def extract(binary_dir: Path, output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    sources = {}
    channels = {}
    for name, index in CHANNELS.items():
        path = binary_dir / f"digital_{index}.bin"
        channels[name] = read_channel(path)
        sources[path.name] = {"bytes": path.stat().st_size, "sha256": sha256(path)}

    manifest = {
        "schema": 1,
        "source_recording": "2026-10-25 phase01, pre-resistor NEGEDGE pattern write",
        "sample_rate_hz": RATE,
        "sample_time_origin": "Absolute source-capture time; seconds = sample / sample_rate_hz",
        "columns": ["sample", *CHANNELS],
        "channel_map": CHANNELS,
        "source_binary_files": sources,
        "sample_offset_ns": 0,
        "default_data_width": 4,
        "filtering": "None: every recorded transition in each selected interval is retained",
        "fixtures": {},
    }
    for name, (start_s, end_s) in WINDOWS.items():
        start = round(start_s * RATE)
        end = round(end_s * RATE)
        states = {}
        changes = {}
        transition_counts = {}
        for signal, (initial, edges) in channels.items():
            lo = int(np.searchsorted(edges, start / RATE, side="right"))
            hi = int(np.searchsorted(edges, end / RATE, side="right"))
            states[signal] = initial ^ (lo & 1)
            times = edges[lo:hi]
            ticks = np.rint(times * RATE).astype(np.int64)
            if np.any(np.abs(times * RATE - ticks) > 1e-5):
                raise ValueError("Source transitions do not match the recorded sample grid")
            if len(ticks) and (ticks[0] <= start or ticks[-1] > end):
                raise ValueError("Source timestamp boundary differs from rounded sample boundary")
            if len(ticks) > 1 and np.any(np.diff(ticks) <= 0):
                raise ValueError("Repeated/nonmonotonic transition on a source channel")
            for tick in ticks:
                changes.setdefault(int(tick), []).append(signal)
            transition_counts[signal] = len(ticks)

        text = io.StringIO(newline="")
        writer = csv.writer(text, lineterminator="\n")
        writer.writerow(["sample", *CHANNELS])
        writer.writerow([start, *(states[k] for k in CHANNELS)])
        for tick in sorted(changes):
            for signal in changes[tick]:
                states[signal] ^= 1
            writer.writerow([tick, *(states[k] for k in CHANNELS)])
        # The final unchanged snapshot preserves the exact clip end as well.
        if end not in changes:
            writer.writerow([end, *(states[k] for k in CHANNELS)])
        payload = text.getvalue().encode("ascii")
        path = output_dir / f"{name}.csv.gz"
        # An empty header filename and fixed mtime make regeneration byte-stable.
        with path.open("wb") as raw:
            with gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as zipped:
                zipped.write(payload)
        manifest["fixtures"][name] = {
            "path": path.name,
            "first_sample": start,
            "last_sample": end,
            "window_seconds": [start / RATE, end / RATE],
            "event_rows": len(changes) + 1 + (end not in changes),
            "transitions": transition_counts,
            "uncompressed_bytes": len(payload),
            "uncompressed_sha256": hashlib.sha256(payload).hexdigest(),
            "gzip_bytes": path.stat().st_size,
            "gzip_sha256": sha256(path),
        }

    manifest["expected"] = {
        "first-write": {
            "host_commands": [13, 55, 23, 25],
            "acmd23_blocks": 3730,
            "cmd25_lba": 14920,
            "complete_data_blocks": 1,
            "first_payload_sha256": "edaa20b916c05736099950fe1a98748051a712a2233738d79398c288dbcdf53a",
            "first_payload_prefix_hex": "47585232000000000000000000000000",
            "data_crc_received": [56679, 53491, 54883, 61273],
            "accepted_tokens": 1,
            "busy_edge_start_sample": 105704624,
            "busy_edge_end_sample": 105765650,
            "busy_edge_duration_samples": 61026,
            "busy_edge_duration_us": 244.104,
        },
        "final-stop": {
            "host_commands": [12, 13, 13],
            "r1_status_words": [3072, 3584, 2304],
            "busy_edge_start_sample": 159918394,
            "busy_edge_end_sample": 160132045,
            "busy_edge_duration_samples": 213651,
            "busy_edge_duration_us": 854.604,
            "cmd12_response_start_sample": 159918457,
            "busy_precedes_cmd12_response": True,
            "last_r1_current_state": "TRAN",
            "last_r1_ready_for_data": True,
        },
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary_dir", type=Path, help="Existing phase01/signals/binary export directory")
    parser.add_argument("--out", type=Path, default=Path(__file__).parent / "fixtures")
    args = parser.parse_args()
    manifest = extract(args.binary_dir, args.out)
    print(json.dumps(manifest["fixtures"], indent=2))


if __name__ == "__main__":
    main()
