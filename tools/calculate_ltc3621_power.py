"""Reproducible screening calculations for power.md; not a circuit simulation.

Specified values retain their test conditions in power.md. Efficiency and
capacitor insulation resistance are assumptions, not manufacturer guarantees.
"""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
R_START = 330_000.0
R_OFF = R_GPIO = 100_000.0
V_OUT = 3.3
I_OUT = 0.250
L = 6.8e-6
F = 1e6


def parallel(a, b):
    return a * b / (a + b)


def divider(vbat, rstart=R_START, roff=R_OFF, run_sink_a=0.0):
    return vbat * roff / (rstart + roff) - run_sink_a * parallel(rstart, roff)


button_rows = []
for v in (8.0, 13.0, 13.2):
    current = v / (R_START + R_OFF)
    button_rows.append({
        "v_battery_v": v,
        "v_run_v": divider(v),
        "button_current_ua": current * 1e6,
        "r_start_power_mw": current**2 * R_START * 1e3,
        "r_off_power_mw": current**2 * R_OFF * 1e3,
    })

pout = V_OUT * I_OUT
efficiency_rows = []
for eff in (0.85, 0.90, 0.95):
    pin = pout / eff
    efficiency_rows.append({
        "efficiency_assumption": eff, "output_power_w": pout,
        "input_power_w": pin, "battery_current_at_13v_ma": pin / 13 * 1e3,
        "converter_loss_mw": (pin - pout) * 1e3,
    })

switch_insulation_ohm = 1e9
cin_insulation_assumption_ohm = 100e6
switch_leak = 13 / (switch_insulation_ohm + R_START + R_OFF)
cin_leak = 13 / cin_insulation_assumption_ohm
duty = V_OUT / 13
ripple = V_OUT * (1 - duty) / (L * F)
result = {
    "status": "Screening arithmetic only; no guaranteed assembled OFF-current bound",
    "date": "2026-09-07",
    "assumptions": {
        "output_voltage_v": V_OUT, "output_current_a": I_OUT,
        "inductance_h": L, "frequency_hz": F,
        "r_start_ohm": R_START, "r_off_ohm": R_OFF, "r_gpio_ohm": R_GPIO,
        "capacitor_insulation_ohm_ASSUMED": cin_insulation_assumption_ohm,
        "regulator_shutdown_reference": "0.1 uA typical / 1 uA max, VIN=12 V RUN=0 TJ=25 C; not a 13 V or full-temperature guarantee",
    },
    "button": button_rows,
    "run_screening_corners": {
        "low_at_8v_1pct_20na_sink_v": divider(8, R_START * 1.01, R_OFF * 0.99, 20e-9),
        "high_at_13p2v_1pct_20na_source_v": divider(13.2, R_START * 0.99, R_OFF * 1.01, -20e-9),
        "hold_screening_25c_v": 3.267 - 0.4 - 0.9,
        "hold_margin_above_1v_v": 3.267 - 0.4 - 0.9 - 1.0,
        "gpio_reverse_leak_voltage_5na_v": 5e-9 * R_GPIO,
        "gpio_reverse_leak_voltage_80na_v": 80e-9 * R_GPIO,
        "run_shift_80na_leak_v": 80e-9 * parallel(R_START, R_OFF),
    },
    "off_illustration_at_13v": {
        "warning": "12 V regulator data borrowed as references; CIN resistance assumed; unallocated paths excluded",
        "switch_insulation_ua": switch_leak * 1e6,
        "cin_assumed_leakage_ua": cin_leak * 1e6,
        "typical_reference_subtotal_ua": 0.1 + (switch_leak + cin_leak) * 1e6,
        "max_reference_subtotal_ua": 1.0 + (switch_leak + cin_leak) * 1e6,
        "run_voltage_from_switch_insulation_v": switch_leak * R_OFF,
        "mah_per_year_at_1ua": 1e-3 * 24 * 365,
    },
    "efficiency_scenarios": efficiency_rows,
    "battery_current_at_90pct_ma": {str(v): pout / 0.9 / v * 1e3 for v in (8.0, 13.0, 13.2)},
    "ideal_ccm_screening": {
        "duty": duty, "inductor_ripple_a_pp": ripple,
        "inductor_peak_a": I_OUT + ripple / 2,
        "old_210uf_bank_linear_charge_current_a": 210e-6 * V_OUT / 0.8e-3,
        "old_bank_plus_250ma_load_a": 210e-6 * V_OUT / 0.8e-3 + I_OUT,
    },
}
out = ROOT / "docs/power/ltc3621-calculations.json"
out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result, indent=2))
