# TIM5 qualification of the exposure marker: native RAW10 v29b

October 17, 2026. One autonomous cold start captured a discernible LED panel at native **1120 × 1364, 10-bit precision**, inspected by the root bench controller. This isolated derivative of v25 adds input-only TIM5 captures on the existing PA0 sensor STROBE connection. It preserves the EXTI/PE0 timing markers, native image checks and sensor sequence. The unused TIM2 candidate was never executed; the ROM already owns TIM2, so the tested build uses previously disabled TIM5.

| Observation | Result |
| --- | ---: |
| NRST to first external exposure marker | 23.732160 ms |
| NRST to first synchronized TIM5 rising edge, empirical bracket | 23.728175–23.731486 ms |
| First synchronized edge to PE0, empirical bracket | **0.6743–3.9855 µs** |
| Largest upper marker-delay endpoint across four edges | **4.1001 µs** |
| NRST to first complete frame | 45.589920 ms |
| First external exposure pulse width | 10,984.000 µs |
| First timer pulse width using independent near-exposure calibration | 10,983.945 µs |

All four rising/falling captures passed validity flags, pin levels and ordered event association. No overcapture or record overflow was observed; the independently sampled timer/DWT counters confirmed their 3:4 clock ratio. The first pulse preceded the first complete frame. The native frame passed the exact 3,055,360-byte receiver counter, intact canary, matching MCU/host byte checksum and zero invalid upper sample bits. The [separate visual record](visual-review.json) preserves the root's image assessment without rewriting the original result's pending-inspection field.

## Calibration and limits

The CPU and timer share the oscillator error: nominal 400/300 MHz are not exact. Independent, near-exposure non-strobe events 26-to-29 measured CPU 396.715738 MHz and TIM5 297.536803 MHz. Other non-strobe intervals had different average rates. The decoder retains these observations and an empirical frequency envelope, including an explicit total 20.32 µs endpoint allowance. That allowance consists of 10 µs logging displacement and one 0.16 µs Saleae sample per endpoint; it is a conservative assumption, not a proved bound.

An initial attempt to use the much longer event 3-to-40 interval as a constant clock predicted 10,978.717 µs for the first pulse and failed the consistency check against 10,984.000 µs externally. [The rejected-calibration note](rejected-long-calibration.json) reconstructs this failed calculation from unchanged raw records. The final [timer analysis](capture/timer-analysis.json) uses the independent near-exposure interval and retains all other rates. No physical cause for their variation is established. The observed frequency envelope is neither a universal nor a pointwise instantaneous-frequency bound.

The delay brackets are relative to TIM5's synchronized input. They exclude sensor-output, translator and timer-input synchronization delays. The NRST-relative values apply that correction to sampled markers; their displayed precision does not remove the external trace's 0.16 µs sample spacing or establish calibrated absolute-time accuracy. Adding counter reads slightly perturbs the instrumented callback; this is an observed qualification of this diagnostic, not an exact correction to every earlier capture or a universal interrupt-latency guarantee. Nevertheless, the observed microsecond delay is far smaller than the millisecond-scale optimization questions.

The existing startup D-PHY control-sequence error remains a separate qualification issue. Native image integrity and recognizable content do not establish that every receiver error has been eliminated. See the full [experiment report](../../experiments.md).

## Reproduction and provenance

The [archive index](archive-index.json) contains exact SHA-256, byte lengths and original paths for 56 copied files (~1.45 MB). It preserves the matched digital event trace, rail validation, timer words, result JSON, build manifests, programming verification, exact manifest-declared source bytes and analysis tools. [Source provenance](source-provenance.json) maps content-addressed copies back to their sources. Vendor notices are included under `licenses/`. Source manifests retain their original pre-execution status.

The receiver SHA-256 is `1f2872c92f99e7aba87e5e0dc13e224f4912bd7fc667e53304ec136318dece26`. The programmed and verified 64 KiB sector SHA-256 is `a5a3fb619cfcfaff4f7cd4c83a8d5103053fe43b791e3ca66dc1230c6d85e7ca`. Full frame bytes, previews, NOR dumps, large analog traces and Saleae recordings remain outside this compact archive. The parent evidence `.gitattributes` disables Git text conversion. The one-off archive script assumes its original `tmp/capture-research` location; source/tool snapshots are preserved for provenance.
