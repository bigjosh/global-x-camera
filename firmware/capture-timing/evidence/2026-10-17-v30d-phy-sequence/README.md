# Guarded continuous-clock receiver sequencing comparison

This checkpoint preserves successful debugger recovery after the [failed v30b trial](../2026-10-17-v30-phy-sequence/README.md), followed by the actual matched v30d early/late trials. **Late receiver release removed the observed startup warning but also lost reception. It is not a working workaround.** No v25 restoration or final bench-release claim belongs to this checkpoint.

Both variants use native 1120 × 1364 RAW10, the same manual exposure/gain, documented I²C follower mode, and continuous camera clock. The early control releases/configures the receiver before waiting for START acknowledgment and sensor STREAMING; the late variant waits first. Both qualify data-lane Stop before arming and issuing FSYNC. Exact build sources and manifests are retained. Diagnostic snapshots skip CSI accesses while its peripheral reset is asserted or required clocks are disabled; `PRCR=0xFFFFFFFF` marks an unread record, not a measured register value.

| Observation | Early receiver | Late receiver |
| --- | ---: | ---: |
| START command returned, ms after NRST | 18.68592 | 19.41104 |
| After PEN release marker, ms | 22.20176 | 24.92000 |
| START acknowledgment/STREAMING observed, ms | 24.08720 | 24.77760 |
| Startup lane-1 ECTRL callback, ms | 23.63280 | None observed |
| Data-lane Stop qualification, ms | 24.20016 | 25.40640 |
| FSYNC transaction began, ms | 24.28400 | 25.49040 |
| First exposure strobe, ms | 24.39600 | 25.60592 |
| First complete frame, ms | 46.25792 | None; 2 s timeout |
| Image integrity/visual result | Checks match; recognizable workshop scene | No frame to inspect |

Times come from each capture's matched RAM/external marker records. They are marker timestamps, not exact internal PHY transition instants. The full-resolution early image was personally inspected by the root bench controller: a detailed bench/workshop scene, rather than the earlier LED grid. Its RAW10 words had no nonzero upper bits and all four low-bit combinations were present.

The early run's raw startup snapshot records lane-1 `0x1000`; the HAL software code is `0x8000`. First-frame snapshots contain no recorded CSI errors. A fresh `0x1000` flag appears after sensor stop, distinct from the earlier acknowledged startup event. The HAL masks that source after its first callback, so one callback does not mean only one occurrence. The late run records no CSI errors but reaches failure stage `0x8000001c` without VSYNC/frame completion. Its post-release snapshots never show `ACTCLF`; qualified data Stop has `SR1=0x66180000`. These observations suggest that enabling the PHY after an already-running continuous clock misses the clock's entry sequence. This is an inference, not a captured lane waveform or proven hardware limitation. A matched noncontinuous-clock follow-up is outside this checkpoint.

Both measured cold cycles passed physical discharge/restoration checks on the three probed rails. The bounded diagnostic ring did not overflow. Neither discrete status samples nor a quiet interrupt history establish electrical compliance or the absence of events between samples.

## Recovery evidence

A raw no-core reset pulse returned execution to prefix failure code 17, before NOR loading and receiver/DMA startup. The exact live prefix bytes matched the expected hash, and the preserved prefix/trace/register checks established the restricted maintenance state. Core AP1 access returned without moving BOOT jumpers. The guarded maintenance script disabled caches without sending flash commands; frozen INFO sequence 3520 passed, then early v30d programming sequence 3521 passed full 65,536-byte readback. Proofs, compact raw binaries, scripts, commands and logs are under `extra/recovery/`.

The early image sector SHA-256 is `0194db3a0cbe1cdaf85926ef8ce729ca90b415d0030f620d42dd6aa3f99e1a49`; late is `f6b5eafded82193c2edfa1339cb65f44c75d0fcf59ee555101e712f394260793`. Earlier failed-status buffers remain in the earlier checkpoint and must not be interpreted as successful memory reads.

## Archive integrity

The explicit [configuration](archive-config.json), [ledger](ledger.json), [visual assertion](visual-review.json), and [source provenance](source-provenance.json) distinguish the completed early capture from failed late reception. The index covers **210 files/references, 1,802,007 bytes**, with all manifest sources recovered exactly. Existing exact source objects are shared by reference with earlier archives. Frame pixels, full NOR dumps, analog streams and Saleae sessions remain local. The archiver defaults to validation only and requires `--write` to publish; different-byte overwrites are rejected. This README is outside the immutable index so later results can be linked without rewriting the evidence.
