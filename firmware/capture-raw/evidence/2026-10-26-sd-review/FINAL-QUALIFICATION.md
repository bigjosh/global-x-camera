# Final cold-boot qualification — October 26, 2026

The selected **reviewed four-bit 12.5 MHz startup/no-tail profile** passed one cold awake capture with full SD-to-original-camera-RAM equality, followed by one cold Standby-profile capture with complete saved-image retrieval. Both passed warm UART recovery through the exact installed prefix. The final installed NOR image is the Standby build; the final observed execution state is an awake, idle RAM READ helper after image retrieval.

This profile uses falling-edge host output launch during initialization and normal transfer, rising-edge receiver sampling, GPIO speed3, unchanged compensation and the guarded startup optimization. Tail wait, IDMA READ diagnostics, DMA WFI and 50 MHz mode remain disabled. See [the startup comparison and selection](STARTUP-TRIALS.md) and [the state-machine review](STATE-MACHINE-REVIEW.md).

## Exact installation and recovery

Both installations passed a complete 65,536-byte physical NOR comparison to their frozen sector image. The following 4,096 bytes at offset 65,536 also matched the prior reference, SHA256 `01cc465d3a7581d9d003b09e5db684eb7bec8e8512e12ce3565154c3aced816f`.

| Image | Capture binary SHA256 | Exact prefix SHA256 | NOR sector SHA256 |
| --- | --- | --- | --- |
| Awake | `f8b728723016035a34d11a39768fd03775c725e128e1f37f4016bef4cf92f044` | `54cd99f5b2c02c6561e25d8a59fc98210ecdd799736a0a3a8c749cac57a63777` | `c6a9779db35a458fb2415754c480cc1274d01f662e62fb57a245882cc5db532a` |
| Standby, left installed | `70a1913bd270b72164f4313bf25ba1f5d82276651a9c134b575fe3ac5c9923c3` | `4ef99d3b0b8ac7b790265cd1994428a5804dd3a20ad5587dd1585d2544a74b0b` | `c03e40c8ceea09bd9c171c179f2191a1ef9799c9e615db979a84b9c53ad66010` |

The [independent exact-prefix review](startup125-offline-recovery-admission.json) preserves the 15,804-byte early load, all 20 recovery literals and all 1,774 compared disassembly rows; only the two permitted CRC words change. After each cold capture, one recorded warm UART stimulus reached the exact matching park at `0x3418078C`, with **nine good pulses and zero bad pulses**. The archive uses the post-capture `final-*-read-park` records, rather than the different prefixes seen in the pre-installation recovery records.

## Saved images

| Trial | Slot / first LBA | Saved extent | Verification |
| --- | --- | --- | --- |
| Cold awake | 27 / 100710 | 3,730 sectors, 1,909,760 bytes | All 1,909,600 image bytes equal the original camera RAM and the retrieved RAW; PNG samples match. |
| Cold Standby profile | 28 / 104440 | 3,730 sectors, 1,909,760 bytes | Complete `GXR2`/metadata/RAW10/`GXRE` readback; PNG samples match the retrieved RAW. Original capture RAM is unavailable. |

Both have 152 zero reserved metadata bytes and recognizable illuminated lattice/panel scenes. The [awake image](final-awake-scene.png) and [Standby image](final-standby-scene.png) were independently inspected. Awake frame SHA256 is `bfa07710fab58d8486ff7f4ed4151ce7f5a80af20e20807e13f1376ef3773cc6`; Standby frame SHA256 is `3ab310a55700e2724464102fd0fc3da72288fb9e9a96b462163496d3ad8d4b3d`.

The awake inspection recorded result 0, all 3,730 sectors written, one frame, no camera/guard error, media idle, controller deinitialized and no cleanup error. Its retained startup proof shows a 1.020 ms continuous 100 kHz train, one SCR wire read and one cache hit, followed by cache invalidation. The complete image was ready before storage submission, so the existing IDMA write path was selected without a tail wait.

The awake DWT intervals at 400 MHz were: SD begin to ready **215.587 ms**, subsequent slot scanning **19.885 ms**, storage call **320.859 ms**, and receiver runtime begin to end **561.510 ms**. These are software-counter intervals, not reset-release or power-good timing. The large cold SD initialization interval also demonstrates why the earlier warm RAM totals must not be used as a cold-start prediction. No integrated cycle-energy measurement was performed here.

## Recorded sequence and Standby limit

All times below are UTC host event timestamps; they establish ordering, not submillisecond rail timing.

| Event | Awake trial | Standby trial |
| --- | --- | --- |
| Target power switched off | 06:43:42.881 | 06:50:30.316 |
| Zero current confirmed after about 15 seconds off | 06:43:57.990 | 06:50:45.379 |
| Target power restored | 06:43:58.500 | 06:50:45.884 |
| Post-cycle current signature queried | 06:44:08.854 | 06:50:56.280 |
| Warm UART recovery opened | 06:46:36.014 | 06:51:45.797 |
| UART stimulus completed; connection then closed | 06:46:37.393 | 06:51:47.176 |

The Standby-profile cycle reached a measured low-current signature of **4.892334 V / 8.185014 mA** on the JS-fed board branch. After the warm recovery, the read-only PWR observation at **06:51:57.363 UTC** reported **SBF=1, PDDS=1, STOPF=0**.

The standalone flag reader explicitly reports **`trial_entry_proven: false`**. Its meaning is retained: SBF establishes Standby since the last POR or CSSF clear; the reader itself does not independently prove attribution to this trial without the corresponding pre-entry flag-clear proof and reset/power history. The cold-cycle and recovery event records provide context, but this archive does not change that flag into a stronger assertion. The low-current sample alone is also not an entry proof.

## Final handoff state

The full slot-28 readback completed using the reviewed 12.5 MHz RAM reader, SHA256 `2829eae05cd96f5f7bfe36ac852d6904341c513aba51639a0e800bb171b735f5`. Its final terminal proof reports READ operation 3, result 0, media idle, initialized 0, controller-owned 0 and cleanup-error 0.

At **06:58:15.142580 UTC**, the Joulescope helper stopped cleanly, restored range128 and reported no restoration error. The last sample was **4.879318 V / 82.639635 mA**. That is the **awake READ-helper current**, not Standby current or capture energy. Target power remained on; the final installed NOR remains the Standby image above. Root reported no active bench helper. No additional normal capture is implied by this handoff.

## Evidence and limits

- [Sanitized qualification summary and source-file hashes](final-qualification.json).
- Exact programming/readback proofs: `final-{awake,standby}-nor-write.json`, `final-{awake,standby}-nor.json` and `final-{awake,standby}-nor-following.json`.
- Cold and recovery timelines: `final-{awake,standby}-boot.json`, `final-{awake,standby}-events.json`, `final-{awake,standby}-recovery-uart.json` and `final-{awake,standby}-recovery-park.json`.
- [Awake capture proof](final-awake-capture.json), [awake SD validation](final-awake-readback.json), [Standby SD validation](final-standby-readback.json), [unaltered Standby flag semantics](final-standby-flag.json), [final READ terminal](final-read-terminal.json), and [clean instrument stop](final-instrument-stop.json).

Raw frame payloads and six-line analyzer captures remain in the private `tmp/bringup/sd50-reviewed-20261026/final-*` directories. Those captures were retained but not independently redecoded during this archival step. The image comparisons above are independently checked from the retrieved bytes.

A separate [independent wire review](FINAL-STANDBY-WIRE.md) subsequently
verified all 3,730 packets, all 14,920 lane CRCs and complete wire-to-SD
equality for slot28, including CMD12 busy and final READY/TRANSFER.

These two cold trials do not establish a reliability rate, arbitrary-card compatibility, arbitrary power-loss safety, production power consumption or 50 MHz read reliability. The startup optimization still assumes the card's shared 3.3 V rail is already valid before the retained GPIO-settling interval. The saved-object markers do not add a pixel checksum. The unresolved 50 MHz read failures remain a separate result.
