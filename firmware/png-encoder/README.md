# Streaming grayscale PNG16 encoder

This standalone component encodes the existing right-aligned RAW10 LE16 image
without modifying it. It has no hardware, filesystem, heap, or second-frame
allocation. It is not installed firmware; the board integration and MCU timing
remain separate qualification steps.

Every input sample `v` must be 0–1023. The PNG stores `v << 6`, with grayscale
color type 0, 16-bit big-endian samples, `sBIT=10`, and no interlace. Decoding and
shifting right six bits exactly recovers the original samples. There is no
gamma, contrast, black-level correction or invented precision. White is 65472
rather than 65535, the small zero-fill difference accepted for this prototype.
See [PNG sample scaling](https://www.w3.org/TR/png-3/#sBIT).

## API and bounds

Include `png16.h` and compile **only `png16.c` and `png16_miniz.c`**. The latter
includes the pinned, locally patched checksum/compressor sources under one consistent
configuration. Do not separately compile the vendor C files.

```c
static png16_workspace workspace; /* Explicitly place outside frame/stack. */
png16_stats stats;
png16_result result = png16_encode(
    frame_le16, frame_bytes, 1120, 1364, 2240,
    PNG16_FAST_SUB, &workspace, sizeof(workspace),
    write_all_bytes, sink_context, &stats);
```

The callback accepts **all** supplied bytes and returns nonzero, or returns zero
on failure. Buffers are valid only during the callback. Calls are bounded to
16 KiB; PNG headers/CRCs can be much shorter. Buffer the sink separately for
efficient 32 KiB SD writes. Callback failure stops immediately. Any error leaves
an incomplete stream which must not be reported as a successful photo.

The caller must keep the input stable throughout encoding. Width is 1–1120,
height 1–1364; row stride may include padding. Byte-unaligned input is supported.
Input extent, workspace extent/alignment and overlap are checked. Invalid upper
sample bits are detected while encoding; late discovery can leave partial output.
The encoder does not scan the complete frame an extra time before starting.

The static workspace type reserves **192 KiB**, with 8-byte alignment. The
actual required size is available through `png16_workspace_size()` (170,096
bytes in the tested native 64-bit build). The compile-time budget is enforced.
An integrator may instead allocate the queried size/alignment. Each concurrent
encoder requires its own workspace and sink.

**Reserve at least 16 KiB of stack for the save stage**, and qualify its high
water mark including the sink callback. Upstream dynamic Huffman optimization
uses a 5,576-byte local stack frame on the tested Cortex-M55 `-Os` build, plus
callers. The old capture application's 4 KiB stack reservation is insufficient.
The encode workspace must not be placed on the stack.

Compile with function/data sections and link with `--gc-sections`. The MCU
save-module builder uses `-Os -mno-unaligned-access`: the latter preserves
byte-safe code generation even if a caller enables alignment traps. The
integration must supply its normal memory routines and verify its own map.
The complete reviewed v8b save module is 27,420 bytes of loaded code/data,
including the filesystem, card driver and encoder; its map is the relevant
integration budget rather than the earlier standalone encoder size probe.

## Three comparison modes

| Mode | PNG row filter | DEFLATE |
| --- | --- | --- |
| `PNG16_STORED_NONE` | None | Direct stored blocks; one block per row |
| `PNG16_FAST_NONE` | None | Dedicated one-probe greedy fast LZ/Huffman |
| `PNG16_FAST_SUB` | Sub, bytewise with two bytes per pixel | Same fast compressor |

Each mode is lossless and deterministic. Stored mode writes byte-aligned
[DEFLATE stored blocks](https://www.rfc-editor.org/rfc/rfc1951.html#section-3.2.4)
directly, bypassing miniz's dictionary/hash/literal machinery. Each row is one
block (at most 2,241 data bytes), with its own IDAT chunk; a single
[zlib header and Adler-32 footer](https://www.rfc-editor.org/rfc/rfc1950.html#section-2.2)
wrap the complete stream. CRC-32 still covers each PNG chunk. The exact encoded
size is `88 + height * (18 + 2 * width)` bytes: **3,080,000 bytes** for 1120×1364.
This adds 19,152 bytes versus the earlier miniz stored output for that frame
size, while removing unnecessary per-byte LZ processing. The 32 KiB SD sink
buffer remains the integrator's responsibility. Fast modes may choose
dynamic, fixed or stored blocks. All modes emit one zlib stream divided into
bounded IDAT chunks. The dedicated fast matcher is enabled with local
byte-pointer traversal and forced-inline little-endian byte reads; it does not
depend on undefined misaligned pointer dereferences. This matcher trades
compression ratio for CPU time. Its encoded bytes differ from the previous
general match loop while every reconstructed sensor sample remains identical.

Select a default using **measured total capture/save cost on the MCU**, not
host timings or compression ratio alone. Record conversion/compression cycles,
bytes written, SD transfer and busy intervals, filesystem sync/close and card
ready, and total energy/time. Synchronous callback time is part of encoder wall
time; isolate it or subtract sink timing before calling that compression cost.
Initial synthetic cases and a real LED-panel frame are useful, but noise and
different scenes can change compression substantially.

## Offline verification

```powershell
python -m unittest discover -s firmware/png-encoder -p test_png16.py -v
python firmware/png-encoder/check_arm.py --out tmp/bringup/png16-arm-check
python firmware/png-encoder/benchmark.py --out tmp/bringup/png16-host/report.json `
  --raw <local-native-RAW10-frame.bin>
```

The tests compile the actual C component and independently parse/check PNG
chunks, inflate with Python zlib, reverse filtering and decode with Pillow.
They compare every 16-bit output and reconstructed 10-bit sample, exercise all
1024 values, full-size noise, odd widths/padding, unaligned input, dirty workspace,
callback failures, invalid inputs/aliases, canaries, and supplier hashes.
Stored-block tests independently inspect every BFINAL/BTYPE, LEN/NLEN, payload,
and Adler footer, including aggregate streams crossing 64 KiB and maximum frames.
Six SHA-256 fixtures protect the intended dedicated fast-matcher output and
also decode every pixel. Boundary cases cover 1–4-byte tails, 4 KiB lookahead and
32 KiB dictionary crossings. A standalone Clang ASan/UBSan test adds 432 C
stress cases and asserts that instrumentation has not disabled the fast path.
Host benchmarks verify round trips and report size/host wall time; they never
access the MCU or card. Outputs are JSON summaries, with no PNG/pixel data.

## Dependency provenance

The vendor directory starts from
[miniz 3.1.0](https://github.com/richgel999/miniz/tree/174573d60290f447c13a2b1b3405de2b96e27d6c),
commit `174573d60290f447c13a2b1b3405de2b96e27d6c`. `UPSTREAM.json` records each
original HTTPS source URL, byte count and SHA-256; those original records and
the upstream [license](vendor/miniz/LICENSE) are unchanged.
[LOCAL_PATCHES.json](vendor/miniz/LOCAL_PATCHES.json) separately records the
before/after hashes of three patched vendor files and the
[exact patch](vendor/miniz/fast-loop-byte-safe.patch). The changes replace
misaligned typed-pointer traversal with byte pointers, use defined bytewise
word reads, store exactly two distance bytes in a three-byte LZ token, and keep
the safe path exercised under UBSan. The otherwise unused common LE-read macros
also retain their bytewise fallback. `miniz_export.h` remains a local static-link
visibility shim. No attribution or license terms were removed.

The low-level tdefl API is configured with `TDEFL_LESS_MEMORY=1`; heap, archive,
stdio, time, inflate and zlib-compatible convenience APIs are disabled.
Only the streaming compressor and checksums are used. PNG metadata/chunks are
implemented in this component rather than using miniz's heap PNG convenience API.
