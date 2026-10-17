# Receiver-readiness evidence — October 17, 2026

Final hardware checkpoint: fourteen trials, including the failed retained-both-lanes ForceRx case, three autonomous recovery checks, and a released, powered final default configuration.

Times are microseconds. START is the sensor START-write-end marker. STROBE and VSYNC use the existing Saleae-correlated firmware marker method; no new direct analog exposure measurement is implied.

| Run | Outcome | Readiness condition | STOP dwell, nominal us | START → first STROBE | Arm → first VSYNC | First-frame identity supported | Raw errors |
| --- | --- | --- | ---: | ---: | ---: | --- | --- |
| v36-coarse5-baseline-01 | completed | START ACK and STREAMING; v36 baseline | 100 | 5364.96 | 84.8 | True | 0 sampled records |
| v37-streaming-stop10-install-01 | completed | start_ack_and_streaming | 10 | 5362.72 | 161.28 | True | 0 sampled records |
| v37-streaming-stop0-install-01 | completed | start_ack_and_streaming | 0 | 5361.92 | 141.28 | True | 0 sampled records |
| v38a-ack-stop0-install-01 | completed | start_ack | 0 | 5361.76 | 279.04 | True | 0 sampled records |
| v38b-ack-default-install-01 | completed | start_ack | 0 | 5301.12 | 11171.2 | True | 0 sampled records |
| v39-early-stop100-install-01 | completed | early_data_both_stop_stable100us | 100 | 5361.28 | 517.6 | True | 1 sampled records |
| v39-force-stop100-install-01 | failed | force_rx_both_stop_stable100us | 100 | 5361.6 | None | False | 0 sampled records |
| v41-lane1-stop100-install-01 | completed | force_rx_lane1_both_stop_stable100us | 100 | 5360.64 | 548.16 | True | 0 sampled records |
| v42-both-stop0-install-01 | completed | force_rx_both_stop_stable100us | 0 | 5365.76 | 651.68 | True | 0 sampled records |
| v43-lane1-pen200-install-01 | completed | force_rx_lane1_both_stop_stable100us | 100 | 5364.48 | 548.0 | True | 0 sampled records |
| v41-default-install-01 | completed | force_rx_lane1_both_stop_stable100us | 100 | 5298.24 | 11468.48 | True | 0 sampled records |
| v38a-ack-stop0-cold-02 | completed | start_ack | 0 | 5362.4 | 265.76 | True | 0 sampled records |
| v41-lane1-min-restore-02 | completed | force_rx_lane1_both_stop_stable100us | 100 | 5361.92 | 546.08 | True | 0 sampled records |
| v41-final-normal-02 | completed | force_rx_lane1_both_stop_stable100us | 100 | 5303.36 | 11472.8 | True | 0 sampled records |

Raw errors are decoded independently of HAL callback counts and interrupt-enable masks. Zero retained errors does not constitute a continuous electrical trace or production-corner guarantee. A supported first-frame identity combines STROBE ordinal, frame ordering and complete native-byte integrity; it is not embedded sensor frame-ID readback. Visual assertions are separate.

Event 250 retains an obsolete raw label in some captures; it means receiver configuration complete. Actual arm uses event 22 and FAST snapshot 422. Original raw labels remain unchanged.

For EARLY/ForceRx modes 4, 5 and 6, physical data enable is bracketed by FAST 405/406. Events 437/438 are only no-op lane checks. The raw ForceRx proof is decoded separately. The retained-both-lanes ForceRx trial did not receive any frame, although exposure strobes continued and raw error flags stayed zero. Its original capture failure and unreached shutdown proof are retained; offline timing/rail analysis does not change its failed outcome.

The recovery checks intentionally held PE0 low in the early park. Their generic first-GPIO analyzer failed its normal-boot marker and plateau expectations; that failure is retained. The exact prefix/park check and recorded rail discharge/restoration separately support the intended recovery result. See recovery-checks.json and the original qualification and inspection records.

The selected lane-1 ForceRx sequence keeps the measured 100 us STOP qualification. Its two minimum-exposure trials provide 546.08–548.16 us arm-to-first-VSYNC margin. Moving PEN later by a measured 207.65–215.20 us left first observed both-lane STOP within 0.86–4.20 us of the controls, supporting a sensor/START-relative readiness event rather than a fixed PEN-relative delay. These are observations on this board, not an electrical timing bound over production corners.

Final installed sector SHA-256: `c92ee95920009b188aef53645fce8e9bb6cb8bd34d78cf789d252037be16af2f`. Final normal capture, autonomous recovery park and post-release powered-state checks are retained separately. The latter observed stable rails for 3.019808 s after the JS110 session closed, with OUT0 settings restored to 3300 mV/HIGH.

Validation reported by the owning bench agent: 15 ready_phy offline tests and 10 exact full-prefix/sector allowlist checks passed. Archive byte/provenance validation is performed independently by this archiver.

- [Ledger](ledger.json)
- [Source provenance](source-provenance.json)
- [Visual review assertions](visual-review.json)
- [Archive hash index](archive-index.json)

Only explicitly completed or explicitly identified failed experiments are included. Frozen source bytes and manifests are attributed by SHA-256; unchanged sources may refer to verified objects in earlier archives. Generator-input fingerprints are retained even when an earlier generator revision is no longer available as bytes.

Frame pixels/images, analog CSVs and full Logic recordings remain local and are excluded. Compact status buffers, JSON, digital event CSVs, programming verification and licenses are retained. Run firmware/capture-timing/verify_evidence.py to verify archived bytes without local capture originals.
