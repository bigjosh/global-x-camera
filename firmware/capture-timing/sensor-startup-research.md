# VD56G3 startup investigation

Research date: October 17, 2026. This is source analysis and an experiment plan, not a measured latency result. Root alone controls the shared bench. The qualified bench unit reports model `0x5603`, revision `0x3110`, ROM `0x0420`.

## Source baseline

- [VD56G3/VB56G3 DS12968 Rev 12, October 2025](https://www.st.com/resource/en/datasheet/vd56g3.pdf), especially §§3.1, 3.4.10, 3.5–3.7, 7.3, and 9. The full 43-page PDF was readable through web extraction.
- [UM2602 Rev 8, April 2024](https://www.st.com/resource/en/user_manual/um2602-how-to-integrate-and-configure-the-vd56g3-vd66gy-and-vd16gz-devices-from-a-hardware-and-software-perspective-stmicroelectronics.pdf), §§5, 7, 13, 14.7.5, 18, and tables 45, 46, 49. Direct HTTPS and full web retrieval timed out; the relevant indexed sections were readable. This is not a claim to have reviewed all 72 pages.
- [Embedded VD6G driver](https://github.com/STMicroelectronics/x-cube-n6-camera-capture/blob/e9441cdbb5072a6d3bcef1a5ca4e4d80f850283a/Lib/Camera_Middleware/sensors/vd6g/vd6g.c), pinned `e9441cdbb5072a6d3bcef1a5ca4e4d80f850283a`; local `tmp/bringup/x-cube-n6-camera-capture`. Its local source was inspected directly.
- [Sensor middleware](https://github.com/STMicroelectronics/x-cube-n6-camera-capture/blob/e9441cdbb5072a6d3bcef1a5ca4e4d80f850283a/Lib/Camera_Middleware/sensors/cmw_vd56g3.c) and [camera middleware](https://github.com/STMicroelectronics/x-cube-n6-camera-capture/blob/e9441cdbb5072a6d3bcef1a5ca4e4d80f850283a/Lib/Camera_Middleware/cmw_camera.c), same revision.
- Nucleo BSP in that checkout: `STM32Cube_FW_N6/Drivers/BSP/STM32N6xx_Nucleo/stm32n6xx_nucleo_bus.{c,h}`; camera clock definition in `Lib/Camera_Middleware/cmw_io.h`.
- [ST Linux VD56G3 driver](https://github.com/STMicroelectronics/vd56g3-linux-driver/blob/aff46eb958f4e8dbab4a8b00abbe285421953cb4/vd56g3.c), `aff46eb958f4e8dbab4a8b00abbe285421953cb4`, corroborates the revision-aware patch exemption and readiness state machine. Do not copy GPL code into the embedded implementation.

## Requirements versus convenience waits

The datasheet permits the three sensor supplies and CLKIN to rise in any order, with XSHUTDOWN held low until they are valid. Its 20 µs typical POR release is not a complete startup bound. I²C supports at most 1 MHz and starts in fast-mode-plus, with 20 mA sink capability. CLKIN supports 6–27 MHz; this adapter configuration uses 12 MHz. These facts do not establish adapter rail/oscillator readiness.

UM2602 §5 says I²C responds only after READY_TO_BOOT; polling for an ACK can therefore replace an arbitrary post-reset sleep. Clock-dependent firewall work precedes this. BOOT then leads to SW_STANDBY, where clock/static/context settings are legal. START_STREAM follows configuration. No inspected source supplies a guaranteed XSHUTDOWN-to-first-integration maximum. Tables 45/49 give command and strobe controls; §§13/14.7.5 define line/exposure constraints. They do not establish that command acceptance is physical exposure onset.

| Existing code | Requested delay or work | Candidate change |
|---|---|---|
| `CMW_VD56G3_PowerOn` | 200 ms reset asserted, 20 ms released | One coordinated rail/reset sequence, bounded readiness polling |
| `VD6G_Init` | Another 10 ms asserted, 10 ms released | Remove redundant reset after successful probe |
| `VD6G_PollReg8` | Immediate read, then 10 ms per unsuccessful poll, approximately 500 ms budget | Short polls or independent work, retaining absolute timeout and error checks |
| Original capture application | `GetSensorName` then `Init`, each probing; three discarded settling frames | One initialization; receive and inspect the first frame |
| Linux reference power-on | 3.5–4 ms post-release sleep, then polling | Evidence that 20 ms is not universal; not a proven 3.5 ms minimum |

The measured cut selects the embedded driver's fast-boot branches, skipping firmware and video-timing uploads. Older silicon still needs its supported path. The minimal state progression uses `SYSTEM_FSM 0x0028` = 1, `BOOT 0x0200` ← 1 followed by ACK 0 and FSM 2, configuration, then `STBY 0x0201` ← 1 followed by ACK 0 and FSM 3. Keep command failures distinct from expected pre-readiness NACKs.

## Bus and configuration opportunities

The inspected Nucleo BSP defaults **I²C2 to 100 kHz**; no override was found in the pinned application's Makefile/headers. Its timing generator supports 400 kHz and 1 MHz. Test both after checking the actual adapter and signal margins. At 1 MHz, a one-byte register write needs at least 36 SCL periods (address, two-byte subaddress, data, each with ACK), versus 360 µs at 100 kHz. A one-byte register read needs about 45 periods. This is calculated wire time, excluding software and START/STOP spacing.

The BSP searches candidate timing fields during initialization. Once clocks and electrical assumptions are fixed, precompute the validated timing value. Record the actual peripheral clock and configured timing on every variant.

Use only documented contiguous ranges for burst writes. The middleware already supports 128-byte sequential writes and little-endian multi-byte register values. Good candidates are exposure/gain fields `0x044C..0x0459`, ROI words `0x045E..0x0465`, and GPIO bytes `0x0467..0x046E`. Do not fill gaps with guessed values or cross command/NVM regions. Read back candidate bursts before timing them.

The middleware's two lanes have all three differential-pair polarities swapped; preserve this working mapping. Removing apparent defaults without checking them can silently break reception. Prefer a commissioning/default-register snapshot and omission experiments one group at a time.

For unity gain, avoid the middleware's floating-point conversions and repeated limit reads on the critical path: analog code 0, digital code `0x0100`, after qualification. Configure manual mode before START; the middleware initially chooses AUTO. Keep test-pattern generation disabled and preserve dark calibration/defect correction unless image quality is separately characterized.

## Exposure conversion defect in the existing test

The embedded driver truncates line time to integer microseconds, then divides requested exposure by that truncated value. At line length 1236 and pixel clock 160.8 MHz:

- True line time: 7.686567 µs.
- `SetExposureTime(10000)` computes 1428 lines using 7 µs, approximately **10.976866 ms**, not 10 ms.
- Integer-rational conversion `ceil(us * pixel_clock / (line_length * 1000000))` gives 1301 lines, approximately **10.000224 ms**.

The outer `CEIL` does not recover precision already lost to integer division. Verify actual line length and clocks, read applied coarse exposure `0x0064`, and measure the exposure strobe. Requested exposure alone is insufficient evidence. The driver also retains a 21-line minimum; UM2602 documents different CCA short-exposure behavior. Avoid changing that separately from startup work without a dedicated measurement.

## Recommended experiment order

1. Log timestamps for camera enable/reset release, first I²C ACK, BOOT ACK, configuration completion, START write/ACK, first frame event, and frame completion. Add an independently qualified exposure-strobe edge.
2. Remove duplicate detection/reset and replace millisecond polling sleeps. Keep receiver setup and buffer readiness before first output.
3. Compare 100/400/1000 kHz with identical configuration; retain image checks and I²C error counts.
4. Replace floating-point/manual-control round trips and consolidate safe bursts. Overlap sensor readiness/BOOT waits with CSI, memory and other independent initialization.
5. Compare frame length at fixed exposure, gain and image geometry. This determines whether initial scheduling adds a frame-period-dependent delay; frame arrival by itself cannot answer it.
6. Inspect the first captured LED-panel image on every accepted variant, with retained bytes, histogram, spatial contrast and errors. Compare first versus later frames for clipping, calibration artifacts and lost/truncated data. Nonconstant bytes alone do not prove a valid frame.

Use the measured critical path to bound remaining savings. A few successful room-temperature boots cannot establish a production worst case or a global minimum over different clocks, power hardware and sensor revisions. The requested near-minimum confidence must name its tested configuration and unresolved measurement uncertainty.

## Follow-up: residual sensor delay and bounded tests

Root's v8a experiment reported approximately 6.464 ms from XSHUTDOWN release to READY and 5.3015 ms from START write completion to the first physical strobe. These are bench observations, not specified sensor minima. Consult the retained capture for the timing reference; nominal DWT clock conversion is not the external timebase.

Additional retrieved UM2602 Rev 8 sections: §13.1/pp17–18 (PLL constraints), §13.3/p20 (frame scheduling), §13.4/p21 (MIPI clock), §13.5/pp22–23 (sync), Table 45/p56 (commands), Table 46/p57 (clock settings), and Table 47/pp58–60 (static controls). Full direct PDF retrieval still timed out; these sections were inspected through ST's indexed document content.

**READY delay:** §5.2 attributes pre-I²C work to clock-dependent firewall activity. The clock settings become available only after BOOT. Therefore later PLL writes cannot accelerate that already-completed work. At the module's fixed 12 MHz clock, overlap with host code loading/receiver initialization is the supported software opportunity. A physically different 24 MHz source might reduce the delay, but proportional scaling is an unverified hypothesis, and changing this oscillator is a separate hardware experiment.

**Equivalent PLL test:** Table 46 establishes a completely documented contiguous range `0x0220..0x0227`: EXT_CLOCK (32 bits), PREDIV, POSTDIV, MULT, VT_DIV (one byte each). This resolves the earlier uncertainty about address `0x0225`; it is POSTDIV. The documented SW_STANDBY default is 12 MHz / 1 × 67 / 1, with VT_DIV=5. The embedded driver instead writes predivider 2 and multiplier 134. Both yield 804 MHz / 160.8 MHz pixels. Comparing the two is a valid experiment in PLL reference/lock behavior with unchanged nominal pixel timing. The hypothesis is that a doubled PLL reference could alter part of START latency; no inspected source promises it will.

| Experiment | Hold constant | What it distinguishes |
|---|---|---|
| PREDIV/MULT = 2/134 versus 1/67 | 12 MHz input, POSTDIV=1, VT_DIV=5, all capture settings | PLL reference/lock contribution; both configurations satisfy documented limits |
| FRAME_LENGTH 1500, 4336, 8000 | Full geometry, line length1236, coarse1428, unity gain | First-frame scheduler dependence; first verify exposure margin fits the1500-line setting |
| SW_STANDBY dwell0 versus5 ms after configuration | Identical register writes and START timing measurement | Any undocumented asynchronous settling before START; do not retain a dwell unless total reset→strobe improves |
| MASTER versus documented I²C follower | Same exposure/geometry; send trigger only after valid streaming state | Whether free-running startup scheduling adds avoidable latency; includes trigger transaction cost and needs qualified first-frame strobe |

For each PLL variant, retain post-start status registers `0x0034` EXT_CLOCK, `0x0038` SYSTEM_PLL_CLK, `0x003C` PIXEL_CLK, `0x0040` MCU_CLK (all32-bit), and `0x0044..0x0048` divider/multiplier bytes. These are calculated sensor status values, not an independent oscillator measurement. Retain physical START→strobe, strobe width, first-frame completion, error counts, and the actual LED image.

The documented command list provides no separate PLL-prestart command. GPIO_UPDATE does not document any clock-start effect. I²C follower mode has a documented trigger-to-strobe interval of40–70 µs, but that figure excludes entering STREAMING and therefore cannot replace the measured cold-start delay. Do not conflate it with a cold-start guarantee.

The normal10-bit mode is already at the recommended minimum line length1236 and nominal pixel clock160.8 MHz. Raising line length is discouraged by ST because of retention/performance effects. The9-bit ADC mode changes conversion quality, so it is not an accepted optimization for an unchanged10-bit acquisition requirement. Dark calibration and defect correction likewise remain enabled; no inspected source establishes them as removable fixed startup delays. The output interface has an independent firmware-managed PLL, so a later MIPI-rate sweep could isolate another clock contribution, but it requires matching receiver settings and adds less evidence than the equivalent main-PLL test above.

If these tests leave START→strobe unchanged, describe it as an experimentally invariant delay across the tested controls, not a proven silicon floor. The missing evidence is the sensor firmware's internal START sequence (including power/charge-pump/PLL settling), which the public register interface does not expose in the inspected material.
