# MCU PNG tuning — October 24, 2026

The best tested candidate reduces PNG CPU time from **953.5 ms to 435.1 ms** on this fixed frame, while reducing the file from **1,452,183 to 1,026,718 bytes**: 54.4% less CPU time and 29.3% fewer bytes. It combines the paired literal-Huffman emitter, Sub filtering, O2 compilation and MVE row conversion. The archive contains 57 successful speed runs plus one separately labeled profiling run across 11 executables.

This is a compute-only comparison on the STM32N657 at the existing 400 MHz clock, using one identical uploaded 1120 × 1364 RAW10 frame. Each completed run checks the input before and after encoding, the entire output byte count and FNV digest, stack/frame guards, cache cleanup and exact final RAM park. The host independently encodes and decodes the frozen source version and checks every pixel against the fixture. These tests do not write the SD card or NOR, and do not measure a complete camera cycle or integrated asynchronous storage.

At the previously measured one-bit SD rate, that final PNG would take about **387.4 ms** to transfer. CPU and transfer are now close: a full 32 KiB producer interval averages **13.94 ms** (p95 **15.84 ms**), compared with a modeled **12.37 ms** write. A serial payload estimate is **822.5 ms**; hypothetical perfect overlap is **435.1 ms**, and the measured-interval two-buffer model gives **448.9 ms**. These are storage models, not measured DMA performance or energy. One retained frame establishes this result; other scenes can change the compression ratio and the balance between computation and writing.

The archived records deliberately omit the RAW fixture, PNG images, redundant live code copies and large instrument recordings. The fixture is identified by SHA-256 `ba0e69552271a93a743ebe0778c30fcdfc168532955129eae8312e3cbf7936d3`. Complete target PNG bytes were not downloaded by this compute harness: target verification uses the complete byte count and FNV digest against the independently decoded host result. FNV is an error-detection check, not a cryptographic proof of equality.

The benchmark matrix and final restoration are complete. A manifest's original `unqualified_offline_build` wording remains unchanged; completed hardware qualification is supplied separately by the corresponding run records.

The [comparison tables](comparison.md) separate measured CPU phases from hypothetical storage overlap. [summary.json](summary.json) retains every run and its interval statistics.

The [integration proposal](integration-proposal.md) records how an optional optimized encoder could be incorporated while preserving caller context and existing completion guards. It is a proposal; these compute trials do not qualify that production change.

The [canonical promotion record](canonical-promotion/archive.json) preserves the optional scalar Huffman source, its patch provenance and all 29 passing encoder tests. Its O2 build is byte-identical to the qualified scalar paired candidate. **The installed camera firmware and SAVE mode 1 default remain unchanged; SAVE still rejects mode 3, and MVE has not been promoted.** The measured mode-1 CPU regression is recorded below and must be considered before integrating this source into a new SAVE build.

A [subsequent UTF-8 documentation repair](canonical-promotion/encoding-repair/archive.json) corrects five damaged punctuation sequences without changing executable source. Both the original promotion record and the corrected README are preserved.

## Replaying the evidence

From this directory, using the bundled Python runtime or equivalent standard Python:

```powershell
python replay.py --out summary.json
python test_replay.py
python report.py
python rebuild.py --out D:/Github/global-x-camera/tmp/png-mcu-archive-rebuild
```

`replay.py` verifies every indexed source/record and the pinned shared CMSIS inputs, binds request nonces to raw 512-byte reports, checks interval accounting and successful terminal context, and derives [summary.json](summary.json). No bench package is imported or executed. `rebuild.py` additionally requires the exact STM32 GCC toolchain identified in each archive and reconstructs the executable from the archived sources and shared headers; it refuses an existing output directory. Each completed trial's executable has reproduced byte for byte. Rebuild result metadata is retained under `rebuild-results/`.

Each `trials/<name>/archive.json` records original paths, sizes and SHA-256 hashes. Its `build/` directory contains the frozen source, binary, symbols and manifest. Its `support/` directory preserves the executed runner and validation policy; `records/` contains original plans, requests, reports, interval records and CLI logs. The original executable and source files are never silently rewritten to match later revisions.

The original [miniz license](licenses/LICENSE) and [upstream identity](licenses/UPSTREAM.json) are retained. Experimental sources are local derivatives; their exact contents are separately hashed in each build manifest.

[Host validation support](host-validation/environment.json) records the independent PNG parser and Python/NumPy/Pillow versions. Repeating the full pixel roundtrip requires the deliberately omitted private fixture; compact replay verifies its recorded hash and target/host result agreement.

## Measurement and model boundaries

Speed-comparison medians use three runs per mode; the separately labeled profiling diagnostic has one run. Modes 1, 2 and 3 are fast/no-filter, fast/Sub and literal-Huffman/Sub respectively. Scalar builds explicitly use `-mgeneral-regs-only`, soft-float ABI and `-mno-unaligned-access`; Os/O2 comparisons therefore describe these scalar executables, not a production compiler switch. Reviewed MVE variants have their own exact runner and post-C context-normalization proof, while the scalar runner retains its strict zero-CONTROL policy.

The measured CPU total excludes the complete PNG callback. The cumulative 32 KiB interval CPU value excludes only the measured sink body and still includes callback and timer-edge overhead. Consequently, interval timings are labeled **producer-time proxies** and are not rescaled to the final CPU total. `summary.json` includes mean, p95 and each repeat's timings, plus the conversion, DEFLATE, framing, callback and residual partitions.

The trial names identify complete executables, not isolated single-variable effects. In particular, `mve-local-o2` includes the local-hoist compressor as well as MVE conversion and a different ABI/layout. Its modes 1/2 must not be interpreted as an isolated MVE regression against the earlier pre-hoist `scalar-o2` executable. The source bindings and measured phase partitions remain available for narrower follow-up comparisons.

The paired-emitter scalar candidate demonstrates a real tradeoff: mode 3 improves to about 507 ms CPU, while its measured mode 1 takes about 1,088 ms versus 837 ms in the earlier scalar O2 executable. These results support a specialized mode-3 optimization, not a claim that this entire candidate makes every existing mode faster.

The storage models use the previously measured one-bit SD driver rate of **2,649,960 bytes/s**, from the [October 23 same-frame experiment](../../../capture-sd/evidence/2026-10-23-one-bit-baseline/same-frame/README.md). They are calculations, not simultaneous SD measurements:

- Serial payload estimate: measured CPU time + PNG bytes / prior driver rate.
- Ideal overlap lower bound: max(measured CPU time, PNG bytes / prior driver rate).
- Finite two-buffer proxy: each buffer becomes reusable after its previous write finishes; the producer and writer are scheduled from the measured output intervals and the assumed constant transfer rate.

These models exclude initialization, metadata updates, altered card-busy behavior, DMA setup, bus contention and any CPU cost of the eventual storage driver. No four-bit speed, power or energy result is inferred here. More compact output can improve serial save time even if it costs additional CPU time; with sufficiently fast overlapping writes the fastest producer may instead win.

The interval proxy can omit a small producer tail after its final checkpoint, particularly when output is exactly a multiple of 32 KiB and the sink adds no final partial checkpoint. The current compared PNGs are not exact multiples. This remains a model limit, not measured concurrent-transfer behavior.

## Recovery provenance

[Initial recovery records](initial-recovery/archive.json) preserve both the first incomplete/failed park attempt and the successful second exact v66c park, with small original logs and status records. Large edge lists are represented only by explicitly compacted summaries and source hashes. The bench owner recorded the user's exclusive-bench authorization; that fact does not change repository instrument policy. The compute experiments used RAM-only execution, and the archive tools accessed no hardware.

The [first MVE emitter attempt](failures/mve-emitter-cpacr/archive.json) refused PREPARE with `PB_BAD_CONTEXT` before RAW upload or encoding. Its inherited CPACR was zero: the SRAM bootstrap had not enabled FP/MVE access. The original failed executable, adapter and status are retained. It contributes no speed result, and any subsequent candidate must explicitly acquire FP/MVE access only after checking the inherited context.

The [first restoration attempt](restoration/refused-initial-current/archive.json) verified the fresh final compute proof and exact RAM park, then refused before a power-switch command because its initial current did not satisfy the helper's assumed quiet-current gate. Its original failure and stopped recorder state remain preserved; it is not evidence that a normal camera cycle completed.

The [final checkpoint](restoration/final-state.json), replayable with `final_state.py`, records one later bounded off/on cycle after fresh completed-compute proof. The first attempt's last sample was about 562 mA; the second attempt's six initial readings were already about **83.8 mA before power-off**. The cause is unknown, so the later cold cycle is not credited with resolving that observation.

The second attempt observed 15.016 s off with zero measured current, then active current followed by **8.169 mA at 4.892 V**. It recorded ten complete marker pulses, while the original strict width decoder still failed. The JS helper stopped cleanly on October 24 at 04:15:24 UTC, restored range 128 and left the target powered; the hardware owner reports COM8 closed, BREAK released and Logic 2 running. Installed v66c was unchanged by owner attestation; NOR was not reread at this checkpoint. No new SBF or photo readback was performed, so these observations do not independently prove physical Standby or final image integrity. The restoration host sent no storage commands; the normal camera firmware can save a new photo during this boot.
