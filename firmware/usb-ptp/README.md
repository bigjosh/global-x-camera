# USB photo access

Bare-metal PTP over the Nucleo's **CN8 MCU USB connector**. Windows uses its
native Portable Devices camera driver; no custom driver, drive emulation or
SD filesystem is required. The SD still holds the existing fixed RAW slots.

**November 10 HOLD correction — offline, not installed:** USB mode must
not latch battery power. After the real VBUS sample indicates USB present,
the selector drives **A3/CN4.4/PA2 LOW before loading USB code**; ambiguous or
failed samples also release HOLD before parking. USB entry, service, faults,
shutdown refusal and unexpected WFI return keep it off. Battery capture
retains its original HOLD behavior. [Owning decision and boundaries](NOTES.md#2026-11-10--keep-hold-off-after-usb-mode-selection).
[Offline build and qualification](evidence/2026-11-10-usb-hold-off/README.md).

Early startup and UART recovery precede VBUS classification and still use
provisional HIGH, as does E001 if the selector itself cannot load. Thus this
does not eliminate the short pre-selection assertion with a USB cable
attached. The installed November9 image described below still asserts HOLD
through USB; the correction has not been programmed or hardware-qualified.

**Installed November 9 behavior (superseded by the offline policy above):** the HOLD connection is **A3 / CN4.4 / PA2**.
The installed combined capture/USB firmware asserts it before the unchanged early UART
guard, retains it throughout recovery, capture/save and USB service, and floats
it immediately before final Standby. Both NOR regions now match the reviewed
PA2 package; A3, the remapped knob diagnostic and UART recovery passed smoke
tests. Camera and CN8 were absent, so capture and USB mode were not requalified.
Target power was left OFF through the JS. See the
[live installation record](../control-smoke/evidence/2026-11-09-a3-live/README.md)
and [original offline candidate](evidence/2026-11-09-a3-hold/README.md).

## Using the installed prototype

1. Set the new **SW2 source selector to USB**, and connect **CN8** to the
   computer before starting the target. Its protected USB takeoff feeds the
   selector and CN5.5; all CN9 shunts remain removed. A Joulescope may be in
   series with SW2 COM when measuring. The older external-supply-only bench
   hookup is historical.
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

## Architecture and build

`main.c` owns the SD transport; USB callbacks only publish protocol work.
`ptp.c` serializes requests, cancellation and events. The [storage adapter](storage/README.md)
owns on-card interpretation; the [transport](transport/README.md) wraps ST's
USB Device core and N6 PCD. The [Windows harness](host/README.md) exercises the
same native driver used by Explorer.

```powershell
python firmware/usb-ptp/build.py --out tmp/my-usb-build
python firmware/usb-ptp/package.py --usb tmp/my-usb-build --capture tmp/my-reviewed-pa2-capture/staged --out tmp/my-usb-package
```

The canonical dual-mode package includes the reviewed PA2 HOLD capture build
and preserves its capture payload and the original early UART recovery guard.
The standalone capture build uses `--gpio-hold`; see the [capture build](../capture-raw/README.md).
The package builder requires an explicit capture directory and admits only
independently reviewed exact prefix/sector hashes, not a self-consistent manifest.
The legacy October 28 input is retained for explicit historical reproductions;
it does not implement the A3 capture latch. A small branch after SRAM preparation
loads a checked selector from a separate NOR region. It samples **CN8 VBUS
through R80/R81 → PA11/ADC2 channel 12**. Present USB power selects the PTP
app; absent power resumes capture. A powered charger also selects USB mode.
With the corrected code, HOLD goes LOW after the sample and before any USB
load; ambiguous/failed VBUS results also park with HOLD off. The earlier
E001 selector-load fault has no VBUS result and retains pre-selection HOLD.
Canonical PA2 packages reject `--force-capture`; the option remains only for
explicit legacy capture diagnostics, and cannot override a negative sample.

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
- The corrected USB code keeps PA2 LOW throughout service and cleanup,
  including refusal and WFI return. If power remains, disconnect handling
  waits for protocol/storage quiescence, samples absent VBUS twice, then
  deinitializes SD/USB and attempts guarded Standby. With SW2 on USB, cable
  removal may instead cut power immediately, including during an explicit
  deletion; no graceful hold-up or atomic deletion guarantee is made.
  Shutdown proof schema 3 records USB HOLD-off; frozen schema 2 still
  describes PA2 HOLD-through-service and schema 1 describes PD7. The new
  policy is offline-only; physical unplug/shutdown is not yet tested.
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
