# Frozen diagnostic build inputs

**Work in progress: software review passed; hardware qualification is separate.**
This directory preserves exact v60c awake and v61b Standby phase overlays,
including their frozen source manifests and small firmware payloads. No camera
image, SD-card dump, ELF/debug image, object file or large waveform is included.
Original Windows paths in manifests are provenance, not portable build paths.

The [portable recipe](../archive-build.json) lists the ordered translation units,
flags, linker scripts, payload identities and toolchain hashes. It reuses the
hash-pinned headers and upstream license notices in the adjacent
[October 20 low-power archive](../../2026-10-20-low-power/README.md). Both archive
directories must remain together. This avoids duplicating that dependency tree
and requires no ignored `tmp` checkout. The compiler and runtime libraries are
external, hash-pinned prerequisites and are not redistributed.

The [recorded offline rebuild](rebuild-verification.json) reproduced all seven
payload groups and both complete NOR sectors byte for byte on October 23.

```powershell
python verify_build.py
python rebuild.py --toolchain <matching-tools-root> --out <new-directory> --execute
```

Run from this archive's parent directory. Rebuild is offline only. It requires
byte-identical payloads, ROM headers and complete 64 KiB sectors before success.
The verifier covers the indexed frozen files and shared dependencies while
allowing later qualification addenda to be added alongside them.

| Candidate | Sector SHA-256 |
| --- | --- |
| v60c awake | `20444827100b1a33826c5b7e3362a396a0ce31f27f0c3db7fea12fb755320f7e` |
| v61b Standby | `cc49159990ecd7aab9b0ab9c9055b3c230cc2ef639b1c295c511bea4a8be943f` |

Both use storage module
`51c067de2859588fc87cf1249fdff4186b17a4e0ab85585c72fc9b5dc94379f5`.
The complete early recovery branch, park and referenced literals remain identical
to the qualified baseline. The awake variant uses the v50 maintenance architecture;
the Standby variant retains v59's LPL/LPM ownership gates and late shutdown module.
See the [frozen protocol description](../support/phase_markers/README.md) for
event definitions and timing perturbations. Pulse 10 is intent, not proof of
physical Standby. A later measured result must not silently change these frozen
manifests' original `untested` labels.
