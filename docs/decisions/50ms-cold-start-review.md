# Risks to the 50 ms cold-start exposure target

Reviewed October 15, 2026. **The principal risks are sensor revision/patch loading, the MCU's initial firmware load, battery/rail startup, and bounded storage-state recovery.** D-44/D-45 now establish the mitigation policy: newest sensor revision verified at factory commissioning, plus a minimal bootstrap and optimized staged loading. No measured end-to-end result establishes compliance; these constraints address the identified risks without proving a 50 ms result.

D-43 defers USB implementation details to firmware bring-up. This review covers D-04: physical shutter-button press, starting fully powered off, to **start of the saved exposure**. Exposure duration, frame readout, NAND payload writing/readback/commit, PNG encoding and the 250 ms green success indication occur afterward. Existing power, preservation, manual exposure and full-storage policies remain requirements. Board modifications stay paused until the board arrives.

## Accepted constraints — October 15

**D-44/D-45 — cold-start constraints, approved October 15:** use only the newest image-sensor revision, confirmed during factory commissioning. Optimize the bootstrap loader for minimum practical size and startup time, and optimize the size, placement and loading order of additional code. Start sensor initialization before loading code needed only later, such as NAND payload programming. Overlap later loading with sensor hardware waits where safe; do not require the full application to load before sensor initialization begins. Exact memory layout and staging remain implementation work, and the 50 ms target still needs measurement.

Factory commissioning must read and record actual sensor identity/revision and compare it with the expected newest revision for the production build; older or mismatched sensors do not pass commissioning. The inspected driver currently identifies cut 3 (`0x31` upper revision byte) as fast boot. This evidence is not a permanent definition of “newest”: update the expected identity and supported startup path when silicon changes, and verify that the qualified path still fits the timing requirement. No new runtime LED code or cold-start revision scan is prescribed by this commissioning decision.

The early boot stage must retain HOLD takeover, required rail/clock setup, sensor initialization and dependencies needed to meet exposure timing. Establish trustworthy storage availability before exposure under the existing full-storage policy; a small metadata/read path may therefore be needed early even when NAND payload-programming code loads later. CSI/DMA/buffer setup must be ready when the sensor produces data. Later loads must not block critical sensor transactions or overwrite executing code, active DMA buffers or required interrupt state. The loader strategy, code placement and use of hardware waits are to be measured and implemented; no specific overlay, DMA loader, FSBL byte limit or memory map is frozen.

## Risk priority and closure

| Priority | Risk | What closes it |
|---|---|---|
| 1 | **Sensor revision can make the target impossible.** ST's supported older cut-2 startup uploads firmware and video-timing patches; the cut-3 fast-boot path skips both. | D-44 requires the newest revision and commissioning verification. Qualify the supported fast-boot startup path and production revision controls. The older-patch path is outside the accepted build policy; do not skip required patches on a mismatched part. |
| 2 | **The ROM loads too much firmware before camera setup starts.** Initial serial-NOR loading is slower than the flash's eventual quad/octal operating mode. | D-45 requires a small fast bootstrap and optimized code placement/loading. Begin sensor initialization before loading later code such as NAND programming; measure actual cold ROM-to-first-code delay and critical-path loading. |
| 3 | **Cell sag, inrush, rail sequencing and clocks delay or restart startup.** A regulator's typical soft-start figure is not a complete-system startup bound. | Measure real cell/board rail ramps, reset, clock readiness and HOLD takeover over the intended battery/temperature range; obey required main/AON/AUX and camera sequencing. |
| 4 | **Storage recovery becomes a scan before every shot.** The camera must know a safe usable slot exists before taking a photo; full storage must reject capture. | Bound checkpoint discovery, validation and journal replay, including nearly full media and interrupted transactions. Do not use an unbounded whole-device scan on the normal shot path. |
| Cross-cutting | **Convenience initialization and serial waits consume the remaining margin.** | Overlap independent work, bound optional metadata reads, settle/sample the exposure ADC promptly, and make yellow indication nonblocking. Keep USB, PNG and unrelated peripherals out of battery capture startup. |

## Sensor evidence and a conditional hard limit

[ST UM2602 Rev 8](https://www.st.com/resource/en/user_manual/um2602-how-to-integrate-and-configure-the-vd56g3-vd66gy-and-vd16gz-devices-from-a-hardware-and-software-perspective-stmicroelectronics.pdf) distinguishes the CCA fast-boot variant from earlier devices and describes its exemption from firmware/video-timing uploads. Supplies and CLKIN must be valid before reset release; READY_TO_BOOT, BOOT completion and configuration still precede streaming. Fast boot does not mean zero initialization time.

The official ST driver was inspected at commit **`aff46eb958f4e8dbab4a8b00abbe285421953cb4`**. Its detection path uses revision register `0x0002`'s upper byte: `0x20` selects cut 2, `0x31` cut 3/fast boot. Its legacy power-on path uploads both arrays below; the fast-boot path skips both. [Driver](https://github.com/STMicroelectronics/vd56g3-linux-driver/blob/aff46eb958f4e8dbab4a8b00abbe285421953cb4/vd56g3.c).

| Legacy upload | Bytes in inspected initializer |
|---|---:|
| [Firmware patch 2.28](https://github.com/STMicroelectronics/vd56g3-linux-driver/blob/aff46eb958f4e8dbab4a8b00abbe285421953cb4/vd56g3_patch_cut2.c) | 11,000 |
| [Video-timing patch revision 17](https://github.com/STMicroelectronics/vd56g3-linux-driver/blob/aff46eb958f4e8dbab4a8b00abbe285421953cb4/vd56g3_vtpatch.c) | 6,092 |
| Total | **17,092** |

Reproduction: strip C comments, count comma-separated entries in `patch_cut2[]` and `vtpatch[]`, including the four `VT_REVISION` entries. The VT descriptor sizes also total 6,092. These are array bytes, not source-file lengths.

**Calculated payload-plus-ACK lower bound:** `17,092 × 9 / 1,000,000 = 153.828 ms` at 1 MHz I²C; at 400 kHz it is 384.57 ms. Addresses, transaction overhead, commands and all other startup work add time. Thus this supported legacy path cannot satisfy 50 ms from fully off. This documents why the older revision is excluded under D-44; it is not a finding that the ordered module uses that revision. Actual units still need the required identity/commissioning check.

[CAM-56G3 DB5264 Rev 3](https://www.st.com/resource/en/data_brief/cam-56g3.pdf) identifies CAM-6G3-073CLR as a VD56G3 module, but does not guarantee its silicon cut. Read the actual identity and retain lot/revision evidence. The historical VD55G0 cut-1/cut-2 patch calculations in the September camera review are for a different sensor and must not be reused here.

The inspected Linux driver's 3.5–4 ms post-reset wait, status-poll cadence and long timeout are implementation choices, not a guaranteed MCU startup budget. Qualify the selected embedded driver and sensor state transitions. Fixed gain and manual exposure remove the need to wait for autoexposure convergence; ensure the requested setting applies to the first saved exposure.

[VD56G3 DS12968 Rev 12](https://www.st.com/resource/en/datasheet/vd56g3.pdf) describes the I²C and power/reset conditions. Its page-14 patch prose is internally inconsistent; use UM2602's explicit CCA distinction and the revision-aware driver rather than treating that paragraph as proof of a particular delivered module's boot behavior.

## MCU boot loading

[ST UM3234 Rev 5](https://www.st.com/resource/en/user_manual/um3234-how-to-proceed-with-boot-rom-on-stm32n6-mcus-stmicroelectronics.pdf), tables 14/26 and the serial-NOR boot description, gives the normal ROM legacy single-data-line path: 64 MHz XSPI kernel divided by two, without DMA. The ideal payload ceiling is 4 MB/s. The local [archived manual](../../datasheets/processor/STM32N6_UM3234_boot_ROM.pdf) and MCU-006 retain this evidence.

| ROM-loaded payload | Ideal transfer time only |
|---|---:|
| 32 KiB | 8.192 ms |
| 64 KiB | 16.384 ms |
| 100 KiB | 25.600 ms |
| 200 KiB | 51.200 ms |

ROM overhead, headers/checks, power rise and subsequent startup add time. A fast octal NOR does not by itself speed up that initial single-line load. The [ST Nucleo load-and-run template](https://github.com/STMicroelectronics/STM32CubeN6/blob/main/Projects/NUCLEO-N657X0-Q/Templates/Template_FSBL_LRUN/FSBL/Src/main.c) initializes clocks/external memory, copies an application and then enters it. Audit what must precede exposure rather than treating the complete example as a timing guarantee. HAL remains the accepted starting point; optimize measured delays/copies and unnecessary initialization before assuming a wholesale rewrite is needed.

## Power, storage and parallel work

- **Power:** LTC3621 soft start is 0.8 ms typical, not an end-to-end maximum. Cell/contact resistance, charging capacitors, downstream converters and required sequencing determine actual startup. HOLD must take over early enough to survive button release/bounce; a software debounce delay must not consume the exposure budget. [ADI datasheet](https://www.analog.com/media/en/technical-documentation/data-sheets/ltc3621-3621-2.pdf), [project power review](../power/2026-10-14-power-tree-review.md).
- **Clocks:** the archived STM32N657 crystal-startup figure is 2 ms typical, without a maximum; [ES0620](https://www.st.com/resource/en/errata_sheet/es0620-stm32n6xxxx-device-errata-stmicroelectronics.pdf) also cautions that HSERDY is not proof of stable frequency. Use the actual oscillator mode and errata, not a typical value as a guaranteed allocation.
- **Storage:** as an illustration, 200 metadata page reads at a candidate's 70 µs typical array-read time consume 14 ms before transfer/validation. A 4,096-block marker scan is about 287 ms on that arithmetic. These are not bounds or a selected layout. The [Alliance candidate datasheet](https://www.alliancememory.com/wp-content/uploads/AllianceMemory_AS5F_QSPI_NAND_Flash_3V-1Gb-8Gb_1p8V-2Gb-4Gb-8Gb_Ver3.1_O.pdf) labels the page-read value differently in its parameter and AC tables; clarify it before claiming a maximum. Use a [bounded checkpoint/journal recovery design](slot-state-storage-review.md), not an assumed early free slot. Durable PARTIAL marking is required before payload writing; current policy does not inherently place that program operation before exposure.
- **Overlap:** start safe camera power/clock and exposure-input settling early; perform independent state/metadata work while hardware settles. Optional RTC/orientation reads need bounded failure handling and the accepted BAD fallback. Configure required CSI/DMA/RAM readiness before the first relevant sensor output. Never remove required sequencing, safe-slot checks or fault handling merely to improve a benchmark.

Do not sum all illustrative numbers into a predicted startup time: some tasks can overlap, and the measurements/bounds for the critical path are incomplete. No new per-stage timing allocations or relaxed target are approved here.

## Recommended first verification

Verify the camera revision during bring-up and retain that check in factory commissioning under D-44. When the board arrives, implement the minimal staged boot under D-45 and instrument:

`button edge → rails/reset → first FSBL GPIO marker → camera clock/reset → sensor ready → actual exposure start`

Use a correctly configured sensor exposure-strobe output, or a validated optical timing test, to identify integration start. CSI frame arrival/readout and the software START_STREAM command are not interchangeable with exposure start. UM2602's strobe/VSYNC descriptions distinguish integration from readout; account for configured strobe offsets.

Test real power removal and battery startup, rather than only a debugger-loaded application, reset button or wake from low power. Capture the normal successful path, nearly full storage and recovery after interruption; faults still use the accepted shutdown policy. Measure with the intended potentiometer extremes and fixed gains so the first saved exposure is correctly configured. Retain traces and firmware/image sizes before claiming compliance.

The ≤50 ms target remains accepted. If the delivered sensor needs the legacy upload, resolve revision/supply first; do not silently change to retained sensor power, omit patches or relax the timing requirement.
