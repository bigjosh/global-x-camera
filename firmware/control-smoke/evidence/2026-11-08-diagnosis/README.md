# Exposure ADC isolation diagnosis — November 8, 2026

**Resolved:** ADC12 was nonsecure while PA12, PF3 and PG15 were secure.
STM32N6 keeps those external analog switches open in this combination
(RM0486 section 15.3.16). Register access, calibration and internal-reference
conversion continued to work, so none alone proved that the external pins
were connected. Setting only ADC12's security bit restored the readings.

## Evidence

| Test | Result |
|---|---|
| User's A4 meter sweep | 0–3.28 V |
| Three-channel baseline, v6 | A3 about950, A5 about945, A4 about932 despite driven endpoints |
| VREFBUF clock/external mode, v7 | No correction; CSR remained ENVR=0/HIZ=1 |
| ADC HSI/8 clock, v8 | External readings still wrong |
| User's VREF+ measurement | 1.79 V |
| Internal VREFINT, v9 | 1819–1825, consistent with nominal0.8 V and measured reference |
| User's TP9 measurement | Buffered signal correctly followed the knob |
| ADC12 security correction, v10 | SEC2 0→1; privilege and GPIO security unchanged; A3=2–3, A5=3840, A4 about2900 at that position |
| Final default HCLK/32, v11 | A3 near0, A5=3841; A4 swept0–3841 without reported errors |

The user confirmed the live console now follows the knob. The upper code is
below4095 with the current calibration; this is a functional travel test,
not a linearity, voltage-accuracy or optimized-settling qualification.

Frozen builds, manifests, sources and debugger operations are in `builds/`
and `launches/`. `measurements/adc-secure01/security-proof.json` records the
security-only change. `measurements/sweep-snapshot/` freezes the successful
live-console evidence; the original monitor continued after this snapshot.
The official ST example and reference-manual excerpts are retained in
`official-adc-review/`; the TP9 locator is in `tp9/`.

## Qualification and handoff

Final RAM v11 SHA256:
`3bed14f57abf64211d5ea8794cacf45741797c6163c42b3abf8ae1bfddefc86a`.
The final session is `tmp/bringup/control-smoke-20261107/launch07/session.json`.
The visible console PID9240 logs `live-console-fixed/` in that campaign and
owns ST-LINK while running. Check current ownership before another client.

The target was left ON running this RAM diagnostic, with PD7 HOLD HIGH,
A3 LOW and A5 HIGH. At36000 samples (about1hour) it drives A5 LOW and parks
awake with HOLD HIGH. COM8 was closed/BREAK released; the Joulescope app and
power output were untouched. The upstream supply was not independently
identified. No reset, power cycle, NOR programming, camera or SD command
was used during this diagnosis. Normal October28 camera FLASH is unchanged;
reset discards the RAM diagnostic.

The final warm replacement explicitly restored HCLK/32 but inherited the
enabled VREFBUF peripheral clock from v7. Enabling that clock alone did not
fix the fault; its absence on a fresh cold startup was not qualified. Do not
interpret this test as normal camera integration or cold-start qualification.

`SHA256SUMS` binds the archived file bytes. The local `.gitattributes` retains
those bytes across Git text normalization.
