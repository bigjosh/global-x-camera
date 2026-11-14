# USB PTP decisions

## 2026-11-08  Preserve the qualified capture image behind a checked USB boot selector

**Why:** USB photo access should survive normal reset without replacing the
working single-frame capture sequence or its early UART recovery. The selector
is reached after SRAM preparation and after the exact original recovery guard.
A non-linking branch preserves LR; the hook preserves registers and flags,
synchronizes newly copied code and refuses enabled caches. A separately checked
NOR region holds the selector and USB program. The original capture tail stays
byte-identical, while only a small hook is added to the ROM-loaded prefix.

**Rejected:** initializing the entire USB stack on every battery capture,
overwriting the capture payload, replacing the proven NOR programmer with the
previously failing vendor external loader, or admitting arbitrary self-consistent
firmware manifests as safe recovery code. USB and capture code may share SRAM
because they are mutually exclusive modes, not concurrent applications.

**Evidence:** `package.py`, `boot_hook.S`, `boot_read.h`, `selector.c`,
`recovery.py`, the pinned October 28 capture archive and November 8 campaign.
Offline package checks and hardware qualification are separate claims.

## 2026-11-08  Detect host power using the existing analog VBUS divider

**Why:** MB1939 R80/R81 divide CN8 VBUS by fifteen onto PA11/ADC2 channel 12.
Its approximately 0.33 V cannot be detected reliably as a digital HIGH. The
internal PHY's VBUS-valid indication is not connected to that external supply
on this configuration. The ADC temporarily owns its clock, security and analog
supply setup and restores the prior state before capture resumes.

**Rejected:** testing PA11 as a digital GPIO, assuming USB configuration exists
before the controller is initialized, or probing an unclocked peripheral.
The presence test deliberately includes a powered USB charger; physical
host enumeration is not required to enter USB mode. Ambiguous voltage fails
closed into an awake diagnostic park.

**Evidence:** `vbus.c`; MB1939 C02 R80/R81; RM0486 USB1 PHY VBUS limitation;
RAM04 returned ADC average 766/4095, three samples 766/767/766, zero ADC error
and a 2 ms sampling interval with CN8 connected.

## 2026-11-08  Keep each download tied to one fresh complete RAM snapshot

**Why:** the user requires best-effort retrieval even when an image becomes
unreadable on a later read. A complete fresh slot read precedes each GetObject
and GetThumb; transfer then consumes immutable RAM. Read warnings are included
in EXIF and remembered for later object names, with an ObjectInfoChanged event.

**Rejected:** advertising GetPartialObject while independently re-reading each
range, which could splice different damaged snapshots; inventing stored dates;
silently dropping known unreadable photos; deleting after download; calling
the existing marker-only RAW format checksummed. Compression is deferred until
basic native-host behavior is qualified. The storage/PNG rationale is owned by
[storage notes](storage/NOTES.md), not duplicated here.

**Evidence:** `ptp.c`, cancellation/event tests and the November 8 native WPD
downloads, including full equality of 1,527,680 exported pixels to slot175 RAW10.

## 2026-11-08  Keep PTP cleanup pending until the transport releases its buffers

**Why:** cancellation may arrive during the response phase, after image-data
cleanup has already been checked. Clearing the active flag then leaves a
pending cancel reporting Busy forever. A configured class DeviceReset also
needs real transfer cleanup; it is not a USB bus reset. One pending-cleanup
state now gates every new command and keeps Busy asserted across bounded abort
failures. Data and response buffers remain static and immutable until abort
success or an actual reset/disconnect invalidates hardware ownership.

**Rejected:** checking cancellation only before sending the response, ignoring
an abort failure in reset/error paths, treating a returned C function as proof
that USB has released its buffer, or keeping asynchronous response data on the
stack. Host cancel keeps the PTP session; class reset closes it. Neither may
allow a new operation to overwrite a still-owned transfer buffer.

**Evidence:** `ptp.c`, `test_ptp_transport_mock.c`, and the 21 passing native
cases in `test_ptp.py`, including response-phase cancel/reset, repeated abort
failure, queued-command exclusion, data/response buffer preservation and real
disconnect. The parent campaign owns live qualification of the resulting
firmware; these fault injections do not claim hardware abort failures occurred.

## 2026-11-08  Disable and invalidate instruction cache around the copied boot selector

**Why:** the first persistent USB package stopped with its intended E001
cache guard even though the RAM trial worked. The original stage1 enables
instruction cache after its early UART guard and before our post-memory hook.
The hook now records that state, disables/invalidates instruction cache before
copying and executing the selector, and restores it only when resuming the
original capture path. USB starts with caches disabled as its memory ownership
model requires. Data cache remains rejected. This supersedes the earlier
blanket statement that the hook simply refuses enabled caches.

**Rejected:** removing the coherency guard, assuming RAM-launch context equals
normal ROM boot, changing the capture loader, or enabling USB DMA against an
unqualified cache setup. The checked early UART guard recovered the initial
failure without a physical jumper change.

**Evidence:** package05 E001 diagnostic and UART recovery; package07/08 live
boot proofs; linked cache-transition tests in `test_boot_package.py`; the
[November 8 qualification](evidence/2026-11-08-native-ptp/README.md).

## 2026-11-08  Keep USB mode boot-selected and qualify capture separately

**Why:** the existing camera has a short capture-to-Standby cycle. Adding a USB
application must preserve its byte-exact capture payload and early recovery.
VBUS selects the application at boot; the USB mode owns SD and ADC12 exclusively
and does not capture. A temporary forced-capture selector exercised the return
path while the host cable remained attached, producing two new readable photos
and reusing the explicitly deleted slot. Final package08 restores real VBUS
selection. This test does not prove the physical cable-absent voltage branch,
cold-rail sequencing, or cable-removal Standby.

**Rejected:** silently promoting unrelated HOLD/DMA-sleep candidates, claiming
the two all-LOW GPIO recordings establish exposure timing, or treating a normal
reset as a fully discharged cold start. Automatic hot-plug wake from the existing
capture Standby state is deferred; the user starts a new cycle with USB attached.

**Evidence:** `package07-control`, the two final08 PNG validations, delete/reuse
and reboot tests, exact capture-tail comparison, and the qualification record.

## 2026-11-09  Compose USB with the reviewed early A3 HOLD capture build

**Why:** the canonical latch moved to A3/PA2, and must remain asserted through
the earliest custom boot code, UART recovery, capture/error handling and USB.
The prior USB package used plain October 28 capture plus a later PD7 assertion
inside USB, so changing USB alone would not hold power during battery capture.
The new package binds the exact PA2 capture image and preserves its payload.
The 76-byte early hook occupies verified unused error-reservation padding at
0x34181DF0; the 440-byte USB hook retains 0x34181E40. The UART guard and its
park remain byte-identical. The owning early-hook layout audit is in
[RAW capture notes](../capture-raw/NOTES.md).

**Rejected:** silently packaging the legacy no-HOLD capture image, overlapping
the two hooks in the 448-byte prefix tail, moving UART recovery, trusting an
arbitrary updated manifest, or changing the ADC's PA11 VBUS path to drive PA2.
The builder now requires an explicit reviewed capture input. USB shutdown
proof schema 2 distinguishes PA2 from historical PD7 records. Refused shutdown
and unexpected WFI return retain/reassert HOLD; PA2's WKUP2 source is disabled.

**Evidence:** `package.py`, `main.c`, `shutdown.c`, `test_boot_package.py`,
`test_shutdown.py` and [the offline candidate](evidence/2026-11-09-a3-hold/README.md).
The user confirmed the board is disconnected for assembly; no instrument,
NOR, SD, live recovery allowlist or installed-firmware state was changed.

## 2026-11-13  Move HOLD to D3 and retain USB-selected battery release

**Why:** the user moved the latch wire from A3 to Arduino D3 after PA2 failed
external output tests. D3 is PE9/CN13.4 on main VDD, with secure GPIO base
0x56021000. The combined image must bind its early capture assertion, error and
success shutdown, USB selector and USB teardown to the same physical pin.
The earlier user requirement that USB not keep the battery latch alive still
applies. This branch lacked the already committed `34a49be8` USB-off correction;
its selected-mode behavior is restored and moved to PE9. Capture and early UART
recovery retain HOLD; a USB-present or ambiguous VBUS result releases it before
loading USB. USB service/fault/refusal/WFI-return paths never set it HIGH.

**Rejected:** pairing PE9 USB code with a PA2 capture image; reasserting battery
HOLD on USB shutdown failure; changing the early recovery guard or adding an
unqualified early VBUS sampler. The provisional early HIGH before VBUS selection
is retained, so this is not a guarantee of a zero-pulse USB cold boot. Retired
PA2 and PE6 UART fields are preserved; D3's main-VDD assignment does not grant
powered-off input tolerance or prove the original A3 failure mechanism. Assembly
schematic updates are deferred until the requested firmware smoke test.

**Evidence:** `usb_hold.h`, `selector.c`, `shutdown.c`, exact-pin package guards,
the selector model and 34-case shutdown model (including 4,096 randomized GPIO
states), linked PE9 float/WFI instruction audit, and
[the offline D3 package](evidence/2026-11-13-d3-hold/README.md). USB shutdown schema
4 distinguishes PE9 OFF from older pin/policy records. No instrument operation
or installed-state claim accompanies this offline preparation.

**Provenance:** user D3 wiring request and prior USB HOLD-off instruction;
implementation policy recovered from commit `34a49be8`, whose November 10
candidate was not installed. The November 9 note above describes historical
PA2 behavior and is superseded by this pin and USB-selected release policy.

## 2026-11-13  Substitute D8 HOLD and preserve the existing USB release policy

**Why:** the user superseded D3 with Arduino D8/CN14.1/PD12 and explicitly
requested a simple substitution and reload without further tests. The capture
and USB images must agree on this pin, so USB selected-mode release, refusal
and final float now target only PD12 at secure GPIOD base 0x56020C00. USB
shutdown schema 5 and USB policy schema 4 distinguish this image from PE9.
The capture owner also disables PD12's former phase output to avoid pulsing HOLD.

**Rejected:** keeping different latch pins in capture and USB; retaining the
PD12 phase-marker output; starting another qualification campaign when the user
asked only for substitution/reload. Prior D3 test evidence remains historical;
D8 build/source/artifact checks are not a new hardware or regression qualification.

**Evidence:** `usb_hold.h`, `selector.c`, `shutdown.c`, the exact D8 capture pair
admitted by `package.py`, and [the D8 build record](evidence/2026-11-13-d8-hold/README.md).
Early UART recovery and the provisional pre-VBUS assertion policy are unchanged.
No instrument operation accompanies this offline work.

## 2026-11-14  Read both knobs in the boot selector and edit the loaded capture prefix

**Why:** the user asked for a firmware release in which the two knobs control
the photo. Exposure, gain and frame length are written to the sensor by the
capture prefix, which cannot be rebuilt outside the original ST compiler: it
has four spare bytes, its layout is pinned by hash, and neither stock GCC
12.3.1 nor 13.2.1 can link the capture stage's fixed layout from the same
sources. The selector is
the one piece of code that already runs on every boot before sensor setup,
already brings up the converter, and builds identically in logic with GCC
13.2.1. So `knob.c` reads both knobs there and writes the three values into the
RAM copy of the prefix: bytes 1 to 3 of the manual-exposure block and the
`MOVW` holding the frame length. It runs only when VBUS sampling returned a
certain "absent", checks the exact default bytes before writing, and leaves the
fixed 1428 lines at 1x on any failure, so a knob fault can cost control but not
the photo.

**Rejected:** rebuilding the capture stage to read a mailbox, which is the
cleaner end state but needs the ST compiler and a new capture qualification;
adding converter code to the prefix, which is full; converting the knobs inside
`vbus.c`'s ADC2 session, which would alter the hardware-proven VBUS sampler and
use inputs only proven on ADC1; exciting the knobs before the VBUS decision,
which would drive A4 and A2 in USB mode for no purpose; restoring registers
field by field, which cost 240 bytes of selector for no benefit in
single-threaded code; storing the applied values with the photo, which needs a
capture rebuild and a metadata schema that does not exist; treating the
host-side register model as hardware evidence.

**Evidence:** `knob.c`, `knob_map.h`, `knob_tables.py`, `selector.c`,
`package.py` `knob_sites()`, `test_knob.py`, and
[the build record](evidence/2026-11-14-knobs/README.md). Offline only: no
instrument or camera was used, and the package is not installed.

## 2026-11-14  Open the receiver's fixed-exposure assertion with a five-byte, checksum-neutral edit

**Why:** the reviewed receiver reads back the sensor's applied exposure and
fails the photo with code 0x90 unless it is 1428 lines, so an exposure knob
cannot work against unchanged capture bytes. The assertion is in the
late-loaded range, which the receiver loads and CRC-checks itself after
arming, and the receiver cannot be rebuilt here. `exposure_gate.py` turns its
`beq.n` into `b.n` to the same continuation, which leaves the two failure
instructions after it unreachable, and sets those four bytes so the late
range's CRC-32 is unchanged. Nothing else moves: the checksum constant, the
early receiver, its CRC literals in the prefix and every other capture byte are
as reviewed. The continuation reloads the registers the comparison used, and
no branch or stored address reaches the four bytes. The receiver's only other
exposure-dependent check, the frame-margin test, is not compiled into this
build; the knob mapping keeps the frame 2000 lines longer than the exposure.

**Rejected:** recomputing the late checksum instead, because its constant sits
in the early receiver, whose own checksum is held twice in the prefix: thirteen
bytes in four places rather than five in one; patching the receiver in RAM from
a trampoline, because the late range is loaded after the last point the
selector controls; leaving the assertion and offering gain only; calling the
edit reviewed capture code. It is a new, untested variant of it.

**Evidence:** `exposure_gate.py`; `test_knob.py` `ExposureGateTests`;
`test_boot_package.py` proves that undoing the recorded edit restores the
reviewed capture bytes; flash offsets 0x6B87 to 0x6B8B in
[the build record](evidence/2026-11-14-knobs/README.md); archived receiver
source `capture-raw/evidence/2026-11-13-d3-hold/hold-standby/capture.c` line 762.

## 2026-11-14  Knob ranges: 0.2 ms to 484 ms, 1x to 8x, frame at least exposure plus 2000 lines

**Why:** D-39 asks for an exponential exposure curve and D-50 for 1x to 8x
analog gain in equal stops; both are implemented as 33-point tables with
integer interpolation. The top of the exposure range is set by the sensor mode,
not by choice: exposure and frame length are 16-bit line counts at 7.69 µs per
line, and the receiver requires that line length, so about half a second is
the ceiling. The user had already accepted a 0.5 s limit on November 11. The
frame rule `max(4336, lines + 2000)` is the one the October 24 long-exposure
bench test used at 30000 lines, the only long exposure ever run here, which
caps exposure at 63000 lines. The floor of 26 lines is above the sensor
driver's minimum of 21. Readings below 120 and above 3720 are treated as end
of travel because the calibrated converter tops out near 3839 and the divider
puts the top few percent of travel beyond that.

**Rejected:** one second, which needs a longer line time that ST discourages
and the receiver rejects; a linear exposure scale, which crowds the useful
short exposures into the first few degrees; digital gain beyond 8x; the
sensor's own minimum frame margin of 75 lines, which has never been run;
deriving the top of the range from each boot's calibration factor, which adds
a failure mode for no visible gain; checking the knob's end pins as a wiring
test, which cannot detect a missing wiper.

**Evidence:** `knob_tables.py` and `test_knob.py` (every code 0 to 4095 mapped
and compared with an independent model); `capture-raw/magic_transform.py`
`sensor_exposure()` for the frame rule; `capture-timing/exposure-measurement.md`
for line time and the 650-line and 1301-line runs. Exposures outside 5 ms to
231 ms and gains above 1x are untested on hardware.

## 2026-11-14  Stop the converter before every channel change, and raise the exposure floor to 0.5 ms

**Why:** an independent review of the first knob build, before it was
released or installed, found that it could never read a knob. ST's
`HAL_ADC_ConfigChannel` returns an error while the converter is enabled, and
both calibration and a finished conversion leave it enabled; only
`HAL_ADC_Stop` disables it. `vbus.c` never met this because it converts one
channel. The reader selected its first channel straight after calibration, so
on the chip it would have returned result 6 on every boot and every photo
would have kept the fixed settings. `convert()` now stops the converter first,
as `control-smoke/control.c` always did. The host test missed it because its
stand-in for the driver asserted the rule instead of enforcing it; the
stand-in now returns the driver's error, and `hal_model/` runs the real driver
sources against a model of the bus so the next such rule is not left to a
stand-in.

The same review measured how little time separates arming the receiver from
the picture arriving. Across 37 recorded captures the receiver is armed 5.04
to 5.07 ms after sensor START; the exposure strobe rises at 5.29 ms and readout
starts 0.24 ms after it falls. A 0.2 ms exposure would start readout 0.7 ms
after arming, where the fixed exposure leaves 11.5 ms; if arming ever came
later than readout the single frame would be lost and the photo would fail
after a 3 s wait. The floor is now 65 lines, 0.5 ms, which leaves about 1 ms.
That margin is a judgement, not a measurement.

Three smaller changes came from the same review: the reader refuses to write
if memory protection is enabled, so an unexpected read-only prefix costs knob
control and not a fault; the selector marks the knob record "not read" on USB
boots, where it used to leave the previous photo's result; and the gate's
branch scan now decodes the low-overhead-loop branches the receiver contains.

**Rejected:** releasing the first build on the strength of its own tests;
keeping the 0.2 ms floor, the sensor's 21-line minimum or any other value
whose margin after arming is under 1 ms until the arm time has been measured
on the installed build; treating the recovery allowlist entry for the first
build as still valid, since the hashes changed with the fix.

**Evidence:** `knob.c` `convert()`; ST HAL v1.3.0 `stm32n6xx_hal_adc.c`
`HAL_ADC_ConfigChannel` and `stm32n6xx_hal_adc_ex.c`
`HAL_ADCEx_Calibration_Start`; `control-smoke/evidence/2026-11-09-a3-live/hardware/knob-sweep01/latest.json`,
where the enable bit reads 1 after a conversion and 0 only after a stop;
`hal_model/model.c` and `test_knob.py` (the committed first reader gives result
6 under both models, the corrected one gives 0 with four conversions);
`capture-raw/evidence/2026-10-26-sd25-twenty` and the other `verified.json`
records for the arm time; `capture-timing/exposure-measurement.md` for the
strobe and readout delays. Still offline only.
