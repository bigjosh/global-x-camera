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
