# Four-bit 25 MHz, probes removed: twenty-image stress test

**20/20 images independently verified.** Report generated 2026-10-26T18:04:42.302644+00:00.

The replacement card was tested with falling-edge host launch, GPIO speed 3, inherited compensation, reviewed startup/completion/abort guards, and PIO readback. LP8 signal probes were removed; the 27-ohm CLK resistor and bench wiring were retained according to the bench owner. The first eight and final eight requested captures use normal exposure; captures 9–12 use long exposure plus immediate producer snapshots.

Verified 38,195,200 stored bytes in each direction across 20 images. Every verified image matched all original camera-RAM bytes and independently decoded PNG samples. The public bundle omits image bytes.

| Run | Slot | Exposure ms | Actual write path | SD init ms | Slot write ms | SD read transactions ms | Match |
| ---: | ---: | ---: | --- | ---: | ---: | ---: | --- |
| 1 | 24 | 10.976 | IDMA | 115.723 | 393.480 | 316.745 | Full RAM + PNG |
| 2 | 25 | 10.976 | progressive PIO | 17.375 | 424.286 | 317.957 | Full RAM + PNG |
| 3 | 26 | 10.976 | progressive PIO | 17.374 | 415.559 | 317.120 | Full RAM + PNG |
| 4 | 27 | 10.976 | progressive PIO | 17.375 | 209.286 | 319.259 | Full RAM + PNG |
| 5 | 28 | 10.976 | progressive PIO | 17.375 | 209.265 | 317.470 | Full RAM + PNG |
| 6 | 29 | 10.976 | progressive PIO | 17.375 | 209.403 | 318.421 | Full RAM + PNG |
| 7 | 30 | 10.976 | progressive PIO | 17.374 | 221.915 | 317.229 | Full RAM + PNG |
| 8 | 31 | 10.976 | progressive PIO | 17.375 | 209.084 | 317.573 | Full RAM + PNG |
| 9 | 32 | 230.597 | progressive PIO | 17.371 | 258.483 | 300.824 | Full RAM + PNG |
| 10 | 33 | 230.597 | progressive PIO | 17.371 | 257.464 | 301.061 | Full RAM + PNG |
| 11 | 34 | 230.597 | progressive PIO | 17.370 | 257.632 | 301.325 | Full RAM + PNG |
| 12 | 35 | 230.597 | progressive PIO | 17.370 | 258.521 | 303.203 | Full RAM + PNG |
| 13 | 36 | 10.976 | progressive PIO | 17.374 | 208.412 | 318.086 | Full RAM + PNG |
| 14 | 37 | 10.976 | progressive PIO | 17.374 | 409.474 | 317.320 | Full RAM + PNG |
| 15 | 38 | 10.976 | progressive PIO | 17.374 | 424.198 | 316.938 | Full RAM + PNG |
| 16 | 39 | 10.976 | progressive PIO | 17.374 | 425.554 | 319.348 | Full RAM + PNG |
| 17 | 40 | 10.976 | progressive PIO | 17.374 | 421.193 | 317.393 | Full RAM + PNG |
| 18 | 41 | 10.976 | progressive PIO | 17.375 | 416.231 | 317.449 | Full RAM + PNG |
| 19 | 42 | 10.976 | progressive PIO | 17.375 | 359.045 | 318.712 | Full RAM + PNG |
| 20 | 43 | 10.976 | progressive PIO | 17.374 | 219.967 | 317.358 | Full RAM + PNG |

Card identity stayed constant: 122,507,264 logical 512-byte sectors; captured CID register words `00000053 44553120 1014A11A 76019744`. The complete CSD/OCR and width/startup proofs are retained for every operation.

Primary scene data spans 10-bit values 60–72. This limited scene range does not exercise every pixel bit combination; supplementary sensor-generated patterns provide broader data coverage.

The primary campaign exercised 1 complete-buffer IDMA write and 19 progressive PIO writes. Every readback also used four-bit 25 MHz. The requested images account for 74,600 written sectors and the same number read back, through 160 guarded read operations.

All 80 immediate 512-byte LINE snapshots matched the final camera RAM. Each long exposure began writing before FRAME, by 9.440–9.450 ms. These checks exercise partial-frame publication while SD writes proceed.

Read timing sums the 59 PIO multiblock transactions needed for one complete slot. Each host read request is capped at 512 sectors, giving eight requests and eight initializations. Host/debugger gaps and these initializations are excluded from the data-transaction column; their separate totals are in [summary.json](summary.json). Slot-write timing includes preparation, all data/card stalls and final completion. These are nominal 400 MHz counter timings, not power-on or energy measurements.

Recorded command-CRC-flagged operations: **0**. Data-CRC-flagged operations: **0**. Failed operation records: **0**. These count retained operation records, not raw wire-bit errors. Failed/incomplete attempts and recovery records are retained in summary.json and the evidence inputs.

The installed NOR remains the reviewed 12.5 MHz startup/no-tail Standby firmware. This campaign runs 25 MHz from RAM; it does not promote a new flash profile.

The [initial-state record](inputs/initial-state.json) separately records a disconnected target-power lead, its user-restored connection and successful UART recovery before the campaign. That preflight interruption is not counted as a storage test failure. A possible ordinary boot during power restoration is not counted as a measured 25 MHz image.

The bench owner recorded the [final state and instrument closure](inputs/final-state.json) after the tests. The hardware qualification above is based on the frozen operation proofs, not current alone.

## Supplementary coverage

These checks are additional to the requested twenty images; they do not inflate that count.

- pattern01: sensor-generated diagonal pattern, slot 44, full original-RAM/SD/PNG match, 960 distinct 10-bit levels (64–1023), actual progressive PIO write.
- pattern02: sensor-generated diagonal pattern, slot 45, full original-RAM/SD/PNG match, 960 distinct 10-bit levels (64–1023), actual progressive PIO write.
- Preservation: complete slot 24 reread matches the first original camera frame and its first readback byte-for-byte; PNG samples also match.

## Qualification limits

- Probe-free functional stress at the observed voltage, temperature, wiring and card; no analog margin or formal SD certification.
- No logic-analyzer recording in this campaign; hardware CRC/response checks and complete SD/original-RAM equality establish observed operation.
- Warm RAM capture/read operations do not requalify cold flash boot, Standby, power-loss tolerance or total cycle energy.
- Timings use nominal 400 MHz CYCCNT; overlapping intervals are not additive. Readback sums exclude host/debugger gaps and separately report eight card initializations.
- Transfer time includes controller/card stalls; it is not isolated card flash-programming time.
- The prior HAL DTMODE0 versus reference-manual mode3 discrepancy remains explicitly unresolved.
- Pixel, SD-sector and immediate snapshot bytes stay private; public evidence contains hashes and operation/trace proofs.

See the [prior protocol review](../2026-10-26-sd-review/PROTOCOL-REVIEW.md) for retained command/busy/abort requirements and the DTMODE discrepancy.

## Reproduce offline

```text
python archive.py inspect --source <private campaign folder> --out <report.json>
python archive.py freeze --source <private campaign folder> --out <new evidence folder>
python archive.py verify --out <frozen evidence folder>
```

Inspect may report partial progress. Freeze refuses an incomplete campaign unless explicitly passed `--allow-incomplete`; the resulting verdict still remains incomplete. `verify` checks every frozen file against its manifest. Full pixel re-comparison requires the private source artifacts.
