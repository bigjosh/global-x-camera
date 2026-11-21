# Release decisions

## 2026-11-14  Publish explicitly and preserve firmware tag and asset identity

**Why:** an uploaded firmware image must continue to identify the same source
commit and recovery metadata. The previous push-triggered workflow could replace
assets under an existing tag without checking its commit, so a normal merge or
retry could silently change the meaning of a release. Publishing now requires
manual workflow dispatch, an explicitly enabled committed request and its exact
tag. The historical knob request is disabled. A tag on another commit, changed
metadata or an existing mismatched asset stops publication. A matching published
release is a no-op; only a matching unpublished draft may receive missing assets,
and all downloaded asset bytes are checked before publication.

**Rejected:** publication triggered by an ordinary source push; moving a release
tag; replacing existing assets with `--clobber`; treating network/authentication
errors as proof a release does not exist; publishing a partly uploaded release.
Correcting historical release notes is a separate, explicit action and does not
authorize changing the associated tag or binary assets.

**Evidence:** `.github/workflows/publish-release.yml`, `publish.py`,
`test_publish.py`, and the superseded notice in
`knobs-2026-11-14/RELEASE_NOTES.md`. Offline fake-service tests cover partial
upload/retry, byte mismatches, moved tags, metadata changes and HTTP failures.
No GitHub publication or hardware operation is performed by those tests.

## 2026-11-14  A timed-out NOR write must finish safely before readback or retry

**Why:** `firmware/usb-ptp/nor.py read` halts the target and replaces the RAM
helper. A host timeout does not stop an in-progress flash operation, and even a
`DONE` record can report controller/flash uncertainty. The old release notes
incorrectly suggested an immediate read and retry. Corrected instructions require
a fresh operation-matched completion record and the same result/safety-flag
checks used by `firmware/boot-timing/nor_bench.py` before a helper replacement.

**Rejected:** treating a host timeout, a stale status file, or `DONE` alone as
proof of a safe halt; automatically resetting, reading flash or repeating a
write while the original operation's completion remains unknown.

**Evidence:** `knobs-2026-11-14/RELEASE_NOTES.md`, "If something goes wrong";
`firmware/boot-timing/nor_bench.py` completion checks and timeout behavior;
`firmware/usb-ptp/nor.py` read-helper loading path. This documents the existing
hardware safety requirement and adds no new approval requirement.


## 2026-11-14  Publish calibrated controls as a new r2 prerelease

**Why:** after consolidation the user explicitly asked for the release to
contain our firmware and for a review of its notes. The previous release still
identifies different bytes, so `knobs-2026-11-14-r2` carries the canonical image
under a new immutable tag. It includes both flash sectors, a complete package
with exact recovery records, an installation guide and checksums that match
the actual downloadable files. The outer manifest relocates build provenance
to committed evidence; executable and recovery bytes are unchanged.

**Rejected:** replacing binaries under the old tag, reusing a whole-build hash
list that cannot verify loose downloads, labeling publication as installation,
or calling this bench-specific procedure a portable installer. The notes
separate offline checks from the remaining physical controls, images, USB,
latch/recovery, timing and energy qualification.

**Evidence:** `knobs-2026-11-14-r2/RELEASE_NOTES.md`, `INSTALL.md`, package
manifest and inner/outer SHA256SUMS; `request.json` explicitly enables this
user-requested publication. No instrument or target-memory operation is part
of preparing or publishing this release.


## 2026-11-14  Confirm an existing draft before resuming after lookup uncertainty

**Why:** r2 creation returned successfully, but the immediate tag/list lookup
failed to rediscover the new draft. Subsequent read-only checks found one
matching empty draft, and the normal publisher safely resumed missing uploads.
The cause of the transient lookup result was not determined. After publication,
all eight public downloads and both checksum lists were verified, and the
completed request was disabled again. A future publisher improvement can use
the returned draft ID or bounded read-only rediscovery before reporting failure.

**Rejected:** treating a lookup miss after creation as permission to create
another release, overwriting assets during retry, or assuming upload success
alone proves the public downloads contain the intended firmware.

**Evidence:** `knobs-2026-11-14-r2/PUBLICATION.json`; source/release tag remains
`a2e30d251c39c08378f84ffccc002ea3737b2c5e`. No hardware operation occurred.

## 2026-11-14  Add current knob artwork without replacing release firmware

**Why:** the user explicitly requested the current two-knob SVG in the
repository and attached to the most recent release. The additive
`knob-labels-15p5mm.svg` asset on `knobs-2026-11-14-r2` contains two solid
15.5 mm labels, exposure 1/1000–1/2 second and provisional ASA 100–800,
with centered captions and ASA-only sector dividers. The source generator
and design inputs are retained with the SVG. This artwork is published
after the original firmware release; its asset record carries its own hash.

**Rejected:** moving the firmware tag, repackaging or replacing the eight
existing assets, rewriting their original checksum lists to imply the art
was present at firmware publication, or changing the automatic publisher's
immutable-firmware policy. This is the user's specific authorization for
an additional artwork attachment, not a change to firmware publication rules.

**Evidence:** [SVG](../docs/prototype/knob-labels/knob-labels-15p5mm.svg),
[generator](../docs/prototype/knob-labels/generate-labels.ps1), and
[download verification](knobs-2026-11-14-r2/KNOB_LABELS_ASSET.json).
The downloaded SVG and GitHub's asset digest match the local SHA-256;
the eight previous asset IDs, sizes and digests are unchanged. No hardware
or laser operation occurred.


## 2026-11-14  Give clean Mac installs a development-mode loader procedure

**Why:** the user requested beginner/AI instructions at the top of the release,
starting without project files or STM tooling. STM32CubeProgrammer's bundled
Nucleo external loader provides that route after deliberate development boot
(JP2 pins 2–3), with verified sector1 then sector0 writes. CN10 carries ST-LINK;
CN8 and the prototype selector's USB position supply the target independently
of HOLD. This differs from our normal-boot UART park, where the same standard
loader previously stalled. The Windows bench helpers remain a separate path.
The Mac GUI/CLI route is documented from ST's current guidance and the recorded
Windows development-mode success, not claimed as a fresh Mac hardware test.

**Rejected:** requiring a repo/compiler/Python installation for prebuilt firmware;
using a normal-boot recovery park with the standard loader; carrying forward the
old diagram's CN8-unplugged advice for this two-cable USB-powered procedure;
changing published firmware/archive bytes merely to correct installation text.
`CURRENT_RELEASE_NOTES.md` is the mutable live body. Original attached notes,
INSTALL, ZIP and checksums remain their publication snapshot, explicitly labeled
as such in the current body.

**Evidence:** `knobs-2026-11-14-r2/CURRENT_RELEASE_NOTES.md` and its official ST
links; `firmware/capture-timing/evidence/2026-10-20-vcp-sd-smoke/programming/`
contains successful standard-loader programming, full64KiB verification and
preservation of the following4KiB. The normal-boot distinction is recorded in
`firmware/boot-timing/NOTES.md`. No instrument, firmware or SD operation occurs
in this documentation task.


## 2026-11-14  Use a guided UART installer because the boot jumpers are inaccessible

**Why:** before the preceding Mac-guide draft was published, the user clarified
that the boot jumpers cannot be reached and requested a Python utility using
the existing debug boot path. They then specified novice-friendly prompts:
connect both USB cables, arm recovery, switch to USB, detect the MCU and show
programming progress. The default utility queues C0 at1Mbaud before requesting
the switch, verifies the exact early UART park, backs up both NOR sectors and
the following4KiB, programs secondary then primary, independently rereads all
three regions, and verifies the new UART park before normal reset. The user
explicitly requested offline preparation only; no board/instrument operation
is part of this task.

**Rejected:** the unpublished development-jumper guide (superseding the
preceding entry's proposed path); using ST's stock external loader after
normal-boot UART recovery; hardcoded COM8/Windows/tmp paths; compiling helpers
on the user's Mac; treating timeout or DONE alone as safe flash completion;
resetting or retrying after uncertain completion; silently assuming a physical
power-switch state from elapsed time. The GUI-style console reports actual
stages/pages, and the source-selector instruction remains necessary because
software observes verified recovery, not the switch contact itself.

**Evidence:** `installer/` source, frozen helper manifests/disassemblies and
`assets/PROVENANCE.json`, exact D8/r2 recovery profiles, and offline tests of
recovery, NOR completion and complete installation failure paths. Helper
binaries are unchanged; the new host orchestration and macOS behavior are
explicitly unqualified on hardware. A persistent per-probe record prevents
blind retries after unresolved mutation, including serial reset before a SWD
halt. Original firmware release assets stay immutable; the guided installer
is a separately identified additive asset. `CURRENT_RELEASE_NOTES.md` supplies
the current release body; its older attached notes remain the publication snapshot.

## 2026-11-16  First Mac hardware install needed 200 kHz SWD and two output filters

The guided installer first completed on a Mac (Apple Silicon, STM32CubeProgrammer
2.23.0, ST-LINK V3J15M6 serial 002100203335511035383531) only after three local
changes to `installer/camera_install.py`, all still uncommitted:

- strip ANSI colour codes from CLI output (they hid the `-coreReg` lines from
  the `^`-anchored parser, giving a false "not the reviewed recovery context");
- drop `libusb: warning` lines before the `Error:` check;
- `freq=200` instead of `freq=1000`.

**Rejected:** keeping 1000 kHz. With the camera parked in recovery, hot-plug
reads and `-halt -coreReg` were reliable, but RAM downloads froze the ST-LINK
USB interface (`device not responding`, then `DEV_USB_COMM_ERR` until replug)
after roughly 30-70 KiB sent, on two different Mac ports. Splitting the 64 KiB
download into 4 KiB pieces did not help (failed on the ninth). At 200 kHz about
1.5 MB of RAM downloads and the full install passed with no libusb warning.
Cause not established; a hub and a newer ST-LINK firmware were not tried.

**Evidence:** `~/global-x-camera-installs/20261116-125222-144111` on that Mac
(`complete.json`, verified sector hashes 6ddf4499... / 206da4c0..., backup of the
D8 image 1a9278ab... / ed6d4169...). Knob behaviour, D8 latch and capture on
the r2 image were not checked in this session. `test_camera_transport` has two
path tests that fail on macOS (`/var` vs `/private/var`).

## 2026-11-16  Mac reproduces r2 byte-for-byte; installer gains a second pinned image

ST's macOS build of the same compiler (GNU Tools for STM32
12.3.rel1.20240612-1315, plugin `...gnu-tools-for-stm32.12.3.rel1.macos64_1.0.200.202406191456`
from ST's public STM32CubeIDE 1.16.0 update site, SHA-256 `c11d71cc...1bbb`
as published in that site's index) rebuilds r2 exactly: `package.py` on
unmodified source with the committed `2026-11-13-knob-controls` USB and capture
inputs, HAL v1.3.0 and the committed CMSIS gives sector0 `6ddf4499...` and
sector1 `206da4c0...`. Arm's stock 12.3.Rel1 does not (selector ~300 bytes
larger, hook one word over its slot). Only `package.py` is needed for a
controls-table change; the Windows-only `build.py` scripts are not.

The same build with the 1/8 s exposure table gives sector0 `dadacbe3...2595`,
sector1 `f07fa113...5506`, recovery prefix `0633756f...c783`. Against r2 it
differs in 148 bytes of sector1 (the 65-entry table and the 500000 -> 125000
literal) and 5 bytes of sector0 (boot-header checksum byte at 0x64 and the
4-byte word at hook offset 0x1b4). Nothing else changed; sizes are identical.

Installer: `--target eighth-second-2026-11-16` selects this image from
`assets/firmware-eighth-second`; the default stays r2. The image is added to
`camera_recovery.APPROVED` and `profiles.json` so a camera running it is
recognised and can be rolled back to r2. That allowlist says adding an image
needs review: the review here is the byte diff above, done on the Mac at the
camera owner's request, not an independent one.

Rejected: retargeting the installer's single pinned image (the original
installer would then not recognise the camera, leaving no rollback path).
Not done: release packaging, tag, README/profile wording, knob label.

## 2026-11-16  1/8 s image installed on hardware from the Mac

`camera_install.py --target eighth-second-2026-11-16` over r2 at 200 kHz:
backup matched r2 (`6ddf4499...` / `206da4c0...`), independent readbacks match
`dadacbe3...` / `f07fa113...`, the following 4096 bytes are unchanged, and
post-install UART recovery identified the new prefix. No libusb warnings.
Evidence is the installer's own log folder on the Mac
(`global-x-camera-installs/20261116-213908-892559`, not committed). Photos and
knob behaviour on this image were not checked in this entry.

## 2026-11-16  Third installer image: 1/8 s maximum with ASA fixed at 200

`--target asa200-eighth-second-2026-11-16` (assets in `firmware-asa200`):
sector0 `653b5b29...ed9b`, sector1 `5ac715ac...2ea5`, recovery prefix
`571ea294...03fc`, same compiler and committed inputs as the entries above.
Unlike the 1/8 s image this is a code change, not a table change: the selector
is 72 bytes shorter (7644), so most of sector1 differs and the hook's selector
length and checksum words change. Checked by host test and by disassembly of
`capture_controls_map` (stores gain code 16 and ASA 200 unconditionally); not
independently reviewed. Reason for the change is in `firmware/usb-ptp/NOTES.md`.

## 2026-11-16  ASA-200 image installed on hardware from the Mac

`camera_install.py --target asa200-eighth-second-2026-11-16` over the 1/8 s
image at 200 kHz: backup matched `dadacbe3...` / `f07fa113...`, independent
readbacks match `653b5b29...` / `5ac715ac...`, the following 4096 bytes are
unchanged, and post-install UART recovery identified the new prefix. Photos on
this image were not checked in this entry.

## 2026-11-20  Fourth installer image: exposure 1/6000-1/8 s with ASA fixed at 100

`--target fast-asa100-2026-11-20` (assets in `firmware-fast-asa100`): sector0
`32a29fb2...5e7a`, sector1 `26b3e31b...baae`, recovery prefix
`f9ded0b0...850a`, same compiler and committed inputs as the 2026-11-16
entries. Selector is 7644 bytes, as in the ASA-200 image; the new 65-entry
table is present in `selector.bin` and the disassembly stores ASA 100. Host
test passes; not independently reviewed. `camera_install.py --check` passes
for this target. The two `test_camera_transport` path failures on this Mac
(`/private/var` versus `/var`) are the same without this change. Reason for
the change is in `firmware/usb-ptp/NOTES.md`.

## 2026-11-21  1/6000 s, ASA-100 image installed with `--restart` after three power-on waits found no recovery park

`camera_install.py --target fast-asa100-2026-11-20 --restart` over the ASA-200
image at 200 kHz: readbacks match `32a29fb2...` / `26b3e31b...`, the following
4096 bytes are unchanged, and post-install UART recovery identified the new
prefix (installer log `global-x-camera-installs/20261121-013225-521720` on the
Mac, not committed). Photos on this image were not checked in this entry.

Three attempts without `--restart` (logs `20261120-232448-445382`,
`20261120-233533-945612`, `20261121-011719-711868`) each stopped after 600 s
with "Not a requested early recovery park" and wrote nothing. In the third the
user moved the selector to BATTERY and back to USB while the stream was armed
(Image Capture logged the camera removed 01:17:10 and added 01:17:31 local;
stream armed 01:17:20), yet every status read from 01:17:22 on succeeded and
returned the same record, state 2 / reason 0. On 2026-11-16 the same wait
showed `cube_timeout` until the switch reached USB. So on this day the MCU
stayed powered and readable with the selector on BATTERY and the ST-LINK
attached, and the selector did not produce a power-on reset. Why is not
established; the ST-LINK had been replugged into a different Mac port. The
first attempt's failure was put down to an early flip at the time; that
explanation is not supported by the third attempt.

## 2026-11-21  1/6000 s image withdrawn as a target; fifth image (1/8 s maximum, ASA 100) built and installed

`fast-asa100-2026-11-20` is removed from `TARGETS` and its sector files are
deleted; its entry stays in `APPROVED` and `profiles.json` (marked
superseded) so a camera carrying it is recognised and can be replaced. Reason
in `firmware/usb-ptp/NOTES.md` of this date.

`--target asa100-eighth-second-2026-11-21` (assets in `firmware-asa100`):
sector0 `95c65f79...99c3`, sector1 `17b5381b...0062`, recovery prefix
`55f69301...6785`. Host test passes, `--check` passes, not independently
reviewed. Installed with `--restart` over the 1/6000 s image at 200 kHz:
backup matched `32a29fb2...` / `26b3e31b...`, readbacks match, the following
4096 bytes are unchanged, post-install UART recovery identified the new prefix
(log `global-x-camera-installs/20261121-014418-738162`, not committed). Photos
on this image were not checked in this entry.

## 2026-11-21  Sixth installer image: 1/6000-1/8 s, ASA 100, with rebuilt capture receiver and USB app

`--target sixthousandth-asa100-2026-11-21` (assets in
`firmware-sixthousandth-asa100`): sector0 `98e1eb4e...c60d`, sector1
`27205e4e...fadf`, recovery prefix `509fd796...d2e5`. Unlike every earlier
image from this Mac it is not the 2026-11-13 capture and USB binaries with a
new selector: both were rebuilt from source with the exposure floor at 167 µs
(`firmware/usb-ptp/NOTES.md`, same date). Against the installed ASA-100 image
the 7160-byte prefix differs in 12 bytes: two receiver-CRC words and the
selector checksum word. Not independently reviewed. `--check` passes.

Installed with `--restart` over `asa100-eighth-second-2026-11-21` at 200 kHz:
backup matched `95c65f79...` / `17b5381b...`, readbacks match, the following
4096 bytes are unchanged, post-install UART recovery identified the new prefix
(log `global-x-camera-installs/20261121-021233-105583`, not committed). Photos
on this image were not checked in this entry.
