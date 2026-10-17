# Two native RAW10 cold captures: v25

October 17, 2026. Both autonomous cold starts captured a discernible LED panel at native **1120 × 1364, 10-bit precision**, as inspected by the root bench controller. This build uses the trimmed sensor prefix at `-Os`, retaining the v24b memory bootstrap and native capture protections. Source inputs are the frozen v23 trimmed receiver and v24 size-optimized prefix, transformed by the isolated RAW10 builder.

| Measured milestone | Cold 01 | Cold 02 |
| --- | ---: | ---: |
| NRST to first application marker | 16.26752 ms | 15.69760 ms |
| NRST to first exposure strobe | **23.89520 ms** | **23.32416 ms** |
| NRST to first complete frame | 45.75312 ms | 45.18208 ms |
| First exposure strobe width | 10.98400 ms | 10.98400 ms |
| START write end to first exposure | 5.30096 ms | 5.30224 ms |
| Three-rail common discharged interval | 13.280928 s | 13.399264 s |

Both frames passed the exact 3,055,360-byte receiver counter, intact canary, matching MCU/host byte checksum, and zero invalid upper sample bits. All four low-two-bit combinations occurred. The host used a fixed RAW10 >> 2 preview; image inspection is recorded separately in [visual-review.json](visual-review.json), while original pending-inspection result fields remain unchanged.

The 0.57104 ms difference in first-exposure latency tracks a 0.56992 ms difference before the earliest application marker. That supports treating the two as repeats of the same application path; it does not establish a guaranteed minimum or worst case. The existing startup D-PHY sequence error occurred before exposure in both runs. No further callback was recorded during the first frame, but the HAL disables that interrupt after its first occurrence. These are valid-image results with a remaining receiver qualification issue.

The host chose the relevant NRST release after the midpoint of the measured common rail-off interval, avoiding any initial power-down bounce. Digital traces, rail checks and full ordered event correlations are retained. There was no debugger reset inserted into the measured cold starts. The probes cover the named 5 V, 3.3 V and MCU VDDIO rails, not all internal supplies. The exposure timestamp is a sensor strobe mirrored through an MCU interrupt, with positive propagation/logging delay not yet bounded.

## Evidence

The [archive index](archive-index.json) records exact SHA-256, byte lengths and original paths for 62 copied files (~1.45 MB). [The ledger](ledger.json) preserves first and later strobes and error phases. [Source provenance](source-provenance.json) verifies every copied manifest-declared source. Sources are content-addressed to avoid duplicate copies within this archive, and vendor notices are included in `licenses/`. Source manifests retain their original pre-execution status.

The programmed sector and verified readback share SHA-256 `c43721b29f437546d3090632495f4527f4ba34d4af773a23214cdd86a0adb817`. The receiver SHA-256 is `85313ae05070d80717c29a8a546bf56976930ac1f47b92e4ae70576ae72c940f`. The two captured image hashes remain in their unchanged result JSON and visual-review records.

Images, raw frame bytes, NOR dumps, large analog traces and Saleae recordings are excluded. Git text conversion is disabled through the parent evidence `.gitattributes`. Tool snapshots are provenance; the one-off archive script assumes its original `tmp/capture-research` location. These results do not implement or qualify PNG/PTP export, and the earlier faster RAW8 diagnostic record remains a separate profile.
