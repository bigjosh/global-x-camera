"""Peak pack-power model for a custom PCB on series CR2032 cells.

Assumptions and sources: docs/power/custom-pcb-peak-power.md.

An engineering estimate from datasheet typical values and assumed converter
efficiencies. Not a measurement and not a worst-case bound. Powers are watts,
currents amperes, voltages volts. Run with Python 3; no packages.
"""

from dataclasses import dataclass

# ---- Loads at their own rails (typical) ------------------------------------

V_CORE = 0.81  # STM32N6 VOS low

# STM32N6 core current, DS14791 Rev 10, typical at 25 C, external core supply.
I_LEAK = 0.00906        # Table 42, Stop mode: clocks stopped
I_SLEEP_600 = 0.0418    # Table 40, Sleep at 600 MHz, peripherals disabled
I_RUN_600 = 0.063       # Table 33, Run at 600 MHz, peripherals disabled
I_PERIPH = 0.015        # ASSUMED: the few peripherals in use at the ROM clock profile
ROM_CPU_MHZ = 400.0     # ROM/firmware profile today: 400 MHz CPU, 300 MHz AXI


def core_current(scale, cpu_running=True, peripherals=True):
    """Core current with the whole clock tree scaled by `scale` (1.0 = today)."""
    tree = (I_SLEEP_600 - I_LEAK) * scale          # clock tree and buses
    cpu = (I_RUN_600 - I_SLEEP_600) * (ROM_CPU_MHZ / 600.0) * scale
    periph = I_PERIPH * scale
    return I_LEAK + tree + (cpu if cpu_running else 0) + (periph if peripherals else 0)


MCU_1V8_PLL = 0.0043    # Table 35, 1.8 V analog with PLL running
MCU_1V8_NOPLL = 0.0020  # ASSUMED without PLL
MCU_AON = 0.00045       # Table 37, HSI
MCU_VDD = 0.0003        # Table 31
CSI_PHY_1V8 = 0.010     # ASSUMED receiver PHY current while capturing; not in the datasheet text

# VD56G3, typical at 60 fps full resolution, as recorded in the power-tree review.
SENSOR = {"ana_2v8": 0.0228, "io_1v8": 0.0085, "core_1v15": 0.057}
SENSOR_IDLE = {"ana_2v8": 0.000038, "io_1v8": 0.000013, "core_1v15": 0.0021}
OSC_1V8 = 0.0025        # ASSUMED 12 MHz oscillator

NOR_READ = 0.012        # ASSUMED boot-flash read current at 32 MHz single-line
NAND_PROG = 0.025       # W25N04KW typ 25 mA (35 max); MX35UF typ 23 mA (30 max)
NAND_LOAD = 0.005       # ASSUMED while shifting a page into the cache
SD_TYP, SD_MAX = 0.050, 0.120   # at 3.3 V, Swissbit reference in microsd-feasibility.md

# ---- Conversion (assumed efficiencies) -------------------------------------


@dataclass(frozen=True)
class Tree:
    name: str
    main_v: float          # MCU VDD rail
    eta_main: float        # pack -> main
    eta_1v8: float         # main -> 1.8 V (1.0 when main is 1.8 V)
    eta_core: float        # 1.8 V or main -> 0.81 V
    core_from_1v8: bool
    sensor_core: str       # "ldo" (from 1.8 V) or "buck" (from 1.8 V)
    eta_2v8: float         # pack -> 2.8 V, complete path

    def pack(self, i_core, i_1v8, sensor, storage_w_3v3=0.0):
        """Pack power for the given rail currents."""
        to_1v8 = self.eta_main * self.eta_1v8          # pack -> 1.8 V
        p = 0.0
        # MCU core
        core_w = i_core * V_CORE
        p += core_w / self.eta_core / (to_1v8 if self.core_from_1v8 else self.eta_main)
        # 1.8 V loads (MCU analog, AON, sensor IO, oscillator, NAND, ...)
        p += (i_1v8 + sensor["io_1v8"]) * 1.8 / to_1v8
        # MCU VDD at the main voltage
        p += MCU_VDD * self.main_v / self.eta_main
        # sensor core
        if self.sensor_core == "ldo":
            p += sensor["core_1v15"] * 1.8 / to_1v8
        else:
            p += sensor["core_1v15"] * 1.15 / 0.90 / to_1v8
        # sensor analog
        p += sensor["ana_2v8"] * 2.8 / self.eta_2v8
        # 3.3 V storage (SD card): from a 3.3 V main, or a separate pack buck
        p += storage_w_3v3 / (self.eta_main if self.main_v > 3.0 else 0.88)
        return p


TREES = (
    Tree("A: 3.3 V main, sensor core on an LDO", 3.3, 0.88, 0.92, 0.88, False, "ldo", 0.88 * 0.85),
    Tree("B: 1.8 V main, internal core SMPS, sensor core on an LDO", 1.8, 0.85, 1.0, 0.82, True, "ldo", 0.85 * 0.90),
    Tree("C: 1.8 V main, core buck, sensor core buck", 1.8, 0.85, 1.0, 0.90, True, "buck", 0.85 * 0.90),
)

# ---- Phases -----------------------------------------------------------------

BASE_1V8 = MCU_AON + OSC_1V8


def phases(tree, clock):
    """clock: 'today' (ROM profile throughout) or 'matched' (see the document)."""
    fast = clock == "today"
    cap_scale = 1.0 if fast else 0.5          # sensor link and pipeline slowed 2x
    act_scale = 1.0 if fast else 64.0 / 400   # save on HSI, PLL off
    out = {}
    # The ROM always runs its own 400 MHz profile; sensor boot current is not included.
    out["boot: ROM loading"] = tree.pack(core_current(1.0),
                                         BASE_1V8 + MCU_1V8_PLL + NOR_READ, SENSOR_IDLE)
    out["capture"] = tree.pack(core_current(cap_scale),
                               BASE_1V8 + MCU_1V8_PLL + CSI_PHY_1V8, SENSOR)
    pll = MCU_1V8_PLL if fast else MCU_1V8_NOPLL
    out["long exposure, MCU asleep"] = tree.pack(
        core_current(64.0 / 400 if not fast else 1.0, cpu_running=False, peripherals=False),
        BASE_1V8 + pll, SENSOR)
    out["save: page load"] = tree.pack(core_current(act_scale),
                                       BASE_1V8 + pll + NAND_LOAD, SENSOR_IDLE)
    # During the NAND's internal program time the MCU either busy-waits (today)
    # or sleeps on the slow clock (matched).
    wait = core_current(1.0) if fast else core_current(64.0 / 400, cpu_running=False, peripherals=False)
    out["save: NAND programming"] = tree.pack(wait, BASE_1V8 + pll + NAND_PROG, SENSOR_IDLE)
    for label, amps in (("typical", SD_TYP), ("maximum", SD_MAX)):
        out[f"save: SD card, {label}"] = tree.pack(core_current(1.0), BASE_1V8 + MCU_1V8_PLL,
                                                   SENSOR_IDLE, storage_w_3v3=amps * 3.3)
    return out


# ---- Source: series CR2032 at 50 F ------------------------------------------

COLD = 1.4                      # ASSUMED resistance factor at 50 F
R_BURST = (14.0, 14.0 * 40 / 30)    # ohms per cell, fresh / half used; October 28 trace
R_SUSTAINED = (30.0, 40.0)          # ohms per cell, fresh / half used; Energizer 2 s pulse


def ceiling(cells, r_cell):
    v = 3.0 * cells
    return v * v / (4 * cells * r_cell * COLD)


def main():
    print("Pack power by phase, W\n")
    names = list(phases(TREES[0], "today"))
    for clock in ("today", "matched"):
        print(f"clocking: {clock}")
        print("  phase".ljust(34) + "".join(t.name[:1].rjust(8) for t in TREES))
        table = [phases(t, clock) for t in TREES]
        for n in names:
            print(("  " + n).ljust(34) + "".join(f"{tb[n]:8.3f}" for tb in table))
        print()
    for t in TREES:
        print(f"  {t.name}")
    print("\nSource ceiling V^2/4R at 50 F, W (fresh / half used)")
    for cells in (4, 5):
        b = [ceiling(cells, r) for r in R_BURST]
        s = [ceiling(cells, r) for r in R_SUSTAINED]
        print(f"  {cells} cells  burst {b[0]:.2f} / {b[1]:.2f}   sustained {s[0]:.2f} / {s[1]:.2f}")
    print("\nMCU core current, mA: today %.1f, capture matched %.1f, HSI active %.1f, HSI sleep %.1f"
          % tuple(1e3 * x for x in (core_current(1.0), core_current(0.5), core_current(0.16),
                                    core_current(0.16, False, False))))


if __name__ == "__main__":
    main()
