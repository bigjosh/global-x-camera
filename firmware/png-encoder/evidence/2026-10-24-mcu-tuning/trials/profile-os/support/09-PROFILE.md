# Coarse miniz profiling experiment

This isolated source starts from `huffman-local-source-v1`; it retains its
dictionary and original bit emitter. Production code and installed firmware
are unchanged. All modes retain their exact encoded bytes. The additional
coarse wrappers perturb execution and layout, so this experiment diagnoses
relative costs; it is not an uninstrumented performance comparison.

`bench/build.py` preserves all original compute guard, cache, input/output,
nonce, deadline and exact park checks. It exports counters only after the
encoder returns, into the existing report's 53 reserved words (absolute report
word 74). This is **MPF1**, not the separate MVE extension. No new MMIO access
exists except read-only DWT CYCCNT; the harness already verifies DWT running.
Each scope is assumed shorter than one CYCCNT wrap; totals are 64-bit.

`decode_profile.py terminal.json` validates the extension and subtracts nested
time into disjoint stages. Accumulation includes histogram increments,
dictionary stores and token packing; it excludes child block flushes. Tree
construction is split from dynamic/static header work. Emission, Adler, raw
fallback, histogram clearing, remaining flush bookkeeping and output callback
are separate. Output callback includes PNG framing and sink work, so exclude
it when comparing with the outer PNG DEFLATE category. Initialization is also
reported. Probe and wrapper overhead remains inside the enclosing intervals.
There are no per-byte profiling reads.

The original benchmark runner can execute this exact reviewed build without
changes. It preserves the extension as `reserved0` through `reserved52` in
terminal JSON, while keeping its independent fixture/output/park validation.
The profiler decoder does not itself establish successful benchmark execution.

The existing supplier provenance applies to the parent source; this experiment
is separately hash-recorded in `EXPERIMENT.json` and the build manifest. The
supplier-reversal test is intentionally excluded for the local instrumentation.
All output/golden/sanitizer tests remain required.
