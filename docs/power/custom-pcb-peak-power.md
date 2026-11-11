# Custom-PCB peak power: first exploration

**November 11, 2026. Engineering estimate, not a measurement and not a decision.** The user asked to explore ways to reduce peak current demand on a custom PCB, so that four or five standard CR2032 cells can run it at 50 °F. Figures come from datasheet typical values and assumed converter efficiencies, calculated by [estimate_custom_pcb_peak_power.py](../../tools/estimate_custom_pcb_peak_power.py). Every assumption is marked `ASSUMED` in that script. Battery inputs and the source model are in [punch-list item PL-01](../review/2026-11-10-pcb-readiness-punch-list.md).

## Result

Power drawn from the pack, in watts, for three power trees and two ways of clocking the MCU.

- **Tree A:** 3.3 V main rail; sensor core (1.15 V) on an LDO from 1.8 V.
- **Tree B:** 1.8 V main rail for everything except the sensor's 2.8 V; MCU core from the internal SMPS; sensor core on an LDO from 1.8 V.
- **Tree C:** as B, but the MCU core and the sensor core each get a buck from 1.8 V.
- **Clocking "today":** the boot ROM's 400 MHz profile throughout, as the firmware runs now.
- **Clocking "matched":** sensor link and MCU clock tree halved during capture; the save runs on the 64 MHz internal oscillator with the PLL off, and the MCU sleeps while the NAND programs each page.

| Phase | A, today | B, today | C, today | A, matched | B, matched | C, matched |
|---|---:|---:|---:|---:|---:|---:|
| Boot (ROM loading) | 0.12 | 0.13 | 0.12 | 0.12 | 0.13 | 0.12 |
| Capture | 0.35 | 0.34 | 0.30 | 0.31 | 0.31 | 0.27 |
| Long exposure, MCU asleep | 0.29 | 0.29 | 0.25 | 0.26 | 0.25 | 0.21 |
| Save, NAND: loading a page | 0.11 | 0.11 | 0.11 | 0.05 | 0.05 | 0.05 |
| Save, NAND: page programming | 0.15 | 0.16 | 0.15 | 0.09 | 0.09 | 0.08 |
| Save, SD card typical | 0.28 | 0.29 | 0.28 | 0.28 | 0.29 | 0.28 |
| Save, SD card at datasheet maximum | 0.55 | 0.55 | 0.54 | 0.55 | 0.55 | 0.54 |

What the pack can deliver at 50 °F before its voltage collapses (PL-01 model; the 1.4× cold factor is assumed):

| Pack | Short burst, fresh / half used | Sustained, fresh / half used |
|---|---:|---:|
| 4 cells | 0.46 / 0.34 W | 0.21 / 0.16 W |
| 5 cells | 0.57 / 0.43 W | 0.27 / 0.20 W |

**Reading.** With tree C and matched clocking, capture is about 0.27 W against a burst ceiling of 0.34–0.46 W on four cells, and the NAND save is at most 0.09 W against a sustained ceiling of 0.16–0.21 W. An SD save does not fit on four cells at any setting. A long exposure is the open problem: see the first unknown below.

## What each lever is worth

| Lever | Effect on the peak | Cost |
|---|---|---|
| SPI NAND instead of SD | Save falls from 0.28 W typical (0.55 W at the card's maximum) to 0.15 W | NAND firmware does not exist yet |
| MCU sleeps on a slow clock while the NAND programs; page loads run on the internal oscillator | Save falls from 0.15 W to about 0.09 W | Firmware; a timer wake per page |
| Sensor core from a buck, not an LDO off 1.8 V | Capture falls by about 0.035 W | One more converter |
| Halve the sensor link rate and the MCU clock tree together | Capture falls by about 0.03 W | Readout takes about 10 ms longer; needs the sensor datasheet; the firmware currently insists on the ROM clock profile |
| 1.8 V main rail instead of 3.3 V | About zero | See below |
| Internal core SMPS instead of a core buck | Capture rises by under 0.01 W | Saves a converter |
| Reservoir of order 100 µF on the switched side | Carries the part of the capture burst above the sustained ceiling | About 3 ms of start-up |
| Fifth cell | Raises every ceiling by 25% | Card area; 16.5 V input |

## The three ideas the user raised

**A specific low-power NAND.** This is the largest lever for the save. The stored datasheets give 23 mA typical (30 mA maximum) for the Macronix MX35UF and 25 mA typical (35 mA maximum) for the Winbond W25N04KW, both at 1.8 V: about 45 mW at the part. The candidates differ in program time, 250–600 µs per page typical, which changes energy rather than peak. The NAND also programs each page by itself, so the MCU can sleep meanwhile; an SD card offers no such gap.

**Everything except the 2.8 V sensor rail from one 1.8 V buck.** On power alone this is worth almost nothing against a 3.3 V main rail with efficient converters: trees A and B differ by 7% at most, and B is not the lower of the two. The MCU's own VDD draws about 0.3 mA, so its voltage hardly matters. What matters is linear drops. The one that counts is the sensor core: 57 mA at 1.15 V taken through an LDO from 1.8 V costs about 0.035 W at the pack during capture, so that rail should have its own buck. A 1.8 V main rail is still attractive for other reasons: one converter fewer, VDD and the always-on supply rise together by construction, and the sensor, NAND and ADC connect without level shifting. Its costs are that an SD card cannot signal at 1.8 V without a separate 3.3 V bank, and the firmware's bank set-up changes.

**Slowing the MCU to match the data streams.** Worth doing, with one refinement. The datasheet gives 9 mA of core leakage, 33 mA for the clock tree at full rate and 21 mA for the CPU at 600 MHz. The CPU itself is the smaller part, which agrees with the [isolated-Nucleo measurement](evidence/2026-10-28-isolated-nucleo/README.md) where slowing only the CPU from 400 to 50 MHz saved 13 mW. The saving comes from slowing the whole clock tree and gating peripherals, and from sleeping. The capture clock can only fall as far as the sensor's data rate allows.

## Where the peak sits afterwards

Capture, at about 0.27 W for a few tens of milliseconds. The sensor is about 0.19 W of that with efficient rails: 22.8 mA at 2.8 V, 57 mA at 1.15 V and 8.5 mA at 1.8 V, the typical 60 fps figures recorded in the power-tree review. Board-level changes cannot reduce it further; only the sensor's own settings, the reservoir or more cell area can.

## Unknowns that matter most

1. **Sensor current during a long exposure.** Exposure can be set up to one second. If the sensor draws its streaming current throughout, that is 0.21–0.29 W sustained, above the four-cell sustained ceiling. The datasheet is not in the repo and could not be fetched.
2. **Sensor current against link rate and frame timing.** The 145 mW used here is the 60 fps figure. A search summary of ST's datasheet front page quotes about 120 mW typical and 4 mW in standby; unverified.
3. **MCU peripheral and CSI receiver current.** Assumed 15 mA of core current and 10 mA at 1.8 V. Neither is in the datasheet text.
4. **The cold factor.** Assumed 1.4× on cell resistance at 50 °F.
5. **Converter efficiency** from 12–16.5 V down to 1.8 V at 30–120 mA. Assumed 85%.

## What this asks of the PCB

- A 1.8 V SPI NAND footprint as the storage that the CR2032 path depends on.
- A separate buck for the sensor core, and an efficient path to 2.8 V.
- A series link in every rail so each of the assumptions above can be measured on the board.
- The reservoir footprint.
- Nothing in hardware stands in the way of the clocking changes; the capture path already runs without the crystal.
