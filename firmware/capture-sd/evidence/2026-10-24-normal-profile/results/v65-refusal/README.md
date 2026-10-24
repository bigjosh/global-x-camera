# v65 completion refusal

v65 saved IMG00068.PNG successfully and reached an exact idle failure park.
The late loader then rejected the new SAVE report schema before reading the
late shutdown module: `LPL1 state=3, reason=2`, zero bytes loaded and zero CRC.
This run did **not** enter Standby. Uninitialized LPM bytes must not be read as
entry evidence.

The [summary](summary.json), original failed cycle status, raw proofs and CLI
records are retained. Root verified the precise failure park, storage idle and
XSPI idle before the subsequent UART reset. That reset reached the exact early
recovery park; readback confirmed the v65 NOR sector was unchanged. The original
strict pulse-width decoder failure is preserved as well.

This archive makes no host PNG readback claim for IMG00068.PNG. Later readback
can be appended separately. See the [schema-review correction](../../build/reviews/late-schema-review-correction.json)
and the [v66c build addendum](../../build/v66-addendum.md). Run
`python verify_installation.py` from the parent results directory to replay the
compact identity/proof checks.
