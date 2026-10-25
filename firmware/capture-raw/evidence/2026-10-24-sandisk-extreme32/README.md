# SanDisk Extreme 32 GB — October 24, 2026

Three cold capture/save cycles completed on the replacement card using unchanged **v18 firmware, the original seven-pin breakout, native one-bit SDMMC2 at 25 MHz and 3.3 V**. All three reached independently verified Standby and their complete saved slots were retrieved. The measured image-write throughput was essentially unchanged from the prior card; longer initialization dominated the observed cycle-time increase.

## Capture and write measurements

| Run / slot | Current onset → Standby plateau | Energy | SD initialization | Payload → final card readiness |
|---|---:|---:|---:|---:|
| 1 / 0 | 864.811 ms | 442.064 mJ | 197.046 ms | 635.334 ms |
| 2 / 1 | 882.627 ms | 450.788 mJ | 220.053 ms | 625.074 ms |
| 3 / 2 | 892.197 ms | 455.406 mJ | 220.067 ms | 632.854 ms |
| **Median** | **882.627 ms** | **450.788 mJ** | **220.053 ms** | **632.854 ms** |

Each capture writes one 3,730-sector object: `GXR2`, 152 reserved metadata bytes, 1,909,600 packed RAW10 image bytes and final `GXRE`, totaling 1,909,760 bytes. The driver uses CMD55/ACMD23 followed by one CMD25, and requires final card readiness before shutdown. Image-payload throughput was **3.006–3.055 MB/s**, median **3.017 MB/s** (decimal MB). The one-bit 25 MHz wire ceiling is 3.125 MB/s before protocol overhead; a faster card alone has little transfer-rate headroom here.

SD initialization overlapped acquisition by approximately **17.20 ms**. Frame completion followed the first observed exposure strobe by **21.863 ms** and preceded SD readiness in all three runs. These short-exposure runs therefore do not demonstrate simultaneous image delivery and SD payload writing. Initialization, acquisition and complete-cycle intervals overlap and use different boundaries; do not sum them. The final commit-bookkeeping and deinitialization intervals were approximately 0.022 ms and 0.061 ms, after the payload interval had already included card readiness.

## Same-firmware historical comparison

| Metric | Previous 64 GB card, **one v18 run** | SanDisk 32 GB, median of three |
|---|---:|---:|
| Complete cycle | 780.173 ms | 882.627 ms |
| Measured energy | 411.753 mJ | 450.788 mJ |
| SD initialization | 116.164 ms | 220.053 ms |
| Payload → final card readiness | 626.049 ms | 632.854 ms |
| Image-payload throughput | 3.050 MB/s | 3.017 MB/s |

The observed differences are **+102.454 ms (+13.13%)** and **+39.035 mJ (+9.48%)**. Payload duration increased only 1.09%; the approximately 104 ms increase in initialization explains the dominant timing difference. Component medians need not add to the median complete cycle.

The old-card reference is a new offline analysis of the already-qualified v18 slot-9 recording, captured October 24 at about 18:58 UTC. It uses the identical frozen energy method and original SBF/readback attribution; it is not a new hardware run. **One old-card sample cannot establish its variability or a general ranking of these cards.** Earlier v17d three-run results used different firmware/layout and card state and are not substituted for this same-firmware comparison. Scene, scan position, erase history and controller state also differed.

## Card preparation, identity and verification

The user identified the replacement as SanDisk Extreme 32 GB. Its CID is `035344534533324780a1cd45db019cec`, product `SE32G`; reported capacity is **62,333,952 sectors / 31,914,983,424 bytes**, allowing 16,711 current slots. This is reported geometry, not a full-capacity or retention qualification.

The explicitly authorized whole-card erase completed in **567 ms**, separately from the three measured captures. SCR reports erased byte **0x00**. Reads of LBAs 0, 3730, 7460 and 62,333,951 were entirely zero; four samples do not verify every sector. Normal capture never formats the card.

All three cycles passed warm PE6 recovery, the exact v18 early park and attributed **SBF=1 without intervening power-off**. Full 3,730-sector readbacks of slots 0–2 passed leading/trailing markers, metadata/layout checks and independent PNG sample decoding. Original sensor RAM was lost in Standby, so this is not a comparison against the original acquisition buffers. Markers provide no payload checksum or arbitrary power-loss guarantee.

All three reconstructed images were **near black**, with samples ranging 62–74; no recognizable illuminated scene was established. The saved objects decode, but these runs do not qualify illuminated-scene capture quality. Uncompressed RAW keeps the transmitted byte count identical despite brightness; electrical data-pattern and card-controller effects are not isolated.

## Measurement boundary and firmware identity

Energy integrates native JS110 samples from measured current onset to the stable Standby plateau. The separate one-second plateau confirmation, approximately 40.1 mJ per run, is excluded. Plateau current was **8.196–8.198 mA**. This is the **JS-fed Nucleo branch**, including board overhead and excluding unmeasured bypass paths, not isolated MCU or production battery energy.

The unchanged frozen v66c analyzer verifies sample identities, contiguous coverage, finite selected windows and its original thresholds. Startup current spikes and source-voltage minima remain uncorrected; no new calibration, saturation, suppression or bypass correction is inferred. Saleae and Joulescope clocks are independent, so no per-phase energy is assigned. Events 1–9 decode directly; the final pre-WFI pulse remains unidentified. Strict phase decoding remains failed, while independent SBF establishes actual Standby.

| Artifact | SHA-256 |
|---|---|
| Installed v18 64 KiB NOR sector | `174424c6792f96c72e336fc68e442474e9da665718552d3239a772d59ba73e2e` |
| v18 early recovery prefix | `9401bed4076d6e9e4d2e4f9236661faf7b8f0e051cb332ea4dcbba09da336eba` |
| RAM maintenance build | `1b96bf02555a33035a6ca4b4fd641409d9e2129274f9dfbf326ae1aa26d51b2f` |

No NOR programming occurred in this experiment, and no new full physical NOR readback is claimed. Local build identities and exact live recovery-prefix checks bind the existing firmware.

## Recovery finding

Initial warm recovery and a separately authorized cold recovery failed. The initial 1 Mbaud request produced no UART pulse train despite the host accepting bytes. Separate 115200-baud and then 1 Mbaud transmission tests produced physical PE6 activity; the following 1 Mbaud C0/BREAK request reached the exact v18 park with nine good pulses and zero bad pulses. This is correlation with reconfiguration/reopening, not proof that changing baud is a universal fix or identification of a ST-LINK defect. No jumper move or firmware replacement was required.

## Final bench state

Final state recorded at **2026-10-25 02:55:12 UTC (October 24 locally)**: the target was left powered in the verified **awake, idle RAM READ terminal park** after slots 0–2 were retrieved. It is not currently in Standby. No fourth normal capture was performed. The final proof reports SD idle/deinitialized, no controller ownership and no cleanup error. JS110 closed cleanly/restored range 128; COM8 closed, BREAK released, Logic 2 running with no active capture or bench helper. No fresh post-readback current measurement was taken.

The original carrier and wiring remained: CN8 → CN9.3 → JS110 IN+, JS OUT+ → CN9.2, no CN9 shunts; CN10 connected. D2/R23 remain removed, banks 3.3 V, JP1/JP2 pins 1–2, PE1 wire disconnected. Recheck ownership and wiring before further work; power down before replacing the carrier. The [replacement wiring plan](../../../../docs/prototype/sd-breakout-benchmark.md#october-24-replacement-pzsmocn-pzssd001-full-pin-breakout) is ready; four-bit firmware is not yet installed.

## Saved evidence and offline replay

`index.json` and `objects.zip` retain hash-bound build identities, card/SCR/erase records, terminal proofs, phase records, SBF and full-readback attribution, compact native energy sums, recovery findings and final state. Private image/sector/SRAM bytes and raw instrument arrays are excluded. Replay checks recorded image evidence, not pixels; compact sums reproduce integration without rerunning raw onset/plateau detection.

From this evidence folder:

```powershell
python replay.py --archive .
python ../../energy_compacts.py replay --folder old-v18-reference
```

The separate `old-v18-reference` compact folder preserves the one-run historical comparison. Both replays operate offline and require no instruments. The [current RAW implementation](../../README.md) and [slot format](../../../raw-slots/README.md) describe the unchanged capture path.
