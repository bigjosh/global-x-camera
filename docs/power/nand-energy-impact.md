# Alliance NAND: image-save time and energy impact

> **Historical workload:** this September 7 comparison retains the VD55G0 frame size, memory candidates and assumptions used at that time. It does not qualify the now-selected VD56G3 workload or choose the final NAND. Apply the [current specification](../../spec.md), including 200 usable photos and configurable full-image readback, when rerunning the comparison; device busy-time estimates do not scale into a measured whole-camera energy result.

**September 7, 2026. Analytical comparison, not measured hardware performance.**

The supply-preferred **AS9F14G08SA-45BIN** remains a reasonable candidate, but it is not an established total-energy improvement. Compared with the original **MX30LF2G18AC-TI**, it operates at lower voltage, has the same typical page-program time, and permits slower bus transfers. MCU and other-board energy during that extra time can exceed the flash's own saving. The additional capacity does not require more pages per image.

## Scope and evidence

The baseline is the recovered 3.3 V Macronix, versus the proposed 1.8 V Alliance; the previous ISSI shortlist was not implemented. Full native 644×604 RAW10 is **486,220 bytes**, requiring **238 pages** of 2048 data bytes. A 16-bit container requires 777,952 bytes and 380 pages.

The documented sequence is capture into SRAM, then NAND save, verified commit and shutdown. The 50 ms requirement concerns acquisition; saving is outside that deadline. No integrated firmware, FMC timing registers, DMA implementation, verification policy or measured save-state power is available. See [hardware/firmware contract](../hardware-firmware-interface.md).

Primary references: [Macronix PM2129 Rev.1.4, pp.64–66](../../datasheets/memory/MX30LF2G18AC_datasheet_PM2129_v1.4.pdf) ([manufacturer URL](https://www.macronix.com/Lists/Datasheet/Attachments/8461/MX30LF2G18AC%2C%203V%2C%202Gb%2C%20v1.4.pdf)); [Alliance Rev.1.0, pp.28–30](../../datasheets/memory/Alliance_AS9F_parallel_NAND_datasheet.pdf) ([manufacturer URL](https://www.alliancememory.com/wp-content/uploads/AllianceMemory_AS9Fxx_Series_1Gb_2Gb_4Gb_8Gb_x8bits_SLC_Parallel_NAND_Fl.pdf)).

## Image-save timing

This calculation uses ordinary sequential page programming, a pre-erased destination, and transfers every page's full data and spare area. It excludes command/address/status overhead, ECC computation, metadata, retries and software gaps. Each device runs at its fastest permitted bus cycle: **20 ns original / 45 ns Alliance**. These are device limits, not verified STM32 throughput.

| Packed RAW10 operation | Original Macronix | Alliance |
| --- | ---: | ---: |
| Transfer 238 full pages including spare | 10.05 ms | 23.30 ms |
| Program-busy time, typical | 71.40 ms | 71.40 ms |
| **Transfer + typical programming** | **81.45 ms** | **94.70 ms** |
| Transfer + maximum specified programming | 152.85 ms | 189.90 ms |
| Optional full readback, using maximum array-read latency | +16.00 ms | +30.44 ms |
| Optional erase of four blocks, typical / maximum | +4 / 14 ms | +14 / 40 ms |

The typical-program comparison adds **13.25 ms, about 16%**, under these bus assumptions. The maximum-program row adds 37.05 ms; it is not a complete worst-case save-time bound because controller/software overhead is excluded. Full readback with typical programming gives approximately **97.46 → 125.15 ms** before software overhead; readback uses specified maximum array latency because a typical value is not available.

At a common practical bus cycle of **50 ns**, the same model becomes **96.53 → 97.29 ms**, only 0.76 ms apart. If firmware transfers the same number of populated ECC/metadata bytes for each chip, even that spare-area difference can disappear. Therefore, the 13 ms penalty should not be assumed until actual FMC throughput is established. Cache programming can overlap transfers with array work, but changes the timing/current model and must be qualified separately.

The 16-bit container comparison is **130.05 → 151.21 ms** with typical programming at the respective fastest bus rates. Packing the sensor's RAW10 data saves 142 page programs without reducing sensor precision; account for packing CPU time if the receive path does not already provide packed data.

Four erase blocks assume a block-aligned allocation; sharing blocks changes the per-image allocation, while metadata and bad-block replacement can increase it. Pre-erasing removes erase delay from the save path. Performing erase while USB-powered can also move its battery-energy cost to USB. Merely scheduling erase earlier on battery does not remove that energy.

## NAND power and energy

At nominal rail voltages, normal-program power is **49.5 mW typical / 99 mW maximum-current model** for the original part. Alliance specifies **20 mA maximum**, corresponding to **36 mW**, but gives **no typical normal-program current**. Cache programming instead permits 30 mA maximum. These are supply-mode figures; external signal loading and pull-ups add consumption.

For program-busy energy alone, `E = V × I × 238 × tPROG`:

| Program-busy model | Original | Alliance |
| --- | ---: | ---: |
| Typical current and typical time | 3.534 mJ | Not specified |
| Maximum current with typical time | 7.069 mJ | 2.570 mJ |
| Maximum current and maximum time, nominal voltage | 14.137 mJ | 5.998 mJ |

Products of maxima are screening models, not measured energy distributions or whole-board guarantees. The Alliance 2.570 mJ figure mixes maximum current with typical duration; it must not be labeled typical or guaranteed maximum energy. The maximum-voltage/max-current/max-time products would instead be 15.422 mJ at 3.6 V and 6.497 mJ at 1.95 V. Lower NAND voltage alone cannot establish a typical percentage saving.

## Effect on total battery energy

For a first-order comparison at the regulated loads:

```text
Change in save energy = change in NAND energy
                      + P_other,new × T_new − P_other,old × T_old
                      + changes in verification, erase and other overhead
```

Refer each rail's energy through its converter efficiency to obtain battery energy; add boot, acquisition, shutdown and source overhead. For example, 1 mJ delivered through a 90%-efficient converter requires 1.11 mJ from the battery. The final converters and save-state efficiencies have not been selected or measured.

An illustrative **200 mW average non-NAND load** is consistent in scale with the [current budget](current-budget.md), whose MCU reference alone is about 192 mW at one active 800 MHz operating point. It is not a measured save-state value. At equal non-NAND power, the additional 13.25 ms costs **2.650 mJ**.

Using the original's typical program current and assumed Alliance currents gives this sensitivity analysis:

| Assumed Alliance normal-program current | NAND busy-energy reduction | Additional non-NAND energy at 200 mW | Net change in this partial model |
| --- | ---: | ---: | ---: |
| 10 mA | 2.249 mJ | 2.650 mJ | **+0.401 mJ** |
| 15 mA | 1.607 mJ | 2.650 mJ | **+1.044 mJ** |
| 20 mA, specified maximum | 0.964 mJ | 2.650 mJ | **+1.686 mJ** |

Positive means more energy for Alliance. These rows **omit NAND transfer-phase energy, external I/O/pull-ups, ECC, verification and erase**; they illustrate how extra operating time can consume the apparent benefit, rather than predict a complete capture's energy. At a much lower 50 mW non-NAND load, the time penalty is only 0.663 mJ. At a common bus rate, it is smaller again. Neither an actual saving nor an actual increase is established yet.

If full readback is required, its additional 14.44 ms can add another **2.888 mJ** to a 200 mW non-NAND load. Four on-battery erases add another 10 ms typical compared with the original, costing another **2 mJ** for that load. The verification and erase policies materially affect the answer.

Moving all digital consumers to 1.8 V and eliminating cascaded conversion may provide additional savings, but those belong to the complete power-architecture change and are not credited to this NAND substitution alone. Lower I/O voltage reduces capacitive switching energy at equal capacitance and transition count; final bank loads, activity and leakage remain to be calculated.

Both parts specify 10/50 µA typical/maximum CMOS standby. The NAND must remain on the switched supply for shelf OFF; this substitution does not establish the board's <1 µA OFF target. Alliance POR can reach 50 mA, so 20 mA normal programming is not its peak rail requirement.

## Recommendation

Retain Alliance as the supply/cost candidate, with power and save latency as qualification items. Use packed RAW10, keep an erased-block reserve, and shut down the camera safely after acquisition. Reduce MCU activity during NAND waits, while retaining the memory, clocks and wake path needed by the storage driver; the extra bus-transfer interval still needs its own active-power budget. Measure complete capture-to-shutdown battery energy with the actual FMC configuration, including the chosen commit verification. Do not claim a battery-life improvement from the voltage change alone.

Reproducible arithmetic: [calculation script](../../tools/calculate_nand_tradeoff.py), [results and assumptions](nand-energy-calculations.json).
