"""Reproduce illustrative cold-cycle microSD sensitivity; not card predictions."""
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSUMPTIONS = {
    "image_bytes": 486220,
    "sector_bytes": 512,
    "capture_complete_ms": 50.0,
    "sd_power_on_ms": 0.0,
    "effective_payload_rate_mb_per_s": 20.0,
    "sd_voltage_v": 3.3,
    "sd_idle_current_ma": 2.0,
    "other_board_power_w": 0.2,
    "common_converter_efficiency": 0.85,
}
SCENARIOS = [
    {"name": "short_ready", "sd_ready_ms": 20.0, "tail_ms": 10.0},
    {"name": "intermediate_ready", "sd_ready_ms": 100.0, "tail_ms": 25.0},
    {"name": "long_ready", "sd_ready_ms": 1000.0, "tail_ms": 250.0},
]
NAND_WRITE_MS = 94.70496
NAND_BUSY_ENERGY_MJ = 2.5704


def energy_mj(voltage_v, current_ma, duration_ms):
    return voltage_v * current_ma * duration_ms / 1000.0


def calculate(scenario, current_ma, nand_partial_mj):
    a = ASSUMPTIONS
    sectors = math.ceil(a["image_bytes"] / a["sector_bytes"])
    padded_bytes = sectors * a["sector_bytes"]
    payload_ms = padded_bytes / (a["effective_payload_rate_mb_per_s"] * 1000.0)
    write_start_ms = max(a["capture_complete_ms"], scenario["sd_ready_ms"])
    init_ms = scenario["sd_ready_ms"] - a["sd_power_on_ms"]
    idle_ms = write_start_ms - scenario["sd_ready_ms"]
    cycle_ms = write_start_ms + payload_ms + scenario["tail_ms"]
    after_capture_ms = cycle_ms - a["capture_complete_ms"]
    voltage = a["sd_voltage_v"]
    init_mj = energy_mj(voltage, current_ma, init_ms)
    idle_mj = energy_mj(voltage, a["sd_idle_current_ma"], idle_ms)
    payload_mj = energy_mj(voltage, current_ma, payload_ms)
    tail_mj = energy_mj(voltage, current_ma, scenario["tail_ms"])
    card_mj = init_mj + idle_mj + payload_mj + tail_mj
    other_mj = a["other_board_power_w"] * after_capture_ms
    partial_mj = card_mj + other_mj
    efficiency = a["common_converter_efficiency"]
    assert math.isclose(init_ms + idle_ms + payload_ms + scenario["tail_ms"], cycle_ms)
    assert math.isclose(card_mj, sum((init_mj, idle_mj, payload_mj, tail_mj)))
    return {
        **scenario,
        "assumed_sd_init_write_tail_current_ma": current_ma,
        "sectors": sectors,
        "padded_image_bytes": padded_bytes,
        "payload_ms": payload_ms,
        "initialization_ms": init_ms,
        "idle_waiting_for_capture_ms": idle_ms,
        "write_start_ms": write_start_ms,
        "modeled_cycle_ms": cycle_ms,
        "additional_time_after_capture_ms": after_capture_ms,
        "cycle_delta_vs_nand_ms": cycle_ms - (a["capture_complete_ms"] + NAND_WRITE_MS),
        "card_initialization_energy_mj": init_mj,
        "card_idle_energy_mj": idle_mj,
        "card_payload_energy_mj": payload_mj,
        "card_tail_energy_mj": tail_mj,
        "card_total_energy_mj": card_mj,
        "additional_other_board_energy_after_capture_mj": other_mj,
        "partial_storage_related_load_energy_mj": partial_mj,
        "partial_storage_related_battery_energy_mj": partial_mj / efficiency,
        "partial_load_energy_delta_vs_nand_mj": partial_mj - nand_partial_mj,
        "partial_battery_energy_delta_vs_nand_mj": (partial_mj - nand_partial_mj) / efficiency,
    }


def main():
    a = ASSUMPTIONS
    nand_other_mj = a["other_board_power_w"] * NAND_WRITE_MS
    nand_partial_mj = nand_other_mj + NAND_BUSY_ENERGY_MJ
    assert math.isclose(nand_partial_mj, 21.511392)
    results = [calculate(scenario, current, nand_partial_mj)
               for current in (50.0, 100.0) for scenario in SCENARIOS]
    assert all(row["sectors"] == 950 and row["padded_image_bytes"] == 486400
               and math.isclose(row["payload_ms"], 24.32) for row in results)
    assumed_peak_load_w = a["sd_voltage_v"] * 0.1 + a["other_board_power_w"]
    report = {
        "date": "2026-09-08",
        "status": "All SD scenarios are assumptions for sensitivity, not measured or guaranteed card predictions.",
        "assumptions": a,
        "nand_partial_reference": {
            "part": "AS9F14G08SA-45BIN",
            "source": "docs/power/nand-energy-impact.md and tools/calculate_nand_tradeoff.py",
            "write_ms": NAND_WRITE_MS,
            "modeled_cycle_ms": a["capture_complete_ms"] + NAND_WRITE_MS,
            "program_busy_energy_mj_max_current_typical_duration": NAND_BUSY_ENERGY_MJ,
            "other_board_energy_mj": nand_other_mj,
            "partial_storage_related_load_energy_mj": nand_partial_mj,
            "partial_storage_related_battery_energy_mj": nand_partial_mj / a["common_converter_efficiency"],
        },
        "scenarios": results,
        "assumed_peak_load_example": {
            "sd_current_ma": 100.0,
            "sd_voltage_v": a["sd_voltage_v"],
            "other_board_power_w": a["other_board_power_w"],
            "load_power_w": assumed_peak_load_w,
            "converter_efficiency": a["common_converter_efficiency"],
            "battery_stack_current_ma": {
                str(voltage): assumed_peak_load_w / (voltage * a["common_converter_efficiency"]) * 1000
                for voltage in (12.0, 8.0)
            },
            "qualification": "Assumed load example, not a specified or measured peak. Each series cell carries the stack current.",
        },
        "limitations": [
            "The 20/100/1000 ms ready times and 10/25/250 ms tails are scenario inputs, not typical or worst-case whole-operation limits.",
            "SD is ideally powered at t=0 together with the camera; real MCU boot and driver initiation can delay the first ACMD41 and readiness.",
            "The 50 ms capture completion and 20 MB/s effective payload rate are assumptions; all camera startup and capture timing remain to be measured.",
            "Effective payload rate covers the modeled payload phase; tail represents additional final busy/commit. Do not double-count busy already included in measured throughput.",
            "50 mA and 100 mA are assumed equal initialization/write/tail currents, and 2 mA is assumed idle current. These are not Kingston or other card datasheet claims.",
            "SD initialization energy before capture completion is included; other-board energy already spent capturing is not counted again.",
            "Reported energy is incremental storage-related energy above the common capture load, not complete camera-cycle or battery-life energy.",
            "The NAND reference omits NAND transfer and standby energy, I/O, ECC, metadata, verification, erase, boot and shutdown; its busy-energy model combines maximum current and typical duration.",
            "Both alternatives omit unmodeled software, filesystem, shutdown and regulator-startup costs; measured commit policy can add further time and energy.",
            "85 percent common converter efficiency is an assumption; real rail efficiencies and quiescent currents can differ.",
            "The load example excludes simultaneous camera loads not captured in the 200 mW assumption; real inrush and card peaks require separate measurements.",
        ],
    }
    target = ROOT / "docs/power/microsd-calculations.json"
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(target), "nand_partial_reference": report["nand_partial_reference"],
                      "scenarios": results, "assumed_peak_load_example": report["assumed_peak_load_example"]}, indent=2))


if __name__ == "__main__":
    main()
