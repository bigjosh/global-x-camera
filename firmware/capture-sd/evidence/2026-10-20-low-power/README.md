# Post-save Standby firmware and evidence — October 20, 2026

This archive preserves the **v59 Standby firmware**, its exact build inputs,
and an offline rebuild that reproduced the complete NOR sector byte for byte.
The initial cold boot and three repeated trials each reached the low-current
state and then recovered on the first warm UART request. Each fresh recovery
check observed the exact early park and `PWR_CPUCR.SBF=1` (`CPUCR=0x10201`).
No power cycle occurred between each Standby observation and its UART reset
and SBF read. Three measured cycles reached the Standby plateau in
2.963–2.983 s, using 1.410–1.424 J in the measured JS110 branch. The plateau
drew 8.103–8.212 mA. All six requested files subsequently passed complete
PNG CRC/decoding and sample-format checks through the RAM READ bridge.
Original build manifests retain their pre-test `untested` status; measured
qualification is recorded separately here and in `archive-plan.json`.

The [program/readback result](results/v59-nor-write/verified.json) confirms
the installed sector. The [first recovery](results/v59-recovery-park-1/result.json)
and [first Standby flag read](results/v59-sbf-1/result.json) are followed by
three separately recorded energy trials in `results/v59-energy-*`.
All four recovery reports recorded nine accepted pulses and zero bad pulses.
This demonstrates the tested sequence; it is not a guarantee for every reset
phase, temperature, board, or power topology.

See the [energy analysis](energy/standby/README.md) and its
[qualified comparison figure](energy/standby/cold-cycle-comparison-qualified.png).
The v50 trace supports an approximately 80.03 mA awake-current comparison,
but its detected 1.239 J boundary can occur before final validation completes.
It is **not** a full-cycle baseline and must not be subtracted from v59 energy.

The [readback addendum](qualification/post-standby-readback.json) records
IMG00038 from Stop, IMG00039 from the first Standby trial and IMG00040–42 from
the three energy trials. IMG00001 also matched its original SHA-256 exactly.
All 38 READ chunks reported zero card writes and completed card cleanup.
No original RAW frame survives Standby, so these are complete file integrity
and decoding checks, not comparisons to the captured RAW pixels. This addendum
supersedes the pending readback notes in the frozen energy records without
altering those records or their hashes.

The [final bench state](results/final-state.json) leaves v59 powered after one
more normal cold boot, at an 8.210 mA plateau consistent with Standby. That final
run was left asleep; its SBF flag and expected new file IMG00043 were not read.
The Joulescope helper closed cleanly with range 128 restored, COM8 closed and
BREAK released. LTC RUN power-off and arbitrary SD power-loss behavior remain
unimplemented or unqualified.

The exact first 64 KiB NOR sector has SHA-256
`7fda9d00cc7ffb3fbb9e6aac6695cf18545754b5dbfce1520cf30b2da39c4e63`.
It contains four payloads:

| Payload | NOR offset | Bytes | Execution address |
|---|---:|---:|---:|
| ROM-wrapped recovery prefix | `0x0000` | 6,176 (5,140 raw) | `0x34180400` |
| Camera receiver and small loaders | `0x2000` | 15,560 | `0x34300000` |
| Frozen v8b PNG/FAT32 save module | `0x6000` | 27,420 | `0x34320000` |
| Late Standby completion module | `0xE000` | 3,764 | `0x343C0000` |

The bulk completion code is loaded only after the image has been saved and
the SD card has completed sync and deinitialization. Both NOR loaders require
a successful terminal status and the expected CRC before executing the loaded
code. The completion module has no initialized data or BSS and retains the
caller's stack. Its SRAM and proof areas do not overlap the retained frame,
storage workspace, or stack.

The PE1/PE6 recovery guard, its park at `0x3418078C`, and its referenced literals
remain identical to the v45b reference. This identity does not guarantee that
every warm reset or UART request selects recovery.

The terminal peripheral routine accepts PN1 reading LOW while in AF9, whose
cause remains unexplained. It preloads nCS HIGH, selects GPIO output and requires
HIGH readback before disabling XSPI or changing CLK/MOSI. It sends no NOR
write or deep-power-down command.

## Reproduce the firmware offline

Run with Python 3 and the matching STM32 GCC 12.3.1 toolchain:

```powershell
python verify.py
python rebuild.py --toolchain <matching-tools-root> --out <new-directory> --execute
python verify_git_bytes.py
python verify_git_bytes.py --staged
python energy/replay-energy.py --archive . --out <new-energy-directory> --figures
```

`verify.py` checks the complete file inventory, exact source and binary hashes,
four-payload layout, CRCs, memory bounds and early recovery identity.
`rebuild.py` compiles the four archived source groups in a new directory and
requires byte-identical binaries, ROM wrapper and complete NOR sector. It also
rebuilds the separate 1,324-byte RAM READ bridge, which is never installed in
NOR. The
matching compiler/runtime binaries are external prerequisites, hash pinned
and not redistributed. Actual transitive vendor headers and license notices
are included, so an ignored `tmp` checkout is not required.

Original paths in frozen manifests identify their provenance. Portable ordered
recipes in `archive-plan.json` use archive-relative files. The recipes compile
the frozen generated sources; they do not require rerunning the historical
generation chain. Generator sources are also retained for inspection.

The archive-local `.gitattributes` disables text normalization.
`verify_git_bytes.py` checks Git's actual clean-filter output, and `--staged`
also compares every stage-0 blob with the archived bytes. It does not alter
the index. Run it again after the parent task stages the completed archive.

## Scope and evidence limits

This archive contains no photos, RAW frames, SD sectors, or full raw
multi-gigabyte instrument recordings. Compact power evidence is retained
under `energy/`. Binned signed sums and extrema can reproduce aggregate
energy and figures, but cannot rerun the original raw onset/plateau detector.
Source recording and chunk-index hashes identify the retained local primary
data.

The Saleae summaries retain analog statistics and digital interval counts,
durations and source-file hashes. Threshold chatter is visible during power
transitions; an interval count is not a count of verified MCU resets. Raw
waveforms remain local, and the compact summaries cannot reconstruct them.

A prepared or ARMED SRAM record proves software intent, not physical entry.
Standby loses this SRAM. A fresh early-recovery SBF read can establish hardware
Standby history since the last POR/CSSF clear; attribution to a particular
trial also needs the pre-entry clear and reset/power history. SBF=0 is
inconclusive. GPIO reset behavior and the Nucleo's external regulator topology
matter: Standby releases ordinary GPIOs and removes the target's switched
camera/SD/NOR supplies. Board-level measured power is not an isolated
production-camera consumption figure.
