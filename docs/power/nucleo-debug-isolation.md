# Nucleo debugger isolation and power measurement

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

## Two useful test configurations

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
