# Knob control build, November 14

A firmware package in which the exposure and gain knobs set the sensor for
every battery photo. The user asked for a release that another session could
install over USB-C.

**Offline only. Not installed. Never run on a camera.** It was built in a cloud
session with no bench access. No instrument, debugger or board was operated.
The camera still holds the [November 13 D8 package](../2026-11-13-d8-hold/README.md).
Install steps are in the release notes for tag `knobs-2026-11-14`
([copy in the repository](../../../../release/knobs-2026-11-14/RELEASE_NOTES.md)).

## What was built

`package/` is the output of `package.py`, run on Linux with
`arm-none-eabi-gcc (15:13.2.rel1-2) 13.2.1 20231009`, ST HAL driver v1.3.0 from
GitHub and the CMSIS headers committed under
`firmware/capture-sd/evidence/2026-10-20-hardware/dependencies/`. Inputs were
the reviewed D8 capture build and the installed USB app, both taken unchanged
from [the D8 record](../2026-11-13-d8-hold/README.md):

```sh
python3 firmware/usb-ptp/package.py \
  --usb firmware/usb-ptp/evidence/2026-11-13-d8-hold/usb \
  --capture firmware/usb-ptp/evidence/2026-11-13-d8-hold/capture-input \
  --hal <stm32n6xx-hal-driver v1.3.0> --cmsis <committed CMSIS> \
  --out firmware/usb-ptp/evidence/2026-11-14-knobs/package
```

| Artifact | SHA-256 |
|---|---|
| Prefix, 7160 bytes | `0f87fbbe521230349db3d19b9449db38f2bff8000a4683461db080ad5525acc9` |
| Sector 0 | `06196d10e8ddeb50948ef3666729dbe390d575b58a0c1d2ee7f5796758ece6ad` |
| Sector 1 | `ac1854200e78dfb04f0554b3555ccb794de1e0e2f6ddc587ee3358b3031e9736` |
| USB app, unchanged | `d2bbb76f789e01bb94f09892f291d602b5d7276b96124eb613d70f1bd7b87461` |

`SHA256SUMS` covers every file here except this README. `results.json` holds
the comparisons and test counts below in machine-readable form.

## How it differs from the installed package

Sector 0, 188 bytes:

- The boot hook, rebuilt for the new selector's length, CRC and entry. It is
  440 bytes instead of 444 because the compiler loads the CRC constant from a
  literal instead of building it in three instructions; the instruction
  sequence is otherwise the same. Everything in the prefix before the hook,
  including the reset path and the UART recovery guard, is byte-identical.
- The boot header is byte-identical: the old and new prefixes happen to have the same byte sum, which is all its checksum is.
- Five bytes of capture receiver at flash offsets 0x6B87 to 0x6B8B: the
  [exposure gate](../../exposure_gate.py). The late-range CRC-32, the early
  receiver and its CRC are unchanged.

Sector 1: the selector grew from 4464 to 7228 bytes to hold the knob reader.
The USB app after it is byte-identical.

The ST compiler that built the installed package was not available. The hook
and selector were therefore built with a different compiler from the one the
installed bytes came from. With the installed package's constants this compiler
reproduces the installed hook byte for byte; the selector's instructions
differ.

## What the checks do and do not show

`python3 -m unittest discover -s firmware/usb-ptp -p "test_*.py"` with
`USB_BOOT_TEST_PACKAGE` set to `package/` and `GLOBAL_X_HAL` set to ST's HAL
driver: 52 tests ran, 50 passed, 1 was skipped and 1 could not run. The one that could not run is `test_ptp`, which
fails to link its native library on Linux and does not concern this change.

The tests show that the knob reader drives and releases the right pins against
a register model, writes the expected bytes for a table of readings, leaves the
fixed settings in place on every modelled failure, and that the mapping stays
inside the sensor's limits for every converter code. With ST's real ADC driver
in place of the stand-in, the reader completes four conversions and writes the
same bytes. They show the package
layout, the unchanged capture bytes apart from the gate, and the unchanged USB
handoff. An independent review of the source and the compiled listing of the first build was done before anything was released. It found one blocking defect, described below, and the short-exposure margin that led to the 0.5 ms floor. It checked the pin and register handling, the write into the prefix, the selector decision, the gate and its checksums, the prefix and hook against the installed package, and the instruction-cache handling, and found them correct. The corrected reader was run against the real driver sources; the corrected build has not had a second independent review.

None of this is a hardware result. Open until the camera has run it: knob
settling within the 1 ms allowed, any gain above 1x, exposures outside 5 ms to
231 ms, driving PC12 in the capture path, the added start-up time (estimated
5 ms), and UART recovery with this exact prefix.

## The first build, and what replaced it

Commit `50f2af5b` holds an earlier build of this package (prefix
`71f93596…`, sector 0 `2d4141d3…`, sector 1 `53b8dacb…`). An independent
review found that its knob reader could never succeed on the chip: it changed
the converter's channel while the converter was enabled, which ST's driver
refuses, so every photo would have kept the fixed settings. It was never
released or installed. This folder holds the corrected build; the reasons are
in [the notes](../../NOTES.md), last entry dated 2026-11-14.

## Recovery admission

`recovery.py` `APPROVED` now lists this prefix so that the park can be verified
after an install. That entry rests on the offline comparison above, not on a
hardware test; the D8 entry had the same standing when it was added.
