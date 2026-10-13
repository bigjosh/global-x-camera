"""Reproduce NAND timing and conditional energy scenarios; not measured limits."""
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARTS = {
    "original": dict(part="MX30LF2G18AC-TI", voltage=3.3, spare_bytes=64,
                     cycle_ns=20, program_typ_us=300, program_max_us=600,
                     program_typ_ma=15, program_max_ma=30,
                     erase_typ_ms=1, erase_max_ms=3.5, read_max_us=25),
    "alliance": dict(part="AS9F14G08SA-45BIN", voltage=1.8, spare_bytes=128,
                     cycle_ns=45, program_typ_us=300, program_max_us=700,
                     program_typ_ma=None, program_max_ma=20,
                     erase_typ_ms=3.5, erase_max_ms=10, read_max_us=30),
}


def calculate(image_bytes, p):
    pages = math.ceil(image_bytes / 2048)
    blocks = math.ceil(pages / 64)
    transfer_ms = pages * (2048 + p["spare_bytes"]) * p["cycle_ns"] / 1e6
    busy_typ_ms = pages * p["program_typ_us"] / 1000
    busy_max_ms = pages * p["program_max_us"] / 1000
    return dict(
        image_bytes=image_bytes, pages=pages, blocks_if_aligned=blocks,
        full_spare_transfer_ms=transfer_ms,
        program_busy_typ_ms=busy_typ_ms, program_busy_max_ms=busy_max_ms,
        write_typ_program_fastest_bus_ms=transfer_ms + busy_typ_ms,
        write_max_program_fastest_bus_ms=transfer_ms + busy_max_ms,
        readback_max_array_fastest_bus_ms=transfer_ms + pages*p["read_max_us"]/1000,
        erase_aligned_typ_ms=blocks*p["erase_typ_ms"],
        erase_aligned_max_ms=blocks*p["erase_max_ms"],
        busy_typ_energy_mj=(None if p["program_typ_ma"] is None else
                            p["voltage"]*p["program_typ_ma"]*busy_typ_ms/1000),
        busy_max_current_max_time_nominal_voltage_mj=
            p["voltage"]*p["program_max_ma"]*busy_max_ms/1000,
        busy_max_current_typ_time_nominal_voltage_mj=
            p["voltage"]*p["program_max_ma"]*busy_typ_ms/1000,
    )


results = {fmt: {name: calculate(size, p) for name, p in PARTS.items()}
           for fmt, size in {"raw10": 486220, "container16": 777952}.items()}
old, new = results["raw10"]["original"], results["raw10"]["alliance"]
delta_ms = new["write_typ_program_fastest_bus_ms"]-old["write_typ_program_fastest_bus_ms"]
scenarios = []
for other_w in (0.05, 0.1, 0.2, 0.4):
    for alliance_ma in (10, 15, 20):
        old_busy = old["busy_typ_energy_mj"]
        new_busy = 1.8*alliance_ma*new["program_busy_typ_ms"]/1000
        scenarios.append(dict(other_board_power_w=other_w,
                              assumed_alliance_program_ma=alliance_ma,
                              additional_other_board_energy_mj=other_w*delta_ms,
                              old_busy_minus_new_busy_mj=old_busy-new_busy,
                              partial_board_energy_delta_mj=other_w*delta_ms+new_busy-old_busy))

report = dict(
    date="2026-09-07", parts=PARTS, results=results, scenarios=scenarios,
    assumptions=[
        "Sequential ordinary page programming; full data+spare transfer; no cache or two-plane overlap.",
        "Each part at fastest permitted bus cycle, not verified FMC throughput.",
        "Readback rows use maximum array latency and fastest bus; not whole-operation maxima.",
        "Erase counts assume block-aligned image allocation, no metadata or bad-block retries.",
        "Nominal rail voltage; maximum products are specification-based models, not battery bounds.",
        "Alliance typical normal-program current is unspecified; 10/15/20mA are sensitivity inputs.",
        "Energy scenarios omit NAND loading, I/O/pullups, ECC, metadata, verify, erase, boot and shutdown.",
        "Other-board power is a common illustrative average, not measured save-state consumption.",
    ],
)
target = ROOT / "docs/power/nand-energy-calculations.json"
target.write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
print(json.dumps({"output": str(target), "raw10": results["raw10"],
                  "raw10_additional_bus_ms": delta_ms}, indent=2))
