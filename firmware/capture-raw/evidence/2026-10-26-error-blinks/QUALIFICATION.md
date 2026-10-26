# Installed error firmware: measured checks

The selected four-bit 25 MHz Standby firmware passed a normal cold capture
and synthetic error tests. Its exact receiver, prefix and programmed sector
identities are in [the archive overview](README.md). These tests qualify the
observed behavior; they do not reproduce every physical failure condition.

| Test | Result |
| --- | --- |
| Normal cold boot | 15-second JS output-off interval with near-zero current, then the installed image; no debugger/UART during boot |
| Saved image | Slot 51 was FREE beforehand; complete 3,730-sector readback at 25 MHz passed GXR2/GXRE and zero metadata checks |
| Independent image decoding | All recovered packed RAW10 samples matched the independently decoded 16-bit PNG after shifting samples left six; samples 74–1023 |
| Normal completion current | About 8.176 mA on the JS-fed Nucleo branch |
| Exact-prefix synthetic failure | The live 6,500-byte prefix matched at preparation and launch; stage-one result 17 was injected and its bridge entered directly |
| Prefix blink sequence | Ten pulses in five sets of two; on/off/set intervals consistent with 100/400/2,000 ms within the recorded uncertainty |
| Error completion current | About 8.066 mA after the final pair |
| Recovery after completion | Exact new-prefix early park; nine good UART pulses, zero bad |
| Recovery during error display | Requested 1.374658 seconds after launch, within the nominal 11.4-second sequence; first attempt reached the exact early park with nine good pulses and zero bad |
| Guarded completion flags | SBF=1, PDDS=1, STOPF=0; `trial_entry_proven:false` preserved |

Slot 50 was already occupied and is not attributed to the new normal test.
Slot 51's original camera RAM was lost in Standby; the private replay compares
SD chunks, the recovered slot and decoded PNG, not the lost camera source.
The bench owner visually inspected the recognizable patterned screen, beams
and cables. Photos remain private; their hashes and exact operation records
are public.

The current traces use native sample identifiers and retained 5 ms bins, with
conservative edge/filter uncertainty. Typical inferred on intervals were
95–105 ms, inter-blink dark intervals 405–410 ms, and inter-set dark intervals
2,015–2,020 ms. The source requests the exact nominal durations; this method
does not distinguish a small clock/loop error from current-bin threshold bias.
Startup nonfinite samples make whole-session coverage false, while all samples
within the reported fault windows are finite and continuous. No optical LED
probe, energy comparison or precision clock calibration is claimed.

The firmware source/model tests cover all codes and timer-failure positions;
178 capture tests passed in the final offline run. Codes 1 and 6 remain
reserved without detectors. Synthetic code 7 does not prove real full-card
allocation, and synthetic result 17 does not prove physical camera-disconnect
handling. The separate failure shutdown intentionally does not assert media
idle or successful commit and does not qualify SD power-loss preservation.

## Frozen records and replay

[The initial snapshot](snapshots/initial/summary.json) contains the build,
review, initial synthetic RAM tests and installation proof. [The qualification
snapshot](snapshots/qualification/summary.json) adds the normal cold capture,
same-speed readback, and exact production-prefix test. It binds the initial
snapshot by the SHA-256 of its manifest.

```text
python -B archive.py verify
python -B archive.py inspect --name qualification
```

The public verifier checks every archived byte, operation extent/error/clock
record, exact prefix identity, retained power flag and waveform analysis.
Photo reconstruction was performed against local private bytes at freeze time;
[private-image-check.json](snapshots/qualification/private-image-check.json)
records that result and its hashes. The public checkout cannot reconstruct
omitted photo payloads. Current replay uses only the frozen bins and NumPy.

The qualification snapshot preserves its then-pending closure state. The
separate [closure snapshot](snapshots/closure/summary.json) finishes that record:
the complete physical NOR sector still matched after the error tests, the
following 4 KiB remained unchanged, and a fresh exact park preceded another
normal cold boot. The JS110 closed cleanly at **20:59:16.244780 UTC**, restoring
range 128 and leaving target power on; its last observation was **4.892189 V /
8.181944 mA**. COM8 was closed and BREAK released according to the archived
parent checkpoint.

That final boot is a low-current signature only. Its expected next slot 52
and SBF were not reread; slot 51 is the fully verified saved image. No new
energy, analog-margin, formal SD compliance or power-loss claim is made.
