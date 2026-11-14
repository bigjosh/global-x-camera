# Camera controls: exposure and ASA — r2

## Quick Install Instructions

**Mac, no project files and no access to the boot jumpers:** use the guided
installer below. It contains this release's firmware and enters the camera's
existing ST-LINK serial recovery path automatically during startup.

**The installer is offline-tested, not yet tested on a physical Mac/camera.**
The underlying flash helpers have prior bench evidence. The r2 firmware also
remains an offline-qualified prerelease; publication is not a new installation.

1. **Download and unzip the [guided Mac installer](https://github.com/bigjosh/global-x-camera/releases/download/knobs-2026-11-14-r2/global-x-camera-installer-r2-v1.zip).**
   Keep the extracted folder together. It includes both firmware sections,
   the small Python utility and its flash helpers; no repo clone or compiler
   is needed. The ZIP SHA-256 is `80c2eb4d7af4a7e3f8af3fbe94adf524afd502d8b68a239226c1ae1230a3f001`.
2. **Install the two prerequisites once.** Install Python 3.10 or newer from
   [Python for macOS](https://www.python.org/downloads/macos/), then
   [STM32CubeProgrammer 2.23.0 from ST](https://www.st.com/en/development-tools/stm32cubeprog.html).
   For ST's download choose **MacOS Arm / STM32CubePrg-McA** on an M-series Mac,
   or **STM32CubePrg-Mac** on an Intel Mac. Unzip ST's download and run its setup
   app. Java is bundled; CubeIDE is not needed. ST may request a login/email
   and macOS may request installation permission.
3. **Double-click `Install.command`.** It prepares a private Python environment
   and installs `pyserial` into it on the first launch. If Finder will not
   launch it, open Terminal, type `bash `, drag `Install.command` into that
   window, then press Return. The utility explains what to do next; it can
   also help locate CubeProgrammer if it was installed somewhere unusual.
4. **Follow the cable and switch prompts.** Connect data-capable USB cables
   between this Mac (or a powered hub) and **BOTH** camera USB ports:

   | Port | Location | Role |
   |---|---|---|
   | **CN10 / ST-LINK** | Debugger end | Firmware download/programming |
   | **CN8 / HOST / MCU USB** | Beside the Ethernet jack | **Camera power**, plus photo access after installation |

   Finish any capture/save/transfer and close other camera, serial or debugger
   apps. The utility first asks for the selector on **BATTERY**, without pressing
   the shutter, and Enter when the cables are attached. It then arms the recovery
   signal and says **“OK, now switch the camera's power switch to USB.”**
   It detects a verified MCU recovery response and starts programming; a timer
   alone never counts as detection. **Keep the selector on USB and both cables
   attached until completion.** Leave boot jumpers untouched and the modified
   prototype's CN9 power-selection jumpers removed. Do not use the shutter or
   battery latch to keep it alive during installation.
5. **Wait for 100% and the success message.** The utility backs up existing
   firmware, programs the USB section before the boot section, independently
   reads both back, checks neighboring flash is unchanged, and rechecks UART
   recovery. Progress messages identify each stage and real flash-page counts.
   Logs/backups go to `~/global-x-camera-installs/<timestamp>/`. It then releases
   normal startup; ST-LINK can be unplugged after completion.

With HOST connected and the selector on USB, expect **USB photo-access mode**,
not a new photo or a mounted disk. macOS Image Capture is an app to try for
importing photos, but this firmware's Mac PTP compatibility is not yet qualified.
For a later photo, finish transfers, unplug HOST, select battery and press the
shutter. This update does **not** require formatting the SD card.

**If the utility stops, follow its message.** Missing connections or unrecognized
firmware cause a stop before programming. If it reports uncertain programming
or verification, leave power/cables unchanged and keep its logs; do not reset,
rerun or delete its persistent safety record. It never automatically retries an
uncertain flash write. The installer admits the previous November 13 D8 image
and this r2 image; a damaged/erased boot guard or other firmware needs separate
recovery. Its post-install resets use the previously observed ST-LINK BREAK
behavior, still to be qualified on the Mac host path.

**For the user's AI:** the default `python3 camera_install.py` is the same
interactive wizard; `--check` performs offline file checks without any device
access. The included README describes `--non-interactive --confirm-idle --restart`
for an already idle, USB-powered camera, serial selection and saved logs.
Use our included ROM-context helpers, **not STM's stock external loader from
this normal-boot recovery state**. Do not change boot jumpers, OTP or security
settings, or run a full-chip erase.

These instructions supersede the old CN8-unplugged/Windows-bench instructions
in the original firmware ZIP and its diagram. The firmware and original
publication assets themselves are unchanged.

---

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

Use the **Quick Install Instructions above** for the guided, no-jumper Mac
installation. The separate installer ZIP includes the exact r2 firmware pair
and the required RAM helpers/recovery profiles.

The original [complete firmware/recovery ZIP](https://github.com/bigjosh/global-x-camera/releases/download/knobs-2026-11-14-r2/global-x-camera-knobs-2026-11-14-r2.zip),
loose sectors, attached `INSTALL.md`, `RELEASE_NOTES.md`, port diagram and original
checksums remain the immutable publication snapshot. The original
[Windows bench guide](https://github.com/bigjosh/global-x-camera/blob/knobs-2026-11-14-r2/release/knobs-2026-11-14-r2/INSTALL.md)
requires its existing repo/local helpers. Follow the current live release's
Mac guide for this installation; do not mix the two power/installation procedures.


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
