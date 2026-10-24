# Repeated one-bit SAVE measurements

Three guarded RAM SAVE operations reused the same 1120 × 1364 RAW10 frame, card,
25 MHz one-bit SDMMC2 setup and instrumented v60c cached fast-none encoder.
Each produced a reported 1,458,185-byte PNG. Target counters and final storage
guards passed; subsequent bytewise readbacks are recorded separately, preserving
this analysis's original pending readback state.

The later [verification addendum](verification-addendum.json) confirms that
**IMG00062.PNG, IMG00063.PNG and IMG00064.PNG** all passed complete host readback,
all PNG chunk CRCs and all 1,527,680 pixel comparisons against RAW sample `<< 6`.
Their byte hashes are identical to the separately verified automatic
IMG00061.PNG. No image payload is included in this archive.

| Measurement | Median | Observed range |
| --- | ---: | ---: |
| COMPLETE, including final uncached frame check | 2.102061 s | 2.099228–2.104129 s |
| Legacy total, before that final check | 1.720871 s | 1.718038–1.722939 s |
| Encoder time excluding its output callbacks | 0.931825 s | 0.931625–0.931870 s |
| Output callback time | 0.555159 s | 0.555151–0.561849 s |
| SD driver write time | 0.552968 s | 0.549086–0.555298 s |
| SD driver physical write throughput | 2.64996 MB/s | 2.63331–2.66310 MB/s |
| Final uncached frame validation | 0.380714 s | 0.380714–0.380714 s |

Scopes overlap: callback time is within encoding, driver writes occur within
callbacks and filesystem work, and ready polling overlaps driver commands and
transfers. Do not add these rows. These repetitions reinitialize an already
powered card in about 26.6 ms; the automatic cold-capture SAVE's initialization
took about 122.6 ms. Do not pool the two conditions. Host process setup and
transport delays also remain separate from target timing.

The fixed-COMPLETE-duration energy analysis gives median lower/upper bounds of
**0.951779–1.023486 J**. This is a conditional containment interval, not a point
estimate or confidence interval: it assumes the reported 400 MHz cycle clock
and an explicit analyst-selected ±50 ms UTC mapping allowance, checks observed
mapping residuals, and considers **every** possible placement inside each
recorded host run-to-terminal bracket. No waveform feature or Saleae edge was
used to choose alignment. No idle baseline was subtracted. The measured branch
excludes other CN8/debugger supply paths. The wider host-bracket integrals and
their 3.016/3.125/3.063-second durations remain in `comparison.json`.

A deliberately optimistic payload-only model at the same 25 MHz changes each
data byte's wire time to one quarter, holding recorded sector counts and all
other work constant. It saves about **0.374–0.376 s**, giving **1.724–1.728 s**
COMPLETE (about **17.8% shorter**). This is not measured four-bit performance or
a strict bound. Card busy, protocol overhead, CPU service and future software
changes can alter it; compression, initialization and frame checks do not
automatically get four times faster. No four-bit energy prediction is made.

`summary.json` and the three `*-sliding.json` files hold exact values and limits.
`records/` preserves original SAVE reports, memory proofs, calls, host logs and
finalized raw-log metadata. Gzipped chunk logs retain exact power sample sums
and extrema; multi-gigabyte float arrays, camera pixels and SD file payloads are
excluded. The recorder and its pinned owner/helper sources are in
`recording-source/` for audit, not for execution from this archive.

Run `python replay.py --out NEW_DIRECTORY` to check every manifest hash, fresh
SAVE proof, card/frame identity, four-bit arithmetic and all energy bounds.
This portable replay uses the archived RAW SHA/FNV identity and target proofs;
it cannot independently recalculate the private frame's hash or decode images.
The original local analysis did verify that RAW file's SHA and FNV. These three
trials describe this frame/card/bench, not worst-case card behavior.
