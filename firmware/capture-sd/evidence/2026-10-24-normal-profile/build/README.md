# Frozen normal-profile builds

These are the exact reviewed v64 awake and v65 Standby candidates. Hardware
qualification is recorded separately; their original `untested` manifest labels
are preserved. No camera images, SD-card contents, ELF files, object files or
large instrument waveforms are included here.

| Build | Complete 64 KiB sector SHA-256 |
| --- | --- |
| v64 normal awake | `6823ef327e6625d26877aa5d3a9b09353b52556434f41fc8d736e64bad508cc7` |
| v65 normal Standby | `409628f664b41b39b8a6397d9098a7bd3420d23c9d8441538e11e59ae9ee593c` |

Both use the 28,960-byte marked SAVE module
`0a1a116fea60ba1b60c8974853e69f29edf8a38faf3b934d1811f816f77396d6`.
The normal profile skips the receiver's full-frame statistics/hash scan, three
SAVE verification scans and the full stack fill/watermark scan. It retains cheap
raw CSI history, actual RAW10 and DMA-size checks, canaries, bounded sensor stop,
code identity checks, cache cleanup and SD/card-ready checks. Skipped work has
explicit report flags and zero fields; it is not reported as validated.

The [correction record](proof-address-correction.json) explains the earlier
LED/RCP2 overlap. RCP2 now occupies `0x343F8A80..0x343F8B00`, beyond the complete
LED record at `0x343F89C0..0x343F8A40`. The [layout regression test](../test_layout.py)
checks the actual copied headers, all 22 simultaneous high-SRAM records and the
separate early-helper lifetime map. It rejects the previous address and a
future LED-record expansion. An additional conservative prefix-stack reservation
was added to the audit after these builds froze; it changes no firmware byte or
original manifest.

The [portable build recipe](../archive-build.json) preserves the original ordered
translation units, compiler flags, linker scripts and exact source hashes. It
uses the hash-pinned ST/CMSIS headers in the adjacent
[October 20 archive](../../2026-10-20-low-power/README.md). Keep both directories
together. Original Windows paths in frozen manifests are provenance; the
portable recipe supplies local paths and needs no ignored `tmp` checkout.
The matching compiler and runtime libraries are external prerequisites.

Run from the archive root (the directory containing `archive-build.json`):

```powershell
python verify_build.py
python test_layout.py
python rebuild.py --toolchain <matching-tools-root> --out <new-directory> --execute
```

Rebuild is offline only and requires every payload, ROM header and complete
sector to match exactly. The two [peer reviews](reviews/) check sources, payload
packing, the unchanged early recovery branch and its 20 literal words, raw CSI
history, and the normal-profile completion gates. PD12 phase pulses remain
software observations; pulse 10 is entry intent, not proof of physical Standby.
