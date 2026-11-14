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
