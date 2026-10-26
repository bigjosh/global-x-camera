# Additional illuminated-scene capture at 25 MHz

**Passed.** One extra real-scene image follows the [completed twenty-image campaign](../2026-10-26-sd25-twenty/README.md). The user illuminated the scene after that campaign; its frozen records and twenty-image count are unchanged.

Slot **46** passed exact comparison of all **1,909,600 original camera-RAM bytes**, the complete **1,909,760-byte / 3,730-sector** stored object, and independently decoded PNG samples. Both write and every readback used four-bit **25 MHz** on the same card. GXR2/GXRE markers and all 152 reserved metadata bytes were checked.

The actual write path was **progressive PIO**, using one preannouncement and one CMD25. Readback used eight guarded operations containing 59 PIO multiblock transactions. All nine capture/read operation records have zero retained command/data CRC flags, operation errors and cleanup errors. The image spans **73–1023** with **924 distinct 10-bit levels**; its sample mean is 142.778.

| Measured interval | Time |
| --- | ---: |
| Sensor exposure | 10.976 ms |
| SD initialization | 17.370 ms |
| Slot write | 206.812 ms |
| Readback data transactions, summed | 314.793 ms |
| Eight readback reinitializations, summed | 138.426 ms |

These are nominal 400 MHz counter intervals. Readback data time excludes debugger/host gaps and the separately reported initializations. Transfer intervals include card/controller stalls and do not isolate physical flash programming or energy.

The bench-owner [final state](inputs/lit-scene01/final-state.json) and [fresh exact idle gate](inputs/lit-scene01/final-idle/verified.json) are preserved. The installed NOR remains the reviewed 12.5 MHz startup/no-tail Standby firmware; this additional test runs awake from RAM.

The bench owner visually inspected the reconstructed PNG and recognized ceiling beams, a hanging fixture and a patterned screen, with shadow detail and bright openings. No Joulescope session or new current/energy measurement was performed for this addendum.

## Limits

- Probe-free functional stress at the observed voltage, temperature, wiring and card; no analog margin or formal SD certification.
- No logic-analyzer recording in this campaign; hardware CRC/response checks and complete SD/original-RAM equality establish observed operation.
- Warm RAM capture/read operations do not requalify cold flash boot, Standby, power-loss tolerance or total cycle energy.
- Timings use nominal 400 MHz CYCCNT; overlapping intervals are not additive. Readback sums exclude host/debugger gaps and separately report eight card initializations.
- Transfer time includes controller/card stalls; it is not isolated card flash-programming time.
- The prior HAL DTMODE0 versus reference-manual mode3 discrepancy remains explicitly unresolved.
- Pixel, SD-sector and immediate snapshot bytes stay private; public evidence contains hashes and operation/trace proofs.

## Offline replay

The original image, SD-sector and PNG bytes remain private. The public bundle retains hashes, exact code/source, operation/clock/ownership proofs, trace telemetry, recovery and final-state records.

```text
python -B archive.py inspect --source <private campaign folder> --out <report.json>
python -B archive.py freeze --source <private campaign folder> --out <new evidence folder>
python -B archive.py verify --out <frozen evidence folder>
```

Freeze requires the image comparisons, all nine operations and the separate final-state gate to pass. Full pixel replay requires the private source data. The pinned base verifier is copied unchanged from the prior campaign.
