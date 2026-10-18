# Nucleo debugger isolation and power measurement

## D2 and R23 removed: CN8-only functional operation — October 18

The user reports **D2 and R23 physically removed**. Only these two changes are confirmed; other assembly-guide rework remains pending. No instrument or firmware action was performed for this follow-up.

CN8 can still supply the MCU/camera with CN10 unplugged. Use either the established CN9.3 → JS110 → CN9.2 path with every CN9 shunt absent, or the normal CN9 **3–4** selection without the JS path. Disconnect LTC/external target power in this USB-only configuration. Removing D2 opens the direct target-5V-to-U10 debugger supply route; removing R23 only disables LD1.

The remaining interface does not establish zero debugger leakage, but the specific connected pins must be distinguished from generic clamped inputs. The visually verified C02 sheet13 connects target reset through R75 (0 Ω) to debugger **PA6**, target VDDIO through R65/R70 (10 kΩ/10 kΩ) to **PA0**, and target 5 V through R73/R74 (5.1 kΩ/10 kΩ) to **PB1**. DS11853 Table10 classifies **all three as FT**, including the two ADC-capable sensing pins. Nominal sense levels are 1.65 V and 3.31 V. The other connected debug/UART GPIOs are FT or FTf as well. Table13's FT absolute maximum is VDD + 4.0 V; normal 3.3 V signals do not by themselves exceed it when debugger VDD is zero. Table14 notes that positive injection does not occur below the specified FT maximum. These tables also carry supply-condition footnotes; absolute maximum ratings are not a functional or powered-off leakage guarantee. [F723 datasheet, Tables10/13/14](https://www.st.com/resource/en/datasheet/stm32f723ie.pdf).

**Powered-off input clarification:** [AN4899 Rev4, §§4.2, 5.2.2 and 6.3](https://www.st.com/resource/en/application_note/DM00315319-.pdf) explicitly distinguishes FT inputs from ordinary TC inputs. FT inputs lack the conventional protection diode to VDD, and the generic guidance permits up to 3.6 V when VDD is zero, subject to the device datasheet. Therefore a 3.3 V signal is not automatically an overvoltage merely because debugger VDD is zero. Figure16 on page26 shows a leakage path through an enabled pull-up and separately labels the upper diode **TC only**; it is not evidence that every FT pin necessarily backfeeds through an upper ESD diode. Enabling an analog peripheral can connect a parasitic VDDA path and removes FT behavior. This depends on the analog peripheral switch, not merely GPIO analog mode. The PA0/PB1 sense inputs and the transition from running ST-LINK firmware to an unpowered debugger therefore deserve specific checks; their actual power-down configuration has not been established.

The 5 V sense tap has limited voltage margin: 5.00 V gives 3.31 V, while a hypothetical 5.50 V source gives 3.64 V before resistor tolerance. The latter exceeds AN4899's generic 3.6 V guidance but remains below F723's 4.0 V absolute maximum at VDD = 0; neither figure establishes reliable leakage behavior. Do not apply a raw 5 V signal to the unpowered debugger or extrapolate its powered 5 V tolerance to VDD = 0.

**Recommendation:** keep CN10 independently powered for development after D2 removal. CN8-only operation with CN10 absent remains an unqualified functional-test configuration, not a blanket electrical-safety or zero-leakage assurance. If qualifying it, check **3V3_STLK**, interface loading/current, DUT NRST release and autonomous capture, including debugger power transitions. A debugger rail near zero alone does not prove zero current into that rail or ground. For complete debugger disconnection, open the actual signal and sense links in addition to D2; software cannot guarantee an unpowered device's pin configuration. Passive divider loads remain even without pin leakage. No new bench test was performed for this clarification. Historical statements below about D2 still supplying ST-LINK describe the board before this reported removal.

## Selected assembly path — October 18

The user has selected LTC3621 at **5.0 V**, retaining the Nucleo's downstream converters, and Alliance NAND on Arduino-header bit-banged GPIOs. Follow the [consolidated assembly guide](../prototype/nucleo-assembly-guide.md) and its verified ST assembly-location diagrams. **D2 and R23 are now reported removed**, breaking the main target-to-debugger supply and disconnecting LD1. For the planned LTC configuration, keep all CN9 shunts absent and feed CN9.2 from LTC through the JS110 if desired. That replaces the CN8/CN9.3 source; keep CN8 unplugged while using LTC. The USB-only configuration above remains a separate functional-testing option.

The guide separately identifies **U24** removal for Ethernet load elimination. Leave the unused U14 converter's supply links alone: its EN pull-down already disables it with R22 absent. The NAND conversion removes SB24/R88/R89 and uses 1.8 V VDDIO4. These are not direct-3.3 V changes to the main supply tree.

Retain separately powered CN10 and the qualified PE1 recovery path during development. **This does not qualify complete debugger isolation:** R65/R70 draw approximately 165 µA from powered target 3.3 V and R73/R74 draw approximately 331 µA from target 5 V; SWD, reset and other interfaces remain. Full OFF-state/backfeed qualification and standalone energy measurement remain separate work. The current RAM-only firmware behavior below is unchanged.

## Current firmware readiness for power characterization — October 17

The installed guarded v41 default-exposure image boots from NOR and acquires its first image autonomously. It does not require a host debugger command to start capture. The [qualified sequencing report](../../reports/Camera%20lane%20startup%20mismatch.md) identifies the exact installed image and its normal/recovery tests. Removing CN10 has not yet been tested with this exact image; autonomous cold captures so far retained the physical debugger USB connection without issuing debugger commands during capture.

The current firmware is a timing/integrity diagnostic, not the final take/save/shutdown cycle. After the first native RAW10 frame is in RAM, it reads diagnostic registers, stops the snapshot pipe, disables idle CSI data receivers, and commands the sensor into software standby. It then scans all 3,055,360 image bytes for statistics and checksums, emits completion event 40, and stays in `for (;;) __NOP();`. It neither enters MCU sleep nor removes camera/board power, and it does not save the frame to NAND. Debug access and RAM contents remain available while powered. See the [exact archived capture source](../../firmware/capture-timing/evidence/2026-10-17-receiver-ready/source-objects/443318cf3089950611bdc944f23384c53a72da2371dbbd6da49be60e83636275.c#L602).

In the final recorded default-exposure run, the first frame completed about 45.68 ms after reset release; final diagnostic completion was about 485.51 ms. Integrating through event 40 includes sensor stopping, diagnostic work and the full-buffer checksum. Current after that event is awake diagnostic idle, not product shutdown current. [Recorded marker timing](../../firmware/capture-timing/evidence/2026-10-17-receiver-ready/captures/v41-final-normal-02/timing.json).

The proposed CN10-unplugged measurement removes the debugger's independent USB source, but **does not isolate ST-LINK**: target `5V` can supply its regulator through D2, downstream of the JS110. This can move debugger consumption into the measured current. CN9 shunts are already absent and do not interrupt D2. Signal/sense connections also remain. The [supply topology below](#supply-path-and-proposed-separation) remains the isolation constraint; no D2 or interface rework has been performed or qualified.

An unchanged-board acquisition trace is useful as a whole-board bring-up baseline. Debugger-free DUT energy requires verified separation of the debugger supply and interface paths; final cycle energy additionally requires the intended post-capture shutdown/storage firmware. These are distinct steps. No new power measurement or firmware change was performed for this readiness review.

**October 17 measured update:** the user moved JS110 IN+ to **CN9 pin 3** and connected a second USB source to **CN8**, retaining OUT+ at CN9 pin 2 and all CN9 shunts absent. This source stayed near 4.99 V while the target was off and restored the target rails on every trial. NRST was initially stuck low; one ST-LINK `HWRSTPULSE` released it. Three subsequent recorded cycles booted autonomously, with **15.20–15.43 ms from NRST rising to PD0**, and about 13 seconds with both measured rails below 0.1 V beforehand. No debugger command occurred during those cycles. The roughly 50 ms hold did not recur, but its original cause is unresolved. See the [complete evidence and limits](../../firmware/boot-timing/bench-results-2026-10-17.md). This establishes the present bench cycling path, not full debugger isolation or production energy performance.

**October 16 measured update:** CN9 current-path insertion and Saleae rail/GPIO probes support the [first-GPIO timing experiment](../../firmware/boot-timing/bench-results-2026-10-16.md). Two manual ST-LINK USB power-ups reached PD0 about 63 ms after the first 4.50 V target-rail crossing, including about 50 ms with NRST held low. JS110 disconnection removed target power while its input stayed near 4.92 V; reconnecting the load caused the upstream source to collapse. A USB reconnect restored it. Automatic power cycling and the source of the reset hold remain unresolved; do not treat this setup as qualified debugger isolation.

**PWR STATUS follow-up:** the user reports LD4 turns solid red when the CN9 target connection is opened and remains red after reconnection. This identifies ST-LINK's overcurrent-shutdown indication; the trigger remains unresolved. A retained controller fault is consistent with the behavior, but is not a proven latch inside the auto-retry eFuse. See the [LED finding and recovery evidence](../../firmware/boot-timing/bench-results-2026-10-16.md#pwr-status-turns-red-when-cn9-is-opened). USB replug is the demonstrated recovery; CN9 alone does not reset ST-LINK.

**October 15 status:** the Nucleo has arrived and the [RAM-only camera test](../../firmware/bringup/README.md) captures images successfully over ST-Link. The user has a Saleae Logic Pro 8 and Joulescope JS110 available for timing and power measurements. Start with external timing markers on the existing USB-powered setup; supply measurement boundaries and debugger isolation remain to verify. No power-circuit rework or additional voltage approval is implied.

**October 14, 2026.** The user asked to establish how to isolate the debug portion of NUCLEO-N657X0-Q for realistic power measurements. This is a documented investigation and proposed rework plan, not a claim that hardware has been modified or qualified. It supplements the [energy comparison](power-cost-comparison.md) and [power-tree review](2026-10-14-power-tree-review.md). The goal is that the camera's battery does not supply ST-LINK, and that a connected debugger cannot keep the camera powered after shutdown.

## What ST provides

UM3417 Rev4 provides **individual MCU-rail measurement points at CN12**, rather than a documented switch that removes the complete debugger. Remove the relevant zero-ohm bypass and measure the voltage across the precision shunt that remains. For example:

| Measurement | Bypass removed | CN12 pair | Remaining shunt |
|---|---|---|---:|
| External core converter input | R28 | 1–2 | 0.33 ohm |
| Core supply, external converter mode | R40 | 3–4 | 0.05 ohm |

Use `I = Vshunt / Rshunt`; 5 mV across 0.05 ohm means 100 mA. Do not insert an ammeter across an intact parallel shunt and expect it to measure all current. Input and output measurements of the same converter must not both be counted as independent loads.

These points exclude the debugger's separate supply branch, but they do not measure complete camera energy. CN9 selects the board's source. JP3 is STLINK reset, not supply disconnection. No debugger-off jumper or breakaway procedure is documented. For an external CN1 probe, ST instructs keeping embedded ST-LINK running. [UM3417 Rev4, §§7.3.3, 7.4.1, 7.4.4](https://www.st.com/resource/en/user_manual/um3417-stm32n6-nucleo144-board-mb1940-stmicroelectronics.pdf).

ST staff also explicitly confirm the R40/R41 voltage-measurement procedure in [Measuring Current on NUCLEO-N657X0-Q](https://community.st.com/t5/stm32-mcus-boards-and-hardware/measuring-current-on-nucleo-n657x0-q/td-p/809142). Thus the user's expectation of measurement provisions is correct; whole-system battery isolation needs additional work.

## Supply path and proposed separation

The official MB1940 C02 schematic's indexed sheet13 identifies two diode-fed inputs to U10, the debugger's ST730M33R regulator:

```text
Target board 5 V ── D2 ──┐
                         ├── U10 ── 3V3_STLK ── debugger MCU and LEDs
Debugger USB VBUS ─ D1 ──┘
```

**D2 is the candidate to open for the main debugger-supply separation.** D1 would retain debugger-USB power. This is circuit inference from the schematic, not an ST-published low-power modification. Prefer reversible removal or lifting one D2 terminal, with a removable series link if practical. Preserve the original diode and its polarity when restoring the connection; replacing D2 with a wire is not the same circuit.

**October 17 convenience review:** the recommended minimal modification for active-capture power measurements is to lift one end of D2 or remove it, then keep CN10 connected so D1 supplies the debugger independently. Keep all CN9 shunts absent and the existing CN8 → CN9.3 → JS110 → CN9.2 target path. This removes the main target-to-debugger supply branch while retaining programming/recovery access. No equivalent debugger-power jumper was found; JP3 only resets ST-LINK. U10 has an enable input, but its board connection has not been visually verified, so grounding EN is not a supported alternative. D2's exact physical position and delivered-board connection still require confirmation before rework. The official indexed sheet 13 was rechecked; a bounded direct download of the full drawing failed, and no physical location is inferred from the schematic.

After this proposed change, check for residual target-rail powering with the JS110 output off and CN10 connected. Signal and sensing paths remain, so removal of D2 alone is main-supply separation, not a qualification of zero backfeed or 100 nA shutdown current. No diode removal or new power measurement has yet been performed.

CN9 also connects `5V_STLK` to the target when its 1–2 jumper is fitted. During separately powered bench measurements, that connection must remain open so debugger USB does not supply the camera. Target-USB, external supply and any other source paths must match the chosen test configuration. Exact external 5 V injection and source-isolation wiring remain in the power-tree review.

**October 15 clarification — CN9 completely open, external power applied directly to `5V`:** the schematic still shows the path `5V → D2 → U10 → 3V3_STLK → debugger`. D2 connects to the global `5V` net, not `5V_STLK`; this branch never passes through CN9. Sheet9 identifies CN9's common side as `5V` (pins2/4/6), with `5V_STLK` on pin1. Removing the source-selection jumper therefore does not remove D2's separate feed. This was independently rechecked against official indexed sheets9/13; delivered-board population and physical continuity remain to verify. The source-selection connector and the debugger supply diode solve different isolation paths.

Opening D2 alone does **not** disconnect the target-facing signal and voltage-sense networks. They can load the camera or introduce unintended powering depending on pin type, direction and supply state. Do not assume every interface pin has the same clamp behavior, or claim a quantified leakage from the schematic alone. JP3 cannot remove these physical connections.

## Holding ST-LINK in reset to release its outputs

**October 17 follow-up:** JP3 does not disconnect debugger power, but holding it asserted is a useful candidate for making the debugger's target-facing GPIOs high impedance. With D2 open, keep CN10 supplying ST-LINK and fit JP3 throughout acquisition; retain the CN8 → JS110 → target supply and absent CN9 shunts. Remove JP3 to restore debugging. ST-LINK USB/debug access will be unavailable while reset is held. This is a proposed test configuration, not a completed hardware test or a zero-current isolation claim.

The indexed MB1940 C02 schematic identifies JP3 as `STLK_NRST`, separate from DUT `NRST`. The principal target-facing signals use ordinary STM32F723 GPIOs: SWDIO PF9/PH7, SWCLK PH6, SWO PD2, JTDI PF8, target reset PA6, UART PG9/PG14 and optional MCO PA8. [RM0431 §6.3.1](https://www.st.com/resource/en/reference_manual/rm0431-stm32f72xxx-and-stm32f73xxx-advanced-armbased-32bit-mcus-stmicroelectronics.pdf) specifies floating inputs during reset for these GPIOs. The debugger MCU's own SWD pins PA13/PA14 are separate, at reserved CN7; their reset pull settings must not be confused with the DUT-facing SWD interface. The named PB3 JTAG-return alternative is also documented as floating at reset.

ST explicitly documents held STLINK-V3EC reset as a GPIO high-impedance mechanism on another board in [UM3255 §7.1.3](https://www.st.com/resource/en/user_manual/um3255-discovery-kit-with-stm32wba55cg-mcu-stmicroelectronics.pdf). That supports the mechanism but is not an MB1940 measurement guarantee: UM3417 itself describes keeping the embedded debugger running for an external probe. The recommendation here is an inference from MB1940 wiring and F723 reset behavior, to be checked by target reset/rail/capture observations. No documented host command that guarantees release of every debug, UART and sensing connection has been established.

High impedance removes active GPIO drive; it does not remove passive sense loads, pin leakage or capacitance. R65/R70 and R73/R74 remain connected regardless of GPIO mode. Their exact divider currents are not claimed without a verified wire topology. The F723 [DS11853 Rev9 Table61](https://www.st.com/resource/en/datasheet/stm32f723ie.pdf) permits input leakage up to ±1 µA under its normal powered conditions; that specification is not a measurement here, a 100 nA bound, or an unpowered-chip guarantee. Many interface pins are five-volt-tolerant, so a universal upper-ESD-diode backfeed model is also unjustified. Keep ST-LINK powered independently for this initial held-reset test rather than assuming an unpowered debugger is electrically disconnected.

Before accepting the configuration for active-cycle measurements, verify DUT NRST can release, the camera still captures, and measured target rails discharge with the JS110 output off. Precision shutdown-current isolation would still require separating the remaining physical interface/sense paths. D2 removal and the JP3 test are both still pending; this review made no hardware or firmware changes.

## Interface paths to verify on the actual board

These are **inspection candidates from indexed official schematic sheets3 and13, not a final remove-parts recipe**. Verify the delivered revision, actual population, pin-to-pad continuity and every branch before rework. A resistor associated with an interface is not automatically proof that removing it disconnects every branch.

| Interface | Components/nets identified | Proposed treatment for fully standalone battery testing |
|---|---|---|
| SWD data and clock | R60 / `MCU.SWDIO`; R27 / `MCU.SWCLK` | Establish a reversible open circuit at the verified boundary. |
| SWO and JTAG input | R25 / `MCU.SWO`; R54 / `MCU.JTDI`; target-side SB22 on JTDI | Include connected paths even if the application does not use tracing/JTAG. |
| Virtual COM serial | R26 / STLINK receive; R24 / STLINK transmit | Disconnect both directions for standalone qualification. |
| Target reset | R75 / `NRST` | Separate debugger reset output while preserving target reset circuitry and external probe access. |
| Target-voltage reference | `VDDIO`–LNK3–`T_VCC`; R65/R70 sensing network | Verify and open the target-to-debug sense path. LNK3 construction and exact resistor placement remain unverified; do not assume it is a removable jumper. |
| Target 5 V detection | R73/R74 / `T_PWR_EXT` | Verify the divider's source-side element and remove its target load for complete isolation. |
| Debugger clock output | R45 and target-side SB37 / MCO | Keep MCO disconnected; verify the independent target clock works. |

Reference: [MB1940-N657X0Q-C02 official schematic](https://www.st.com/resource/en/schematic_pack/mb1940-n657x0q-c02-schematic.pdf). The manual documents the target's independent 48 MHz crystal as the default, with SB37 open; camera firmware must not rely on the debugger's MCO clock. [UM3417 §7.5.2](https://www.st.com/resource/en/user_manual/um3417-stm32n6-nucleo144-board-mb1940-stmicroelectronics.pdf).

Full target-interface disconnection will disable the onboard debug/serial connection until restored. Prefer a recoverable arrangement, or plan to use CN1 with an external probe once the embedded interface is electrically separated. The stock-board manual's instruction to keep embedded ST-LINK running still applies to an unmodified board; using an unpowered, still-connected debugger is not a documented alternative.

## Reversible JS110 insertion — October 16

This section preserves the original ST-Link-USB-powered hookup. It was superseded on October 17 by the [CN8 source below](#board-source-using-the-second-usb-connector) after the ST-LINK source tripped during reconnection. The original arrangement replaced the **CN9 STLK source-selection jumper on pins 1–2** with the Joulescope JS110 current path. It does not select an LTC3621 output voltage.

| JS110 terminal | Connection |
|---|---|
| IN+ | CN9 pin 1, `5V_STLK` from the ST-Link USB power switch |
| OUT+ | CN9 pin 2, common target-board `5V` rail |
| IN− | Board GND, for example CN5 pin 6 |
| OUT− | Board GND, for example CN5 pin 7 |

Disconnect board USB/external power before wiring. Remove the CN9 1–2 shunt and leave all other CN9 pairs open. Keep the source and return leads short. Power the JS110 through its own host USB, select automatic current ranging, and reconnect only the Nucleo's ST-Link USB at CN10; target USB CN8 and external VIN/5V feeds remain disconnected. Leave boot configuration as already selected for RAM development. The JS110 replaces the jumper; do not leave a parallel jumper that bypasses it.

Flow: `CN10 USB → board eFuse → CN9.1 → JS110 IN+ → current shunt → OUT+ → CN9.2 → target-board regulators/camera`. ST-Link also has a direct USB supply branch, so this setup keeps the probe available while switching the main target feed.

The pin mapping is corroborated by [UM3417 Rev4 §7.4.1 and Arduino connector table](https://www.st.com/resource/en/user_manual/um3417-stm32n6-nucleo144-board-mb1940-stmicroelectronics.pdf) and indexed [MB1940 C02 schematic sheet 9](https://www.st.com/resource/en/schematic_pack/mb1940-n657x0q-c02-schematic.pdf): pin 1 is `5V_STLK`, 3 is `5V_USB_SNK`, 5 is `5V_VIN`, and pins 2/4/6 share `5V`. Ground points are CN5 pins 6/7. A usable drawing could not be downloaded in this pass, so no physical left/right orientation is claimed. Identify pin 1 on the board; with all sources disconnected, CN9 pin 2 can be checked for direct continuity to CN5 pin 5 (`5V`). JS110 terminal roles follow its [user guide Rev1.3 §6](https://download.joulescope.com/docs/JoulescopeUsersGuide/JoulescopeUsersGuide_v1_3.pdf). This is a documented hookup recommendation, not confirmation the user has wired it or that measurements passed.

**Measurement boundary:** current through CN9 includes the target-board regulators, MCU, camera and other downstream board loads. It is not isolated MCU current or a final-product energy result. D1 supplies the debugger directly from USB, but D2 diode-ORs the measured target 5V into the same debugger-regulator input and could share some debugger load; do not claim complete debugger exclusion. D2 points from target 5V toward the debugger, so it is not itself a direct USB-to-target bypass when the target feed is off. No D2 removal or other component rework is required for this initial hookup.

Before calling JS110 on/off a true cold cycle, measure target rail decay with the JS110 off; powered SWD, UART, reset and sensing paths can retain residual power. Observe the switched target 5V and 3.3V, not just JS110's voltage display: on the standard front panel JS110 senses voltage at IN, upstream of its disconnect. Its display can therefore still show source voltage while OUT is disconnected. If the target remains powered, resolve the bypass instead of interpreting reset/reinitialization as a cold-power measurement.

## Further measurement configurations

### CN8 bypass audit — October 17

**CN8 is qualified for our timing experiments, not as an electrically isolated source for precision DUT energy measurements.** Removing every CN9 shunt does not disconnect the other USB circuits. This read-only audit supplements the earlier CN8 recommendation; no wiring, firmware or instrument state was changed.

The official [MB1940 C02 schematic, sheet 8](https://www.st.com/resource/en/schematic_pack/mb1940-n657x0q-c02-schematic.pdf) identifies these connections outside the JS110's current path:

| Connection | Measurement implication |
|---|---|
| CN8 VBUS → R157 → Q2 → SB1 → target `5V` | Separate USB source/provider power branch bypassing CN9. Normally disabled; actual gate state and leakage have not been measured. |
| VBUS → R80 140 kΩ → PA11 sense node; R81 10 kΩ to ground | Nominal 33.3 µA divider current and 0.333 V at PA11 for 5 V input. This is primarily current to ground, not a measured 33.3 µA feed into the MCU. Unpowered-pin injection remains unquantified. |
| CN8 D+/D− → U20 → MCU USB pins | Filter/protection remains connected; external data-line bias depends on the host/charger. |
| CN8 CC pins → U22 → MCU | Mode-dependent signal connection. |
| VBUS → U22 bias/sensing; VBUS → R76/Q3 indicator drive | Upstream consumption omitted by JS. The indicator LED's collector current is supplied by measured target VDD3V3. These loads are not themselves proof of MCU back-power. |

[TCPP03-M20 Tables 11–12](https://www.st.com/resource/en/datasheet/tcpp03-m20.pdf#page=11) specify provider gate OFF, CC switches OFF and IANA OFF in the EN-low reset state, while the consumer gate is self-biased from VBUS. The v41 source inspection found no PA7/EN configuration or TCPP03 programming; the expected state is therefore the default, not a demonstrated conducting Q2 bypass. Future USB-controller firmware can change that assumption. OFF switches do not establish zero leakage. U22's open-drain FLGn uses a target-powered pull-up, so its assertion loads the measured rail rather than actively supplying it from VBUS.

**Recommendation for the next precision power configuration:** unplug CN8 and move JS110 IN+ from CN9.3 to the independent regulated 5.0 V supply. Keep OUT+ on CN9.2, common ground and every CN9 shunt absent. This removes the CN8 influences without board rework. It does not resolve the separate D2/debugger/interface issue. This change is proposed, not performed.

The prior observed rail discharge and autonomous captures remain valid observations; they do not bound residual current or prove complete power accounting. Opening SB1 alone would only address the provider branch. A data-disconnected USB cable alone would only address D+/D−. Neither is complete CN8 isolation.

### Board source using the second USB connector

**October 16 follow-up:** the user has a bench supply but prefers a source accessible on the board. A circuit-supported alternative is **CN8 USB power → CN9 pin 3 (`5V_USB_SNK`) → JS110 IN+ → OUT+ → CN9 pin 2 (target `5V`)**. It requires a second USB cable/source, but no soldering. Leave every CN9 selector jumper absent, keep VIN disconnected, retain the common grounds and ST-LINK USB CN10, and move only the JS110 input-positive lead from CN9 pin 1 to pin 3. Power down for that current-path rewiring. This is an alternative to the independent bench-supply configuration below; its instruction to leave CN8 unplugged does not apply here.

CN8's sink path uses U22 TCPP03-M20 and Q1 through SB12, independently of ST-LINK's U6. The board manual specifies default dead-battery support. [UM3417 §§7.4.1 and 7.10](https://www.st.com/resource/en/user_manual/um3417-stm32n6-nucleo144-board-mb1940-stmicroelectronics.pdf), [schematic sheets 8 and 9](https://www.st.com/resource/en/schematic_pack/mb1940-n657x0q-c02-schematic.pdf)

TCPP03 tables 11/12 specify that with EN low, its consumer gate is enabled and powered from incoming VBUS even without the target supply. This supports keeping CN9 pin 3 powered while JS110 disconnects the target. The first-GPIO payload does not configure PA7 (U22 EN) or I2C. **Measured October 17:** CN9 pin 3 stayed near 4.99 V during each off interval; the measured target rails discharged and recovered. After the initial reset-release diagnostic, three captured cycles produced autonomous boot markers. See the record above for limits. Later firmware that changes USB power-controller state requires reassessment. [TCPP03-M20 datasheet §6.2](https://www.st.com/resource/en/datasheet/tcpp03-m20.pdf#page=11)

In that OFF/dead-battery state, TCPP03's overvoltage protection operates but its overcurrent protection does not. Use a protected 5 V USB source; this does not resolve the board's external-SMPS inrush warning discussed below. The debugger-power-sharing and signal-path limitations also remain. The earlier assertion about no verified convenient **raw ST-LINK VBUS** header still stands; CN9 pin 3 uses a different USB input.

### Separate 5 V source for repeated boot experiments

**October 16 proposal, pending supply selection and physical wiring:** feed the JS110 from an independent regulated **5.0 V** supply, replacing its connection to protected `5V_STLK`. This removes U6 and ST-LINK's source-enable decision from the target's main supply path. It has not yet been tested on this bench.

| Connection | Destination |
|---|---|
| External supply positive | JS110 IN+; disconnect its previous CN9 pin 1 connection |
| External supply negative | JS110 IN− / common board ground |
| JS110 OUT+ | CN9 pin 2, target `5V` |
| JS110 OUT− | Board GND; existing ground wiring can remain |
| CN9 selector jumpers | All absent; no direct source-to-target bypass |

Use a regulated, current-limited source. Power down while changing the current-path wiring. Leave target USB CN8 and VIN disconnected. Keep normal flash boot selected: JP1 and JP2 pins 1–2. ST-LINK USB CN10 can provide the debugger's own supply during target cycling; the JS110's host USB remains connected for API control.

Before repeated cycling, resolve the [existing external-SMPS bring-up warning](2026-10-14-power-tree-review.md): UM3417 Rev4 §7.4.3 warns of potentially damaging inrush when unused `VDDSMPS` and `VDDA1V8PMU` are not grounded, and states the board schematic omits that recommendation. Delivered-board compliance remains unverified. This does not establish why our source tripped, and a bench supply's current limit alone is not proof the condition is safe. Do not increase available current simply to defeat the observed protection response.

`CN9.1` and `CN15.8` carry protected `5V_STLK`, so neither bypasses the ST-LINK switch. `CN3.6`, `CN3.18`, `CN5.5`, and TP2 are target `5V`, not independent input sources. Raw `VBUS_STLK` exists upstream of U6, but no convenient header/test-point connection to it was verified; a board solder tap is not the selected approach. [UM3417 §§7.4.1, 8.1, 8.5 and 8.6](https://www.st.com/resource/en/user_manual/um3417-stm32n6-nucleo144-board-mb1940-stmicroelectronics.pdf), [schematic sheets 9 and 13](https://www.st.com/resource/en/schematic_pack/mb1940-n657x0q-c02-schematic.pdf)

The existing D2 branch can still supply or share the debugger-regulator load from measured target `5V`. D1 blocks reverse feed into raw USB through that diode-OR branch. This setup therefore permits separate supply control but does not establish debugger-free energy measurement or eliminate signal-driven residual power. No D2 rework is needed for the first cycling trial. Verify target-rail decay and restoration with the LP8, then verify flash-boot markers over repeated API-controlled cycles before calling the arrangement reliable.

### Measurement isolation goals

1. **Development measurements:** power ST-LINK from its USB connector and the target from its separate, measured supply; isolate the D2 branch and the CN9 STLINK-to-target source connection after confirming the circuit. Use CN12 to diagnose individual MCU rails. This retains debug capability and removes the debugger's main supply from the battery budget, but sense-network loading and debugger effects remain. It does not qualify true cold boot, final shutdown or 100 nA OFF current.
2. **Standalone qualification:** debugger USB unplugged, main debugger feed open, all connected target/debug signal and sense paths isolated, and firmware booting independently from NOR. Measure the complete main input upstream of LTC3621, including camera, storage, converter losses, startup and shutdown. Keep the RTC backup as the accepted separate budget. This is the configuration needed for final battery energy and main-path leakage claims.

For whole-system energy, integrate `Vbattery × Ibattery` across the complete cycle. Rail shunts are diagnostic tools, not a substitute for that measurement.

## Bring-up completion checklist

- Record the board reference/revision and obtain a visual schematic/PCB match; resolve the candidate links above into exact pad-level instructions.
- With all sources disconnected, verify continuity and source separation before any powered test.
- In development mode, confirm debugger USB cannot raise the target rail when the target source is off, and the measured target source does not supply the debugger's main rail. Treat signal-driven residual current separately.
- In standalone mode, confirm `3V3_STLK` stays unpowered with target power on, and confirm target rails remain off when the camera is shut down. A dark LED alone is not evidence of zero current.
- Confirm independent boot, camera capture/save and controlled shutdown without USB, debug clock or a debugger session; measure full-cycle energy and input-current waveforms.
- Measure the main-path OFF current at room temperature with the button released and target/debug USB absent; separately test USB-connected source transitions.
- Verify programming remains possible through the planned restore/external-probe path. Do not make an irreversible PCB cut merely to avoid these checks.

**Evidence limitation:** the manual and indexed official schematic were readable. The full schematic exceeds the web reader's size limit; direct HTTPS downloads from ST timed out, and old community attachment links redirect or have expired signatures. No usable schematic drawing was obtained in this pass. Consequently the supply topology and candidate interface map are recorded, but a visually verified pad-level modification and demonstrated electrical isolation remain open bring-up work. No native browser download/save dialog was invoked.
