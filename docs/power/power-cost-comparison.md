# Prototype power cost: 5 V Nucleo, modified 3.3 V Nucleo, custom PCB

**October 14, 2026 — engineering estimate, not measurements or a voltage decision.** This answers the user's comparison request and supplements the [power-tree review](2026-10-14-power-tree-review.md). Calculations are reproducible in [estimate_prototype_power.py](../../tools/estimate_prototype_power.py). The accepted camera, battery, latency, readback and OFF-current requirements are unchanged.

## Result and recommendation

**The 5 V intermediate is a relatively small cost after unnecessary board loads are removed.** In this example, converting a debugger-isolated Nucleo to 3.3 V saves about 12% of battery energy; with the power indicator removed in both cases, the conversion change saves about 7%. A custom board saves more by improving the 1.8 V and camera supplies and removing unused electronics.

All figures below are **at the battery**, including estimated LTC3621 and downstream conversion losses. The same illustrative 0.86-second cycle is used for every row. Values are rounded to avoid implying measurement precision.

| Configuration | During capture phase | During save/readback | Average across cycle | Energy per photo |
|---|---:|---:|---:|---:|
| Standard Nucleo, LTC3621 at 5 V; illustrative 30 mA debugger load | 0.77 W | 0.42 W | 0.46 W | **0.39 J** |
| Reference: same 5 V board with debugger isolated | 0.60 W | 0.25 W | 0.29 W | **0.25 J** |
| Modified Nucleo at 3.3 V, debugger isolated | 0.55 W | 0.22 W | 0.25 W | **0.22 J** |
| Custom PCB at 3.3 V with efficient 1.8 V conversion and camera gating | 0.40 W | 0.15 W | 0.17 W | **0.15 J** |

These are phase-average estimates, **not peak-current ratings or worst-case bounds**. The comparison assumes firmware powers down unused Ethernet and USB functions even on the mechanically unmodified board. A completely unconfigured development board can consume more.

The debugger's actual current is unknown. The stock row is explicitly illustrative: choosing 15, 30 or 50 mA at the 5 V input gives **0.32, 0.39 or 0.49 J/photo**, respectively, while holding everything else fixed. Those currents are sensitivity examples, not a sourced current range. This uncertainty can exceed the entire benefit of a 3.3 V conversion.

**Recommendation for discussion:** keep the existing 5 V conversion tree for initial bring-up; first investigate isolating ST-LINK and removing the permanent power LED, and configure unused peripherals for minimum power. That brings this model to **0.23 J/photo at 5 V**, compared with **0.21 J/photo for a similarly stripped 3.3 V board**. Measure before undertaking the more involved 3.3 V supply/USB rework. The custom example is approximately 0.15 J/photo without assuming faster firmware or lower MCU workload. No output voltage or rework has been approved by this estimate.

## Why 5 V does not cost 34% across the board

Only a linear 5-to-3.3 V branch has the ideal 3.3/5 = 66% conversion efficiency. The Nucleo's core and auxiliary 3.3 V branches already use switching regulators. Eliminating their intermediate voltage helps less. LTC3621 also tends to be slightly more efficient producing 5 V than 3.3 V at the same output power. The [power-tree study](2026-10-14-power-tree-review.md) records the branch topology and modification constraints.

This model uses LTC efficiencies of 88% at 5 V and 86% at 3.3 V, core-converter efficiencies of 83% and 86%, and 90% for the stock auxiliary buck and custom 1.8 V buck. These are representative assumptions. The LTC graph supports approximately 88–90% versus 86–89% around 0.5–1 W output; the lighter save load is less firmly supported. The core graph is for 0.9 V, so applying it to 0.81 V is an extrapolation. The auxiliary/custom 90% figures are design assumptions, not verified operating points. [LTC3621 Rev D, p1](https://www.analog.com/media/en/technical-documentation/data-sheets/ltc3621-3621-2.pdf), [TPS62088 Rev F, Fig8-7](https://www.ti.com/lit/ds/symlink/tps62088.pdf).

With debugger isolated, the exact model results are 0.24655 J at 5 V and 0.21756 J at 3.3 V: **13.3% extra energy at 5 V**, or **11.8% saved by moving to 3.3 V**. About 13 mJ of the 29 mJ difference comes from dimming the existing resistor-fed power LED. Removing that LED in both cases yields 0.22867 versus 0.21232 J, a **7.1% saving**. Do not label the whole 12% as regulator loss alone.

An illustrative sensitivity sweep of auxiliary efficiency 85–95% and an LTC 3.3 V disadvantage of 1–4 percentage points gives roughly **7–19% extra energy at 5 V** with the LEDs retained and debugger isolated. This is not a statistical interval or guaranteed device range; workload and actual low-load efficiency can move the answer outside it.

## Workload and timing assumptions

| Phase | Assumed duration | Activity |
|---|---:|---|
| Cold start, exposure and readout | 100 ms | MCU, boot NOR and camera active; conservatively charge full streaming camera consumption for the whole interval. |
| Save, full payload readback and commit | 750 ms | NAND active, MCU handling storage, camera stopped and in reset on evaluation hardware; camera fully gated on custom hardware. |
| Shutdown | 10 ms | Reduced MCU activity while completing shutdown. |

The 100 ms first phase is an energy-model assumption, **not measured boot time and not a replacement for the accepted 50 ms button-to-exposure-start deadline**. Long exposures add time. At the modelled active powers, each additional 100 ms adds approximately 77 mJ for the illustrative stock board, 55 mJ for modified 3.3 V, or 40 mJ for custom hardware. Status indication, real startup sequencing, allocation recovery and actual exposure settings may also extend the cycle.

The selected 1124 × 1364 packed RAW10 frame contains **1,916,420 bytes**, occupying 936 2048-byte NAND payload pages before object metadata. For the candidate Alliance 1.8 V NAND, 600 µs typical page programming adds 561.6 ms; 70 µs typical page reading adds 65.5 ms. At 100 MHz quad, one padded-image transfer takes 38.3 ms. Thus save is about 600 ms and full readback about 104 ms, or **704 ms before commands, software, metadata and journal overhead**. At 50 MHz the sum is about 780 ms before overhead. The 750 ms model assumes 100 MHz and modest overhead; it is not a timing guarantee. [Alliance Rev3.1, pp7,45,47](https://www.alliancememory.com/wp-content/uploads/AllianceMemory_AS5F_QSPI_NAND_Flash_3V-1Gb-8Gb_1p8V-2Gb-4Gb-8Gb_Ver3.1_O.pdf).

Full readback remains enabled for bring-up. Disabling it later removes roughly 104 ms at this assumed bus rate, not the approximately 562 ms of NAND programming. FREE slots are assumed already erased during USB deletion; no block erase is charged to capture. Object/control layout remains open, so its exact timing is not established.

## Load assumptions and evidence

| Load | Capture | Save/readback | Shutdown | Evidence boundary |
|---|---:|---:|---:|---|
| MCU core delivered power | 85 mW | 55 mW | 10 mW | Workload allowances, not measured camera firmware. |
| MCU main/IO current | 2 mA | 2 mA | 0.5 mA | Switching allowance, not characterized board consumption. |
| MCU 1.8 V AON current | 0.45 mA | 0.45 mA | 0.1 mA | Active value anchored to datasheet reference; shutdown assumed. |
| MCU 1.8 V auxiliary analog current | 5 mA | 5 mA | 0.3 mA | Rounded allowance near datasheet reference; CSI activity remains to measure. |
| 1.8 V boot NOR | 10 mA | 1 mA | 0.1 mA | Allowance; assumes working code is primarily in RAM during save. |
| 1.8 V NAND | 0.1 mA | 20 mA | 0.1 mA | Active value is typical read/program current; idle values are allowances. |

For scale, STM32N657's 600 MHz, 0.81 V, CoreMark-in-ITCM reference with peripherals disabled is about **53.5 mW at the core** and **62.5 mW summed across MCU supply rails** with external core conversion; neither includes board conversion losses or external memories. Camera/DMA activity differs. The internal-SMPS reference is not directly additive to core power, and switching to it does not automatically save energy. [STM32N657 DS14791 Rev11, tables32–42](https://www.st.com/resource/en/datasheet/stm32n657x0.pdf).

Camera reference currents at 60 fps are 8.5 mA on 1.8 V IO, 57 mA on 1.15 V core and 22.8 mA on 2.8 V analog. The evaluation adapter's three LDOs draw approximately **291 mW from 3.3 V** to supply those currents, before oscillator/regulator overhead; the model adds 2 mW. Reset still draws approximately 7.1 mW at the adapter input, plus that overhead. Custom hardware instead feeds the camera core LDO from an efficiently generated 1.8 V rail, giving approximately **208 mW upstream of its local converters**, including the same overhead, and gates it after readout. These are supply-path estimates using sensor reference currents, not measured single-frame energy. [VD56G3 Rev12, tables13–14](https://www.st.com/resource/en/datasheet/vd56g3.pdf), [STEVAL-CAM-M0I schematic](https://www.st.com/resource/en/schematic_pack/steval-cam-m0i-schematic.pdf).

Leaving the camera streaming during the 750 ms save interval would add roughly **0.25–0.27 J** on the Nucleo, larger than the voltage-change saving. Stop streaming promptly; reset is not complete power removal. Correct sensor shutdown sequencing and the adapter's controllable states need validation.

Board-specific overhead:

- **ST-LINK is a separate MCU.** The indexed official schematic shows main `5V` through D2 and U10 feeding `3V3_STLK`, so unplugging debugger USB does not alone establish zero debugger draw. Its actual input current and selected source configuration must be measured. D2 isolation is a candidate investigation, not a verified rework recipe; check signal/reset back-power paths.
- The permanent power LED uses R23 = 820 ohms. Assuming a 2 V LED drop gives about **18 mW at 5 V**, versus **5 mW at 3.3 V**. Actual LED voltage varies. User status LEDs are assumed off except brief indications; their unspecified pulse durations are excluded.
- Ethernet is assumed in firmware General Power-Down: **3.2 mA at 3.3 V**, approximately 11 mW. Its reset-state reference is 31 mA, approximately 102 mW; unplugging the cable is insufficient. Remaining in that state for the whole cycle would add approximately **0.10 J at the battery** on the 5 V board. Time spent before firmware power-down adds proportionally.
- Six ADC-buffer channels add about **168 µA at 1.8 V**. USB controller EN is assumed low. Custom hardware omits these unused circuits.
- Miscellaneous switched peripherals/control circuits receive a 2 mW allowance; regulator overhead adds 1 mW on the Nucleo or 0.5 mW on custom hardware. These placeholders require replacement by a complete BOM/current budget, including the exposure potentiometer once selected.

Sources: [MB1940 C02 schematic, sheets7/9/10/13](https://www.st.com/resource/en/schematic_pack/mb1940-n657x0q-c02-schematic.pdf), [LAN8742A §§3.8.3 and5.4.2](https://www.microchip.com/content/dam/mchp/documents/OTH/ProductDocuments/DataSheets/DS_LAN8742_00001989A.pdf), [TSZ122 table3](https://www.st.com/resource/en/datasheet/tsz122.pdf), [TCPP03-M20 tables6/11](https://www.st.com/resource/en/datasheet/tcpp03-m20.pdf). Schematic topology was read from indexed manufacturer text; the full drawing was not visually verified. This evidence supports the estimate, not exact disconnect-pad instructions.

## Scope, uncertainties and validation

**Follow-up:** the [debugger-isolation investigation](nucleo-debug-isolation.md) distinguishes ST's individual-rail measurement provisions from whole-system battery measurement and records the candidate D2 and signal/sense disconnects. The debugger-isolated rows above remain conditional estimates until that separation is implemented and verified.

The custom example retains the same MCU load and cycle duration. Its savings come from supply conversion, removing unused hardware and camera gating. Lower clocks, sleep during NAND busy periods, shorter boot paths and different storage are further possibilities, not savings already claimed here. A compliant custom AON/core/AUX sequencing design remains necessary.

Startup capacitor charging, USB operation, separate RTC-backup energy and the button/RUN-divider energy are excluded. C14's 220 µF stores 2.75 mJ at 5 V or 1.20 mJ at 3.3 V; stored energy is not total energy drawn while charging. Initial inrush and phase transitions therefore need measurement. These omissions and unmeasured workloads mean the absolute figures can shift materially; the model is useful for choosing what to investigate first.

All configurations still target complete main-power shutdown between shots. This comparison does not demonstrate the 100 nA OFF-current requirement or improve it merely by lowering output voltage. At 12 V, the illustrative stock capture phase averages about 64 mA from the series pack; the custom example is about 34 mA. **Neither figure establishes CR2032 pulse capability or shots per battery pack**: cell impedance, voltage sag, usable capacity and reservoir design remain qualification work.

Validate one complete short-exposure cycle by measuring battery input energy, with separate readings for debugger powered/isolated, camera streaming/reset, and Ethernet before/after power-down. Capture startup, save and shutdown timing and supply dips. Use those measurements to replace assumptions in the script before deciding whether the 3.3 V board rework is worthwhile. Exact rework, source isolation and board revision checks remain in the [power-tree review](2026-10-14-power-tree-review.md).
