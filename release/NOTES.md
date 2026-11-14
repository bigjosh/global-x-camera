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
