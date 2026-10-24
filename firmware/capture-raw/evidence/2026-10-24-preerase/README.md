# ACMD23 and one whole-image write — October 24, 2026

The user requested CMD55 + ACMD23 followed by one multiblock payload write,
benchmarked against the current RAW firmware, with saved images verified.
The experiment passed. **V16 remains installed and selected**; the old chunked
path remains available. The gain is small on this native one-bit, 25 MHz link.

## Results

Both groups used the same board, SD card, scene, exposure setting, probes,
debugger connection and JS-fed power route. Each run began with a measured
15-second target power-off. No card format, wiring change, SD clock change,
compression or image-size change occurred between groups.

| Metric, median of three cold runs | Chunked v15 | ACMD23 + one CMD25, v16 | Observed change |
| --- | ---: | ---: | ---: |
| Current onset → stable Standby plateau | 796.377 ms | 780.385 ms | −2.01% |
| Energy over that same interval | 435.297 mJ | 426.796 mJ | −1.95% |
| Payload submission → padded payload ready | 633.320 ms | 626.438 ms | −6.882 ms (−1.09%) |
| SD initialization | 111.085 ms | 101.518 ms | −9.568 ms |
| SD ready → first payload | 16.591 ms | 18.735 ms | +2.143 ms |
| Payload ready → FULL commit | 1.908 ms | 2.090 ms | +0.182 ms |

| Run | Saved slot | Complete-cycle time | Energy |
| --- | ---: | ---: | ---: |
| Baseline 01 | 10 | 783.9855 ms | 428.727237 mJ |
| Baseline 02 | 11 | 797.5735 ms | 435.417894 mJ |
| Baseline 03 | 12 | 796.3765 ms | 435.296842 mJ |
| Candidate 01 | 15 | 774.2365 ms | 423.762709 mJ |
| Candidate 02 | 16 | 780.3850 ms | 426.795861 mJ |
| Candidate 03 | 17 | 794.0275 ms | 433.323253 mJ |

Payload duration ranged 633.320–634.288 ms for v15 and 625.914–626.952 ms
for v16. Pure payload wire time is 611.1232 ms for 3730 × 512 bytes at 25 Mbit/s
(611.072 ms for the unpadded image). Framing, card busy periods and command
handling account for the additional observed time; this experiment does not
separately measure each contribution.

The full-cycle ranges overlap. SD initialization varied independently, later
captures scanned more headers, and card internal state was uncontrolled.
Three chronological observations per group do not establish statistical
significance. Do not attribute the entire ~2% reduction to the payload change,
or separate the effect of the hint from that of grouping the write. This is
measured Nucleo-branch energy, including board overhead and excluding bypass
paths outside the JS110, not isolated MCU or production battery energy.

## Implemented sequence

The v15 baseline used four payload CMD25 transactions of 1024, 1024, 1024 and
657 sectors, plus a separately padded final CMD24 sector. V16 does:

1. Initialize the card and scan for a FREE slot. Require validated FRAME before
   writing its PARTIAL header.
2. Check the original 32-byte frame guard. Write 160 zero padding bytes in place;
   a separate guard after the padded allocation remains intact.
3. Establish fresh card readiness, send `CMD55(RCA)`, then `ACMD23(3730)`.
4. Issue `CMD25(payload LBA)` immediately next and send all 3730 sectors through
   one polling IDMA request. Both application-command acknowledgments are required.
5. Require successful transfer completion, send CMD12, and check fresh CMD13
   READY/TRANSFER, DAT0 high and idle host state.
6. Require sensor STOP and the post-padding guard; write FULL separately,
   deinitialize storage, tear down peripherals and enter MCU Standby.

The announcement excludes the two header writes. ACMD23 is a preparation hint,
not CMD23's bounded transfer mode or a cache-flush operation. Interrupted-write
and arbitrary card power-loss behavior remain unqualified. The new path adds no
full-frame CPU copy, checksum or compression; only the tail padding is filled.

The selected build is polling IDMA, asynchronous STOP, LINE publication and
`--whole-image-preerase`, with DMA-WFI disabled. Whole-image mode deliberately
waits for validated FRAME. This card's cold initialization already finishes
after FRAME, so the wait adds no observed delay. The prior chunked LINE option
remains useful for future cards ready before acquisition completes.

## Verification and limits

All six comparison cycles passed first-attempt warm PE6 UART recovery, exact
allowlisted early park, and SBF=1 with no intervening power-off. The root's
qualification binds the cold POR/CSSF history to each SBF observation.
Only baseline02 decoded all ten timing pulses. The other five final pulses
remain unidentified under the original tolerance; independent SBF establishes
Standby. No failed pulse is relabeled by its expected order.

All six saved slots were read completely: valid FULL header/CRCs, exactly
1,909,600 image bytes, 160 zero padding bytes, and independent PNG16 decoding
matching every retrieved RAW10 sample shifted left six bits. Their original
camera RAM was lost in Standby, so these reads do not claim source-RAM equality.
Separately, deterministic pattern slot13 and normal flash-boot scene slot14
each matched all saved bytes to the retained original camera RAM. The whole-write
trace records one 3730-sector payload call, zero errors, validated original guard,
zero padding and intact post-padding guard. The recovered scenes visibly show
the illuminated panel and bench geometry.

The 70 offline tests passed: 48 capture/integration, 9 slot-format/core, 2 actual
driver protocol-model/ARM compilation, and 11 recovery READ tests. Hardware
installation matched all 65536 NOR bytes; the following 4096 bytes are unchanged.
Exact prefix comparison differs only at the two existing CRC literals; all
recovery instructions are unchanged and early receiver load remains 15804 bytes.

One offline safe-start attempt rejected an awake build because its caller used
the default Standby expectation. No power cycle or storage operation occurred
in that refusal. The temporary runner was corrected to pass explicit `awake`;
the subsequent awake02 run passed. The baseline02 qualification wrapper also
initially refused a successfully decoded final marker; it was corrected to
accept either directly decoded event10 or an explicitly unknown final pulse,
while still requiring independent SBF. Raw measurements were not altered.

## Selected images and final state

| Build | Complete 64 KiB sector SHA-256 |
| --- | --- |
| Baseline v15 | `efb3c440e008e448a1682285034fe30b77bdbb5834024da9de787f3f51f42629` |
| V16 awake qualification | `52edac834cc8aebd649c8d35a8f3fd6ef20e2e6c12dc99bcf0944a636d445508` |
| **V16 selected Standby** | `285fba4951f88deb12033e7b3c2948c802371862982da5a8e304c6cae35fb58f` |

Selected prefix: `31b8a97eb8a68e574c1adab17e44b838044277bd95f81f5b22c30b9fdaaccd2e`.
Receiver: `401d3865e93d1f9dfae7530bb9410b00ab76e7a696fc7565015e5d3c8903e010`.
Early recovery park remains `0x3418078C`. Use the exact v16 allowlist and existing
idle/code/context guards before maintenance; a current plateau alone is insufficient.

At **2026-10-24 16:23:03.973899 UTC**, the extra final normal cold boot left the
target powered at **4.892441 V / 8.083381 mA**. Its expected slot18 and SBF were
not reread. It is a low-current signature and decoded events1–9, excluded from
the qualified A/B sample; its last pulse remains unknown. JS110 stopped cleanly
and restored range128, COM8 closed/BREAK released, Logic2 running and no bench
helper active. Boot jumpers remain pins1–2. Power is CN8 → CN9.3 → JS IN+, JS OUT+
→ CN9.2, no CN9 shunts; CN10 connected, D2/R23 removed, GPIO banks3.3V. Probes
remain CH0 NRST/CN3.14, CH1 PD12/CN15.21, CH4 target5V/CN3.18, CH6 PE6/CN15.2,
GND CN3.19. RAW generation10785350417884675236 and 32834-slot geometry are unchanged.

## Offline replay

`index.json` maps exact sources, generated binaries/ELFs/listings, measurement
records and proofs to hashed objects. Scene pixels are omitted with hashes;
the deterministic pattern is retained. `qualification.json` records completed
offline replay. The archived native-sample sum bins reproduce interval energy;
they do not replay the original raw onset/plateau classifier or establish analog
calibration. The original 9.5 A validity criterion is unchanged, including the
recorded brief 7.4 A startup peaks. No filtering was introduced for this comparison.

```powershell
python firmware/capture-raw/evidence/2026-10-24-preerase/replay.py
python firmware/capture-raw/evidence/2026-10-24-preerase/materialize.py --build flash-standby-v16 --out tmp/preerase-v16-frozen
```

Both commands are offline. Extract only into a new directory. The prior RAW
archive remains unchanged; its historical failures and qualifications still apply.
