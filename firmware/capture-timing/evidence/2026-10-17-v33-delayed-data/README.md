# Early clock and delayed data lanes capture the first image

**Three cold starts captured the first requested native image without recorded startup or through-frame CSI errors.** This v33 candidate enables the receiver clock module early while keeping its two data-lane modules shut down. It enables the data modules only after sensor START acknowledgment and STREAMING, then qualifies data Stop, arms capture and issues one FSYNC. The existing error masks, flags and handler are unchanged. This is a working sequence on the present board; the exact offending electrical transition remains unmeasured.

| Cold run | First exposure, ms after NRST | Complete first frame, ms | Sole ECTRL, during later stop, ms |
| --- | ---: | ---: | ---: |
| 01 | 24.60960 | 46.47120 | 49.39360 |
| 02 | 25.07664 | 46.93840 | 49.86912 |
| 03 | 24.64016 | 46.50176 | 49.42512 |

The root bench controller personally inspected every image and confirmed a recognizable detailed workshop/bench scene. MCU/host integrity checks pass for all three 1120 × 1364 RAW10 frames. No invalid upper bits are present; complete raw sample statistics are retained. Every run passes the measured cold-cycle rail checks, and each 24-record diagnostic history has zero overflow. The sole recorded error is physical lane-1 ECTRL (`SR1=0x1000`, HAL code `0x8000`) between the before-stop and after-stop snapshots, after frame completion. It remains an unresolved shutdown behavior, not an image-transfer error in these runs.

## The sequence uses independent documented lane enables

`CSI_PCR` provides independent `CLEN`, `DL0EN` and `DL1EN` controls; `NPWRDOWN=1` selects the active state. Before `PEN` releases the PHY digital reset, v33 changes PCR from `0x0F` to `0x03`, leaving the clock module enabled and both data modules shut down. After sensor readiness it sets only the data-enable bits, restoring PCR to `0x0F`. These are documented controls, although the manual does not guarantee that this particular delayed sequence will be free of transients. ([RM0486 §§40.9.2, 40.10.1](https://www.st.com/resource/en/reference_manual/rm0486-stm32n647657xx-armbased-32bit-mcus-stmicroelectronics.pdf))

The recorded PCR is `0x03` through STREAMING and immediately before data enable. The next snapshot shows PCR `0x0F` and SR1 `0xE6180000`: received-clock activity and both data Stop flags, without error bits. **Clock-active status was not observed while the data modules were disabled.** The inference is that early clock-module enable preserves necessary initialization; the data does not directly prove earlier clock lock or identify the sensor's startup edge.

Sensor configuration, prefix and HAL sources match the early continuous-clock control; only the receiver source changes to sequence the data enables. All three lanes retain the original polarity/routing. The receiver's mapping and frequency configuration are not changed after PHY release. The manifest declares `captured_sensor_frame=1`, `first_frame_latency_eligible=true`, and `data_lane_enable=after_sensor_streaming`, unlike the deliberately second-frame [v32 diagnostic](../2026-10-17-v32-second-trigger/README.md).

The prior [v30d](../2026-10-17-v30d-phy-sequence/README.md) and [v31](../2026-10-17-v31-phy-sequence/README.md) late-full-PHY trials lost the first frame; [v32](../2026-10-17-v32-second-trigger/README.md) accepted the second after clock/data Stop without resetting or rearming. Together, these controlled changes support a receiver/transmitter initialization mismatch. They do not prove sensor noncompliance, qualify other boards/revisions, or establish the lowest possible latency. This diagnostic still uses follower mode and bounded readiness checks; production integration remains a separate decision.

## Archive integrity

The [configuration](archive-config.json), [ledger](ledger.json), [separate visual assertions](visual-review.json), [phase checks](extra/analysis/phy-v33-phase-verification.json), and [source provenance](source-provenance.json) cover **248 files/references, 1,959,568 bytes**. The independent offline phase check confirms every nonzero error snapshot lies strictly between the before-stop and after-stop records. All manifest sources were recovered exactly, reusing content-addressed historical objects where available.

The 65,536-byte programmed sector passed full readback verification with SHA-256 `f0b9f40f5b0c05b75c7168014d81c723e4cc5e6d444af37a36028e4ed7ced61d`. Frame pixels, full NOR readback, analog streams and Saleae sessions remain local. Final baseline restoration and instrument release are recorded separately by the bench owner; this checkpoint makes no claim about the final installed firmware.
