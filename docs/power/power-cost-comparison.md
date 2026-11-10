# Prototype power cost: 5 V Nucleo, modified 3.3 V Nucleo, custom PCB

## November 6: 2.2-ohm input resistor tested

Three cold cycles with the user-installed 2.2-ohm series resistor reduced
median sampled peaks **6.140→1.743 A** initially and **1.311→1.051 A** at the
secondary startup pulse. All three images passed complete 25 MHz readback,
independent decoding and visual review. Sleep current remains **3.309 mA**;
first exposure is **24.58–25.27 ms** after measured current onset. Normal
firmware is unchanged. The target was left intentionally powered off.

Post-5-ms cycle energy ranged **168–263 mJ**, versus **159–169 mJ** previously.
Longer SD activity dominates the median increase; the closest-duration run
used about5.3% more whole-cycle energy. This does not isolate resistor loss.
Actual board-side voltage and MCU rail rise times remain unmeasured.
[Measured comparison, images, interpretation and final handoff](evidence/2026-11-06-series-resistor-tested/README.md).

## November 6: C17 removed, repeated startup comparison

The user removed **C17 / 10 µF**, with C14 and U42 already removed. Three
cold cycles on the unchanged normal firmware reduced the median JS110 sampled
peak from **6.497 to 6.140 A (5.5%)**, first-250-µs net charge from **0.18540
to 0.14588 mC (21.3%)**, and time above 5 A from **18 to 13.5 µs**. These are
fixed-10-A, native-2-MS/s observations on direct regulated 5 V, with the latest
three LOW-current runs as control. The preceding suspected-short runs are
excluded. Source-side voltage and instrument response do not qualify actual
target-rail extrema or LiPo operation.

Sleep current remains **3.310 mA**, versus 3.311 mA before removal. Post-5-ms
energy fell from a median 256.77 to 159.97 mJ, but SD transport shortened from
383.68 to 164.86 ms and accounts for that difference; this is **not a C17
whole-cycle energy-saving claim**. Firmware and SD format are unchanged.
[Three-run results, saved-image checks and measurement limits](evidence/2026-11-06-c17-removed/README.md).

## November 6: remaining input-capacitance candidates for a stiff LiPo

**Update after testing:** C17 has now been removed and tested as described
above. Its [verified underside locator](evidence/2026-11-05-inrush/cap-locations/c17-location.png)
remains available for reference. The next untested candidate is **C12 (10 µF)**,
keeping C28 (1 µF), because U14 is already
disabled and its output is disconnected in the fitted C02 configuration (R22
and R10 absent). **C12/C28 remain unchanged.** The principal nominal direct-input
inventory is now about 44 µF after C14/C17 removal; removing C12 would take it
to 34 µF, versus 54 µF after C14 alone. This is not the whole board's capacitance and does
not predict a 37% peak-current reduction. Effective ceramic capacitance varies
with bias, and removing caps changes the transient circuit itself.

An additional later experiment could reduce U17's C19/C23 pair from 20 µF to
10 µF, retaining the capacitor with the best local VIN/GND loop. This requires
layout confirmation and input/core rail startup, ripple and load-step tests.
TI says 4.7 µF is sufficient for most TPS62088 applications, but that is not a
board-specific guarantee. Keep U34's C76/C82, regulator output capacitors and
MCU/sensor bypass capacitors for now. A stiff LiPo lowers low-frequency source
impedance; its leads and protection/switch circuitry cannot replace local
high-frequency decoupling or regulator output-filter stability requirements.
[TPS62088 section 8.2.2.6](https://www.ti.com/lit/ds/symlink/tps62088.pdf#page=13),
[ST1S31 input-capacitor guidance](https://www.st.com/resource/en/datasheet/st1s31.pdf#page=16).

Full U14 input isolation would require R32, R33 **and C26** to be opened, with
no external feed across CN12.5/6; C26 bridges the same input nodes. LNK2 ties
the positive measurement node to 5V and is not another bypass into U14 VIN.
That three-part rework is deferred in favor of the simpler C12-only candidate.
The original candidate review did not change hardware or firmware; the later
C17 experiment above supersedes its prior untested status.
Capacitance reduction lowers charge demand; a controlled input ramp is still
the more direct way to bound the peak. Retest startup/shutdown rail sequencing
as well as image capture after any input-capacitance change.

## November 6: excess active current is absent after a suspected short correction

Three unchanged cold capture/save cycles now average **79.65–80.03 mA** and use
**256.56–260.89 mJ**, measured from 5 ms after current onset through the low
plateau. The previous approximately 331 mA / 1.03–1.04 J results had an extra
load that is now absent. During testing the user reported an inadvertent short
may have been fixed; its exact location and repair timing were not inspected.
C14 remains removed and normal firmware is unchanged. Do not use the abnormal
runs as the ordinary C14-removed power budget or attribute their offset to C14.
The final auto-range shutdown plateau is **3.311 mA at 4.99554 V**.
[Three-cycle comparison, controls and limits](evidence/2026-11-06-active-current/README.md).

C79 is a **1 nF, 2 kV Ethernet cable-termination capacitor**, not a power-rail
reservoir. Leave it fitted: removing it offers no relevant DC or supply-inrush
saving. No C79 removal is reported. The initial multiampere startup transient
remains a separate inrush issue.

## November 5: U42 removal and remaining sleep loads

The user reports successful U42 removal and **3.3 mA after sleep**. The November5 API check now independently confirms **3.31mA at4.995V**, or16.53mW, with direct regulated5V through JS110. This is about5.2mA below the earlier roughly8.5mA plateau, consistent with LD1117 bias, but is not a matched before/after isolation of U42 or a fresh MCU Standby-flag proof. Earlier U42-fitted estimates and measurements below remain historical. [New baseline, inrush capacitor audit, prepared experiments and missing-debugger boundary](evidence/2026-11-05-inrush/README.md).

The user subsequently clarified that the SD carrier power LED was **already removed**. Its removal date and individual saving were not supplied; do not count it as another available reduction.

Remaining-load review:

| Item | Evidence and expected scale | Tradeoff / next step |
|---|---|---|
| SD carrier power LED | User confirms already removed. Its historical individual current is unmeasured. | No further saving available from this removal; preserve signal pull-ups. |
| SD card and carrier supply | `sd_deinit()` disables the controller, not the supply. Historical disconnected/connected tests suggest an order0.5mA difference, but are not matched controls and do not isolate the former LED from card. | Next attribution: after a successful save and completed shutdown, remove only the card and observe the current change, leaving the carrier and wires intact. No measurement has yet been reported. Moving supply to AUX3.3V requires GPIO release/backfeed, cold-init and sequencing qualification. |
| ST-LINK voltage dividers | R73/R74=5.1k/10k draw331uA at5V; R65/R70=10k/10k draw165uA at3.3V. Main LDO passes the latter current, giving about496uA input total. | Do not remove them while relying on ST-LINK voltage detection. Tenfold ratio-preserving resistance could save about446uA ideally, but input leakage and ADC settling/recovery must be checked. No resistor substitution selected. |
| Main/AON regulator bias | U33/U23 LD39020:20uA typical no-load each. U14 already disabled; U34 and core are controlled by PWR_ON; U25 is unpowered with VIN unused/CN9 shunts absent. | No second U42-like unused milliamps regulator found. Keep these parts; confirm actual AUX/core rail collapse if unexplained residual persists. |

The last installed source leaves SD CMD/DAT pins as inputs with pull-ups after deinit, only CLK pulled down; the final normal Standby preparation does not introduce data-line pull-downs. Thus the carrier's10k data pull-ups are not established static-current loads. Ethernet, camera and analog-buffer supplies are auxiliary and should already be off in true Standby; their active-current reductions are separate from this3.3mA plateau. Do not attribute the remaining current entirely to intrinsic MCU Standby or to the already-removed SD LED.

Sources: [C02 schematic](https://www.st.com/resource/en/schematic_pack/mb1940-n657x0q-c02-schematic.pdf), [LD39020](https://www.st.com/resource/en/datasheet/ld39020.pdf), [ST1S31](https://www.st.com/resource/en/datasheet/st1s31.pdf), [divider audit](nucleo-debug-isolation.md), [carrier LED observation](../../firmware/capture-raw/evidence/2026-10-25-sd-fourbit/README.md), [current SD wiring](../prototype/sd-breakout-benchmark.md). No new hardware test, firmware change or further removal occurred.

## Earlier measured baselines

The latest [October 28 complete-camera comparison](../../firmware/capture-raw/evidence/2026-10-28-ethernet-powerdown/README.md)
qualifies Ethernet PHY power-down in installed normal firmware. Median energy
over the measured window fell **224.82→173.65 mJ (22.8%)**, while median cycle
duration changed **396.12→413.88 ms**. Median power during SD transport fell
**603.39→431.93 mW (28.4%)**; the approximately 8.66 mA shutdown plateau did not
improve. Each group has three cold cycles; card latency varies substantially.
The energy window begins 5 ms after current onset and ends at the low plateau,
so startup inrush and LTC/battery losses remain outside this comparison.

The preceding [October 28 isolated-Nucleo measurements](evidence/2026-10-28-isolated-nucleo/README.md)
identify **182.85 mW / 36.76 mA at 5 V** saved by Ethernet PHY power-down,
roughly half its matched awake board load. CPU-only 400→50 MHz division saves
13.31 mW but doubles energy per completed synthetic update; instruction cache
reduces energy per update 38.76%. The shutdown plateau is 8.0766 mA / 40.3322 mW,
with later retained Standby flags. Camera and SD were physically disconnected;
these are separate controls from the complete-photo comparison above. Normal
NOR was unchanged and JS output disabled at that historical checkpoint; use
AGENTS.md for the current bench state.

The preceding [aligned direct5V measurements and ablations](evidence/2026-10-28-aligned-ablation/README.md)
quantify phase energies, camera/SD overlap and incremental sensor/receiver
savings. The exact MCU-versus-regulator/board split remains unresolved; main
3.3 V and auxiliary 1.8 V branch currents are the next useful hardware measurements.
Component reference values below remain dated estimates, distinct from measured
results; their earlier unmeasured-Ethernet caveat is superseded by the isolated test.

## October 28: battery-side trace and remaining overhead

The user now reports **four series CR2032 cells → JS110 → LTC3621/DC1863A → target**. The supplied [startup screenshot](../../research_notes/Camera%20power/startup%204x2032%20via%20LTC.png) measures upstream of LTC, unlike the older target-5-V recordings. The user confirms no further power-removal work beyond D2/R23: **U24, the LAN8742 Ethernet PHY itself, remains fitted**. It is not a separate Ethernet regulator. Exact USB/source isolation and target contacts were not independently checked. No instrument action or firmware change accompanied this analysis.

The displayed pack-side voltage starts near 12.56 V and bottoms at 2.73 V; peak current is 280 mA. Approximate simultaneous points read visually are 70 mA at 8.3 V (0.58 W), 110 mA at 6.5 V (0.72 W), and 130 mA at 5.2 V (0.68 W). These are screenshot estimates, not raw-data integrations. Increasing current as voltage falls is consistent with a roughly constant-power load while the buck remains in regulation. All four series cells carry the full current. The recovery in voltage after the load falls suggests source impedance/polarization, not proof of permanent cell damage; holder, wiring and instrument drops have not been separated.

DC1863A specifies its 5 V output for **5.2–17 V input**. LTC3621 is a buck, so it cannot sustain 5 V from a 2.73 V input. The actual 5 V output was not recorded, and resets, image success, or precise firmware phases cannot be established from this screenshot. Its 800 µs soft start and 1 A output capability do not constitute coin-cell current limiting. [DC1863A Table 1](https://www.analog.com/media/en/technical-documentation/user-guides/dc1863af.pdf), [LTC3621 datasheet](https://www.analog.com/media/en/technical-documentation/data-sheets/ltc3621-3621-2.pdf).

| Contributor | What is established | Interpretation |
|---|---|---|
| Ethernet U24 | Still fitted; powered from auxiliary VDD3V3, which switches off in Standby. Active capture source contains no explicit PHY management/power-down sequence. LAN8742 reference is 103 mW in reset versus 11 mW in general power-down. Its reset releases with target NRST; actual subsequent state/current is unmeasured. | An order-0.1-W removable-load candidate, not a measured 103 mW attribution. At an assumed 90% auxiliary-buck efficiency, 103 mW corresponds to about 114 mW at target 5 V. |
| Camera sensor and adapter | VD56G3 full-resolution 60 fps reference: 8.5 mA at 1.8 V, 57 mA at 1.15 V, 22.8 mA at 2.8 V, totaling about 145 mW. The three adapter LDOs draw approximately 291 mW from 3.3 V for those loads. | About 146 mW of adapter LDO loss while operating at that reference. Efficient rail generation can reduce it, but cannot remove the sensor's own consumption. This is a streaming reference, not a measured one-shot energy. |
| Camera upstream rail | CN6.22/VDD_CAM receives auxiliary VDD3V3 through SB10. November 5 correction: the C02 BOM marks U42 fitted and only its output link SB31 not fitted; the alternative path does not supply the camera, but U42 remains powered from 5 V. | With an assumed 90% auxiliary buck, the 291 mW sensor-rail load is about 324 mW at 5 V, excluding oscillator and small losses. Do not model it as a main 5-to-3.3 V LDO cascade or omit the separate unused-U42 overhead below. |
| Unused camera LDO U42 (identified November 5) | LD1117S33TR input is directly on target 5 V; its output supplies only the local capacitor and open SB31 in the default C02 configuration. BOM population and schematic/ODB connectivity are verified; the delivered board has not been newly inspected. | Datasheet Table 6 gives 5 mA typical / 10 mA maximum quiescent current under its stated conditions, suggesting roughly 25 mW typical at 5 V. This is a candidate contribution to the residual board current, not a measured attribution or qualified removal saving. No rework performed. |
| SD supply | Current user-selected CN3.5 is main VDDIO through U33, the 5-to-3.3 V LDO; the previous CN5.4 supply was the auxiliary buck. | Ideal linear efficiency is 66%: for every 100 mA the card draws, 330 mW reaches it and 170 mW is dissipated by U33. This is a scaling example, not measured card current. Preserve main/AUX sequencing when considering a different supply. |
| MCU | Datasheet reference sums to about 62.5 mW across its rails at 600 MHz HSI, CoreMark in ITCM, peripherals disabled; core accounts for 53.5 mW. | Not our 400 MHz CSI/SDMMC workload, a lower bound, or a rail measurement. Core conversion, active peripherals, RAM/interconnect and external NOR add demand. |
| ST-LINK and power LED | D2 and R23 already removed. | Do not count removal of their main loads again as prospective savings. Signal/sense paths remain unqualified. |

Sources: [LAN8742 §5.4.2/Table 5-5](https://www.microchip.com/content/dam/mchp/documents/OTH/ProductDocuments/DataSheets/DS_LAN8742_00001989A.pdf); [VD56G3 Table 13](https://www.st.com/resource/en/datasheet/vd56g3.pdf); [camera adapter schematic](https://www.st.com/resource/en/schematic_pack/steval-cam-m0i-schematic.pdf); [Nucleo C02 schematic](https://www.st.com/resource/en/schematic_pack/mb1940-n657x0q-c02-schematic.pdf); [STM32N657 Tables 32/34/36/38](https://www.st.com/resource/en/datasheet/stm32n657x0.pdf). Board rail connections were also checked against the retained ST C02 manufacturing ODB++ data. Do not add these reference rows into a precise cycle budget: their operating conditions and active intervals differ.

The earlier [three-cycle 25 MHz reference](../../firmware/capture-raw/evidence/2026-10-25-sd25-crc/QUALIFICATION.md) measured about 226–230 mJ over 410–420 ms at the target-5-V branch, roughly 0.55 W average. It used earlier card/wiring conditions and excludes LTC input losses; it is context, not a matched control for this trace. The October 14 model below suggested approximately 40% lower energy on a custom board, but used hypothetical NAND timings and excluded inrush. It cannot establish a 40% overhead fraction here.

**Recommendation:** first quantify Ethernet removal or explicit power-down on a stable supply, then measure the camera and SD supply branches. Treat input inrush separately from sustained capture/save demand. Even substantial board savings leave a several-hundred-milliwatt camera/storage system plausible; a reservoir recharged with controlled battery current remains a candidate for direct coin-cell operation. No reservoir topology/value or additional board rework is selected here. Do not derive energy by multiplying the displayed average voltage and current: they are strongly correlated and need sample-by-sample power integration.

## Historical October 14 model

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
- The permanent power LED uses R23 = 820 ohms. Assuming a 2 V LED drop gives about **18 mW at 5 V**, versus **5 mW at 3.3 V**. Actual LED voltage varies. **D-41 update, October 15:** the model excludes the newly accepted flashing yellow load from power-up through capture/save and the 250 ms green interval after successful save. Published totals therefore omit both the indication energy and any additional powered-system energy during that interval. Recalculate after LED current/duty cycle and the MCU/rail state during green are defined; no revised measured energy is implied.
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
