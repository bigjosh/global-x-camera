# Nucleo debugger isolation and power measurement

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

CN9 also connects `5V_STLK` to the target when its 1–2 jumper is fitted. During separately powered bench measurements, that connection must remain open so debugger USB does not supply the camera. Target-USB, external supply and any other source paths must match the chosen test configuration. Exact external 5 V injection and source-isolation wiring remain in the power-tree review.

**October 15 clarification — CN9 completely open, external power applied directly to `5V`:** the schematic still shows the path `5V → D2 → U10 → 3V3_STLK → debugger`. D2 connects to the global `5V` net, not `5V_STLK`; this branch never passes through CN9. Sheet9 identifies CN9's common side as `5V` (pins2/4/6), with `5V_STLK` on pin1. Removing the source-selection jumper therefore does not remove D2's separate feed. This was independently rechecked against official indexed sheets9/13; delivered-board population and physical continuity remain to verify. The source-selection connector and the debugger supply diode solve different isolation paths.

Opening D2 alone does **not** disconnect the target-facing signal and voltage-sense networks. They can load the camera or introduce unintended powering depending on pin type, direction and supply state. Do not assume every interface pin has the same clamp behavior, or claim a quantified leakage from the schematic alone. JP3 cannot remove these physical connections.

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
