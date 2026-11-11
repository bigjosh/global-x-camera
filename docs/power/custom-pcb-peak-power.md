# Custom-PCB peak power: first exploration

**November 11, 2026. Engineering estimate, not a measurement and not a decision.** The user asked to explore ways to reduce peak current demand on a custom PCB, so that four or five standard CR2032 cells can run it at 50 °F. Figures come from datasheet typical values and assumed converter efficiencies, calculated by [estimate_custom_pcb_peak_power.py](../../tools/estimate_custom_pcb_peak_power.py). Every assumption is marked `ASSUMED` in that script. Battery inputs and the source model are in [punch-list item PL-01](../review/2026-11-10-pcb-readiness-punch-list.md).

**Updated the same day** with the sensor figures from the [VD56G3 datasheet](../../datasheets/camera/VD56G3_DS12968_datasheet.pdf), DS12968 Rev 12, which the user supplied.

## Sensor facts from the datasheet

Typical supply current by state (Table 13), and the maximum over process, voltage and temperature (Table 14):

| State | 1.8 V I/O | 1.15 V core | 2.8 V analog | Total |
|---|---:|---:|---:|---:|
| Reset | 0.013 mA | 2.1 mA | 0.038 mA | 2.5 mW |
| Software standby | 0.013 mA | 3.3 mA | 0.043 mA | 4 mW |
| Follower mode, 0 fps | 5.5 mA | 43 mA | 13.5 mA | 97 mW |
| Leader mode, 30 fps | 6.8 mA | 49.5 mA | 17.4 mA | 120 mW |
| Streaming, 60 fps | 8.5 mA | 57 mA | 22.8 mA | 145 mW |
| Streaming, 60 fps, maximum | 11 mA | 86 mA | 25 mA | about 189 mW |

- The sensor draws 97 mW when it is streaming-ready but reading out no frames, and readout adds about 48 mW on top. This model takes the 0 fps row as the level during a long exposure. The datasheet does not state that case directly, so it is an inference.
- Figure 23 shows the supply currents stepping up at the start-streaming command and reaching the full level about 4 ms later.
- Figure 24 shows a first analog-rail transient of about 106 mA carrying 3.5 µC, lasting tens of microseconds. Local decoupling covers it.
- Supplies and clock may come up in any order with XSHUTDOWN low; power-down is software standby, then XSHUTDOWN low, then supplies in any order (sections 7.3 and 7.4). This confirms the repo's earlier second-hand record.
- The datasheet is short-form. It has no register detail, so it does not say whether a lower link or PLL rate reduces the 0 fps current.

## Result

Power drawn from the pack, in watts, for three power trees and two ways of clocking the MCU.

- **Tree A:** 3.3 V main rail; sensor core (1.15 V) on an LDO from 1.8 V.
- **Tree B:** 1.8 V main rail for everything except the sensor's 2.8 V; MCU core from the internal SMPS; sensor core on an LDO from 1.8 V.
- **Tree C:** as B, but the MCU core and the sensor core each get a buck from 1.8 V.
- **Clocking "today":** the boot ROM's 400 MHz profile throughout, as the firmware runs now.
- **Clocking "matched":** sensor link and MCU clock tree halved during readout; otherwise the 64 MHz internal oscillator with the PLL off, and the MCU asleep during the exposure and while the NAND programs each page.

| Phase | A, today | B, today | C, today | A, matched | B, matched | C, matched |
|---|---:|---:|---:|---:|---:|---:|
| Boot (ROM loading) | 0.12 | 0.13 | 0.12 | 0.12 | 0.13 | 0.12 |
| Exposure, MCU asleep | 0.22 | 0.22 | 0.19 | 0.19 | 0.18 | 0.15 |
| Readout, about 11 ms | 0.35 | 0.34 | 0.30 | 0.31 | 0.31 | 0.27 |
| Readout, sensor at its maximum | 0.42 | 0.42 | 0.36 | 0.39 | 0.38 | 0.32 |
| Save, NAND: loading a page | 0.11 | 0.11 | 0.11 | 0.05 | 0.05 | 0.05 |
| Save, NAND: page programming | 0.15 | 0.16 | 0.15 | 0.09 | 0.09 | 0.08 |
| Save, SD card typical | 0.28 | 0.29 | 0.28 | 0.28 | 0.29 | 0.28 |
| Save, SD card at datasheet maximum | 0.55 | 0.55 | 0.54 | 0.55 | 0.55 | 0.54 |

What the pack can deliver at 50 °F before its voltage collapses (PL-01 model; the 1.4× cold factor is assumed):

| Pack | Short burst, fresh / half used | Sustained, fresh / half used |
|---|---:|---:|
| 4 cells | 0.46 / 0.34 W | 0.21 / 0.16 W |
| 5 cells | 0.57 / 0.43 W | 0.27 / 0.20 W |

**Reading, with tree C and matched clocking.**
- **Short exposures on four cells: inside the ceilings.** Readout is 0.27 W against a burst ceiling of 0.34–0.46 W, and the NAND save is at most 0.09 W against 0.16–0.21 W sustained.
- **Long exposures on four cells: at the edge.** The exposure itself is a sustained 0.15 W, which is 72% of the fresh sustained ceiling and 95% of the half-used one. The readout that follows then needs the reservoir, because the pack is already loaded.
- **Long exposures on five cells: inside,** at 57–76% of the sustained ceiling.
- **An SD save does not fit on four cells at any setting.**

**Exposure limit.** The user will accept a maximum exposure of 0.5 s on coin cells if necessary, possibly depending on temperature. That does not lower the 0.15 W; it halves how long the cells must hold it. Cell resistance grows with the length of the load, from about 14 Ω per cell over tens of milliseconds to about 30 Ω over two seconds, so a shorter exposure sees a lower resistance and a higher ceiling. The repo has no figure for 0.5 s.

## What each lever is worth

| Lever | Effect on the peak | Cost |
|---|---|---|
| SPI NAND instead of SD | Save falls from 0.28 W typical (0.55 W at the card's maximum) to 0.15 W | NAND firmware does not exist yet |
| MCU sleeps on a slow clock while the NAND programs; page loads run on the internal oscillator | Save falls from 0.15 W to about 0.09 W | Firmware; a timer wake per page |
| MCU sleeps on a slow clock during the exposure | Exposure falls from 0.19 W to 0.15 W | Firmware; the receiver must be ready again before readout |
| Sensor core from a buck, not an LDO off 1.8 V | Readout falls by about 0.035 W, exposure by about 0.025 W | One more converter |
| Halve the sensor link rate and the MCU clock tree together | Readout falls by about 0.03 W on the MCU side | Readout takes about 10 ms longer; the sensor-side effect is unknown; the firmware currently insists on the ROM clock profile |
| 1.8 V main rail instead of 3.3 V | About zero | See below |
| Internal core SMPS instead of a core buck | Readout rises by under 0.01 W | Saves a converter |
| Reservoir of order 100 µF on the switched side | Carries the readout burst above the sustained level | About 3 ms of start-up |
| Fifth cell | Raises every ceiling by 25% | Card area; 16.5 V input |

## The three ideas the user raised

**A specific low-power NAND.** This is the largest lever for the save. The stored datasheets give 23 mA typical (30 mA maximum) for the Macronix MX35UF and 25 mA typical (35 mA maximum) for the Winbond W25N04KW, both at 1.8 V: about 45 mW at the part. The candidates differ in program time, 250–600 µs per page typical, which changes energy rather than peak. The NAND also programs each page by itself, so the MCU can sleep meanwhile; an SD card offers no such gap.

**Everything except the 2.8 V sensor rail from one 1.8 V buck.** On power alone this is worth almost nothing against a 3.3 V main rail with efficient converters: trees A and B differ by 7% at most, and B is not the lower of the two. The MCU's own VDD draws about 0.3 mA, so its voltage hardly matters. What matters is linear drops. The one that counts is the sensor core: 57 mA at 1.15 V taken through an LDO from 1.8 V costs about 0.035 W at the pack during readout, so that rail should have its own buck. A 1.8 V main rail is still attractive for other reasons: one converter fewer, VDD and the always-on supply rise together by construction, and the sensor, NAND and ADC connect without level shifting. Its costs are that an SD card cannot signal at 1.8 V without a separate 3.3 V bank, and the firmware's bank set-up changes.

**Slowing the MCU to match the data streams.** Worth doing, with one refinement. The datasheet gives 9 mA of core leakage, 33 mA for the clock tree at full rate and 21 mA for the CPU at 600 MHz. The CPU itself is the smaller part, which agrees with the [isolated-Nucleo measurement](evidence/2026-10-28-isolated-nucleo/README.md) where slowing only the CPU from 400 to 50 MHz saved 13 mW. The saving comes from slowing the whole clock tree and gating peripherals, and from sleeping. The readout clock can only fall as far as the sensor's data rate allows.

## Where the peak sits afterwards

In the sensor. During readout it is about 0.19 W of the 0.27 W at the pack, and during a long exposure about 0.13 W of the 0.15 W. Board-level changes cannot reduce it further; only the sensor's own settings, the reservoir or more cell area can.

## Unknowns that matter most

1. **Whether the sensor's armed current can be reduced** by a lower PLL or link rate. That needs ST's register and integration manual, which is not in the repo.
2. **Whether a long exposure really sits at the 0 fps figure.** Inferred here, not stated by the datasheet.
3. **MCU peripheral and CSI receiver current.** Assumed 15 mA of core current and 10 mA at 1.8 V. Neither is in the MCU datasheet text.
4. **The cold factor.** Assumed 1.4× on cell resistance at 50 °F.
5. **Converter efficiency** from 12–16.5 V down to 1.8 V at 30–120 mA. Assumed 85%.

## What this asks of the PCB

- A 1.8 V SPI NAND footprint as the storage that the CR2032 path depends on.
- A separate buck for the sensor core, and an efficient path to 2.8 V. Size the sensor rails for the datasheet maxima: 86 mA core, 25 mA analog, 11 mA I/O.
- A fifth cell position if it can be placed, since long exposures are marginal on four.
- A series link in every rail so each of the assumptions above can be measured on the board.
- The reservoir footprint.
- Nothing in hardware stands in the way of the clocking changes; the capture path already runs without the crystal.
