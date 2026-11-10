"""Read clock/power configuration at the exact installed early UART park.

No reset, power change, RAM/peripheral write, or helper execution. The existing
check_park guard may halt the core, only after verifying exact approved code and
park records. PWR and DBGMCU are skipped unless their clocks/reset allow reads.
Root alone runs this script while owning the bench. Every read is a documented
CMSIS register; no read crosses a reserved address range.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "firmware/capture-sd/low_power"))
import read_standby_flag as guard

BUILD = ROOT / "tmp/bringup/sensor-autostop-promote-20261028/flash-standby-v1/staged"
EXPECTED_PREFIX = "6378483a91b560ffc6b31d74a9dd1205996a14c8030447ffddf7deddc9d23874"
HEADER = ROOT / ("firmware/capture-sd/evidence/2026-10-20-low-power/dependencies/"
                 "st/STM32Cube_FW_N6/Drivers/CMSIS/Device/ST/STM32N6xx/Include/stm32n657xx.h")

# (block name, first address, exact contiguous nonreserved register names).
RCC_BLOCKS = [
    ("rcc-cr", 0x56028000, "CR SR"),
    ("rcc-cfgr", 0x56028020, "CFGR1 CFGR2"),
    ("rcc-hsi", 0x56028048, "HSICFGR"),
    ("rcc-pll1", 0x56028080, "PLL1CFGR1 PLL1CFGR2 PLL1CFGR3"),
    ("rcc-pll2", 0x56028090, "PLL2CFGR1 PLL2CFGR2 PLL2CFGR3"),
    ("rcc-pll3", 0x560280A0, "PLL3CFGR1 PLL3CFGR2 PLL3CFGR3"),
    ("rcc-pll4", 0x560280B0, "PLL4CFGR1 PLL4CFGR2 PLL4CFGR3"),
    ("rcc-ic", 0x560280C4, " ".join(f"IC{i}CFGR" for i in range(1, 12))),
    ("rcc-reset", 0x56028208,
     "MISCRSTR MEMRSTR AHB1RSTR AHB2RSTR AHB3RSTR AHB4RSTR AHB5RSTR"),
    ("rcc-enable", 0x56028240,
     "DIVENR BUSENR MISCENR MEMENR AHB1ENR AHB2ENR AHB3ENR AHB4ENR "
     "AHB5ENR APB1ENR1 APB1ENR2 APB2ENR APB3ENR APB4ENR1 APB4ENR2 APB5ENR"),
]
PWR_BLOCKS = [
    ("pwr-cr", 0x56024800, "CR1 CR2 CR3 CR4"),
    ("pwr-vos", 0x56024820, "VOSCR"),
    ("pwr-cpu-supply", 0x56024830, "CPUCR SVMCR1 SVMCR2 SVMCR3"),
]


def decode(raw):
    r = {k: v["value"] for k, v in raw.items()}
    cfgr = r["RCC.CFGR1"]
    d = dict(
        cpu_requested_source=["HSI", "MSI", "HSE", "IC1"][(cfgr >> 16) & 3],
        cpu_actual_source=["HSI", "MSI", "HSE", "IC1"][(cfgr >> 20) & 3],
        system_requested_source=["HSI", "MSI", "HSE", "IC2/IC6/IC11"][(cfgr >> 24) & 3],
        system_actual_source=["HSI", "MSI", "HSE", "IC2/IC6/IC11"][(cfgr >> 28) & 3],
        hsi_divider=1 << ((r["RCC.HSICFGR"] >> 7) & 3),
        ic={f"IC{i}": dict(pll=1 + ((r[f"RCC.IC{i}CFGR"] >> 28) & 3),
                           divider=1 + ((r[f"RCC.IC{i}CFGR"] >> 16) & 255))
            for i in range(1, 12)},
    )
    if "PWR.CR1" in r:
        cr, vos, cpu = r["PWR.CR1"], r["PWR.VOSCR"], r["PWR.CPUCR"]
        d["power"] = dict(
            sden=bool(cr & 4),
            vcore_source="internal SMPS enabled" if cr & 4 else "external VCORE source",
            requested_voltage_scale=0 if vos & 1 else 1,
            active_voltage_scale=0 if vos & (1 << 16) else 1,
            vos_ready=bool(vos & 2), active_vos_ready=bool(vos & (1 << 17)),
            pdds=bool(cpu & 1), stopf=bool(cpu & (1 << 8)), sbf=bool(cpu & (1 << 9)),
            vddio_range={
                name: "1.8 V" if r[reg] & (1 << bit) else "3.3 V"
                for name, reg, bit in (
                    ("main", "PWR.SVMCR3", 24), ("IO2", "PWR.SVMCR3", 25),
                    ("IO3", "PWR.SVMCR3", 26), ("IO4", "PWR.SVMCR1", 24),
                    ("IO5", "PWR.SVMCR2", 24))},
            limitation="Configuration only: not measured rail voltage. SBF/STOPF are history, not trial proof.")
    if "DBGMCU.CR" in r:
        d["debug"] = {name: bool(r["DBGMCU.CR"] & (1 << bit)) for name, bit in
                      (("dbg_sleep", 0), ("dbg_stop", 1), ("dbg_standby", 2), ("dbgclken", 20))}
    return d


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", required=True, type=Path)
    args = p.parse_args(argv)
    out = args.out.resolve()
    if out == HERE or HERE not in out.parents:
        raise ValueError("Output must be a new child directory of this campaign")
    code, approved = guard.check_park.checked_build(BUILD)
    if guard.sha(code) != EXPECTED_PREFIX:
        raise ValueError("Build is not the exact currently installed October28 profile")
    out.mkdir(parents=True, exist_ok=False)
    result = dict(passed=False, began_utc=guard.utc(), build=str(BUILD),
                  prefix_sha256=guard.sha(code), reader_sha256=guard.sha(Path(__file__).read_bytes()),
                  cmsis_header=str(HEADER), cmsis_header_sha256=guard.sha(HEADER.read_bytes()),
                  reset_or_power_changed=False, peripheral_writes=False, ram_writes=False,
                  nor_commands=False, sd_commands=False, raw={}, skipped={})
    def save():
        (out / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    try:
        result["stage"] = "fresh-exact-park-check"
        save()
        fresh, fresh_sha = guard.fresh_park_check(BUILD, out)
        guard.validate_park_result(fresh, code, approved)
        result.update(park_result=fresh, park_result_sha256=fresh_sha)
        b = guard.Bench(out / "registers")
        result["guard_before"] = guard.live_guard(b, code, approved, fresh, "before")
        def block(domain, spec):
            name, addr, names = spec
            names = names.split()
            result["stage"] = name
            save()
            values = struct.unpack(f"<{len(names)}I", b.upload(addr, 4 * len(names), name + ".bin"))
            for i, (reg, value) in enumerate(zip(names, values)):
                result["raw"][f"{domain}.{reg}"] = dict(address=hex(addr + 4*i), value=value, hex=f"0x{value:08x}")
            save()
        for spec in RCC_BLOCKS:
            block("RCC", spec)
        r = {k: v["value"] for k, v in result["raw"].items()}
        if r["RCC.AHB4ENR"] & (1 << 18) and not r["RCC.AHB4RSTR"] & (1 << 18):
            for spec in PWR_BLOCKS:
                block("PWR", spec)
        else:
            result["skipped"]["PWR"] = "PWREN absent or PWR reset asserted; no clock/reset write attempted"
        if r["RCC.MISCENR"] & 1 and not r["RCC.MISCRSTR"] & 1:
            block("DBGMCU", ("dbgmcu-cr", 0x54001004, "CR"))
        else:
            result["skipped"]["DBGMCU"] = "DBGEN absent or DBG reset asserted; no clock/reset write attempted"
        result["decoded"] = decode(result["raw"])
        result["guard_after"] = guard.live_guard(b, code, approved, fresh, "after")
        result.update(passed=True, stage="complete", persistent_halt_after_disconnect="not_guaranteed",
                      post_disconnect_execution="may resume verified branch-to-self park")
    except Exception as error:
        result["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        result["ended_utc"] = guard.utc()
        save()
    print(json.dumps(dict(passed=True, output=str(out / "result.json"), decoded=result["decoded"]), indent=2))


if __name__ == "__main__":
    main()
