# Four-bit SD carrier qualification — October 24–25, 2026

**V23 is installed and passed three cold capture/save cycles with the PZSSD001 full-pin breakout at native four-bit SDMMC2 / 12.5 MHz / 3.3 V.** Median complete cycle time fell **34.4%**, and measured board-branch energy fell **31.3%**, relative to the same SanDisk Extreme 32 GB on the original seven-pin carrier at one bit / 25 MHz. All three saved images were retrieved completely, decoded and visually inspected; each cycle independently reached Standby.

The selected profile retains GPIO speed 3 and the inherited compensation setting. **25 MHz is not qualified on this wiring**: separate default-slew and fixed-compensation write trials failed CRC checks, and a speed-zero trial failed its first header read. The lower clock was selected without relaxing CRC, recovery or storage-idle checks.

## Three-cycle comparison

Both groups use the same card identity, unchanged 1120 × 1364 packed RAW10 data, 1,909,760-byte slots, 152 bytes of front metadata, approximately 10.976 ms exposure, one announced CMD25 per image, explicit pre-test whole-card erase, and the same native JS110 analysis criteria. Exactly three normal captures followed the final erase; their slots are 0–2.

| Configuration | Run | Current onset → Standby plateau | Energy over that interval | First payload → full-slot commit |
|---|---:|---:|---:|---:|
| Original carrier, one bit, 25 MHz | 1 | 864.811 ms | 442.064 mJ | 635.356 ms |
| | 2 | 882.627 ms | 450.788 mJ | 625.096 ms |
| | 3 | 892.197 ms | 455.406 mJ | 632.876 ms |
| **Original median** | | **882.627 ms** | **450.788 mJ** | **632.876 ms** |
| New carrier, four bits, 12.5 MHz | 1 | 564.048 ms | 302.478 mJ | 327.321 ms |
| | 2 | 582.883 ms | 311.783 mJ | 330.084 ms |
| | 3 | 578.942 ms | 309.532 mJ | 323.369 ms |
| **New median** | | **578.942 ms** | **309.532 mJ** | **327.321 ms** |
| **Median reduction** | | **34.4%** | **31.3%** | **48.3%** |

The storage column uses Saleae event 6 → 8, including the final commit stamp. Earlier reports use event 6 → 7 for payload/card-ready time: the corresponding medians are 632.854 and 327.299 ms. The approximately 0.022 ms difference is accounting, not a further storage operation. Image-payload throughput using event 6 → 8 is **3.017 → 5.834 MB/s** (decimal MB; excludes metadata bytes from the numerator).

| Measured interval | Old median | New median |
|---|---:|---:|
| Receiver entry → first observed strobe IRQ | 1.276 ms | 1.278 ms |
| First observed strobe IRQ → frame IRQ | 21.863 ms | 21.863 ms |
| SD initialization | 220.053 ms | 215.732 ms |
| SD ready → first payload submission | 8.259 ms | 6.703 ms |
| First payload → payload/card ready | 632.854 ms | 327.299 ms |
| Commit stamp | 0.022 ms | 0.022 ms |
| SD deinitialization | 0.061 ms | 0.062 ms |

Camera reception overlaps SD initialization by approximately 17.085 ms; these intervals are not additive. They describe this exposure, not arbitrary long exposures. Independent analyzer clocks prevent assigning JS energy to these individual Saleae phases. SD initialization now occupies much of the remaining cycle.

## Image, overlap and recovery checks

- The three measured slots each passed all 3,730 sectors of readback, GXR2/GXRE markers, front metadata checks and independent PNG decoding equal to the retrieved RAW samples. All three scenes visibly contain the illuminated panel structure and surrounding cables. Much of the scene is dark and the brightest lights clip; this is functional verification, not image-quality calibration. Original camera RAM was lost in Standby, so these three results are **not** original-RAM comparisons.
- A separate deterministic capture at 12.5 MHz matched **every one of the 1,909,600 image bytes** to original camera RAM. The [earlier diagnostic archive](../2026-10-24-sd-fourbit-diagnostics/README.md) preserves that result and the first failed 25 MHz write.
- A separate **230.597 ms exposure** on the selected profile also passed full original-RAM equality. Its first write began **4.711 ms before FRAME**. Twenty immediate LINE-tail snapshots, 10,240 bytes in total, matched final RAM. This is sampled visibility evidence; the consumer did not exhaust its published prefix, so prolonged physical FIFO starvation remains unqualified.
- Each measured cycle passed warm PE6 C0/BREAK recovery into the exact v23 early park and independently attributed **SBF=1 without intervening power-off**. The final Saleae pulse remains outside the strict decoder tolerance and is left unclassified. Standby is established by the separate hardware flag, not by relabeling that pulse.
- The existing offline checks passed: 91 RAW tests, six SD driver test groups including ARM compilation, and twelve recovery tests. The control four-bit/25 MHz build remains byte-identical to v19b; low-slew and fixed-compensation options remain separate RAM diagnostics.

Markers establish the expected completed object structure, not a payload checksum or arbitrary power-loss atomicity. Normal capture still does no full-frame CPU checksum or PNG encoding. PNG conversion above was an offline verification step.

## Why 12.5 MHz was selected

Initially, both the new four-bit candidate and frozen previously working one-bit reader failed at CMD8, before width negotiation. After CLK/CMD probes were attached, valid card responses and four-bit reads were observed. No cause was established for that change; the power LED alone is not a rail-quality measurement. CH5 was not moved to card VCC.

At 25 MHz, 65,536 varied readback bytes matched the known image and distinguished all 24 permutations of DAT0–DAT3. However, the first progressive write failed with a data-CRC error. A later CMD13 READY response did not clear the host's active/uncertain state; the failure was never called safe idle. The user's explicit experimental-card reset permission allowed bounded recovery.

Two isolated follow-ups also failed:

| Trial | Observed result |
|---|---|
| 25 MHz, GPIO speed 0, unchanged compensation | First header CMD17 failed CRC; no image write launched |
| 25 MHz, GPIO speed 3, fixed VDDIO5 compensation `0x287` | Progressive CMD25 failed CRC; partial card modification possible and idle not established |
| 12.5 MHz, GPIO speed 3, unchanged compensation | Pattern equality, long-scene equality and all three cold save/readback/Standby cycles passed |

The compensation experiment proved the required supply/clock/reset access conditions and recorded `0x78 → 0x287`; it did not merely assume the workaround was applied. See [bound follow-up diagnostics](followup-diagnostics.json). Neither this trial nor the lower-clock success identifies the electrical root cause. No production margin, temperature, cable variation or long-run reliability qualification is implied. Keep the [current wiring](../../../../docs/prototype/sd-breakout-benchmark.md#october-24-replacement-pzsmocn-pzssd001-full-pin-breakout) while reproducing this result.

## Measurement boundary and identities

The headline energy integrates native JS110 power samples from current onset to the stable Standby plateau. The separate one-second plateau confirmation, **39.55–40.10 mJ**, is excluded. Plateau current was **8.083–8.194 mA**. This is the **JS-fed Nucleo branch**, including board overhead and excluding unmeasured bypass paths; it is not isolated DUT or production battery energy.

The unchanged analyzer verifies sample identity, contiguous coverage, finite selected windows and the same thresholds used for the one-bit baseline. Startup spikes/source sag remain uncorrected; no calibrated peak-current or new saturation/suppression correction is claimed. Local compact sums reproduce the selected energy intervals; native samples are needed to rerun boundary classification. The public summary checks recorded arithmetic only.

This is an **old-carrier/one-bit/25 MHz versus new-carrier/four-bit/12.5 MHz comparison**, not a pure width experiment. The new breakout has an illuminated power LED of unmeasured draw; CLK/CMD probes were added; tests occurred sequentially; and the old images were nearly black while the new scene was illuminated. Fixed RAW length keeps bytes transferred identical, but electrical data-pattern and card-controller effects are not isolated. No LED-current subtraction is made. Three runs per configuration establish this bench result, not population reliability.

| Artifact | SHA-256 |
|---|---|
| Installed v23 64 KiB NOR sector | `bb31867394a4e0d0fb9ab3f9fa96d0d16ffc7256e2a274db74be4f11f9cfdc14` |
| Early recovery prefix | `09fb59cfed0f715927e76f32d5f74187e4c2f1702a70ce192e0d17dcee2f822a` |
| Flash receiver | `8cc696ab6a9ff055bc2e4924d9aca63b905f333fc2b3ae05c06abdb45e0af30c` |
| Scene RAM maintenance build | `a09d3e3639b4978093818684ac2a9e313f85b2d13c0c30fb91ace45478191a6f` |

The complete 64 KiB physical NOR readback matched the built sector, and the following 4 KiB matched the original reference. See [installation proof](installation-proof.json). Only two CRC data words changed in the prefix relative to v18; recovery instructions and the 15,804-byte early load remained fixed. The selected builds explicitly specify four bits and 12,500,000 Hz; historical defaults were not changed.

## Final bench state

At **2026-10-25 04:11 UTC**, the board was left powered in a verified **awake, idle RAM READ terminal**, after downloading slot 2. It is not currently in Standby. No fourth normal capture was made. Final proof reports SD idle/deinitialized, no controller ownership and no cleanup error. A read-only JS session measured **4.879883 V / 82.7232 mA**, which is awake-helper current. It closed cleanly with range 128 preserved. COM8 is closed/BREAK released; Logic 2 is running with no capture; no bench helper remains active. The next normal cold boot uses installed v23.

CN8 → CN9.3 → JS110 IN+, JS OUT+ → CN9.2, no CN9 shunts; CN10 connected. D2/R23 removed, banks 3.3 V, JP1/JP2 pins 1–2, PE1 external wire absent. Probes: CH0 NRST/CN3.14; CH1 PD12/CN15.21; CH2 breakout CLK; CH3 breakout CMD; CH4 target 5 V/CN3.18; CH6 PE6/CN15.2; GND CN3.19. CH5 was not moved to card VCC. Recheck physical ownership/wiring before further hardware work.

## Durable results and verification scope

From this folder, with Python's standard library only:

```text
python verify_summary.py
```

`measurement-summary.json` records the three runs, exact firmware identities, same-card baseline, comparisons and source-result hashes. `verify_summary.py` checks medians, percentage changes, throughput and pinned identities. It does **not** rerun hardware qualification, pixel decoding or integration of native power samples. `installation-proof.json` records the complete local NOR comparison; `followup-diagnostics.json` preserves the failed 25 MHz experiments separately from successful qualification.

The complete locally replayed evidence bundle remains in `tmp/bringup/sd-fourbit-20261024/archive-final-draft/`, with native recordings and private image/readback bytes in the surrounding experiment folder. It binds the cold sequences, erase, exact recovery, independently attributed SBF, bounded image READ proofs and compact energy integrals. The public record intentionally excludes card identifiers, host paths, images, SD/SRAM contents and native instrument arrays. Source hashes bind the recorded results without publishing those private records. Earlier public archives are unchanged.
