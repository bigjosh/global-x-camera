# PNG encoder decisions

## 2026-10-20  Preserve ten sensor bits with a transparent sixteen-bit PNG mapping

**Why:** `sample << 6` stores every RAW10 value losslessly in broadly decodable grayscale16 PNG with `sBIT=10`, while keeping conversion simple. The user accepted zero-filled low bits, including white at 65472 rather than 65535. No gamma, contrast or inferred precision is introduced.
**Rejected:** discarding low sensor bits, inventing extra precision, or applying undisclosed image corrections during storage/export.
**Evidence:** commit `ecc3108d`; [sample mapping](README.md); [approved implementation scope](../../docs/decisions/capture-png-sd-2026-10-20.md#user-approved-scope); full-sample encoder tests.
**Provenance:** migrated 2026-10-24 from the user's explicit acceptance and implementation; product USB-format selection remains in [product decisions](../../docs/decisions/NOTES.md).

## 2026-10-20  Select the faster complete save rather than the smallest PNG

**Why:** on the retained benchmark frame, the v8b dedicated fast/no-filter matcher produced 919,353 bytes versus 746,618 for the general matcher, but reduced COMPLETE time to 1.6831–1.6842 s versus 2.0899–2.1387 s. Direct stored-DEFLATE avoided pointless dictionary work but still transferred 3,080,000 bytes. The cached Os fast-none build was the measured prototype compromise.
**Rejected:** choosing compression ratio or host CPU speed alone; assuming Sub always helps; generalizing one scene/card or differing complete builds into a universal matcher-only performance result.
**Evidence:** commit `5fd94243`; [exact tradeoff table and full pixel readback](../../docs/decisions/capture-png-sd-2026-10-20.md#selected-v8b-compressor-and-v50-integration); [historical installed evidence](../capture-sd/evidence/2026-10-20-hardware/README.md).
**Provenance:** migrated 2026-10-24 from contemporaneous MCU benchmarks. RAW later replaced capture-time PNG; this remains the qualified historical PNG choice, not the currently installed storage path.

## 2026-10-20  Patch the fast matcher for defined byte access and budget its real stack

**Why:** merely enabling miniz's fast loop would retain misaligned typed-pointer traversal and a four-byte distance copy into a two-byte field. The local patch uses byte pointers, bytewise little-endian reads and exact two-byte storage while retaining upstream hashes/licenses. Dynamic Huffman optimization also used a 5,576-byte local frame, exceeding the old capture stack's entire 4 KiB reservation; SAVE reserves at least 16 KiB plus a separate workspace.
**Rejected:** enabling the fast macro without fixing undefined access, depending on alignment traps being off, or putting the encoder workspace on the stack.
**Evidence:** commit `5fd94243`; [patch provenance](vendor/miniz/LOCAL_PATCHES.json); [exact patch](vendor/miniz/fast-loop-byte-safe.patch); [stack and compiler constraints](README.md#api-and-bounds); sanitizer and boundary tests.
**Provenance:** migrated 2026-10-24 from source/disassembly review and executable tests.

## 2026-10-24  Keep the faster Huffman/MVE path an explicit pipeline candidate

**Why:** literal-only Sub/Huffman with bounded batch/pair optimization and MVE conversion reached about 0.435 s compute time and 1,026,718 bytes on one fixed frame, close to the modeled 0.387 s card-write time. This justified investigating real producer/consumer overlap rather than forcing artificial rate matching. It did not measure concurrent SD writes, complete-cycle energy or an integrated SAVE replacement.
**Rejected:** a generic 32-bit bit writer with little benefit; globally applying O2 when the older fast-LZ mode slowed despite identical bytes; treating this single scene as a universal ratio. Returning SAVE code must preserve its caller's CPACR/CONTROL context, unlike the non-returning compute harness.
**Evidence:** commit `6dc71fac`; [MCU study](evidence/2026-10-24-mcu-tuning/README.md); [integration proposal](evidence/2026-10-24-mcu-tuning/integration-proposal.md); [recorded decision](../../docs/decisions/capture-png-sd-2026-10-20.md#october-24--compression-tuned-for-the-one-bit-sd-pipeline).
**Provenance:** migrated 2026-10-24 from repeated compute-only experiments and explicit deferral. DMA/overlap and MVE SAVE integration were not qualified before the RAW pivot.
