# Probe qualification — October 23, 2026

**Work in progress.** These records qualify the physical PD12 probe connection
and a fresh recovery park on unchanged v59. They do not qualify the encoded
phase pulses, an instrumented capture, storage performance, or a new firmware.

The confirmed connections are CH0 to NRST, CH1 to PD12/CN15 pin 21,
CH4 to target 5 V, CH6 to PE6/VCP TX, and common ground. The reversible PD12
test used 6.25 MS/s digital and 31.25 kS/s analog sampling. Those slow GPIO
toggles are only a wiring test; the phase captures use higher sampling rates.

1. [Static reading](probe-static-01/digital-summary.json): NRST and target 5 V
   were HIGH; PD12 and PE6 were initially LOW, with no recorded transitions.
2. [First PD12 test](pd12-toggle-01/result.json): all six requested levels
   matched the MCU's own IDR, and the prior GPIO configuration was restored.
   Nevertheless, the [external probe](pd12-toggle-01/probe-summary.json)
   remained LOW, with an analog range of −0.117 to 0.107 V. This test failed
   physical connectivity qualification; an MCU readback alone was insufficient.
3. After the user reseated the connection, the
   [second test](pd12-toggle-02/result.json) again matched all six requested IDR
   states and restored GPIO configuration. The
   [external measurement](pd12-toggle-02/probe-summary.json) recorded all six
   transitions, reaching 3.348 V. Target 5 V remained 4.827–4.852 V; NRST and
   PE6 stayed HIGH during this slow GPIO test.
4. The [fresh exact park check](smoke-park-02/result.json) passed for the unchanged
   v59 prefix: nine accepted VCP pulses, zero bad pulses, CONTROL=0, caches off,
   and XSPI idle. This is the state from which separately guarded maintenance
   may proceed. The prior [park check](smoke-park-01/result.json) and
   [UART stimulus configuration](smoke-recovery-01/config.json) are also retained.

The GPIO test itself issued no reset, NOR write or SD command. The preceding
UART recovery test intentionally asserted and released reset through BREAK.
Both GPIO attempts restored the original GPIO registers; no wiring success is
claimed from the failed first attempt. The installed sector remained
`7fda9d00cc7ffb3fbb9e6aac6695cf18545754b5dbfce1520cf30b2da39c4e63`.

Compact logs, register dumps, configurations and small digital edge files are
preserved verbatim. [Omitted-waveform references](omitted-waveforms.json)
record the original local paths, sizes and SHA-256 hashes of SAL captures,
large analog/digital CSVs and the large UART interval listing. The
[compact UART summary](smoke-recovery-01/compact-summary.json) preserves
channel extrema, interval counts, the full small NRST interval list, and the
source's limitations. It is explicitly derived; original raw files remain local.
The [stopped JS response](smoke-power/stopped-response.json) records that helper's
timeout and restored range; it is historical and not a claim about later
instrument ownership or target state.
