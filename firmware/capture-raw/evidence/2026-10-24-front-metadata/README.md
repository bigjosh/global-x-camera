# First-sector photo metadata — October 24, 2026

v18 is installed and qualified for the current one-bit SD bench. It moves the
152 previously trailing padding bytes into the first sector, keeping the same
3730-sector slot size and one CMD25 per capture. The card was **not erased**;
previous GXRS slots and new GXR2 slots coexist.

| Bytes within a new slot | Contents |
|---|---|
| 0–3 | `GXR2` layout/occupancy marker |
| 4–155 | 152 reserved metadata bytes; currently zero, no field schema assigned |
| 156–1,909,755 | 1,909,600 packed RAW10 image bytes |
| 1,909,756–1,909,759 | `GXRE` completion marker |

A single 512-byte read now retrieves occupancy and all metadata. It does **not**
check the final completion marker. Zero metadata does not represent a valid
timestamp. Markers do not checksum pixels or qualify arbitrary power loss.

## Hardware verification

| Test | Recorded result |
|---|---|
| Normal pattern, slot 7 | Complete SD image matched original camera RAM; IDMA mode, one 3730-sector write |
| 230.597 ms exposure, slot 8 | Complete SD image matched original camera RAM; progressive PIO mode, first write 9.4470975 ms before FRAME |
| LINE publication, long exposure | 20 immediate published-tail snapshots, 10,240 bytes, matched final RAM |
| Old GXRS slot 0 | Complete slot and RAW hashes unchanged from the previous experiment |
| First-sector directory reads | Exactly four sectors read for slots 0, 7, 8 and 9: occupied, occupied, occupied, free |
| Normal cold v18 capture, slot 9 | Full readback, markers and independent PNG decoding passed; root visually confirmed a coherent illuminated panel/bench scene |
| Warm recovery and Standby | First recovery attempt passed the exact v18 early park; SBF=1 was read without a power interruption and attributed to the recorded cold cycle |
| Installation | Complete 64 KiB NOR readback matched; following 4 KiB unchanged |

The source camera RAM was lost in the slot-9 Standby cycle, so its readback is
not claimed to match original sensor RAM. Slots 7 and 8 supply that separate
comparison. The LINE result is empirical memory-visibility evidence, not an
AXI-drain timing guarantee. This layout change has **no new comparative cycle
time or energy result**.

The runtime preserves the reviewed SD driver, 15,804-byte early load, recovery
instructions and all 20 recovery literal words. Only the two receiver CRC words
change in the 5140-byte prefix. Offline suites passed: capture 67, slot format
20, SD driver 2 and recovery 11 (**100 tests**).

## Installed identity and handoff

- Sector SHA-256: `174424c6792f96c72e336fc68e442474e9da665718552d3239a772d59ba73e2e`
- Prefix SHA-256: `9401bed4076d6e9e4d2e4f9236661faf7b8f0e051cb332ea4dcbba09da336eba`
- Final extra cold boot: **2026-10-24 19:02:04.963439 UTC**, target left powered at **4.892723 V / 8.078679 mA** on the JS-fed board branch.
- Expected final slot **10** and final SBF were **not reread**. This handoff is a low-current signature with events 1–9; the final pulse remains unidentified. It is separate from qualified slot 9.
- JS110 stopped cleanly with range 128 restored; COM8 closed, BREAK released, Logic 2 running and no bench helper active. Wiring and boot jumpers were unchanged.

## Compact archive and offline replay

[`index.json`](index.json) maps 243 logical files to 167 SHA-256-addressed
objects in [`objects.zip`](objects.zip), a 630,201-byte compressed archive.
It includes the three frozen builds, source/manifest/binary identities, exact
recovery review, test logs, terminal proofs, all bounded READ proofs, parsed
metadata, installation checks, phase/SBF records, visual-review attribution and
final ownership state. [`replay-result.json`](replay-result.json) records the
successful standalone check.

From the repository root:

```powershell
python firmware/capture-raw/evidence/2026-10-24-front-metadata/replay.py
```

The replay uses only Python's standard library and never accesses hardware. It
checks archive hashes, frozen firmware/source bindings, recorded terminal
invariants, complete READ extents, metadata, installation preservation and
cycle/image/SBF attribution.

**Private image bytes, whole SD sectors, SRAM dumps, raw instrument captures and
power streams are excluded.** A first directory sector also contains pixels,
so only its parsed metadata and recorded proof/hash are retained publicly. The
archive can replay the recorded verification and attribution; it cannot repeat
pixel decoding, source-RAM comparisons or power integration without the local
private artifacts. Existing evidence archives are unchanged.

Current behavior and extraction instructions are in the
[capture README](../../README.md) and [slot-format README](../../../raw-slots/README.md).
