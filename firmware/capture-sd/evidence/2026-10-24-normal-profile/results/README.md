# Compact awake qualification records

| Run | Firmware | Result |
| --- | --- | --- |
| [awake01](awake01/summary.json) | v62b | Capture and IMG00066.PNG readback passed; receiver proof was overwritten by the LED record after SAVE. Treat its intact timing fields as provisional evidence only. |
| [awake02](awake02/summary.json) | v64 | Corrected receiver proof remained valid after maintenance; capture, SAVE and IMG00067.PNG readback passed. |

Both saved 16-bit grayscale PNGs with `sBIT=10`. Host readback verified all PNG
chunk CRCs and all 1,527,680 pixels against each run's captured RAW10 samples
shifted left by six bits. Original `verified.json` files retain the complete PNG
and raw-frame SHA-256 values. Root also viewed IMG00066.PNG and reported a
discernible room scene. Photographs and raw frame bytes are deliberately absent.

Each run preserves its original directory names, exact maintenance report/card/
filesystem/trace binaries, CLI logs, capture proof and FAST snapshots, six
readback request/result records, phase digital edges, capture configuration and
the original failed strict-width decoder result. The pulse widths were not
qualified; any event labels inferred from source call order belong in separate
analysis. Awake completion is not shutdown or Standby, and the JS measurement
boundary excludes unresolved board bypass paths.

The original recording wrapper's pending qualification flags are unchanged.
Later strict maintenance, frame and PNG results are separate evidence, not
edits to those earlier records. See the [proof-address correction](../build/proof-address-correction.json)
for the v62b limitation.

Run `python verify_awake.py` from this directory to check every indexed file,
raw-report decoding, PNG verification metadata and contiguous readback coverage.
This does not decode the deliberately omitted photographs again. Each
`index.json` lists archived hashes and omitted files; large raw streams were not
re-read solely for archival hashing. Originals remain in the local bench folders.
