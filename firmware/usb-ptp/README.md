# USB photo access

Bare-metal PTP over the Nucleo's **CN8 MCU USB connector**. Windows uses its
native Portable Devices camera driver; no custom driver, drive emulation or
SD filesystem is required. The SD still holds the existing fixed RAW slots.

**November 14 knob build, not installed:** a package that reads the exposure
and gain knobs for every battery photo is built and checked offline. It has
never run on the camera; the installed firmware is still the November 13
package described next. See [Exposure and gain knobs](#exposure-and-gain-knobs)
and [the knob build record](evidence/2026-11-14-knobs/README.md).

**November 13 D8 firmware installed:** HOLD is now **Arduino D8 / CN14.1 / PD12**.
This supersedes the earlier D3 assignment at the user's request. The combined
image preserves early battery HOLD and the UART guard, keeps HOLD through
capture/save/error display, and floats it immediately before battery Standby.
USB-selected HOLD remains LOW. The capture build disables the former PD12
phase-marker output so it cannot toggle the latch. Both flash-sector readbacks match;
[the D8 record](evidence/2026-11-13-d8-hold/README.md) records the reload.
No new functional test campaign was run, as requested.

Once VBUS selects USB mode, HOLD is driven LOW before the USB application is
loaded and stays LOW through service, faults, shutdown refusal and an unexpected
WFI return. It floats at the final USB Standby boundary. This incorporates the
previously committed November 10 USB-off correction. A provisional HIGH still
exists before VBUS selection, and early UART recovery parks before that decision;
there is no claim that a USB-powered cold boot has no initial HOLD pulse.
The original [November 9 PA2 installation](../control-smoke/evidence/2026-11-09-a3-live/README.md)
and [candidate](evidence/2026-11-09-a3-hold/README.md) remain historical evidence.

## Using the installed prototype

1. Connect **CN8** to the computer before starting the target. Keep its existing
   external power connection through the Joulescope; with CN9 shunts removed,
   the USB cable is not the target's complete power supply.
2. Start or reset the target and allow the full-card catalogue scan to finish.
   In Windows File Explorer, open **This PC → Global X RAW Camera → RAW photo
   slots**. This is a camera, so it has no drive letter. The underlying native
   Windows WPD browse/download/thumbnail/delete APIs are hardware-tested.
3. Copy the photos you want. Delete only those you explicitly want to discard.
   To take another photo, disconnect CN8 and start a new target cycle.

The selector checks USB power at boot. Attaching a cable after capture has
already entered Standby does not by itself restart this prototype. A powered
USB charger also selects USB mode. Windows high-speed USB is tested; macOS,
Linux and full-speed USB remain unqualified. Final-build test downloads took
about 6.9 seconds for each 3.06 MB PNG, including fresh SD reading and encoding.

## User-visible behavior

- Browse a flat collection of `GX_0000175.png`-style names and thumbnails.
- Download a fresh RAM snapshot of a stored photo as **1120 × 1364, 16-bit
  grayscale PNG**. All ten sensor bits are retained as `sample << 6`.
- Delete individual photos explicitly from the host. Downloading does not
  delete anything. Bulk deletion and remote capture are not advertised.
- Unreadable sectors are zero-filled in an otherwise valid PNG. Its EXIF
  UserComment describes the read errors; subsequent listings use
  `_RECOVERED`. A host that already cached the old name may retain it, so the
  embedded warning is authoritative for that download.
- Capture dates and orientation are omitted: the existing slot padding has
  no commissioned metadata schema. A valid completion marker is not a pixel
  checksum; these old RAW slots have no stored payload checksum.

PNG uses stored DEFLATE for now. Each exported file is 3,064,188 bytes; the
card retains its smaller packed RAW representation. Thumbnails are generated
from a fresh snapshot too. Neither conversion runs during battery capture.

## Exposure and gain knobs

Built November 14; offline checks only, not installed and not run on hardware.

On the battery path (no cable in CN8) the boot selector reads both knobs once,
after the VBUS check and before the capture code configures the sensor:

| Knob | Pins | Result |
|---|---|---|
| Exposure | A0/PF5 driven LOW, A2/PF6 driven HIGH, wiper A1 → PA9, ADC1 input 10 | 65 to 63000 sensor lines, **0.5 ms to 484 ms**, exponential in knob position; mid-travel 2024 lines, 15.6 ms |
| Gain | A4/PC12 driven HIGH, low end GND, wiper A5 → PG15, ADC1 input 7 | analog gain code 0 to 28, **1x to 8x**, equal stops; digital gain stays 1x |

A higher reading gives a longer exposure or more gain. Readings below code 120
or above 3720 count as the ends of travel, so both extremes are reachable; an
unconnected wiper reads as the low end. The pins are driven only for the
reading, about 2 ms, and every register is put back before capture continues.

The selector then edits the copy of the capture prefix already in RAM: bytes 1
to 3 of the manual-exposure register block (gain code, exposure lines) and the
`MOVW` that holds the frame length. The frame length is the larger of the
usual 4336 lines and exposure + 2000 lines. `package.py` finds both places in
the reviewed prefix and refuses to build if either is not unique; at run time
`knob.c` checks the exact default bytes before writing. Flash is never written
at run time. If the converter cannot be set up, a conversion fails, memory
protection is on or the bytes are not as expected, nothing is edited and the
photo uses the fixed 1428 lines at 1x, as before.

The reviewed capture receiver fails a photo unless the sensor reports exactly
1428 exposure lines. `exposure_gate.py` changes that one conditional branch in
the built image to an unconditional one and sets the four bytes it leaves
unreachable so the late-range CRC-32 is unchanged. Five bytes of sector 0
change; the loader's checksum constant, the early receiver and the boot prefix
do not.

Limits: the applied exposure and gain are not stored with the photo. The knobs
are not read in USB mode. One second is not reachable in the current sensor
mode (16-bit line registers at 7.69 µs per line). The selector grew from 4464
to 7228 bytes, and with the reading itself that adds an estimated 5 ms before
exposure. The 0.5 ms floor keeps the start of readout about 1 ms after the
receiver is armed; see the notes before lowering it. `test_knob.py` models the
logic on the host, and with `GLOBAL_X_HAL` set to ST's HAL driver v1.3.0 it
also runs `knob.c` with the real ADC driver against the bus model in
`hal_model/`. Settling time, gains above 1x and exposures outside 5 ms to
231 ms have never been run on hardware. The selector record at `0x343F9000`
gains word 9, the address of `knob_proof`, and word 10, the result code listed
at the top of `knob.c`, or all ones when the knobs were not read on that boot.

## Architecture and build

`main.c` owns the SD transport; USB callbacks only publish protocol work.
`ptp.c` serializes requests, cancellation and events. The [storage adapter](storage/README.md)
owns on-card interpretation; the [transport](transport/README.md) wraps ST's
USB Device core and N6 PCD. The [Windows harness](host/README.md) exercises the
same native driver used by Explorer.

```powershell
python firmware/usb-ptp/build.py --out tmp/my-usb-build
python firmware/usb-ptp/package.py --usb tmp/my-usb-build --capture tmp/my-reviewed-pd12-capture/staged --out tmp/my-usb-package
```

`package.py` uses the ST compiler recorded in `capture-timing/build_raw10.py`
when it is present, otherwise `arm-none-eabi-gcc` on `PATH`; set
`GLOBAL_X_TOOLCHAIN` to a tools directory to choose another. `--hal` and
`--cmsis` point it at ST driver sources other than the SDK copy under `tmp/`.
The knob package was built on Linux from committed inputs only, plus ST's
HAL driver v1.3.0 from GitHub:

```sh
python3 firmware/usb-ptp/package.py \
  --usb firmware/usb-ptp/evidence/2026-11-13-d8-hold/usb \
  --capture firmware/usb-ptp/evidence/2026-11-13-d8-hold/capture-input \
  --hal <stm32n6xx-hal-driver v1.3.0> \
  --cmsis firmware/capture-sd/evidence/2026-10-20-hardware/dependencies/st/STM32Cube_FW_N6/Drivers/CMSIS \
  --out <new folder>
```

Run `python firmware/usb-ptp/knob_tables.py` after changing a mapping constant;
it regenerates `knob_tables.h`.

The canonical dual-mode package includes the reviewed PD12 HOLD capture build
and preserves its capture payload and the original early UART recovery guard.
The standalone capture build uses `--gpio-hold`; see the [capture build](../capture-raw/README.md).
The package builder requires an explicit capture directory and admits only
independently reviewed exact prefix/sector hashes, not a self-consistent manifest.
The legacy October 28 input is retained for explicit historical reproductions;
it does not implement the D8 capture latch. A small branch after SRAM preparation
loads a checked selector from a separate NOR region. It samples **CN8 VBUS
through R80/R81 → PA11/ADC2 channel 12**. Present USB power selects the PTP
app; absent power resumes capture. A powered charger also selects USB mode.
An ambiguous voltage or failed loader check parks for debugger diagnosis.

Initial boot code remains small. The USB app is loaded only in USB mode.
Packages bind the original capture sector, USB image, selector and recovery
metadata to exact hashes. They are not automatically approved for live
maintenance merely because they build; `recovery.py` pins independently
reviewed packages and reuses the original live UART/context verifier.

`bench.py` runs explicit RAM trials and cooperative stop. `nor.py` is an
expert-only flash tool: first establish a fresh idle recovery context, preserve
both 64 KiB regions and the following 4 KiB, program the secondary region
before publishing the boot branch, and independently reread all regions.
No OTP settings or standard external-loader initialization are changed.

## Boundaries

- Prototype VID/PID `0483:572A` and serial are development identities, not a
  production USB allocation.
- Power-loss-atomic SD deletion remains unqualified. Deletion touches only the
  requested slot, clears the tail first, then releases the header after sync.
  An interrupted explicit deletion can damage that requested photo.
- Catalogue scanning reads every slot header, including beyond deleted holes.
  USB appearance therefore waits for this scan. Unknown occupied slots are
  hidden and are not erased automatically.
- USB mode does not take a photo or sample the exposure controls. Normal
  capture, DMA-sleep and physical HOLD-latch qualification remain separate.
- USB disconnect handling waits until protocol/storage work is quiescent,
  samples absent VBUS twice, deinitializes SD/USB, and attempts guarded
  Standby with PD12 floated at the final boundary. Shutdown proof schema 5
  identifies USB PD12 OFF; frozen schemas 1/2/3/4 describe PD7 HIGH, PA2 HIGH,
  PA2 OFF and PE9 OFF respectively. No refusal or WFI-return path asserts the battery latch.
  Physical cable-removal/shutdown remains unqualified for this candidate.
- A failed header read during initial catalogue scanning currently prevents
  USB service from starting. Unknown/torn header markers stay occupied and
  hidden. Best-effort recovery applies to recognized objects during download;
  warnings are remembered only for the current catalogue session. No
  persistent SD slot-retirement policy has been implemented.
- CN9 shunts must remain removed in this bench setup. CN8 can still cause
  partial backfeed; a Joulescope OFF command is not proof of a cold reset.

The previously installed November 8 release was **package08 / ram08**, USB executable
SHA256 `74c91b77062e899944941006e075ab76039055f5175bee5f497b8d1a242e3679`.
Both NOR regions were independently reread; the following 4 KiB was preserved.
See the [durable qualification record](evidence/2026-11-08-native-ptp/README.md)
for exact identities, test evidence and remaining limits. Full working traces
and local photos remain in `tmp/bringup/usb-ptp-20261108/`.
