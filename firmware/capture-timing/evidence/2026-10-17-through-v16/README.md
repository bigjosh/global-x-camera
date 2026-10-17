# Compact capture evidence through v16

This is an interim offline archive of 17 experiments performed on October 17, 2026. See [the report](../../experiments.md). It contains no images, full NOR dumps, large analog streams or Saleae session files.

- `captures/<experiment>/timing.json`: unchanged externally aligned phase/event result.
- `captures/<experiment>/ram/capture-result.json`: unchanged retrieval/checksum/status record; its visual field is intentionally not overwritten.
- `captures/<experiment>/logic/`: compact digital CSV, analyzer configuration and boot/rail summaries where present. Rail summaries preserve analysis but omit the large source analog streams, so those checks cannot be independently recalculated from this archive alone.
- `builds/`: exact original manifests. Original absolute paths and pre-test status are retained as provenance, not current runnable destinations.
- `source-objects/`: deduplicated source bytes whose hashes match the manifests. `source-provenance.json` maps original paths to objects and records the unavailable historical v3 capture source.
- `archive-index.json`: SHA-256, length and original path of every copied measurement/build/source file.
- `licenses/` and `license-index.json`: original vendor license notices and their hashes. Source headers retain copyright notices; generated driver variants retain the originating vendor's terms.
- `ledger.json`: derived compact timing/error/clock ledger; the first and subsequent exposure pulses are distinct.
- `visual-review.json`: separate assertions from the root bench controller's image inspection. v9-cold was not reviewed. The archiving agent did not inspect images.
- `archive-script.py`: record of the one-off offline extraction script. Its repository-root lookup assumes its original `tmp/capture-research/` location; it is retained for audit and must be adjusted before reuse elsewhere. It does not operate hardware.

The parent `.gitattributes` marks all evidence files `-text`, preserving raw byte hashes across checkout. The archive index intentionally covers copied evidence, while derived ledgers, assertions and this explanation are separate records.

For an independent compact ledger, use the repository's offline summarizer on explicitly chosen archived capture directories, for example:

```text
python firmware/capture-timing/summarize.py firmware/capture-timing/evidence/2026-10-17-through-v16/captures/v16-base-cold --json-out NEW_LEDGER.json
```

This verifies the association between the stored timing and RAM event sequences. It does not validate the visual assertion, infer missing error events, or establish a physical exposure-latency bound. Raw image hashes cannot be recomputed without the separately retained image data.
