# Canonical A3 HOLD — November 9, 2026

**PA2 / Arduino A3 / CN4 pin 4 is now the capture HOLD pin.** The user moved
the exposure potentiometer to A0–A2 and confirmed the board is disconnected.
This is an offline firmware/package qualification: no debugger, instrument,
NOR, SD or physical power-latch operation occurred, and no new firmware is
claimed installed. The [combined USB candidate](../../../usb-ptp/evidence/2026-11-09-a3-hold/README.md)
uses this capture image; its integration evidence is separate.

## Behavior and recovery

The first ROM entry enables GPIOA, preloads PA2 HIGH, selects push-pull output
at low slew with no pull, and resumes the original reset handler. It uses no
stack or RAM. Only PA2's GPIO fields change; the old D9/PD7 HOLD is no longer
selected. Normal sensor startup later changes PA0 only and preserves PA2.

HOLD stays HIGH through capture/save, error blinking, UART recovery, awake
completion and refused Standby. Success/error shutdown floats PA2 with no
pull immediately before WFI; the software does not assert it LOW. An
unexpected WFI return reasserts HIGH. The external R2 turns Q2 off when PA2
floats. No extra C1/D1 delay is assumed or added; AUX shutdown ordering remains
unqualified under the user's accepted prototype policy.

Original startup/UART/loader/bridge bytes remain exact, except the selected
reset vector and two equal receiver CRC words. All twenty UART literals and
the recovery branch/park addresses remain unchanged. The first receiver load
is still 15,804 bytes. Schema **3** strictly binds GPIOA/pin2/A3; schemas **1/2**
remain exact historical PD7 contracts and cannot be relabeled as PA2.

## Non-overlapping prefix layout

| Region | Address | Size / boundary |
|---|---:|---:|
| Original error engine | `0x34181840` | Ends `0x34181DC8` |
| Unused fill | `0x34181DC8` | 40 zero bytes |
| Stackless PA2 boot hook | `0x34181DF0` | 76 bytes; ends `0x34181E3C` |
| Final fill | `0x34181E3C` | 4 bytes |
| Reserved native USB selector tail | `0x34181E40` | 448 bytes available |

The older PD7 hook used `0x34181E40`, which conflicts with native USB. The PA2
hook occupies otherwise unused padding in the fixed 1,536-byte error copy.
It is reachable only via the new reset vector, never from error handling.
The linker refuses overlapping code. The copy audit checks actual error
instructions through their exact end, rejecting branches and PC-relative
references into the boot-only padding. Hook bytes, fill and the end symbol
are separately authenticated. The full 1,536-byte copy/hash remains fixed;
copying the unused hook does not execute it.

Both linked release groups are **70 bytes**, WFI at offset 40, immediate
reassertion at offset 42. Their SHA-256 is
`c1d616c9e36ab5b1ddbe9b75aebbcdf777c59878bc196e431ba024b7c7cf4930`.

## Exact artifacts

| Artifact | Standby candidate SHA-256 |
|---|---|
| Receiver | `b45cb9a76f1fd97e23ac447b4709a82308b50e1f0e9bac70318d8920f5588463` |
| Prefix, 6,720 bytes | `95312a3a9782ddae82157c3d9859c31de157f8a42e4e9cf370ccba93b26acdfc` |
| NOR sector, 64 KiB | `86786daaaa689b1df556603ca3a4df9b09dcff37d1095d56821c6fa01f99ce22` |
| Boot hook | `1c2487687bdd4e11737492c68f50f2409722b319cc4a67c6dd4efe4867489f1e` |
| Error-copy region including unused hook | `722ea4e53321bbc579ec45bccb601bc1912d0dc920a2eff2d746c68e447c1f0a` |

`hold-standby/` is the production capture-path candidate; `hold-awake/` retains
HOLD after successful completion for inspection. Both have independent full
package audits in [results.json](results.json). Generated source, executable,
link map, disassembly and manifests are retained; intermediate objects are
omitted. `support/` freezes the builder/auditors and focused tests.

The disabled-HOLD build reproduces all three October 28 binaries byte for
byte. Both profiles in each of the November 7 and November 8 archives still
pass current inspection; all **348** files in their SHA256SUMS are unchanged.
All **324** capture tests passed with no skips; the complete result is in
`all-tests-final.log`;
the 43 focused HOLD tests also passed, including actual linked instructions,
64 randomized pin-preservation cases, wrong-schema rejection, modified hook
and padding rejection, and forbidden error-engine references into the hook.

## Rebuild and offline inspection

From the repository root, into a fresh output directory:

```powershell
python firmware/capture-raw/build.py --out tmp/bringup/a3-hold-new `
  --flash --standby --error-blinks --magic-format --line-stream --async-stop `
  --sd-bus-width 4 --sd-clock-hz 25000000 --sd-clock-negedge `
  --sd-clock-negedge-init --sd-review-profile --sd-startup-opt `
  --ethernet-powerdown --sensor-single-frame --gpio-hold
```

Omit `--standby` for the awake inspection variant. Omit `--gpio-hold` to
reproduce the October 28 capture control; it does not silently select A3.
Run this archive's `verify_offline.py` to verify checksums and both packages
without hardware access. No live recovery allowlist changed. Physical A3
level, minimum trigger duration, full latch shutdown and recovery with the
assembled latch remain to be measured after the board is reconnected.
