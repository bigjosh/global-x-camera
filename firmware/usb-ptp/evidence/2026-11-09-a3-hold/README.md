# A3 HOLD and A0–A2 exposure wiring — offline candidate

**Not installed.** On November 9 the user confirmed the board is disconnected
for assembly. This work made no instrument, reset, power, NOR, SD or live
recovery-allowlist change. Last installed firmware remains the historical
November 8 package08; it was not reread here.

## Canonical wiring and behavior

| Function | Arduino contact | Firmware role |
|---|---|---|
| Exposure low track end | A0 / CN4.1 / PF5 | LOW during sampling |
| Exposure wiper | A1 / CN4.2 | Buffered PA9 / ADC1 channel 10; PC10 input/no-pull |
| Exposure high track end | A2 / CN4.3 / PF6 | HIGH during sampling, LOW afterward |
| Power HOLD | A3 / CN4.4 / PA2 | HIGH from first custom boot instructions; float immediately before final Standby |

The [canonical SVG](../../../../docs/power/lipo-latch-wiring.svg) includes the
complete power circuit and exposure knob. GPIO HOLD is direct to Q2 gate with
R2 = 100 kΩ to ground. A0 is a driven endpoint, not a fixed ground contact.
The old A3–A5 knob diagnostic must not be used with this latch: it drives A3 LOW.

The combined package now uses the reviewed PA2 capture image. HOLD remains
asserted through the original UART recovery guard, capture/save, error blinks,
and USB service. Success, error and USB shutdown float PA2 with no internal
pull immediately before WFI; refusal retains it and unexpected WFI return
reasserts it. PA2/WKUP2 is disabled as a wake source before Standby. PE6 UART
recovery still requires reset/restart; it is not a Standby UART-wake feature.

The remapped [control diagnostic](../../../control-smoke/README.md) is separate.
**Normal captures still use fixed exposure.** Applying the knob to sensor
settings, optimizing ADC settling and qualifying its cold timing remain future
integration work. No new gain header assignment is made.

## Exact artifacts

The `package-pa2/` directory holds two 64 KiB NOR sectors and checked recovery
metadata; `usb-pa2/` holds its USB executable, manifest and frozen sources.
The input capture image is archived at
[`capture-raw/evidence/2026-11-09-a3-hold/hold-standby/staged`](../../../capture-raw/evidence/2026-11-09-a3-hold/hold-standby/staged).
Frozen manifests retain their original local build paths. The files below,
their SHA256 values, and `SHA256SUMS` identify this candidate independently.

| Artifact | SHA256 |
|---|---|
| USB executable, 34,470 bytes | `acd38fe1d9382c9bca181253738ab55d2f0a73d4bf0f22fa3928521cb02a5206` |
| Combined prefix, 7,160 bytes | `852bc7724a9fc0267fb37e3f93ba52f22137c65c55f2cece47d17dd352093084` |
| NOR sector 0 | `c822d2333ce265ded2ea420fd4c78e2a20e01c4b392b1decb99b80d9a040516d` |
| NOR sector 1 | `347aa3c1db62cb95bd6b66d421c0d9c3db5a706e493baf2f515ac13cb9f4670f` |
| Input PA2 capture prefix | `95312a3a9782ddae82157c3d9859c31de157f8a42e4e9cf370ccba93b26acdfc` |
| Input PA2 capture sector | `86786daaaa689b1df556603ca3a4df9b09dcff37d1095d56821c6fa01f99ce22` |

The early HOLD entry is **0x34181DF0**, before the original reset handler at
0x34180440. The real error engine ends at 0x34181DC8, leaving 40 bytes before
HOLD. Its 76-byte stub ends at 0x34181E3C, before the USB hook at 0x34181E40.
The 440-byte USB hook ends at 0x34181FF8, leaving eight bytes before capture.
All original UART guard instructions, literals and park **0x3418078C** remain
unchanged. The USB composition preserves the entire input capture tail from
NOR offset 0x2000; that input contains the new success/error HOLD release code.

The bootstrap still verifies the 15,804-byte early receiver with CRC32
`D3C8C062`. Selector length is 4,284 bytes, CRC32 `4E682F8F`; USB CRC32 is
`4F5339F8`. Independent inspection checked these against packaged bytes.

## Offline validation

- **26 package tests passed without skips**, including real linked hook
  register/flag preservation, branch targets, exact capture/UART preservation,
  bounds, CRC/layout binding, and rejection of corrupted/self-relabelled inputs.
- **21 PTP tests passed.** PTP protocol/storage behavior was not changed.
- **3 shutdown tests passed**, including 34 native register-model cases with
  **519 checks**, plus actual Cortex-M55 release/WFI/reassert machine bytes.
  PA2 release, refusal/return behavior, unrelated GPIO preservation and cleared
  wake sources were checked. USB proof schema 2 identifies PA2, while historical
  schema 1 remains PD7.
- Separate capture regression, disabled-HOLD reproduction, historic PD7
  inspection and source/layout audits are recorded in the
  [capture evidence](../../../capture-raw/evidence/2026-11-09-a3-hold/README.md).
- Control GPIO/security tests passed for the new A0–A2 mapping; previous
  diagnostic schemas retain their historical pin meanings and are rejected
  by the current launch path. The SVG was parsed and its rendered PNG inspected.
- Independent review found no blocking defect in shared GPIOA/ADC handling,
  early boot layout or recovery preservation. VBUS sampling changes PA11 and
  restores the prior GPIOA configuration; it does not release PA2.

`validation/results.json`, the native register-model output, ARM listing,
instruction hashes and frozen test sources retain the specific checks.
These are offline results, not evidence that this candidate has run on silicon.

## Reproduction and remaining bench work

From the repository root, with the saved SDK and compiler available:

```powershell
python firmware/usb-ptp/build.py --out tmp/new-a3-usb
python firmware/usb-ptp/package.py --usb tmp/new-a3-usb --capture firmware/capture-raw/evidence/2026-11-09-a3-hold/hold-standby/staged --out tmp/new-a3-package
$env:USB_BOOT_TEST_PACKAGE = 'tmp/new-a3-package'
python firmware/usb-ptp/test_boot_package.py
python firmware/usb-ptp/test_shutdown.py
```

Do not load or test while assembly is underway. After reconnection, establish
actual power/USB/latch wiring and ownership on a stable supply. Recover using
the installed package08 contract, preserve both NOR sectors and following
4 KiB, review the new exact prefix for recovery admission, then install using
the existing sector-1-first maintenance workflow and independently read back.
Test actual A3 level/takeover, UART recovery, a saved image, USB browse/download,
and final HOLD release before relying on the latch alone. Check the new A1
knob full travel separately. No new cold timing, latch-window, physical
USB-disconnect shutdown, LiPo headroom or AUX/main rail sequence is claimed.
