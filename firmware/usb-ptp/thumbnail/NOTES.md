# Thumbnail decisions

## 2026-11-08  Prepare fixed-size BMP thumbnails pending native PTP qualification

**Why:** a fixed-size generated preview keeps ObjectInfo sizes deterministic,
needs no additional stored photo or encoder dependency, and can stream from
the current whole-image RAM snapshot. The root requested this BMP experiment
while bringing up GetThumb. Local Windows WIC can decode it, but that alone
does not establish WPD's PTP thumbnail acceptance.

**Rejected:** advertising a thumbnail before its byte representation exists;
creating duplicate stored images just for previews; assuming WIC codec support
proves Explorer/Photos behavior; asserting an unverified JPEG-only requirement.

**Evidence:** `thumbnail_bmp.c/.h`, four passing offline tests in
`test_thumbnail.py`, and primary source links in `README.md` and
`../host/protocol-review.md`. The USB core can retain zero thumbnail fields and
NoThumbnailPresent while the optional candidate remains unqualified.

## 2026-11-08  Enable generated BMP thumbnails after native WPD retrieval passes

**Why:** both the RAM trial and final persistent USB firmware returned the
59,958-byte preview through Windows' standard thumbnail resource. The same
fresh whole-photo snapshot policy applies to thumbnails and full downloads.

**Rejected:** adding a stored duplicate preview or a JPEG dependency before
the native host needs it. WPD retrieval does not establish every photo app's
display behavior, so that broader claim remains unqualified.

**Evidence:** `thumb03-oB0.jsonl` and `thumb08-new.jsonl` in the November 8
[USB evidence](../evidence/2026-11-08-native-ptp/README.md); local BMP/WIC checks.
