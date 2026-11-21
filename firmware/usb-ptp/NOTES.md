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

## 2026-11-13  Sample both knobs only on confirmed battery capture and keep a fixed helper ABI

**Why:** normal capture must use the physical exposure/ASA controls without
disturbing D8 HOLD, early UART recovery or USB-selected battery release. The
post-memory selector has room for a bounded ADC1 batch and sensor helper, while
the boot prefix does not have room for their complete implementation. Its
reviewed frame-write call and manual-data pointer therefore refer to a fixed,
CRC-loaded helper at 0x34200100 and a 128-byte CKN1 record at 0x343F9400.
Only confirmed absent VBUS samples controls; present/ambiguous VBUS keeps the
existing USB HOLD-off behavior. Excitation is off before capture resumes, and
ADC/security/rail/cleanup failures propagate through the camera initialization
error display and shutdown instead of silently using stale settings.

The user's calibration has exposure decreasing electrically toward CCW and ASA
increasing: normalize to measured endpoints/references and invert exposure only.
The manually estimated middle position is not a calibration anchor. The revised
range is logarithmic 1 ms to 500 ms, with ASA sectors 100/200/400/800 mapped to
analog gain codes 0/16/24/28 (1/2/4/8x), always unity digital gain. Constant line
length 1280 allows the true half-second endpoint plus 2000 lines of frame margin
inside 16 bits. It leaves READ_OFFSET18 valid; the actual coarse margin is read
and checked. MAX_AG_CODED defaults to 24 in the manual, so the helper explicitly
sets and verifies 28 before applying the requested 8x manual gain.

**Rejected:** runtime opcode mutation; expanding the tiny boot prefix; knob reads
in USB mode; an assumed 50% mechanical center; advertising 500 ms while clipping
at 488 ms; the superseded 1-second/dynamic-line-length design; inferring a hard
minimum coarse margin from conflicting vendor defaults; silently falling back
after ADC faults. Initial 10 ms settling is conservative and may later be tuned.
The requested load-only workflow defers new hardware and timing qualification;
provisional ASA labels are not calibrated ISO.

**Evidence:** `capture_controls*.c/.h`, `controls_entry.S`, selector/package
composition, capture owner's `knob_transform.py`, and final
`tmp/bringup/knobs-capture-20261113/package-v1`. Selector7716B fits the existing
8192B reservation; helper and manual-pointer patches are the only additional
prefix changes. Targeted ADC/map/callback/selector tests passed before the user
requested no further verification; the build's mandatory boundaries passed.
Package prefix SHA256 `b866589cf472cac9820d961f3243cb8280759614826083757fae374ccee7e242`.
This note records offline implementation, not installation or hardware success.

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

## 2026-11-14  Reconcile the two knob paths as mutually exclusive profiles

**Why:** upstream9f159586 added an independent runtime-prefix knob patch while
our uncommitted source-built controls path already existed. Applying both would
change the frame argument before the local helper validates its fixed call,
causing initialization failure; applying the upstream exposure gate to the new
receiver would also be invalid. Retain both historical implementations as
separate profiles, preserving the upstream toolchain/SDK portability and real
HAL test model, and preserve both frozen package identities. The selected
physical mapping remains the measured CCW-increasing1–500ms/four-ASA-sector
plan recorded in prototype notes. The reconciliation report recommends the
source-built controls path for a later consolidated release; it does not
qualify or install either candidate.

**Rejected:** automatic concatenation of both samplers; applying the old
checksum-neutral assertion-removal patch to the rebuilt receiver; treating
successful publication as hardware qualification; silently changing previously
frozen binaries or deleting the other implementation's history.

**Evidence:** [review, findings and intended consolidation](../../docs/review/2026-11-14-knob-firmware-reconciliation.md).
The pull preserved prior work in stashd0609865 and a separate working-file
backup. The published prerelease points at9f159586 and has matching sector
asset hashes. Both archived firmware manifests/hash lists remain unchanged.
No instrument operation, firmware load, publication or Git push occurred.

## 2026-11-14  Make calibrated source-built controls the default package

**Why:** after the upstream review, the user selected our implementation and
requested consolidation, retention of useful upstream improvements, release
fixes, commit and push. The canonical path preserves measured exposure polarity,
1–500 ms logarithmic exposure, four ASA sectors, the explicit 8× gain limit,
applied-setting checks and CKN1 metadata. Package toolchain/SDK portability and
real-ST-HAL regression coverage are retained. Historical runtime instruction
patching is available only through explicit `--legacy-knobs`; the default
rejects a fixed-settings capture reference instead of silently using that path.

**Rejected:** leaving the superseded profile as the default, sampling twice,
silent fixed-setting fallback, dropping metadata or applied-value checks to
match the old release, changing historical binaries, or treating offline
success as hardware qualification. Firmware installation remains separate.

**Evidence:** `package.py`, `selector.c`, profile regression tests and
[review/consolidation record](../../docs/review/2026-11-14-knob-firmware-reconciliation.md).
The user authorized committing and pushing this consolidation on November 14.
No instrument access is part of it.

## 2026-11-16  First hardware shots on r2: knobs apply to 88 ms; ~0.5 s fails with code 2 after settings verify

First battery captures on the installed `knobs-2026-11-14-r2` image (Mac
install, see `release/NOTES.md`). Thirteen saved photos carry
`settings=applied`: 1,003 to 88,366 us, at ASA 100 (1x) and ASA 800 (8x).
Slower exposure-knob positions give two red flashes (camera initialization)
and no photo; the exact threshold between 88 ms and 0.5 s was not bracketed.

For one failing shot the CKN1 record was read over hot-plug SWD during the
blink display: `state=4` (applied/verified), `error=0`, `flags=0x1f`,
`requested_us=497696`, coarse 62524 (`applied_coarse` equal), line 1280,
frame 64524, margin 68, ASA 100. So `capture_controls_sensor_apply` and the
applied-settings verification passed; the failure is later.

**Not established:** the failing location. The capture failure `where` value
was not read. A candidate from source reading only: the START-acknowledge and
streaming-state waits in `capture-timing/build.py` share a 500 ms
`HAL_GetTick` deadline (`fail(0x75,-100)` / `fail(0x76,-100)`, both classified
as code 2), and this frame lasts about 514 ms (64524 lines x 1280 / 160.8 MHz).

**Evidence:** photos `GX_0000412`-`GX_0000424` on the Mac
(`~/Pictures/Global X Camera`, eXIf user comment), and the record bytes
`434b4e31010000008000000004000000000000001f00000001000000000f0000000f0000`
`0400000002000000ccff00001100000020980700000500000cfc000002003cf400010001`
`0001000164000000009d95093cf40000000000000001000044000000d4d4270078df6d00`
`2bf27700df027a000000000000000000eded17ac`.

## 2026-11-16  Cap the exposure knob at 1/8 s after hardware shots bracketed the failure

Follow-up to the entry above, same day. Sixty-five r2 photos now carry
`settings=applied`. With no debugger attached the slowest saved exposures are
139,709, 142,790, 154,866, 175,180 and 219,256 us, at ASA 100 and 800. The
operator saw two red flashes at slower settings; the fastest such shot whose
value was read is 262,813 us. So the limit lies between 219 ms and 263 ms of
exposure (about 235 to 279 ms of frame time). Its cause is still not
established; the 500 ms START-acknowledge deadline suggested above does not
explain a failure at 263 ms unless that tick is not 1 ms.

**Caveat on the failure readings:** none of the twelve shots taken while the
ST-LINK was attached and polled over hot-plug SWD (200 kHz, about two reads
per second) produced a saved photo, including five the operator judged good
(3.5 ms, 4.6 ms, 79.6 ms). The debugger polling therefore appears to prevent
or lose the save. The failure values above 263 ms were read under that
condition; the two-red-flash symptom itself was first reported without it.

**Change (source only, uncommitted, not built or flashed):**
`capture_controls_map.c` now spans 1,000 to 125,000 us over the same 64
log-spaced intervals (`round(1000*125^(i/64))`), at the user's choice of 1/8 s.
`test_capture_controls.py` passes natively; `test_controls_real_hal.py` was
edited to match but not run here. The frozen-source hashes in `package.py`,
the README's 1/1000-1/2 s wording, the release profile and the 15.5 mm knob
label (`docs/prototype/knob-labels/design.json`) still describe 1/2 s and need
the same update before a release.

**Rejected:** clamping the existing table at 125 ms (leaves the last quarter
of an unmarked knob's travel dead); capping at 1/5 s (only one saved photo is
slower than 200 ms); building here (Arm's stock GCC does not reproduce the
release bytes on this Mac).

## 2026-11-16  1/8 s table built on the Mac, installed, and shot across its range

Supersedes "building here" in the rejected list above: ST's macOS build of the
same compiler reproduces r2 byte-for-byte, so the 1/8 s table was packaged and
installed from the Mac (build identity and byte diff in `release/NOTES.md`).

Six battery shots on that image, no debugger attached, all saved with
`settings=applied` at ASA 800: 1,003, 1,003, 2,683, 23,172, 105,672 and
124,553 µs. The operator reported no two-flash failures across the knob's
travel. The slowest reading is the top of the new table (125,000 µs nominal).

Still open: why exposures above ~220 ms fail on r2; ASA 100-400 and the
intermediate knob positions were not re-shot on this image.

## 2026-11-16  ASA fixed at 200 because the prototype's ASA knob only reads its ends

Every ASA reading from this prototype is at a rail: ten raw wiper samples read
over SWD on r2 were 0-3 or 3840-3841 (with `asa_high` 3840-3841), and all 79
saved photos record ASA 100 or 800, never 200 or 400. Eight shots taken while
stepping the ASA knob across its travel all recorded ASA 100. The exposure
wiper in the same sessions read smoothly (164-3065), and a pair of photos at
matched light (11.8 ms at ASA 800, 98.6 ms at ASA 100) has equal brightness,
so the gain path itself works. The cause at the knob is not established
(wiring, track or a slipping knob); a resistance check from A5 to GND was
suggested and not done.

At the operator's request `capture_controls_map()` now ignores the ASA sector
and always selects ASA 200 (gain code 16). `asa_raw`/`asa_q16` are still
sampled, validated and recorded, so the knob can be diagnosed from the record
later. Host test updated and passing; `test_controls_real_hal.py` edited, not
run.

Rejected: automatic ASA (needs a metering frame in the capture firmware, whose
build scripts are still Windows-only); ASA 100/400/800 (operator chose 200).
Restore the sector line from git history once the knob reads its full travel.

## 2026-11-20  Exposure table extended to the sensor's 21-line floor (1/6000 s) and ASA fixed at 100

**Why:** on the ASA-200 image the user's daylight photos at the 1 ms end were
50-96% clipped (GX_0000544 to GX_0000557, all `exposure_us=1003`), so the
short end needed several stops. The table now runs 167 µs to 125000 µs
(`round(167*(125000/167)**(i/64))`); 167 µs rounds up to 21 lines at line
length 1280, the floor `VD6G_MIN_MANUAL_EXP_COARSE` in ST's `vd6g.c` and the
bound `capture_controls_map` already enforced. Fixed gain drops from code 16 to
0 (ASA 100) for one more stop. Together about 3.6 stops below the previous
shortest setting. The user chose both, knowing the slow end gets a stop darker.

This goes below the 0.5 ms floor that the 2026-11-14 review set for the other
knob path on arm-time grounds: by those figures a 21-line exposure starts
readout about 0.65 ms after the receiver is armed. That margin is not measured
on this build. A late arm would show as a failed photo after the 3 s wait, so
the test is whether fast-end shots save.

Curve error against the ideal exponential is now up to 0.49% (was <0.17%),
because the short-end entries are small integers; the source comment says so.

**Rejected:** stopping at 0.5 ms or 0.25 ms (one or two stops is not enough
for frames that are 90% clipped); keeping ASA 200.

**Evidence:** `capture_controls_map.c`; `test_capture_controls.py` (passes:
endpoints 167/125000, coarse 21 at the short end, gain code 0);
`test_controls_real_hal.py` expectations edited but not run. Not yet installed
or shot when this entry was written.

## 2026-11-21  The 1/6000 s table could never work: the capture receiver rejects under 1000 µs. Table back to 1/1000 s, ASA stays 100

**Why:** on the 2026-11-20 image the user found that only dial positions at
or slower than about 1/1000 s saved a photo. The three that saved recorded
2173, 1114 and 2038 µs. The cause is not arm timing. The prebuilt capture
receiver's `knob_record_valid()` (`evidence/2026-11-13-knob-controls/capture/knob_capture.inc`)
returns 0 when `requested_us<1000U || requested_us>500000U`, and `capture.c`
then fails the photo with code 0x7D after the frame is captured. The helper
and `capture_controls_map.c` accept 21 lines, which is what the 2026-11-20
entry checked; the receiver was not read before that image was built and
installed. That was the mistake. The 2026-11-20 arm-timing concern is
therefore still untested, not disproved.

The table is back to 1000-125000 µs (the 2026-11-16 table) and the source
comment now names the receiver's floor. ASA stays fixed at 100, so daylight
gets one stop less light than the ASA-200 image and nothing more. Shorter
exposures need the receiver rebuilt with a lower bound, which is the Windows
`build.py` path, plus a measurement of the arm margin on that build.

**Rejected:** a byte edit of the receiver's bound from here (it is in the
CRC-checked late range and is reviewed capture code); leaving the 1/6000 s
image on the camera with a quarter of the dial dead.

**Evidence:** `knob_capture.inc` and `capture.c` line 750 in the evidence
folder above; photos GX_0000600 to GX_0000602; `test_capture_controls.py`
passes with endpoints 1000/125000 and gain code 0.

## 2026-11-21  Capture receiver and USB app now build on macOS; exposure floor lowered to 167 µs in all three places

**Why:** the user asked for the receiver to be buildable here so the 1000 µs
floor could be lowered without waiting for a Windows build. With four script
fixes `capture-raw/build.py` and `usb-ptp/build.py` reproduce the committed
2026-11-13 binaries byte for byte on macOS (receiver `8cd86fa7...caaa`,
stage1, capture sector 0, USB app `06dca8da...d6bf`), using ST's macOS build
of the same 12.3.rel1 compiler:

- `GLOBAL_X_TOOLCHAIN` overrides the hard-coded `D:/ST/...` folder in
  `capture-timing/build.py` and `build_raw10.py`. The scripts still call
  `arm-none-eabi-*.exe`, so on macOS the folder holds links with those names.
- `capture-raw/build.py` splits frozen-manifest source keys with
  `PureWindowsPath` (on POSIX `Path('a\\b').name` is the whole string) and
  remaps the manifests' recorded `-ID:\Github\global-x-camera\...` include
  paths onto the current checkout. On the original Windows path both are
  no-ops.
- `usb-ptp/build.py` sorts the `st-usbd` source glob. Unsorted, APFS returned
  a different order from NTFS, the link order changed, and 1853 bytes of
  `usb.bin` differed. Sorted order equals the NTFS order.
- `tmp/bringup/x-cube-n6-camera-capture` must be ST's public repository at
  `e9441cdbb5072a6d3bcef1a5ca4e4d80f850283a` (a plain clone; git-ignored).

Then the floor: `capture-raw/knob_capture.inc` (`requested_us<167U`),
`capture-raw/knob_transform.py` (contract and record check),
`storage/photo_store.c` (`requested_us<167`) and the table in
`capture_controls_map.c` (167-125000 µs again, ASA 100). 167 µs is 21 lines.
The receiver shrinks by 4 bytes, so most of it shifts; in the stage1 prefix
only the two receiver-CRC words change. `package.py` admits the new
(stage1, sector 0) pair as `pd12-knob-controls`, with a comment that it is not
independently reviewed.

**Rejected:** a checksum-neutral byte edit of the old receiver; keeping the
USB metadata check at 1000 µs (short exposures would save but export without
their settings).

**Evidence:** `test_capture_controls.py` passes; `capture-raw/test_knob_controls.py`
runs 4 tests with the same single error before and after (it needs
`tmp/bringup/d8-hold-20261113`, which is not in the repository). The arm-time
margin at the short end (2026-11-14 and 2026-11-20 entries) is unmeasured. No
photo had been taken on this build when this entry was written.

## 2026-11-21  First photos on the rebuilt 167 µs image: short exposures save

Fourteen photos (GX_0000603 to GX_0000616) taken on battery on
`sixthousandth-asa100-2026-11-21` all exported with `settings=applied`, ASA
100, and exposures from 167 µs to 125007 µs; five are at 167 µs (21 lines)
and two at 438 µs. So the receiver, the applied-value check and the USB
metadata check all accept the new floor, and a 21-line exposure did not lose
the frame to a late arm in these five shots. Whether any shot failed is not
known: failed shots leave no record, and the user reported none.

The scene was dim. Median level falls from 41.7% of full scale at 125 ms to
6.3% at 167 µs, which is about the sensor's black level, so these frames show
that short exposures complete and save, not that they are correctly exposed.
A daylight series is still needed for that.

## 2026-11-21  No failed shots in the first series on the 167 µs image

The user confirmed that none of the shots in the GX_0000603 to GX_0000616
series gave an error blink, so all fourteen attempts saved, five of them at
21 lines. This closes the open question in the previous entry; correct
exposure in daylight is still unchecked.

## 2026-11-21  `test_usb_exporter_must_bind_current_ckn1_schema_and_reader` now errors, and is left that way

`package.py` refuses a USB build whose recorded `storage/photo_store.c` hash
is not the tree's, and this test checks the archived 2026-11-13 USB manifest
against the tree. Lowering the metadata floor changed `photo_store.c`, so the
archived USB build no longer matches and the test raises "Canonical controls
require the matching CKN1 metadata-capable USB build". That refusal is the
check working: the 2026-11-13 USB app should not be packaged with a receiver
that accepts 167 µs. The consequence is that r2 and the three 1/8 s images
can no longer be repackaged from this tree's default inputs; they need the
tree at the commit before this one.

Deferred to the repository owner: freeze the 2026-11-21 capture and USB builds
as evidence and point the test at them, or decide the floor differently. The
build outputs themselves are under the git-ignored `tmp/` and are not
committed; the installer assets carry the resulting sectors.

On macOS two other tests in this folder fail with or without these changes
(`test_knob` and `test_selector_hold` selector cases: the host compiler rejects
an ELF section attribute for Mach-O).
