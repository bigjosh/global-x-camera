# Rail current budget and dual-buck assessment

> **Historical load model:** these September 7 allocations describe the earlier camera and are neither measurements nor limits for CAM-6G3-073CLR/VD56G3. Four series CR2032 cells and LTC3621 are now the selected prototype direction; LTC3622 remains a comparison. Rebuild the load budget for the [current prototype](../../spec.md) and integrate it with the [current power study](../../power.md) before choosing rails and passives.

**September 7, 2026. Status: preliminary calculations, not measured limits or a schematic change.**

A dual buck is a reasonable candidate for generating 3.3 V and 1.8 V directly from SYS_IN. The main load is on **1.8 V**, which supplies the STM32's internal core SMPS as well as the camera core regulator. The current recovered design instead generates 1.8 V from 3.3 V, so its 3.3 V regulator must carry both its direct loads and the converted 1.8 V load.

The assumptions here are the single-frame RAW acquisition/storage workflow in [spec.md](../../spec.md), without deliberately exercising the NPU, GPU or video encoder. Clock configuration, interface activity and startup current remain unqualified. These figures replace neither measurements nor a final temperature-qualified budget.

## Working numbers for regulator selection

| Output | Preliminary active-use allocation | High-load allocation to reserve initially | Regulator capability to investigate |
| --- | --- | --- | --- |
| 1.8 V, including the internal SMPS input | 150–250 mA | Approximately 1 A, pending qualification | Prefer 2 A capability; 1 A is conditional on workload/temperature validation |
| 3.3 V, direct consumers only | 50–100 mA | Approximately 150 mA, excluding uncontrolled inrush | 0.5 A or more leaves useful margin |
| 3.3 V in the existing cascaded design | Approximately 140–250 mA | Approximately 760 mA using the allocations above | Includes the downstream 1.8 V converter; do not add it twice |

**Neither allocation column is a guaranteed whole-system maximum.** The active-use ranges are engineering estimates around published operating examples. The high-load allocations combine published reference maxima with explicit allowances for unresolved loads. Inrush, dynamic voltage transitions, the actual board's I/O switching and concurrent accelerator workloads can require a different allocation. A converter's current rating is capability, not current consumed continuously.

The cascaded row assumes 90% efficiency for U7:

```text
I(3.3 V total) ≈ I(3.3 V direct) + [1.8 / (3.3 × efficiency_U7)] × I(1.8 V)
              ≈ I(3.3 V direct) + 0.6061 × I(1.8 V)

Lower active allocation:  50 + 0.6061 × 150 = 141 mA
Upper active allocation: 100 + 0.6061 × 250 = 252 mA
High-load allocation:    150 + 0.6061 × 1000 = 756 mA
```

90% is an illustrative efficiency assumption, not a guaranteed TPS62825 efficiency. Thus the earlier 250 mA at 3.3 V remains a plausible operating design point, but is not an established peak or all-temperature limit. With a dual buck, the 1.8 V load moves off the 3.3 V output; it still draws energy from the battery or USB input.

## Basis of the 1.8 V allocation

STM32 figures below use internal-SMPS input current plus the separately tabulated shared analog and always-on branches. **Do not add VDDCORE output current again.**

| STM32 benchmark case | Typical, TJ = 25°C | Characterized maximum, TJ = 125°C |
| --- | ---: | ---: |
| HSE, 800 MHz, ITCM/DTCM, peripherals disabled | 60.44 mA | 497.63 mA |
| Same, peripherals enabled | 106.87 mA | 567.64 mA |
| HSI, 800 MHz, AXI-SRAM2/cache enabled, peripherals enabled | 103.72 mA | 761.18 mA |

These are arithmetic sums of Tables 36, 38 and 39, not new whole-device guarantees. The tests use CoreMark, analog-mode I/O and 1.8 V VDD/VDDIOx. Our mixed 3.3/1.8 V configuration and active interfaces differ. In particular, the often-cited **757.5 mA** is one 125°C SMPS-input maximum; the typical value in that row is **100.6 mA**. [STM32 datasheet, conditions pp134,145; current tables pp151–154](https://www.st.com/resource/en/datasheet/stm32n657x0.pdf#page=145).

The camera adds **46.25 mA typical / 61.5 mA tabulated maximum** through its core LDO and direct I/O supply. These are sensor reference figures at 644×604, 185 fps, RAW10, 1.2 Gbit/s, 12 MHz MCLK and 60°C, with a **1.15 V core**. Our current U10 produces 1.2 V, so these are useful reference values rather than a qualified bound for the module in our configuration. The LDO input current is approximately its output current plus ground current; no buck-conversion ratio applies. [VD55G0 datasheet p16](../../datasheets/camera/VD55G0_DS13170_datasheet.pdf).

For scale, the HSE enabled-peripheral typical subtotal plus camera is `106.87 + 46.25 = 153.12 mA`, before additional interface and small-load allowances. At the larger characterized hot case, the subtotal is `761.18 + 61.5 = 822.68 mA`. This is why 150–250 mA is a useful active-use estimate while a 1 A converter has limited unqualified hot-corner margin.

Additional accounting items:

- Figure 17 groups PLL, CSI analog and USB analog current together. Adding full active PHY figures to that shared baseline conservatively overlaps idle current. Use active-minus-idle increments when those become known.
- USB HS Table 126 lists 13.35/17.92 mA typical/maximum on its 1.8 V analog input. Core-side PHY power must be referred through the internal SMPS; core output milliamps cannot simply be added to 1.8 V input milliamps.
- CSI Table 125 has inconsistent Min/Max/Typ column headings. The largest displayed two-lane, 1 Gbit/s values are 2.84 mA analog, 5.80 mA VDDCSI and 12.36 mA core logic. Treat these as conservative numerical allowances pending clarification, not corrected manufacturer guarantees.
- As an illustrative screening sum, adding full USB/CSI analog figures and core contributions to the 822.68 mA subtotal gives about 870 mA using 0.9 V core and 80% internal-SMPS efficiency. This deliberately overlaps some baseline current. Allowing another 20 mA for bias, ADC, I/O and small loads brings it to about 890 mA. The 20 mA is an engineering allowance, not a derived bound; approximately 1 A rounds up this scenario but does not qualify all workloads.
- LIS2DW12 high-performance consumption is 90 µA typical, or 120 µA with low-noise enabled, with no guaranteed current maximum. Its TPS22918 switch adds 10.2 µA typical / 17 µA maximum at 1.8 V. U10 ground current is small but lacks a guaranteed maximum at the relevant camera load. [Accelerometer](../../datasheets/sensors_timing/LIS2DW12_datasheet.pdf), [switch](../../datasheets/power/TI_TPS22918_datasheet.pdf), [core LDO](../../datasheets/power/onsemi_NCP115_datasheet.pdf).

The hot characterization case is a stress reference, not a prediction that this brief-capture product will reach 125°C. Actual temperature and workload qualification may justify less current capability.

## Basis of the direct 3.3 V allocation

| Consumer | Typical reference | Published maximum at the stated mode |
| --- | ---: | ---: |
| Camera analog, through 2.8 V LDO | 17.3 mA | 21 mA |
| W25Q128JV NOR, 104 MHz read | 12 mA | 20 mA |
| W25Q128JV NOR, program/erase instead of read | 20 mA | 25 mA |
| MX30LF2G18AC NAND, read/program/erase | 15 mA | 30 mA |
| NAND power-on/POR instead of normal operation | Not given | 50 mA |

NAND two-plane programming has a 25 mA typical value. Alternative operating modes of the same device must not be summed. NOR figures exclude output loading. Sources: [Winbond Rev. M, PDF p64](../../datasheets/memory/W25Q128JV_datasheet_RevM.pdf), [Macronix Rev. 1.4 p64](../../datasheets/memory/MX30LF2G18AC_datasheet_PM2129_v1.4.pdf), and camera reference above.

Camera analog + NOR read + NAND operating current is approximately **44.3 mA typical**. Camera + simultaneous programming-reference maxima for both memories is **76 mA**. Substituting NAND POR raises that arithmetic subtotal to **96 mA**; this combines independent reference conditions conservatively and is not a measured startup waveform.

Add MCU VDD and I/O-bank currents, external signal loading and pull-ups, approximately 1 mA for the LED, RTC and LDO overhead. Adding a 20–40 mA allowance for the unresolved MCU/interface contribution to the 44.3 mA reference gives about 64–84 mA before the small loads. The 50–100 mA active range is a broader planning envelope spanning different activity levels; 150 mA rounds up the higher reference combinations with these allowances. The allowance needs calculation from actual clock rates and pin loads, followed by measurement. As a scale example, `I = V × f × C` gives 3.3 mA for one 3.3 V output charging 10 pF at 100 MHz; multiple active bus signals can be material.

The separately supplied **3V3_USB** branch belongs to U4 on USB VBUS, not the main 3.3 V converter. Its STM32 PHY reference is 3.39/3.64 mA typical/maximum during the specified USB HS transmission test, plus U4 overhead. RTC backup consumption likewise belongs to the battery-cell tap when backup is selected. See the [complete power tree](power-tree.md).

## Dual-buck candidates and recommendation

| Candidate | Outputs / input range | Control | OFF-current qualification | Assessment |
| --- | --- | --- | --- | --- |
| LTC3622, adjustable | 1 A each; 2.7–17 V input | Independent RUN1/RUN2 | 0.1 µA typical; ±1 µA maximum at 12 V and 25°C only | Closest low-leakage candidate; 1.8 V current margin needs validation |
| LTC3633A | 3 A each; common input 3.6–20 V | Independent RUN1/RUN2 | 13 µA typical, no stated maximum | Ample capacity, poor match for shelf-current target |
| LT8653S | 2 A each; 3–42 V input | Common EN; separate soft-start/sequencing inputs | 1.7 µA typical; 4 µA max at 25°C, 8 µA max across −40…125°C for I grade | Better current/voltage margin, misses OFF target |

Sources: [LTC3622 Rev. D](https://www.analog.com/media/en/technical-documentation/data-sheets/LTC3622-3622-2-3622-23-5.pdf), [LTC3633A](https://www.analog.com/media/en/technical-documentation/data-sheets/3633a1fb.pdf), [LT8653S](https://www.analog.com/media/en/technical-documentation/data-sheets/lt8653s.pdf).

The adjustable **LTC3622IDE#PBF** or **LTC3622IMSE#PBF** is worth evaluating. Prefer examining the 1 MHz version first for the large input-to-1.8 V step-down ratio. The adjustable `-2` runs at 2.25 MHz; the fixed `-23/5` version produces 5 V/3.3 V and is unsuitable for these two outputs. Distributor stock has not been reliably confirmed for the exact proposed order code.

A dual IC still needs **two inductors**, output capacitors and feedback networks. Direct 1.8 V conversion removes a cascaded power-conversion stage, but efficiency and total area must be compared at our actual loads. Source selection, transient limits and PCB thermal/layout requirements still apply.

The two output voltages also do not eliminate the STM32's supply groups: **1.8 V AON must survive while AUX is removed**. A controlled/discharged AUX branch or a small additional AON regulator remains necessary. Independent enables help, but do not alone establish the required shutdown ordering. None of the checked dual parts guarantees the complete board's **<1 µA OFF** target.

**Recommendation:** keep LTC3622 as a conditional candidate, without changing the schematic yet. Retain a preference for 2 A capability on 1.8 V until the selected clock/workload/temperature and startup behavior justify 1 A. The next selection should be driven by measured or qualified current and the OFF-current/sequence solution, rather than IC count alone.
