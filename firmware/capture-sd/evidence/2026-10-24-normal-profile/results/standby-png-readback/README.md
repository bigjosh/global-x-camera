# Post-Standby readback

The frozen read-only RAM bridge retrieved IMG00068.PNG (the v65 save before its shutdown refusal), IMG00069.PNG through IMG00071.PNG (the three v66c qualification cycles), and the original IMG00001.PNG. The original [verification](verified.json) records valid PNG chunk CRCs, complete independent decoding, 1120 × 1364 grayscale 16-bit pixels, sBIT=10, and left-aligned 10-bit samples. IMG1 remains byte-identical to its previously recorded SHA-256. All 27 READ requests report zero card writes and finish with the controller deinitialized and media idle.

The captured RAW buffers were lost on Standby. These files therefore have **no exact sensor-sample comparison**; structural decoding and dynamic range are narrower evidence. The hardware owner additionally viewed IMG71 and reported a discernible brick wall and monitors. Earlier pending-image notes in the v65 refusal and standby02–04 records are superseded by this readback; the original records remain unchanged.

This archive contains compact guards, result structures, CLI logs, original verification metadata, and a hash index. It intentionally omits the images and SD read payloads. Run `python ../verify_readback.py` to replay archive identities, READ-only requests, raw report bindings, contiguous chunk coverage, and the preserved IMG1 hash claim. It cannot rerun image decoding without the omitted pixels.
