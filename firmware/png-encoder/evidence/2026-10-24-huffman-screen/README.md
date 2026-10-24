# Cheaper lossless PNG screen — October 24, 2026

This is an **offline host screen**, not a new installed firmware or an MCU
performance claim. Every PNG still represents the original RAW10 samples as
16-bit grayscale `sample << 6`, with `sBIT=10`. No RAW frame, PNG or other image
payload is included. The input hash identifies the private IMG67 source.

The current MCU timing breakdown for IMG67 put about 786.5 nominal milliseconds
in DEFLATE including Adler, 131.5 ms in conversion/validation, 33.9 ms in PNG
framing/CRC, and 552.3 ms in synchronous output callbacks. Those are distinct
measured scopes; DEFLATE is not a pure match-loop measurement. See the
[normal-profile analysis](../../../capture-sd/evidence/2026-10-24-normal-profile/analysis/README.md).

## Screen results

The Clang `-O2` host builds use the frozen `baseline/` sources. Each case has
one warm-up and five timed encodes, including Python collecting callbacks.
The cases were run sequentially, not interleaved; OS scheduling affected some
samples. Every result was independently CRC-checked/inflated and all 1,527,680
pixels compared exactly. These figures rank candidate experiments, not expected
Cortex-M55 speedups.

| Variant on private IMG67 | PNG bytes | Host median encode |
| --- | ---: | ---: |
| Current one-probe fast LZ, None | 1,452,183 | 28.09 ms |
| Current fast LZ, Sub | 1,305,199 | 27.73 ms |
| Forced fixed Huffman, None | 2,033,582 | 29.37 ms |
| Stock Huffman-only, Sub | 1,026,718 | 43.82 ms |
| Stock RLE, Sub | 1,057,252 | 47.04 ms |
| Stock filtered matches, Sub | 1,031,235 | 63.34 ms |
| Two probes/general loop, Sub | 1,187,954 | 44.66 ms |
| Larger default miniz workspace, Sub | 1,238,094 | 32.73 ms |
| **Direct literal-only prototype, Sub** | **1,026,718** | **19.82 ms** |

The current one-probe mode already selects miniz's dedicated fast match loop.
RLE, filtered matches and different probe counts select its general loop.
Even stock Huffman-only builds unused hash chains; the direct prototype removes
that work while retaining the shared Huffman, raw fallback and checksum code.
Forced fixed codes preserve the fast matcher but substantially enlarge this
image. Increasing the miniz workspace from 170,216 to 321,768 host bytes made
only a modest size improvement here and was not faster.

The direct prototype is **not universally better**: for a constant-value frame,
Huffman+Sub produced 386,324 bytes versus 20,307 bytes for fast-LZ+Sub, and took
more host time. On full-range synthetic RAW10 noise it produced about 2.278 MB,
close to the fast path's 2.305 MB. The complete per-case timings, ranges, sizes
and input hashes are in `host-screen.json`; do not extrapolate a single scene
to all camera captures.

## Optional implementation and qualification

The public encoder now exposes `PNG16_HUFFMAN_SUB = 3`. Its narrow explicit
vendor flag selects the literal-only loop only for supported callback/checksum
configuration. This production candidate is derived from the screen prototype,
but the table above describes the prototype, not a newly timed MCU build.
The camera SAVE default and installed image were not changed by this work.

The candidate passed 26 offline tests, including all sensor values, odd rows,
padding/alignment, full-size noise, dirty workspace, individual source-byte
changes, every output-callback failure boundary, and timing partition checks.
Six prior fast-mode output hashes remain unchanged. A standalone actual-C
ASan/UBSan stressor passed 648 cases. Low-level tests cover one-byte input calls,
32 KiB dictionary wrap, incompressible raw fallback, full flush, rejected
strategy flags and output exhaustion. Both provenance patches reverse exactly
to the original pinned upstream bytes. A Cortex-M55 `-Os` standalone link passed
with no unresolved symbols (13,556 bytes text); it is not deployable firmware.

Next qualification should compare fast-None, fast-Sub and Huffman-Sub on the
same retained MCU frame, separating CPU encode cost from SD writes. Keep all
checksums and exact sample conversion. Measure several real scenes before
selecting a default. Filtering, batching, checksum implementations and adaptive
match skipping are separate experiments; their benefits have not been measured
by this screen.

## Reproduction

`baseline-index.json` pins the 17 source/dependency/license files used by the
screen. `screen.py` makes disposable copies and applies the recorded variants;
it accepts an optional private frame and writes only a JSON result plus code
build outputs. The direct prototype insertion is in `direct-prototype.txt`.
The baseline source snapshot is deliberately historical and does not replace the
current encoder. `candidate-index.json` separately pins the tested optional
implementation and test sources in `candidate/`; `qualification.json`,
`tests.log` and `arm-link-check.json` record its offline checks. The original
supplier license and provenance accompany both snapshots.

```powershell
python firmware/png-encoder/evidence/2026-10-24-huffman-screen/screen.py `
  --raw <private-1120x1364-raw10-le16-frame.bin> --out <new-local-output-folder>
```

Without `--raw`, only deterministic noise and constant synthetic cases run.
Timing depends on host/compiler/load. The recorded source hashes and image
sizes can be reproduced; identical wall times are not expected.
