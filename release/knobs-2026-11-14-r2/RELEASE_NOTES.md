# Camera controls: exposure and ASA — r2

**This is our selected controls firmware, replacing the superseded
`knobs-2026-11-14` prerelease. It is qualified offline only: not installed or
tested as a complete capture/USB system on the camera.** Publishing these
files does not change the board's firmware.

The last recorded installation is the earlier D8 fixed-settings package.
The current physical runtime was not reread during this release work.

The image matches our reviewed November 13 controls package byte for byte.
The consolidated sources retain the useful real-ST-ADC-driver tests and
portable build tooling from the subsequent review. The old release keeps its
original tag and assets for identification; use this r2 package for the next
controlled installation.

## What the knobs do

Both controls are sampled once before starting a battery-powered capture.
**Counterclockwise increases both exposure time and ASA.** Keep the existing
wiring; no end-wire swap is required.

| Control | Wiring | Behavior |
|---|---|---|
| Exposure | A0 LOW, A1 wiper, A2 HIGH | Continuous logarithmic **1/1000–1/2 second** (1–500 ms) |
| ASA | A4 HIGH, A5 wiper, low end GND | Four sectors: **100 / 200 / 400 / 800**, selecting analog gain **1× / 2× / 4× / 8×** |
| Power HOLD | Arduino **D8 / CN14 pin 1 / PD12** | Retained through capture/save and released just before battery Standby |

The exposure knob's measured polarity is inverted in firmware; the ASA knob
has the opposite electrical polarity. ASA labels are provisional, **not a
calibrated ISO sensitivity**. Digital gain stays at 1×.

The sensor's maximum analog gain is explicitly configured and read back to
permit 8×. Applied exposure, frame timing and analog/digital gain are checked
before capture success is declared. A control or sensor-setting failure uses
the existing error indication and shutdown instead of silently taking a photo
at fixed settings. The two knob supply outputs return LOW after sampling.

## Photos, USB and recovery

- Photos remain packed RAW in the existing SD slots; this update requires no
  card format. Existing photos remain readable.
- New photos include a controls record in the existing first-sector metadata
  space. USB PNG comments report exposure, analog gain and provisional ASA.
- A saved record distinguishes **configured** settings from settings already
  **verified against the sensor** when that record was saved. An early saved
  snapshot is not rewritten merely because verification completes later.
- Older photos or invalid controls metadata report settings unavailable;
  settings are never invented. The metadata CRC does not checksum image pixels.
- **CN8** remains the camera's USB photo port: Windows can browse, download and
  explicitly delete photos through PTP. The shutter/knobs are not sampled for
  USB operation. No custom Windows driver or emulated disk is needed.
- Once USB mode is selected, D8 HOLD stays LOW. The existing early boot HOLD
  assertion and early UART-recovery park remain; this is not a promise of no
  initial HOLD pulse before USB detection.
- **CN10/ST-LINK** remains the programming/recovery connection. The original
  early UART-recovery code is retained. Its operation in this combined image
  still needs a live post-install check.

## Download and install

Use the [complete recovery/package ZIP](https://github.com/bigjosh/global-x-camera/releases/download/knobs-2026-11-14-r2/global-x-camera-knobs-2026-11-14-r2.zip)
and [installation guide](https://github.com/bigjosh/global-x-camera/blob/knobs-2026-11-14-r2/release/knobs-2026-11-14-r2/INSTALL.md).
The ZIP contains the package, recovery metadata, guide, notes, USB-port diagram
and checksums. It is **not a standalone portable installer**: the current
procedure requires the existing Windows bench tooling and reviewed NOR helpers.

Loose `sector0.bin`, `sector1.bin`, `manifest.json` and `SHA256SUMS` assets are
also provided. Do not attempt installation with only the two loose binaries;
the scripts need the matching package and recovery records.

| Artifact | Size | SHA-256 |
|---|---:|---|
| `sector0.bin` — boot/capture, NOR offset `0x00000` | 65,536 bytes | `6ddf4499865264aec845150597aa6b8d44cb89e7d5e621dd324a0e1a9170b499` |
| `sector1.bin` — selector/USB, NOR offset `0x10000` | 65,536 bytes | `206da4c0a8bdcda6205d7ccdb3d9ac02548e9db6852b1fa47afa6327b76473d8` |
| `stage1.bin` — recovery identity, inside package | 7,160 bytes | `b866589cf472cac9820d961f3243cb8280759614826083757fae374ccee7e242` |

`stage1.bin` is an identity artifact, not a third flash-write instruction.
Use the release `SHA256SUMS` to check the downloaded ZIP and other assets.
The tag and firmware assets are immutable; a different firmware image requires
a different release tag.

## Qualification and remaining checks

Offline checks cover both knob mappings, ADC cleanup/failure paths with ST's
actual driver model, sensor configuration/readback rules, metadata/USB handling,
linked memory layout, D8 HOLD and preservation of the early UART guard. A
rebuild of the consolidated controls path reproduces the binary hashes above.
The earlier live knob diagnostic established direction and approximate taper;
it did not qualify this integrated image.

After installation, the remaining hardware checks are:

1. Knob endpoints/center and all four ASA sectors, including applied 8× gain.
2. Recognizable saved photos at short and long exposures; settings reported
   accurately on USB download, including configured-versus-verified status.
3. D8 latch takeover/release, missing-sensor/error shutdown and UART recovery.
4. USB mode with HOLD LOW, browsing/downloading/deleting old and new photos.
5. Analog settling, total cycle energy and timing, including the 50 ms startup
   target. No new timing or energy improvement is claimed by this release.

A normal LED sequence alone does not verify the selected exposure or gain.
See the [firmware documentation](https://github.com/bigjosh/global-x-camera/blob/knobs-2026-11-14-r2/firmware/usb-ptp/README.md),
[controls evidence](https://github.com/bigjosh/global-x-camera/blob/knobs-2026-11-14-r2/firmware/usb-ptp/evidence/2026-11-13-knob-controls/README.md)
and [reconciliation review](https://github.com/bigjosh/global-x-camera/blob/knobs-2026-11-14-r2/docs/review/2026-11-14-knob-firmware-reconciliation.md)
for the exact implementation and qualification limits.
