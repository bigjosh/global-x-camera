# Final native RAW10 repeats: v25 starts 03-05

All three discharged cold starts captured a discernible LED panel at native 1120 x 1364, 10-bit precision. The root bench controller personally viewed each fixed-scale preview. These use the exact selected v25 firmware from the unchanged [earlier two-run archive](../2026-10-17-native-raw10-v25/README.md).

| Measured milestone | Cold 03 | Cold 04 | Cold 05 |
| --- | ---: | ---: | ---: |
| NRST to first application marker | 16.38368 ms | 16.20352 ms | 16.28512 ms |
| NRST to first exposure strobe | **24.01344 ms** | **23.83360 ms** | **23.91440 ms** |
| NRST to complete first frame | 45.87136 ms | 45.69152 ms | 45.77232 ms |
| START end to first strobe | 5.30080 ms | 5.30176 ms | 5.30432 ms |
| Common measured rail-off interval | 13.381056 s | 13.544640 s | 13.303680 s |

All three passed the exact 3,055,360-byte receiver counter, canary, MCU/host integrity and sample upper-bit checks. Each retained the pre-exposure D-PHY state-sequence error; no recorded CRC/ECC error appeared. The lane interrupt disables itself after the first error, so this is not exhaustive electrical qualification.

Across the five starts of the selected v25 image, exposure began at **23.32416-24.01344 ms** after NRST (median **23.89520 ms**). The complete-frame range was **45.18208-45.87136 ms**. These are five room-temperature observations, not production bounds. The strobe is mirrored through an interrupt; see the separate timing-probe qualification for observation delay.

Firmware was restored and fully verified before starts 03 and 05; start 04 repeats start 03 without another programming cycle. Both restoration records share sector SHA-256 `c43721b29f437546d3090632495f4527f4ba34d4af773a23214cdd86a0adb817`. All three results identify receiver SHA-256 `85313ae05070d80717c29a8a546bf56976930ac1f47b92e4ae70576ae72c940f`. This archive contains 58 indexed files (176,262 bytes), including exact timing/results, digital/rail data, small RAM diagnostics, programming metadata and manifests. Source provenance references matching content-addressed objects in the earlier archive rather than duplicating them. No prior archive is modified.

Images, raw frames, full NOR dumps, large analog streams and Saleae recordings are omitted. Original result visual fields remain unchanged; [visual-review.json](visual-review.json) preserves the separate root-controller assertions. This is an offline archive, and no instrument was accessed while constructing it.
