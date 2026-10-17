# Late receiver accepts the second triggered image

This v32 diagnostic keeps the late receiver and noncontinuous camera clock from [v31](../2026-10-17-v31-phy-sequence/README.md), then requests another image after the first exposure and subsequent clock/data Stop indications. **The first requested image is lost; the second is received intact.** No PHY reset or DCMIPP rearm occurs between requests. This is diagnostic evidence about receiver initialization, not a successful first-frame capture or a new latency result.

The manifest explicitly records `captured_sensor_frame=2` and `first_frame_latency_eligible=false`. These semantics are also copied into the derived ledger. Its generic `first_frame_complete` field means the first frame actually received, which is the second requested sensor image here. It must not be combined with the first strobe timestamp to claim first-image latency.

| Observation | Time after NRST, ms |
| --- | ---: |
| First exposure strobe rises | 25.16496 |
| First exposure strobe falls | 36.14864 |
| All three lane Stop flags observed | 47.23712 |
| Stop qualification complete | 47.37296 |
| Second FSYNC transaction begins | 47.38000 |
| Second exposure strobe rises | 58.49296 |
| Second exposure strobe falls | 69.47696 |
| First receiver VSYNC | 69.73184 |
| Received frame complete | 80.35472 |
| Lane-1 ECTRL callback during later sensor stop | 83.27568 |

The root bench controller personally inspected the second image and confirmed a recognizable detailed workshop/bench scene. Full native RAW10 geometry and MCU/host integrity checks pass. The diagnostic ring did not overflow, and the physical cold-cycle validation passed for all three measured rails. The archive omits pixel data but retains the exact host/MCU checks and the separate visual assertion.

Raw status history is clean through the received frame and the pre-stop snapshot. The sole recorded error is physical lane-1 `0x1000` (`0x8000` in the HAL software code), observed between the before-stop and after-stop snapshots. The HAL acknowledges it, so the later cleared status does not erase its recorded occurrence. Callback timestamps follow hardware detection; they are not exact electrical-transition times.

The result strengthens the hypothesis that the late receiver misses the initial clock-entry/qualification sequence, then becomes able to receive after the transmitter returns to a recognized Stop state. It also establishes that the late path can receive valid data without a receiver reset or another setup pass. It does **not** identify the exact initial wire transition, prove the first transfer's clock behavior, or make discarding the first image acceptable for the project. The next early-clock/late-data first-frame experiment is separate. Final baseline restoration is pending with the bench owner.

## Archive integrity

The immutable [configuration](archive-config.json), [ledger](ledger.json), [visual assertion](visual-review.json), and [source provenance](source-provenance.json) cover **111 files/references, 1,608,481 bytes**. All manifest sources were recovered exactly, with shared objects referenced by hash. The programmed 65,536-byte sector passed full readback verification with SHA-256 `4abd59ddd5418e82462aeb33dd075470c7ec756836540816f1cd94bc607e02ac`. Compact raw diagnostics, digital traces, rails, programming records and manifests are retained; frames, full NOR content, analog streams and Saleae sessions remain local. This README is outside the immutable index for later cross-references.
