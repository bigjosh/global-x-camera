# PCB readiness review — hardware punch list

**Reviewed November 10, 2026**, before starting custom-PCB design. Hardware only; firmware items appear only where they change copper. Ordered by severity, most important first. Nothing here is decided: each item is for discussion, and the outcome of each discussion gets a dated entry in the owning `NOTES.md` when it is resolved.

## What was reviewed, and its limits

- The working system: NUCLEO-N657X0-Q + STEVAL-CAM-M0I1 adapter + CAM-6G3-073CLR, SD card on SDMMC2, LiPo latch, two pots, native USB PTP, as recorded through the November 10 wiring update.
- The recovered September KiCad design and its [47-finding review](../DESIGN-REVIEW.md).
- Measured evidence under `docs/power/evidence/`, `firmware/*/evidence/` (README records, not raw captures).
- STM32N6 primary documents stored in `datasheets/processor/` (DS14791 Rev 10, AN5967 Rev 5, AN6000, UM3234, RM0486).
- **Not reviewed from primary sources:** VD56G3 datasheet, CAM-6G3-073CLR schematic/STEP, STEVAL-CAM-M0I1 schematic, MB1940 Nucleo schematic and UM3417. None are stored in the repo, and this cloud session cannot reach vendor sites. Camera facts below are the repo's second-hand record of those documents.
- Battery-capability figures in PL-01 are my estimates from public cell datasheets and are labelled as such.

**Severity:** S1 = must be answered before schematic capture can start. S2 = a wrong answer means a dead board or a respin. S3 = material, but can be settled during schematic capture. S4 = improvement.

**Type:** C = clarification needed from you. P = problem or gap. I = improvement.

## Summary

| ID | Sev | Type | Item |
|---|---|---|---|
| PL-01 | S1 | C | Energy source and the CR2032 budget. Inputs settled November 11; cell count still open |
| PL-02 | S1 | C | What this board spin is for, and what is on it |
| PL-03 | S1 | C | Storage medium on the PCB (SD, SPI NAND or both) |
| PL-04 | S1 | P | The recovered KiCad design is not the system that works |
| PL-05 | S1 | P | Missing primary documents and tooling for doing the design here |
| PL-06 | S2 | P | STM32N6 main/AUX sequencing, shutdown order and rail limits |
| PL-07 | S2 | P | No power tree exists for either battery; rail currents were never measured |
| PL-08 | S2 | P | Latch and source selection as built are not transferable to the PCB |
| PL-09 | S2 | P | Camera: the adapter board's functions must move onto the PCB |
| PL-10 | S2 | P | Pin map and I/O voltage domains must be re-planned without the Nucleo's conditioning |
| PL-11 | S2 | P | The 50 ms requirement has never been measured end to end |
| PL-12 | S2 | C | Mechanical envelope: nothing closes at 5 mm yet |
| PL-13 | S3 | P | Boot flash, straps and a programming path without ST-LINK |
| PL-14 | S3 | P | SD electrical design (if SD stays) |
| PL-15 | S3 | P | USB: VBUS sense, PHY supplies, inrush |
| PL-16 | S3 | P | Battery monitoring and brown-out protection do not exist |
| PL-17 | S3 | C | User controls: real parts for the thumbwheels and the SPDT shutter |
| PL-18 | S3 | C | Indicators: three colours required, one LED in the old design |
| PL-19 | S3 | C | RTC and accelerometer: on this board or not |
| PL-20 | S3 | C | Board technology, fabricator and assembler |
| PL-21 | S4 | I | Bring-up and measurement provisions |
| PL-22 | S4 | I | Improvements worth deciding on now |

---

## S1 — needed before schematic capture

### PL-01 · Energy source: no numeric target defines "CR2032-viable"

**Situation.** Four CR2032 in series is the goal; the LiPo is a stand-in because peak draw is too high. The one CR2032 attempt collapsed the pack from 12.56 V to 2.73 V at 280 mA ([power notes, Oct 28](../power/NOTES.md)). No number says how low the peak has to go, so the PCB has no input-voltage range, no converter topology and no way to tell whether it succeeded.

**Measured today** (Nucleo, bench 5 V, 2.2 Ω in series, [Nov 6 evidence](../power/evidence/2026-11-06-series-resistor-tested/README.md)):

| Phase | Power at the 5 V input | Duration |
|---|---:|---:|
| Exposure and readout | about 0.62 W (123 mA), 1 ms peak 0.67 W | about 22 ms |
| SD initialisation and write | about 0.42–0.45 W | 165–382 ms write, plus 90–110 ms init |
| Board awake, no camera, no SD | about 0.185 W | — |
| Whole cycle | 168–263 mJ | 446–648 ms |

**Source model (added November 11).** Two anchors, both more direct than the vendor pulse ratings my first pass used:
- The October 28 trace ([screenshot readings](../power/power-cost-comparison.md#october-28-battery-side-trace-and-remaining-overhead)): 12.56 V open-circuit, then 70 mA at 8.3 V, 110 mA at 6.5 V and 130 mA at 5.2 V. That is a pack resistance of 55–61 Ω, about 14 Ω per cell, for fresh cells loaded for tens of milliseconds. It includes holders, wiring and the meter.
- The stored [Energizer sheet](../../datasheets/reference/CR2032_Energizer_reference.pdf), typical 2-second pulse resistance at 21 °C, read from its graph: about 30 Ω per cell fresh, about 40 Ω after 100–125 mAh, about 60 Ω after 150 mAh, then rising steeply.

A regulated converter is a constant-power load. A source of open-circuit voltage V and resistance R can deliver at most V²/4R; ask for more and the pack voltage collapses. At 12 V that ceiling is 0.60 W for 60 Ω, 0.30 W for 120 Ω, 0.23 W for 160 Ω and 0.18 W for 200 Ω.

**Reading of the October 28 collapse.** The Nucleo system needs about 0.62 W at 5 V, so roughly 0.7 W at the pack after the converter. That pack's ceiling was about 0.69 W. The load sat on the knee and the pack collapsed. Fresh cells at room temperature almost ran today's hardware; the shortfall is margin for used, aged and cold cells rather than an order of magnitude. The vendor pulse ratings (10 mA Duracell, 15 mA EEMB, 50 mA for Murata's high-drain CR2032R) describe conditions that preserve rated capacity and are more conservative than this.

**Figure of merit.** Collapse resistance, V²/4P at 12 V: the largest source resistance a configuration survives. Rows marked "model" are my estimates from datasheet typicals with assumed 85–90% conversion, not measurements.

| Configuration | Peak at the pack | Collapse resistance |
|---|---:|---:|
| Nucleo prototype today | about 0.69 W | about 52 Ω |
| Custom board, capture burst, no reservoir (model) | 0.27–0.34 W | 105–135 Ω |
| Custom board, SD save, typical card current (model) | 0.27–0.34 W | 105–135 Ω |
| Custom board, SD save, card at its datasheet maximum (model) | 0.53–0.60 W | 60–68 Ω |
| Custom board, SPI NAND save (model) | 0.15–0.21 W | 170–240 Ω |

For comparison the pack itself is about 57 Ω fresh for short loads, about 120 Ω fresh for 2-second loads, about 160 Ω half used, and higher when cold (no temperature data is in the repo).

**Consequences for the PCB.**
- The 100 nA OFF target stays. Capacitor leakage alone makes a large always-connected reservoir on the battery side impractical within it.
- A reservoir on the switched side of order 100 µF at pack voltage could carry the 22 ms capture burst and recharge well inside one second. It costs about 3 ms of ramp against the 50 ms budget.
- Storage choice (PL-03) matters as much as the regulators: the save lasts hundreds of milliseconds, where the higher 2-second resistance applies, and only the NAND row clears it with margin.
- Depth of discharge is not the limiter. Four cells hold about 9,500 J; 20,000 shots at 0.1 J use about a fifth of that. Temperature, cell brand and shelf age are the derating factors that matter.

**Settled by the user, November 11** ([owning note](../power/NOTES.md#2026-11-11--design-the-pcb-for-standard-cr2032-cells-at-50-f-without-further-nucleo-power-experiments)):
- Work down to 50 °F (10 °C); colder is a bonus.
- At most one shot per second.
- Standard cells, for example Energizer CR2032. The CR2032 was chosen as the most widely available primary cell that fits the 5 mm thickness. Other suggestions, including a mechanical generator, remain welcome.
- CR2032 holders go on this spin, accepting that they may prove unusable.
- A fifth cell is acceptable if it physically fits.
- No charger.
- No further power experiments on the Nucleo before layout: it differs too much from a custom board for more data to be worth taking. The four measurements proposed here on November 11 are withdrawn; the PCB itself is the experiment.

**Design case at 50 °F (my model).** Per-cell resistance: 14 Ω for short loads (the October 28 trace) and 30–40 Ω for 2-second loads (Energizer typical, fresh to half used), both multiplied by 1.4 for 50 °F. The 1.4 is my assumption; the repo holds no temperature data and the vendor sites could not be reached from this session. "Usable" is 70% of the ceiling.

| Pack | Capture burst: ceiling / usable | Save: ceiling / usable |
|---|---:|---:|
| 4 cells, fresh | 0.46 / 0.32 W | 0.21 / 0.15 W |
| 4 cells, half used | 0.34 / 0.24 W | 0.16 / 0.11 W |
| 5 cells, fresh | 0.57 / 0.40 W | 0.27 / 0.19 W |
| 5 cells, half used | 0.43 / 0.30 W | 0.20 / 0.14 W |

Against the custom-board model above (capture 0.27–0.34 W; SD save 0.27–0.34 W typical; NAND save 0.15–0.21 W):
- **Capture** is inside the ceiling on four cells with little margin. A switched-side reservoir of order 100 µF, or a fifth cell, gives the margin.
- **An SD save** exceeds the ceiling on four cells and is marginal at best on five.
- **A NAND save** sits at the ceiling on four cells and inside it on five, provided the MCU's awake power lands at the low end of the model. That number is the largest unknown.

The ceiling scales with the total face area of the cells, whatever their size or connection. Five CR2032 give 25% more than four.

**Consequences for this spin.**
- Rate the input for five fresh cells, 16.5 V. The LTC3621 studied earlier is limited to 17 V and is too close; a part rated 20 V or more is needed. Four cells alone would fit it.
- Lay out four cell positions, plus a fifth with a bypass link if placement allows. In board cutouts at about 22 mm pitch, four cells take about 42% of the card and five about 59% (PL-12).
- Keep a LiPo as the working source. Per the user it may occupy the holder area with the holders unfitted.
- Include the reservoir footprint.
- When the board exists, "CR2032-viable" is tested with real cells at 50 °F, or from a bench supply through a series resistor. On the model above that resistor is about 170 Ω for four fresh cells and 225 Ω half used.

**Further user inputs, November 11.**
- "5xcr3032" was a typo for five CR2032.
- If necessary the CR2032 holders can be left unfitted and their space used for a LiPo. The two sources are alternatives in the same area, not fitted together.
- The user expects further savings on a custom board (a low-power NAND, a 1.8 V main rail, slowing the MCU to its data streams) and asked for them to be explored. The [first exploration](../power/custom-pcb-peak-power.md) puts capture near 0.27 W and a NAND save at or under 0.09 W, inside the four-cell ceilings above; an SD save does not fit, and a long exposure is unresolved.

**Still open.**
- Four positions or five. Decide in the placement study.
- Whether holders should also accept the thinner CR2025 (2.5 mm), which is as widely sold and frees 0.7 mm of the thickness budget. Its pulse resistance against the CR2032 is unverified.
- Sensor current during a long exposure, which needs the VD56G3 datasheet (PL-05).

### PL-02 · What this board spin is for, and what is on it

**Situation.** The record allows two different boards: a credit-card, ≤5 mm product board, or a functional integration board that replaces the Nucleo wiring and is allowed to be thicker. They differ in connectors, layer count, part packages, debug access and risk.

**Recommendation.** Make this spin a functional board in the credit-card outline, with full debug and measurement access, and treat thickness as best-effort (see PL-12). It will carry a 264-ball BGA, a 0.35 mm-pitch camera connector and a new power tree, none of which has been built before; a second spin for the final envelope is likely either way.

**Need from you.** The goal of this spin, the quantity, and a yes/no on each block: microSD, SPI NAND, RTC, accelerometer, both knobs, three LEDs, USB-C, charger.

### PL-03 · Storage medium on the PCB

**Situation.** Everything that works uses an SD card (four-bit, 25 MHz). The specification still describes raw NAND, and D-46 (Alliance SPI NAND) is nominally in force, but the NAND was never wired and no NAND firmware exists. D-49 chose SD as "the immediate bring-up path" without claiming SD meets the retention, endurance or power-loss requirements. No decision exists for the custom board.

**Why it matters now.** The two options use different pins, voltage banks and supplies, and they differ by several times in peak power (PL-01). SD also takes 90–227 ms to initialise, so "storage full, take no photo" cannot be decided before exposure.

**Recommendation.** Fit both: a microSD socket on the SDMMC2 pins the firmware already uses, and a 1.8 V SPI NAND footprint on its own pins. The board then works on day one and can test the CR2032 path without a respin.

**Need from you.** SD only, NAND only, or both.

### PL-04 · The recovered KiCad design is not the system that works

**Situation.** `hardware/kicad` is the September Flux recovery. Against the working prototype it has a different camera wiring (one lane, no strobe, 1.2 V core), parallel NAND, a different battery and converter, the internal core SMPS, a 40 MHz crystal, a different boot flash on the wrong chip-select pin, and pins that collide with SDMMC2 (PC0, PC2, PC3, PC4 are LED and accelerometer there). Five blockers and 22 high findings remain open on it.

**Recommendation.** Start a new schematic from the hardware the firmware actually runs on (the Nucleo and camera-adapter subsets in use, plus the new power stage). Reuse verified symbols and footprints from the recovered library where they survive checking. Then close each of the 47 findings as fixed, carried over or superseded.

**Need from you.** Agreement on a new schematic rather than editing the recovered one.

### PL-05 · Missing primary documents and tooling

The new schematic of PL-04 would be derived from two of these documents (the Nucleo and camera-adapter schematics), and the camera pinout, rail limits and mechanics come from the others.

- Not in the repo: VD56G3 datasheet, CAM-6G3-073CLR schematic and STEP, STEVAL-CAM-M0I1 schematic, MB1940 schematic, UM3417.
- This cloud session cannot reach st.com, ti.com, analog.com, hirose.com, the distributors or JLCPCB.
- KiCad is not installed here. The repo's files are KiCad 9 format; the package available here is KiCad 7, which cannot open them. Without it I can generate files but cannot run ERC or DRC.

**Need from you.** Either add the documents to `datasheets/` and run ERC/DRC on your machine, or widen this environment's network access and let me install a matching KiCad.

---

## S2 — a wrong answer means a dead board or a respin

### PL-06 · STM32N6 main/AUX sequencing, shutdown order and rail limits

**Requirements** (AN5967 §3.5, DS14791 Tables 24–25):
- Main supplies (VDD, VDDA18AON) first; auxiliary supplies after PWR_ON rises.
- At power-off, auxiliary supplies discharge below 0.6 V **while main is still within operating range**.
- VDD is valid only at 1.62–1.98 V or 3.0–3.6 V. The band between is not an operating range.
- Rails must ramp, up and down, between 20 µs/V and 1500 µs/V.
- The power notes also record tight main-to-AON tracking at power-up (AON over its threshold within 250 µs of VDD).

**Situation.** The prototype floats HOLD just before Standby, so main and auxiliary supplies lose their source together and fall at whatever rate the leftover load and capacitance give. No rail waveform has been captured. The question posted to ST on November 7 had no reply in the record. The Nucleo itself has no hold-up or supervisor.

**Risk.** Out-of-order collapse is what ST warns can leave the device in an unstable state. On a board with small capacitors and a hard cutoff, the fall-rate limit is also missed by a wide margin.

**Recommendation.** Sequence in hardware: PWR_ON enables the auxiliary regulators, which have output discharge; main regulators are disabled a few tens of milliseconds after PWR_ON falls, also with discharge; the battery switch opens last. Put a test point on every rail.

**Need from you.** Whether to design to the ST sequence in full now (my recommendation) or wait for ST's answer.

### PL-07 · No power tree exists for either battery; rail currents were never measured

**Situation.** The prototype feeds a LiPo into the Nucleo's 5 V bus. No capture has been measured on the LiPo; the minimum working input voltage is unknown; a planned 4.2/4.0/3.8/3.6 V sweep was not run. The power notes read the auxiliary 3.3 V buck's datasheet curve as leaving regulation near 4.1 V input, and flag that reading as uncertain. The Nucleo tree is also wasteful: three of its five rails are linear from 5 V or 3.3 V, and by the repo's estimate the camera adapter draws about 291 mW to deliver 145 mW.

**Decisions needed.**
- Main VDD at 3.3 V (matches the firmware today) or 1.8 V (uses all of a single lithium cell, but changes bank setup).
- VDDCORE from an external buck as on the Nucleo, or from the internal SMPS as in the recovered design. The firmware never writes the SMPS or voltage-scaling registers, so the internal-SMPS path is untested.
- The core voltage setpoint. The Nucleo's actual value is not in the record; 400 MHz needs only the low setting (0.81 V nominal).
- How the three camera rails, the card rail and the USB PHY rail are derived and switched.
- A 1.8 V ADC reference. Firmware uses an external VREF+ and never enables the internal buffer.

**Recommendation.** For this spin keep the Nucleo's electrical arrangement as seen by the MCU (3.3 V main, external core buck enabled by PWR_ON), generated by efficient converters from a wide-range input. With a 3.3 V main and one LiPo cell, the usable battery window ends near 3.4–3.5 V and needs a lockout (PL-16).

### PL-08 · Latch and source selection as built are not transferable

Problems to solve in the PCB circuit:
1. **Reverse blocking.** A single P-FET conducts backwards through its body diode. With USB at 5 V and a LiPo at 3.7 V that charges the cell uncontrolled. With primary cells, any charging path is a safety issue; the stored Energizer sheet allows at most 1 µA of reverse current.
2. **Priority.** A 4×CR2032 pack sits above VBUS, so diode-OR logic picks the battery. "USB present" must force the battery path off in hardware.
3. **Gate voltage range.** One circuit spanning 3–13.2 V needs a FET that is fully on at −2.5 V and survives −13.2 V at the gate. The kit AO3401 is rated ±12 V (existing finding PWR-002).
4. **OFF leakage.** The kit FETs are specified at up to 1 µA each, ten times the whole 100 nA budget. Latch leakage has never been measured; the Joulescope position used cannot see the R1/Q2 branch.
5. **Press length.** The press must outlast firmware HOLD takeover, estimated at 25–30 ms and never measured. A short tap gives a partial boot and no photo.
6. **No off-delay.** With C1/D1 removed there is nothing to keep main power up while the auxiliary rails discharge (PL-06).
7. **Stuck on.** Nothing in hardware limits on-time. Besides a plain hang, the firmware deliberately parks awake with HOLD high on an ambiguous VBUS reading, on a low or noisy recovery pin (PE1, PE6) at boot, and when Standby is refused. On a battery board each of these drains the cells flat.
8. **USB mode drain.** With HOLD high under USB power, R1 draws about 37 µA from the battery.
9. **ESD.** The shutter contact connects directly to the Q1 gate.

**Recommendation.** Back-to-back P-FETs with nA-rated leakage; a VBUS-driven inhibit; a hardware limit on on-time, or the watchdog used as one; external pull-ups on the recovery pins; a low-leakage clamp at the button. One candidate to analyse for items 5 and 6 together: a gate-to-source capacitor on Q1 stretches a short tap, ignores battery insertion and delays turn-off after HOLD releases. It was in an earlier revision of the latch (C2) and needs simulating across 3–13.2 V before it is trusted.

### PL-09 · Camera: the adapter board's functions must move onto the PCB

**Situation.** The module does not plug into the Nucleo directly. The STEVAL-CAM-M0I1 adapter supplies three LDO rails, a 12 MHz oscillator, level translation and an XSHUTDOWN pull-up. That pull-up lets the sensor boot while the MCU is still in ROM, and the 23–25 ms time-to-exposure depends on it. Releasing reset from firmware instead would add about 6.5 ms.

**The PCB must provide.**
- 2.8 V, 1.8 V and 1.15 V rails that rise with main power, not under firmware control.
- A 12 MHz clock running before XSHUTDOWN rises (firmware PLL constants assume 12 MHz).
- A hardware XSHUTDOWN release that waits for rails and clock.
- Both CSI data lanes. The recovered design routes one; one lane cannot carry this mode.
- A deliberate P/N polarity choice. Firmware currently inverts all three pairs to match the adapter chain.
- I2C, strobe and reset at 1.8 V, either on a 1.8 V bank or through translators, with pull-ups sized for 1 MHz.
- A rebuilt J3 land pattern. The connector part is right for this module; the footprint has the known geometry fault (CAM-001).

**Also.**
- The firmware expects a cold sensor at every boot and never pulses reset; a warm MCU reset fails. In Standby the reset pin floats, so a bare pull-up releases the sensor again unless its rails are off.
- The strobe level translator on the adapter takes its direction from a sensor GPIO. A translator-free 1.8 V input removes that dependency.
- The start-up lane error is handled by a firmware workaround qualified on one board; it must be re-qualified on new copper.
- Pins 15/17/19/21 of the module are not established.
- Only sensor revision 0x31xx meets the timing.

**Need from you.** The primary documents (PL-05), and a physical check of which face the module's plug is on and which way the flex leaves.

### PL-10 · Pin map and I/O voltage domains

**Situation.** Several prototype signals reach the MCU through Nucleo or adapter circuitry that will not exist:
- Pot wipers go through dividers and buffers. The N6 ADC is a 1.8 V domain, so a pot excited from a 3.3 V GPIO would overdrive the input. On the PCB the pots must be excited from 1.8 V, ideally from the ADC reference.
- Camera I2C, strobe and reset are translated from 1.8 V to 3.3 V by the adapter.
- VBUS is sensed by an ADC (PA11) through a ÷15 divider, against fixed code thresholds.
- On the Nucleo, VDDIO2, VDDIO4 and VDDIO5 all run at 3.3 V and only VDDIO3 (boot flash) is 1.8 V. The sensor's I/O is 1.8 V, so the camera control pins (I2C2 on PB10/PB11, reset on PO5, strobe on PA0) cannot connect directly where they are.
- The recovery inputs (PE6, PE1) rely on internal pull-ups enabled by the first-stage code.
- The installed image always drives three diagnostic outputs (PD0, PE0, PD12) and bit-bangs the Ethernet PHY on PF4/PG11.

Some present assignments also sit on boot-ROM serial pins: PA2 (HOLD) is USART2_TX, PF6 is USART2_RX, PA0 (strobe) is UART4_TX, PE5/PE6 are USART1, and PG10 is the ROM's boot-failure output. UM3234 reads as though the ROM drives a TX pin only after it sees activity on RX, so this is a caution to check rather than a known fault.

**Recommendation.** Produce one pin table for the new board (signal, ball, function, bank, voltage, reset state, firmware change needed) and agree it before placement. Keep SDMMC2, XSPI boot, USB and CSI where the firmware has them; move only what the voltage domains force.

### PL-11 · The 50 ms requirement has never been measured end to end

**Measured.** About 25 ms from supply onset to first strobe, on a stiff bench 5 V supply, with no latch and no battery. Roughly 15 ms is ROM, 5.3 ms is the sensor's own start latency and 2.3 ms is I2C. The record puts remaining software headroom at 1–1.5 ms.

**Not in that number.** Latch closure, the ramp from a real battery, the USB-mode selector that now runs on every boot (a NOR load plus an ADC sample), and pot sampling.

**What the PCB controls.** Rail ramp to NRST release: about 1–2 ms on a stiff supply, 7.5 ms on the Nucleo's slow USB path, and unknown from CR2032 cells through a soft-started buck. That leaves about 25 ms for everything new.

**Recommendation.** Write the budget down as a table before choosing converters. Choose soft-start times of 1 ms or less, keep the NRST capacitor at or below 10 nF (the recovered design has 100 nF), add no supervisor that delays reset, and keep the sensor auto-start of PL-09.

### PL-12 · Mechanical envelope

**Situation.** The camera module is 4.68 mm tall. On a 1.6 mm board that is 6.3 mm, so the 5 mm target needs the module in a board cutout. A CR2032 is 3.2 mm before contacts. The USB-C part in the old design is about 3.2 mm above the board. No STEP of the module is in the repo, and the connector orientation was never validated. No placement drawing exists for lens, shutter, knobs, USB, card slot or cells.

**Need from you.** A sketch of where each user-facing item goes on the card, whether this spin must hit 5 mm, and a physical module to check orientation against.

---

## S3 — settle during schematic capture

### PL-13 · Boot flash, straps and programming path

- The ROM boots from serial NOR on PN6/PN1/PN2/PN3 in one-bit mode. The recovered design has chip select on PN12 (finding MCU-001).
- The Nucleo flash is a 1.8 V octal MX25UM51245G on a 1.8 V VDDIO3. The first-stage code refuses to run unless the ROM's exact clock and XSPI register values are present, and the NOR tools are specific to that part.
- The project has programmed no OTP fuses, and the firmware checks that two OTP bits are at their defaults before Standby. A new MCU should behave the same; verify on first power-up. Whether a 3.3 V flash would need an OTP setting is unresolved in the record.
- The custom board has no ST-LINK. Recovery today is a 1 Mbaud pulse train into PE6 from the ST-LINK serial port (or PE1 held low), followed by reprogramming over SWD. The board needs SWD pads, NRST, BOOT0 and BOOT1 access, those two recovery pins, and a way to power the board without the latch.

**Recommendation.** Use the same flash part and VDDIO3 voltage as the Nucleo for this spin.

### PL-14 · SD electrical design (if SD stays)

- The 25 MHz CRC failures on jumper wires went away with a clock probe, a 27 Ω series resistor or a twisted clock/ground pair. Root cause is unresolved. 50 MHz mode fails read CRC and is unqualified.
- Pull-ups today are the MCU's internal ones, absent during reset.
- The card is never power-cycled and stays powered through Standby. Card current has never been measured.

**Recommendation.** Series-resistor footprint at the clock source, external pull-ups on CMD and all four data lines, short referenced routing, and a decision on a card load switch (it removes the card from the Standby and OFF budgets, but firmware assumes a stable card rail at boot).

### PL-15 · USB

- VBUS sensing by ADC sits on the capture path of every shot. A divider to a digital input would remove it (PL-22).
- VDD33USB and VDDA18USB are auxiliary supplies and must follow PWR_ON.
- USB mode needs HSE at 48 MHz for the PHY reference. The recovered design has 40 MHz.
- USB inrush is unlimited today; R0 is only in the battery branch.
- Only High-Speed on Windows has been exercised.

### PL-16 · Battery monitoring and brown-out protection

No battery-voltage sensing exists; fault code 1 is reserved. The board needs a switched divider into the 1.8 V ADC (switched so it does not count against OFF current), a threshold checked under load before exposure, and a lockout so a save is never started on a collapsing supply. For a series primary pack, an undervoltage cutoff also guards against driving the weakest cell into reversal (existing finding PWR-007).

### PL-17 · User controls

- The thumbwheels are hobby parts with no datasheet, and their pin numbering is still unverified. The PCB needs a part with a drawing.
- The latch needs a momentary SPDT shutter switch. The switch in the old design (Omron B3U) is SPST and cannot drive the capacitor trigger.

**Need from you.** Part choices, or permission to propose them.

### PL-18 · Indicators

D-48 uses red, blue and green; fault codes need red. The recovered design has one yellow-green LED. Decide the product indicator set, and where it sits relative to the lens so it cannot leak into the exposure.

### PL-19 · RTC and accelerometer

Both are still required by the specification (D-06, D-20) and neither exists on the prototype; the metadata bytes are written as zero. If they go on this board, note that the old RTC pins (PE5/PE6) include the recovery input (PE6), the old accelerometer pins collide with SDMMC2, and the RTC backup tap on one cell of a series pack unbalances it slightly.

**Need from you.** In or out for this spin.

### PL-20 · Board technology, fabricator and assembler

D-35 deferred this. Layout cannot start without real design rules and a stackup. I recommend six layers with filled via-in-pad for the 0.8 mm BGA, rather than the four-layer working target, and a decision on who places the BGA and the 0.35 mm connector.

---

## S4 — improvements

### PL-21 · Bring-up and measurement provisions

Per-rail series links for current measurement, a battery-line link for the Joulescope, test points on every rail plus PWR_ON, NRST, HOLD and strobe, a force-on link that bypasses the latch, and a debug header that costs no leakage when unused.

### PL-22 · Improvements worth deciding on now

1. **HOLD from PWR_ON instead of a GPIO.** PWR_ON rises as soon as the main rails pass their power-on threshold, before any firmware, which shortens the minimum press from about 30 ms to a few. It falls at Standby, which starts the off-delay automatically. The cost: a board that never reaches Standby stays on, so it needs the hardware time limit of PL-08. The power notes already call this the preferred source; GPIO was chosen for the prototype only to stay on the Arduino headers.
2. **Digital VBUS detect** in place of the ADC sample, removing a NOR load and ADC start-up from every shot.
3. **Switch the camera rails off after readout and the card rail outside the save**, to cut energy and overlap of peaks.
4. **Keep the Nucleo's 48 MHz crystal and flash part** so clocks, USB and boot tooling carry over unchanged.
5. **Mid-mount USB-C and a thinner board** (0.8–1.0 mm) toward the 5 mm target.
