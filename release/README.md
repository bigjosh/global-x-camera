# Firmware releases

The current firmware release is
[knobs-2026-11-14-r2](https://github.com/bigjosh/global-x-camera/releases/tag/knobs-2026-11-14-r2).

For a clean Mac, use the **Quick Install Instructions** at the top of the live
release, maintained in
[CURRENT_RELEASE_NOTES.md](knobs-2026-11-14-r2/CURRENT_RELEASE_NOTES.md).
The [guided installer](installer/README.md) uses the existing UART recovery
path with boot jumpers untouched. It includes the pinned RAM flash helpers and
firmware; no repository checkout or compiler is needed. Two USB cables connect
CN10 for programming and CN8 for power, with the prototype selector on USB
throughout programming. The guide explains the initial switch transition.
The portable Mac path remains offline-tested pending a physical trial.

The tag, firmware, ZIP, attached `RELEASE_NOTES.md`, `INSTALL.md`, and original
checksum lists remain the publication snapshot. Do not change those files to
refresh the live release description; the checksums must continue to identify
the actual downloads. `PUBLICATION.json` records that original publication.
Later documentation-only updates are recorded separately; they do not establish
installation or hardware qualification.

Before a notes-only update, compare GitHub's current body with the last known
body and preserve any concurrent changes. After updating, read it back and
verify that the release tag and every existing asset's ID, size and digest
remain unchanged. Firmware publication still follows [NOTES.md](NOTES.md),
`publish.py`, and the explicit request/manual workflow; do not enable that
workflow merely to change release text.
