# Noncontinuous-clock receiver sequencing comparison

This checkpoint tests whether noncontinuous camera clock repairs the failed late-enable reception observed in [v30d](../2026-10-17-v30d-phy-sequence/README.md). **It does not: the late variant again exposes an image but receives no frame.** The matched early control captures a valid first image with the usual startup lane-1 control error. A later second-trigger diagnostic and final v25 restoration are outside this archive.

Both variants retain native 1120 × 1364 RAW10, manual unity gains, the same exposure, and I²C follower operation. The documented camera `DPHYTX_CTRL` is changed to noncontinuous clock (`0x0C`), with the readback retained. The early receiver starts tracking before sensor START completes; the late receiver is held reset until acknowledgment/STREAMING is observed. Both qualify the data-lane Stop flags before arming and triggering.

| Observation, ms after NRST | Early receiver | Late receiver |
| --- | ---: | ---: |
| START transaction returned | 19.00576 | 18.88640 |
| After PHY PEN release marker | 22.52064 | 24.39120 |
| Sensor STREAMING observed | 24.40624 | 24.24880 |
| Startup lane-1 ECTRL callback | 23.95728 | None observed |
| Data-lane Stop qualified | 24.51904 | 24.87760 |
| FSYNC transaction began | 24.60288 | 24.96160 |
| First exposure strobe | 24.72032 | 25.07680 |
| First complete frame | 46.58224 | None; 2 s timeout |

The root bench controller personally viewed the early image and confirmed a recognizable detailed workshop/bench scene. MCU/host integrity checks match, RAW10 upper bits are valid, and all low-bit combinations are present. The late failure is stage `0x8000001c`; no image exists to inspect. Neither trial overflows its diagnostic ring, and both measured cold-cycle rail checks pass.

The late run records no CSI errors and no `ACTCLF` after PHY release. Its readiness snapshot is `SR1=0x66180000`, with both data Stop flags but no clock Stop or active-clock indication. After the missed frame the final snapshot is `0x76180000`, now including clock Stop. These observations show that data-lane Stop alone did not establish receiver readiness and that changing the requested clock mode alone did not repair late first-frame reception. They do not show the exact wire sequence, certify transmitter noncontinuous behavior electrically, or prove an analog fault. An error-free status record without image reception is not a successful workaround.

## Guard correction and instrument ownership

The original failure-recovery guard rejected a live receiver whose only differences from the expected image were three bytes inside its final `SystemCoreClock` word: initializer 64 MHz, runtime 400 MHz. The raw rejected code, trace/status reads, and an independent byte comparison are retained. The reviewed correction accepts only that explicitly identified aligned word and its expected runtime value; every other code byte, terminal-loop identity, interrupt state and no-DMA/reset proof remains checked. Successful guarded maintenance records for the v30d and v31 late failures are archived alongside the source and targeted test file. This corrects a false rejection; it does not weaken checks for arbitrary live-code changes.

The previous JS110 session stopped normally and restored range 128. A 35.064288 s external capture confirms all three measured rails and NRST/PD0 remained high across session renewal. The old session log and stop response are preserved. Session 2 was still active at this checkpoint: its archived log/response are snapshots, **not final release evidence**. No new MIPI probes were attached.

## Archive integrity

[Configuration](archive-config.json), [ledger](ledger.json), [visual assertion](visual-review.json), and [source provenance](source-provenance.json) preserve explicit outcomes. The index covers **211 files/references and 4,305,789 bytes**, with all manifest sources recovered exactly; source objects are shared by verified hash where possible. Compact raw register/event/status records and programming verification are retained. Full frame pixels, NOR readback, analog exports and Saleae sessions remain local. Existing files are immutable; this README can link later experiments without replacing the recorded evidence.
