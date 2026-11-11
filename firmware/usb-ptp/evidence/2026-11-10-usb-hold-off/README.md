# USB mode must release battery HOLD — November 10, 2026

**Status: built and tested offline; not installed.** The user corrected the
power policy: USB mode must not assert HOLD, so removing the cable does not
leave the camera running on its battery. The November9 installed package
still uses the previous behavior. No bench or storage operation occurred.

## Implemented behavior

- Early battery boot and the original UART recovery guard are unchanged.
- Once VBUS is sampled, a present or ambiguous result drives PA2/A3 LOW
  before any USB-image load or USB/voltage-error park. Absent VBUS returns
  to the unchanged capture path with HOLD asserted.
- Release occurs **after** the VBUS sampler returns: that sampler restores
  GPIOA MODER/PUPDR from its entry snapshot. Releasing before sampling could
  be undone by cleanup.
- USB app entry, including standalone RAM entry, releases before its checks
  and SD initialization. Fault handlers repeat the release. USB service,
  refused shutdown and unexpected WFI return never assert HOLD. Final WFI
  changes only PA2 to input/no-pull, with the external100kohm pull-down.
- The builder requires USB policy schema2 / `mode=usb-off` and shutdown
  proof schema3. Capture's schema3 continues to describe battery behavior;
  the two contracts are separate in the package manifest.
- New PA2 packages reject `--force-capture`: that diagnostic could return
  into battery code and later reassert HOLD. The explicit legacy package
  option remains, but cannot turn ambiguous VBUS into a capture decision.

## Validation

`qualification.log` records **62 tests passed, zero skips/failures**, including:

- Actual C selector and GPIO helper: absent/present/ambiguous VBUS, USB-load
  failure, GPIO refusal and unrelated-pin preservation.
- Package mutation tests rejecting missing/old HOLD-high contracts and the
  PA2 forced-capture override.
- All original capture bytes from sector offset0x2000 onward unchanged;
  original UART instructions and park unchanged. Prefix hook remains440
  bytes inside its448-byte reservation; selector4456 bytes is inside8192.
- Native shutdown model:34 cases,4096 randomized helper configurations,
  41518 checks, no PA2 HIGH writes; real ARM42-byte float/WFI group audit
  confirms no HOLD-reassert instruction group on return.
- Existing PTP/session/transfer/delete/cancellation regressions pass.

The package manifest contains absolute original build paths as provenance.
The sibling `usb/` and `package/` directories preserve those artifacts; the
capture input is the existing November9 reviewed PA2 capture evidence.
`SHA256SUMS` binds the archived files without line-ending normalization.

## Candidate identities

| Artifact | SHA-256 |
|---|---|
| USB app,34578 bytes | `ee74781b963c43baa9f1a104113ab633528d08db7fb774e1a1d92003f36cbe4d` |
| Combined prefix,7160 bytes | `b897daeb9ce97a48a244ccc495c2a96190b4ce6e41367225dcbbe7dd5142da03` |
| Sector0,65536 bytes | `8795a26f6226e88e64531728f886e34f20f155cca18f80a97aced854877a9790` |
| Sector1,65536 bytes | `4f5b112469f19b548a8b86d035a1a61863c9fc2ab5ea2ccca21982cc95414627` |

## Limits and handoff

This policy starts at USB classification, **not at power arrival**. The
unchanged early bootstrap asserts HOLD before it can sample analog VBUS.
The early UART park and selector-load failure E001 are before classification
and still retain HOLD. Eliminating any HIGH pulse with a cable attached
requires an earlier detection/hardware redesign and separate qualification.

USB removal may immediately remove target power. The firmware intentionally
does not hold the battery to finish a USB operation; these tests do not add
power-loss-atomic deletion or guarantee cleanup after cable loss. The manual
SW2 selects physical power; VBUS independently selects application mode.

No A3 waveform, physical unplug, PTP requalification, new cold capture or NOR
readback was performed for this candidate. Installed prefix remains
`852bc7724a9fc0267fb37e3f93ba52f22137c65c55f2cece47d17dd352093084`.
Recovery allowlists were not updated. User retains bench control; confirm
current source/wiring/ownership before installation and live testing.

[Owning policy note](../../NOTES.md), [current wiring](../../../../docs/power/lipo-latch-wiring.svg).
