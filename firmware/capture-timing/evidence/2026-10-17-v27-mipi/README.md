# Independent MIPI startup diagnostics

These two v27 RAW8 experiments use the calibrated, size-optimized v24 prefix as their common baseline. Both produced a discernible LED panel confirmed by the root controller, matching image integrity checks and passing three-rail cold-cycle validation.

| Experiment | Change | START end → first strobe | First strobe after NRST | First frame after NRST |
| --- | --- | ---: | ---: | ---: |
| v27a | `DPHYTX_CTRL 0x0956 = 0x0C`, verified before START; same 804 Mbps and receiver | 5.29680 ms | 23.63792 ms | 45.49440 ms |
| v27b | Request 1000 Mbps at `0x0312`, verify it; receiver nominal PHY entry 1000; continuous clock retained | 5.29760 ms | 23.62832 ms | 45.48480 ms |

Neither change shortens the approximately 5.3 ms first-exposure interval or removes the startup `0x8000` D-PHY state-sequence error. No recorded CRC/ECC error appeared. The latter remains a qualification limitation because the HAL disables the first offending D-PHY interrupt source.

The v27b applied readback packs MIPI multiplier 39 in trace word 56 (`0x27018602`), with output divider 1 in word 57. The documented formula gives `804 MHz × 39 / 1 / 32 = 979.875 Mbps`. This is a nominal register-derived rate, not a lane-frequency measurement. ST's pinned nearest-rate selection still chooses the nominal 1000 receiver entry. Its table maps that entry to HSFR `0x0A` and oscillator target 460; the baseline 800 entry uses HSFR `0x09` and the same target. No numerical bin boundary is inferred from those enum names.

Timing/result/digital records are unchanged. Programming metadata, manifests and exact source hashes are preserved; identical source objects are referenced from the earlier v17–v24 archive. Images, full NOR content, large analog streams and Saleae sessions are omitted. Root owns execution and visual inspection; archival work was offline.
