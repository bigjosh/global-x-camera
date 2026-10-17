# Fast free-running PHY evidence — October 17, 2026

Completed hardware checkpoint: 14 capture runs, a separate v36 cold recovery-park verification, final normal-boot confirmation and measured powered state after releasing the instrument session. No in-flight or proposed experiment is assigned a result.

All times below are microseconds. Reset means the measured NRST release; START means the end of the sensor START write. Exposure timing retains the existing Saleae/firmware STROBE-marker correlation. This archive does not introduce a direct analog exposure measurement.

| Capture | Applied coarse lines | Reset → first STROBE | START → first STROBE | Arm → first VSYNC | First frame ordinal supported | Raw SR1 error union through first frame | Raw SR1 error union during sensor STOP |
| --- | ---: | ---: | ---: | ---: | --- | --- | --- |
| v34c-baseline-01 | 1428 | 24092.8 | 5300.48 | not instrumented | not instrumented | not instrumented | not instrumented |
| v34c-baseline-02 | 1428 | 23877.92 | 5303.04 | not instrumented | not instrumented | not instrumented | not instrumented |
| v35-early-install-01 | 1428 | 24150.88 | 5302.56 | 11000.64 | yes | 0x00001000 | 0x00001000 |
| v35-streaming-install-01 | 1428 | 23972.16 | 5303.2 | 11022.88 | yes | 0x00000000 | 0x00001000 |
| v35-streaming-cold-02 | 1428 | 24167.52 | 5300.16 | 11013.44 | yes | 0x00000000 | 0x00001000 |
| v35-coarse5-install-01 | 5 | 24005.12 | 5361.44 | 95.04 | yes | 0x00000000 | 0x00001000 |
| v35-coarse21-install-01 | 21 | 23758.4 | 5304.8 | 204.96 | yes | 0x00000000 | 0x00001000 |
| v35-coarse40-install-01 | 40 | 24072.8 | 5299.2 | 349.12 | yes | 0x00000000 | 0x00001000 |
| v35-early-coarse5-install-01 | 5 | 24203.36 | 5361.28 | 86.08 | yes | 0x00001000 | 0x00001000 |
| v36-shutdown-install-01 | 1428 | 24197.28 | 5299.84 | 11010.56 | yes | 0x00000000 | 0x00000000 |
| v36-shutdown-coarse5-install-01 | 5 | 24256.8 | 5361.6 | 70.88 | yes | 0x00000000 | 0x00000000 |
| v36-coarse5-cold-02 | 5 | 23754.72 | 5358.88 | 51.36 | yes | 0x00000000 | 0x00000000 |
| v36-default-restore-02 | 1428 | 24542.24 | 5300.8 | 11010.72 | yes | 0x00000000 | 0x00000000 |
| v36-final-normal-03 | 1428 | 24241.12 | 5299.2 | 11008.48 | yes | 0x00000000 | 0x00000000 |

For the completed v36 five-line captures, observed arm-marker to first-VSYNC-marker margin is 51.36–70.88 µs. These bench runs do not qualify a guaranteed margin across voltage, temperature, sensor revisions or production variation.

5 v36 runs completed with shutdown proof: 3 at the default exposure and 2 at the five-line minimum. Every one supports first-frame ordinal 1, matches native frame integrity and has no sampled raw CSI errors in any recorded phase.

Final installed first-64-KiB image SHA-256: `40743205503bdb465d0549b7764f1590c48b7aaac621bf096aa4b9618957c1bd`.

The root agent reported 117 passing offline tests on the unchanged source:
- `python -m unittest discover -s firmware/boot-timing/tests -p test_*.py` — 58 passed.
- `python -m unittest discover -s firmware/capture-timing -p test_*.py` — 41 passed.
- `python firmware/capture-timing/fast_phy/test_fast_phy.py` — 18 passed.

An initial boot-test discovery command targeted the wrong directory and found zero tests. The corrected command above ran and passed all 58 boot tests; the zero-test invocation was not a test failure.


Raw status unions are independent of HAL callback counts and interrupt-enable masks. They describe the retained snapshots and IRQ-entry records; a zero value is not a continuous electrical lane trace. `0x00001000` is the lane-1 D-PHY control/state-sequence error. The ledger also retains SR0 protocol-error masks, all raw phase records, interrupt-enable values and shutdown proof where instrumented.

A supported first-frame ordinal combines the first-STROBE ordinal from the FAST buffer, correlated first-pulse/VSYNC/frame order, completed frame readback and matching integrity. It is not sensor embedded frame-ID readback. Visual review is recorded separately and is never inferred from pixel statistics.

For v35/v36 FAST builds, the inherited raw label on event 250 is obsolete: this event means receiver configuration completed. Actual arm timing uses event 22 and FAST snapshot 422. The archived raw labels are preserved without alteration.

- [Ledger and derived phase records](ledger.json)
- [Explicit visual review assertions](visual-review.json)
- [Final recovery park verification](recovery-checks.json)
- [Final powered state and released instrument session](final-state.json)
- [Build source provenance](source-provenance.json)
- [Archive hash index](archive-index.json)

Every capture is linked to a receiver manifest and a complete prefix image verified by full 64 KiB programming readback. The ledger records the recovery GPIO source hashes and each prefix hash; the earlier [diode recovery qualification](../2026-10-17-diode-recovery-smoke/README.md) remains the electrical recovery evidence. Original manifests retain their build-time `hardware_status` fields unchanged.

The archive contains compact JSON, status buffers, source objects, build manifests, programming verification and digital event CSVs. Frame images, raw frame pixels, analog CSVs and full Logic recordings remain local under `tmp/bringup` and are deliberately excluded. Unchanged source objects may be referenced by verified hash from earlier evidence archives. Vendor licenses and provenance are retained.

Each manifest preserves its original generator-input fingerprints. A fingerprint does not imply the historical generator bytes were recovered: separately archived generator revisions appear explicitly in the hash index. Compiled source files are individually attributed in the source-provenance record.

The top-level `firmware/capture-timing/verify_evidence.py` checks every indexed byte without the local capture originals. Replaying this archive script requires the original paths named in its configuration. Publication uses `--write` and refuses differing overwrites.
