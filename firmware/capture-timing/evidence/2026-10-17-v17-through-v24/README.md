# Compact capture evidence: v17 through v24

This checkpoint archives 11 additional autonomous cold-start experiments performed on October 17, 2026. It supplements [the through-v16 evidence](../2026-10-17-through-v16/README.md); see [the consolidated experiment report](../../experiments.md). Hardware execution and visual review belong to the root bench controller. Archive preparation was offline.

The archive includes unchanged timing/result JSON, compact digital traces, capture settings, rail-validation summaries, small RAM status/event records, programming-verification metadata, build manifests and hash-matched source snapshots. It excludes images, full NOR dumps, large analog streams and Saleae session files.

- `ledger.json` derives phase times and distinguishes first and later strobes. It does not replace raw evidence.
- `captures/<experiment>/timing.json` and `ram/capture-result.json` retain original bytes and visual-status fields.
- `captures/<experiment>/logic/` preserves digital edges, analyzer configuration and available rail summaries. Large analog streams are omitted, so the three-rail discharge calculation cannot be independently repeated from this compact archive alone.
- `captures/<experiment>/cycle/` preserves the programmed-sector SHA-256 and byte-for-byte readback verification, plus maintenance and NOR preflight results where available. No NOR image is included.
- `builds/` retains original manifests, including pre-execution `hardware_status: untested`. The captures provide subsequent test evidence.
- `source-objects/` deduplicates source bytes by SHA-256. `source-provenance.json` associates each build with its exact available source; a mismatch is recorded rather than silently substituted.
- `visual-review.json` records separate root-controller assertions that the LED grid is discernible. The archive author did not inspect these images, and the raw result's earlier pending-review field remains untouched.
- `licenses/` and `license-index.json` preserve the applicable vendor notices.
- `archive-index.json` hashes copied evidence. Derived records and this explanation remain separate from that index.
- `archive-script.py` is the offline extraction script. Its root lookup matches this archived location; it requires the original ignored experiment directories to run again and refuses differing overwrites.

The parent `.gitattributes` marks evidence files `-text` to preserve hashes across checkouts. All included results remain RAW8 timing diagnostics; this checkpoint does not establish the final RAW10/PNG16 path, production worst-case timing, or absence of the recorded startup D-PHY state-sequence error.
