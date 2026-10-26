# 12.5 MHz startup and tail-wait trials

The selected configuration for the next flash qualification is **reviewed four-bit 12.5 MHz, falling-edge output launch during both initialization and transfer, startup optimization enabled, tail wait disabled**. Compensation, GPIO speed3 and the existing guarded source-publication rules remain unchanged. These are RAM-awake experiments; they do not establish cold-start timing, Standby behavior or energy consumption.

All four complete SD readbacks independently match their original camera RAM, including all 1,909,600 packed RAW10 bytes. Their 1,909,760-byte slots contain `GXR2`, 152 zero metadata bytes, the image and `GXRE`. Independent PNG decoding reproduces the retrieved samples. No erase was required for these trials.

## Measured intervals

All values are milliseconds from the fixed 400 MHz RAM counter. Each row is one observed run. The logger span starts at logger initialization and ends at its completed publication; it is not a power-good or reset-release interval. Storage starts at `RP_FIRST_WRITE` before the SD stream call and ends at `RP_PAYLOAD_DONE` after its return.

| Trial / slot | Initial clock train | ACMD41 | SD initialization | Capture SCR API | Slot scan | Tail wait | Storage | Logger span |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Prior startup + tail diagnostic / 23 | 10.021 | 203.689 | 227.397 | 0.180 | 17.417 | 0; already complete | 323.056, IDMA | 582.492 |
| Optimized startup + tail / 24 | 1.021 | 12.089 | 26.339 | 0.003 | 13.925 | 10.005; timeout | 321.562, PIO | 386.287 |
| Optimized startup, long exposure / 25 | 1.020 | 12.089 | 25.844 | 0.003 | 15.117 | 0; frame incomplete | 321.376, PIO | 771.483 |
| Optimized startup, no tail / 26 | 1.022 | 12.089 | 26.375 | 0.003 | 15.198 | disabled | 321.701, PIO | 377.896 |

**Do not attribute the roughly 200 ms difference from the first row to this optimization.** The control's card ACMD41 readiness took 203.689 ms, versus about 12.089 ms in the subsequent runs. The source change deliberately removes 9 ms of nominal initial clock training, about 1 ms of nominal divider settling, and the duplicate SCR wire transaction. Card readiness and scan position vary independently. The measured clock-switch interval, including callbacks and the required fresh status check, changed from 1.072 ms to about 0.148 ms in the ordinary startup runs; it is not simply the configured 1 µs delay.

The tail-enabled optimized run waited 10.005 ms for validated frame/STOP publication, then timed out and used PIO. The no-tail run began PIO about 0.013 ms after scanning, while storage duration stayed within 0.139 ms of the tail-enabled run. These observations support removing that deliberate wait at 12.5 MHz. They do not prove that PIO universally outperforms IDMA or that energy improves. Slots 24 and 26 scanned 25 and 27 headers respectively, so their total difference is not an isolated single-variable benchmark.

## Long-exposure and image verification

Slot 25 used 230.597 ms exposure, SD preinitialization and twenty immediate LINE snapshots. The first write began **9.433 ms before FRAME**, retained progressive PIO and did not wait for the tail while the frame was incomplete. All twenty 512-byte snapshots match the corresponding final frame bytes. These observations exercise the overlap and conservative publication path; the different exposure, preinitialization and diagnostic copies make this row unsuitable for a normal-cycle speed comparison.

The short and long reconstructed scenes were independently inspected: both show the illuminated triangular lattice/panel and surrounding structure. The long exposure reveals more of the surrounding equipment. See [short-exposure image](startup-notail-scene.png) and [long-exposure image](startup-long-scene.png).

Each capture ended with result 0, all 3,730 sectors written, media idle, controller deinitialized and no retained cleanup error. The image comparisons are stronger than the magic markers alone; the slot format still has no on-media pixel checksum and these tests do not qualify arbitrary power loss.

## Admission and replay

- [Structured timing, source hashes and byte-equality summary](startup125-trials.json).
- Per-trial small proofs: `tail125-{capture,readback,trace}.json`, `startup125-{capture,readback,trace}.json`, `startup-long-{capture,readback,trace}.json`, and `startup-notail-{capture,readback,trace}.json` in this directory. Full RAM/SD payloads and analyzer recordings remain in the private `tmp/bringup/sd50-reviewed-20261026/` tree.
- [Exact flash recovery admission](startup125-offline-recovery-admission.json): awake and Standby each retain the 15,804-byte early load, all 20 recovery literals and all 1,774 compared disassembly rows. Only the two allowed CRC words differ from frozen v23. Both exact prefix/sector gates pass; eight park and fourteen readback regressions pass. This admits the particular images for separate hardware qualification and does not claim they are installed.

The shorter startup clock train assumes the card's shared 3.3 V supply is already valid before the retained 1 ms GPIO settling interval. It must be requalified for a newly switched or ramping card rail. High Speed 50 MHz read errors remain unresolved; none of these lower-clock successes qualifies that mode.
