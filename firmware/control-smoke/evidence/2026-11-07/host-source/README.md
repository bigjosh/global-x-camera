# Exposure knob RAM smoke test

This diagnostic exercises the user's November 7 exposure-knob wiring:

| Knob connection | Arduino contact | MCU function |
|---|---|---|
| Low track end | A3 / CN4.4 | PA2 push-pull LOW |
| Wiper | A4 / CN4.5 | PF3, ADC1 input16 through the onboard divider/buffer |
| High track end | A5 / CN4.6 | PH2 push-pull HIGH |

PC12, A4's digital companion, is input/no-pull. PF3 is analog/no-pull.
Default SB3/SB5 fitted and SB2/SB4 open are assumed; no I2C routing change.
The 3.3 V header voltage must not be applied to an unconditioned ADC pin.

`build.py --out <new-directory>` builds offline using the saved CubeN6 SDK
and local GNU Arm compiler. The resulting manifest binds code and copied
sources. No hardware API is imported. The normal capture firmware and NOR
are unchanged. This directory does not by itself prove a successful bench run.

Launch only from the existing reviewed RAM bridge after confirming the
exact UART recovery park and idle camera/storage. The probe checks the
inherited 400 MHz CPU clock profile, disabled caches/interrupt context,
and disabled CSI/DCMIPP/SDMMC2 clocks before ADC work. It asserts PD7 HOLD
before its checks, preserving power if the experimental latch is fitted.

The probe checks the VDDIO4 3.3 V range selection, monitors that bank and the
ADC analog supply for ready (bounded20ms waits), releases VDDIO4 isolation,
releases analog supply isolation via PWR ASV, selects ADC HCLK/32,
uses 12-bit single-ended software-triggered ADC1 channel16 with1499.5-cycle
sampling, and runs the vendor's bounded calibration routine. Calibration
can reduce usable analog full range; CALFACT is reported. These readings
are direct ADC conversion codes, with no knob-to-exposure mapping or
voltage-accuracy claim. A generous10ms excitation-settling delay precedes
sampling. There is no optimization of settling or power in this diagnostic.

**Supply-monitor limitation:** ES0620 Rev5 section2.2.29 says the VDDIO4
PVM monitor does not operate correctly. Its observed ready flag is diagnostic
only, not proof of a valid physical rail. This test relies on the board's
unchanged 3.3 V VDDIO4 wiring; the VRSEL check only checks configuration.
See the [power erratum record](../../docs/power/NOTES.md#2026-11-07--st-forum-guidance-distinguishes-direct-shutdown-historically-but-does-not-reconcile-the-current-limit).

## SRAM host interface

- Code/vectors: `0x34300000`; exact entry and terminal park in manifest.
- Stack: `0x343AF000` through `0x343B0000`.
- Request: eight32-bit words at `0x343C1F00`:
  magic`0x31544F50`, nonzero nonce, maximum sample count(1–36000),
  period in milliseconds(20–1000), zero, zero, zero, stop command(initially0).
- Status:64words at`0x343C2000`, manifest lists fields in order.
  Status magic`0x31434441`, version1, request nonce;
  STATE4means sampling,8means clean stopped,15means failure.
- For approximately10Hz sampling use maximum6000and period100.
- The host reads the256-byte status once and accepts a sample only when
  `SEQUENCE` equals the trailing sequence at word63 and both are even.
  RAW, MIN_RAW, MAX_RAW, SAMPLE_COUNT, MILLISECONDS and register
  snapshots are published together. The 12-bit digital full-scale is4095;
  actual end stops depend on supplies, conditioning, calibration and wiring.
- To stop, write`0x504F5453` to request word7(`0x343C1F1C`).
  The firmware stops the ADC, drives A5 LOW and parks awake with PD7 HIGH.
  Sample-limit expiry follows the same path.
- Error codes:1invalid request,2context,3clock profile,4camera/storage active,
  5DWT unavailable,6wrong VDDIO4 voltage range,7VDDIO4 not ready,
  8ADC analog supply not ready,10ADC init,11channel config,12calibration,
  13start,14conversion timeout,15stop; `0xF000|IPSR` means fault.
  FAIL_STAGE retains the preceding state, and CFSR/HFSR/HAL error are saved.

The helper sends no SD/NOR/camera commands, makes no reset or power-switch
request, and never enters Standby. It does not use the recovery UART, so the
local console can display SRAM readings via ST-LINK without occupying COM8.
RAM residency ends on reset/power loss; the unchanged FLASH program then boots.

This makes no promise that the external HOLD circuit bridges an NRST/reset
interval. The root bench owner must establish actual supply and recovery
conditions before launch and record the final hardware state afterward.

## Local console

`console.py launch --cli <programmer.exe> --build <frozen-build> --sha256 <hash>
--out <new-run-folder>` checks the exact installed UART park, executes the
existing reviewed SRAM bridge, verifies the full diagnostic readback and
starts the RAM test. It does not send UART recovery itself. The default
36000 samples at100ms expire after approximately one hour.

`console.py monitor --cli <programmer.exe> --session <run-folder>/session.json
--out <new-console-folder>` prints raw A4, min/max, sample count, endpoint
logic levels and error state, saving JSONL and the latest snapshot. Host
updates are slower than the MCU's10Hz sampling. This console owns ST-LINK
while open; close it before another debugger client. Ctrl+C stops monitoring
only, not the MCU diagnostic. The stop mailbox above ends the diagnostic
without resetting the board. Normal camera FLASH remains unchanged.
