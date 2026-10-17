#!/usr/bin/env python3
"""Offline equivalent of the pinned Nucleo BSP's first I2C_GetTiming call.

Derived from STMicroelectronics stm32n6xx_nucleo_bus.c, copyright 2024,
in the local X-CUBE-N6 camera capture checkout. This reproduces that source's
integer-nanosecond rounding, loop ordering, first-per-prescaler candidate,
strict comparisons, analog filter enabled and DNF=0. It is not a new electrical
timing optimizer. Actual pullups, rise/fall times and bus frequency need checking
on the board. Each call starts with an empty candidate table, like a cold boot.

Usage: python i2c_timing.py --clock 150000000 --verify-baseline
"""

import argparse
import hashlib
import json
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2] / (
    "tmp/bringup/x-cube-n6-camera-capture/STM32Cube_FW_N6/Drivers/BSP/"
    "STM32N6xx_Nucleo/stm32n6xx_nucleo_bus.c"
)
# freq, freq_min, freq_max, hddat_min, vddat_max, sudat_min,
# lscl_min, hscl_min, trise, tfall, dnf: identical to the pinned BSP.
PROFILES = (
    (100000, 80000, 120000, 0, 3450, 250, 4700, 4000, 640, 20, 0),
    (400000, 320000, 480000, 0, 900, 100, 1300, 600, 250, 100, 0),
    (1000000, 800000, 1200000, 0, 450, 50, 500, 260, 60, 100, 0),
)


def calculate(clock: int, requested_hz: int) -> dict:
    if clock <= 0:
        raise ValueError("source clock must be positive")
    profile = next((p for p in PROFILES if p[1] <= requested_hz <= p[2]), None)
    if profile is None:
        raise ValueError("frequency is outside the BSP's supported bands")
    (freq, freq_min, freq_max, hddat_min, vddat_max, sudat_min,
     lscl_min, hscl_min, trise, tfall, dnf) = profile
    tick = (1000000000 + clock // 2) // clock
    target = (1000000000 + freq // 2) // freq
    sdamin = max(0, tfall + hddat_min - 50 - (dnf + 3) * tick)
    sdamax = max(0, vddat_max - trise - 260 - (dnf + 4) * tick)
    sclmin = trise + sudat_min
    candidates = []
    previous_presc = 16
    for presc in range(16):
        for scldel in range(16):
            if (scldel + 1) * (presc + 1) * tick >= sclmin:
                for sdadel in range(16):
                    if sdamin <= sdadel * (presc + 1) * tick <= sdamax:
                        if presc != previous_presc:
                            candidates.append((presc, scldel, sdadel))
                            previous_presc = presc

    best = None
    best_error = target
    for presc, scldel, sdadel in candidates:
        tpresc = (presc + 1) * tick
        for scll in range(256):
            low = 50 + dnf * tick + 2 * tick + (scll + 1) * tpresc
            if low > lscl_min and tick < (low - 50 - dnf * tick) // 4:
                for sclh in range(256):
                    high = 50 + dnf * tick + 2 * tick + (sclh + 1) * tpresc
                    period = low + high + trise + tfall
                    if (1000000000 // freq_max <= period <= 1000000000 // freq_min
                            and high >= hscl_min and tick < high):
                        error = abs(period - target)
                        if error < best_error:
                            best_error = error
                            best = (presc, scldel, sdadel, sclh, scll, period)
    if best is None:
        raise ValueError("no valid timing found by the pinned BSP algorithm")
    presc, scldel, sdadel, sclh, scll, period = best
    timing = presc << 28 | scldel << 20 | sdadel << 16 | sclh << 8 | scll
    # This second model only removes BSP's source-clock rounding. It retains
    # the assumed analog-filter delay and rise/fall times; it is not a measured Hz.
    exact_period = (100 + (2 * dnf + 4 + (scll + sclh + 2) * (presc + 1))
                    * 1000000000 / clock + trise + tfall)
    return {
        "clock_hz": clock, "requested_hz": requested_hz, "profile_hz": freq,
        "timingr": f"0x{timing:08X}", "presc": presc, "scldel": scldel,
        "sdadel": sdadel, "sclh": sclh, "scll": scll,
        "bsp_rounded_clock_period_ns": tick, "bsp_period_ns": period,
        "bsp_error_ns": best_error, "candidate_prescalers": len(candidates),
        "exact_clock_model_period_ns": round(exact_period, 6),
        "exact_clock_model_hz": round(1000000000 / exact_period, 3),
        "assumed_rise_ns": trise, "assumed_fall_ns": tfall,
        "analog_filter_enabled": True, "digital_filter_coefficient": dnf,
    }


def evaluate(clock: int, timing: int, frequency: int, source_tolerance: float = 0.02) -> dict:
    """Evaluate fields with exact source periods at nominal and fast-clock limits.

    The zero-edge model deliberately excludes rise/fall delay when computing
    maximum SCL frequency. Shorter real edges can make the bus faster than the
    BSP's assumed 60 ns/100 ns Fast-mode Plus edges. This is still conditional
    on analog filter minimum 50 ns and the requested source-frequency bound.
    """
    profile = next(p for p in PROFILES if p[1] <= frequency <= p[2])
    (_, _, _, hddat_min, vddat_max, sudat_min,
     lscl_min, hscl_min, trise, tfall, dnf) = profile
    presc, scldel, sdadel = (timing >> 28) & 15, (timing >> 20) & 15, (timing >> 16) & 15
    sclh, scll = (timing >> 8) & 255, timing & 255
    cases = []
    for factor in (1.0, 1.0 + source_tolerance):
        tick = 1000000000 / (clock * factor)
        tpresc = (presc + 1) * tick
        low = 50 + (dnf + 2) * tick + (scll + 1) * tpresc
        high = 50 + (dnf + 2) * tick + (sclh + 1) * tpresc
        setup = (scldel + 1) * tpresc
        hold = sdadel * tpresc
        hold_min = max(0, tfall + hddat_min - 50 - (dnf + 3) * tick)
        hold_max = max(0, vddat_max - trise - 260 - (dnf + 4) * tick)
        cases.append({
            "source_factor": factor, "setup_ns": round(setup, 6),
            "setup_min_ns": trise + sudat_min, "sdadel_ns": round(hold, 6),
            "sdadel_min_ns": round(hold_min, 6), "sdadel_max_ns": round(hold_max, 6),
            "low_ns": round(low, 6), "low_min_ns": lscl_min,
            "high_ns": round(high, 6), "high_min_ns": hscl_min,
            "passes_bsp_timing_constraints": (setup >= trise + sudat_min and
                hold_min <= hold <= hold_max and low > lscl_min and high >= hscl_min),
            "assumed_edge_period_ns": round(low + high + trise + tfall, 6),
            "assumed_edge_hz": round(1000000000 / (low + high + trise + tfall), 3),
            "zero_edge_period_ns": round(low + high, 6),
            "zero_edge_hz": round(1000000000 / (low + high), 3),
        })
    return {"timingr": f"0x{timing:08X}", "profile_hz": frequency, "cases": cases}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clock", type=int, default=150000000)
    parser.add_argument("--frequency", type=int, nargs="+", default=[100000, 400000, 1000000])
    parser.add_argument("--verify-baseline", action="store_true",
                        help="assert the observed cold-start 150 MHz/100 kHz TIMINGR")
    parser.add_argument("--timingr", type=lambda value: int(value, 0), nargs="*",
                        help="also evaluate candidate fields using the 1 MHz profile")
    parser.add_argument("--source-tolerance", type=float, default=0.02,
                        help="fractional fast-clock allowance for candidate evaluation")
    args = parser.parse_args()
    if args.verify_baseline:
        actual = calculate(150000000, 100000)["timingr"]
        if actual != "0xD0902D2F":
            raise AssertionError(f"baseline mismatch: {actual} != 0xD0902D2F")
    result = {
        "source": str(SOURCE),
        "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest() if SOURCE.exists() else None,
        "baseline_verified": bool(args.verify_baseline),
        "timings": [calculate(args.clock, frequency) for frequency in args.frequency],
    }
    if args.timingr:
        result["candidate_evaluations"] = [evaluate(args.clock, timing, 1000000,
            args.source_tolerance) for timing in args.timingr]
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
