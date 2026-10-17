# Receiver PHY sequencing diagnostic — failed trial checkpoint

Later evidence: [core recovery and guarded v30d comparison](../2026-10-17-v30d-phy-sequence/README.md) succeeded in restoring debugger access and testing both variants. The pending statements below describe this earlier immutable checkpoint.

This archive preserves the actual early v30b trial, its second cold-cycle recovery observation, and the unflashed guarded v30d candidate pair. **Neither hardware run produced a readable RAM event dump, validated PHY snapshot, or image.** It does not establish whether delayed receiver release resolves the original D-PHY error. Board recovery and final bench validation remain pending with the root bench owner; this checkpoint does not claim restoration.

The installed early v30b sector was verified byte-for-byte before the first cycle: 65,536 bytes, SHA-256 `ca5352274f193613707a71180e230f5a62d280b9a62c2122600bbef49809efd4`. Both completed Logic exports contain **24 PE0 transitions** after NRST release. Their order is consistent with prefix execution through receiver handoff event 207. Because the core could not be read, those event identities are a source-order inference rather than a match against a RAM event buffer. Offline analysis of the existing analog exports validates discharge/restoration of the three measured rails; this is not proof of all internal MCU supplies or successful boot.

Source review identifies the next intended operation as `late_init` snapshot 299, which attempted to read CSI while its peripheral reset remained asserted. That is the leading diagnostic-stall explanation, not a directly captured bus fault or a finding about sensor signaling. The guarded v30d pair avoids access to reset/clock-disabled CSI and was compiled and checked offline. Its manifests and exact sources are included as **unflashed candidates**, separately from the programmed v30b build.

Recovery logs preserve one successful AP2 initialization and RCC reset-register read after a reset sequence. Later accesses failed, and the second cold cycle's AP2 initialization returned `0x05` rather than success. Raw buffers accompanying unsuccessful status replies must not be decoded as target memory. No successful core recovery is claimed in these records.

The immutable [configuration](archive-config.json) records the UTC evidence checkpoint and explicit failed outcomes. The [ledger](ledger.json) intentionally contains null capture timing summaries; the external-only edge/rail analyses live under each capture as `offline-failure-summary.json`. Images and visual-success assertions are absent. The archive index verifies 181 files/references totaling 1,616,089 bytes, with all declared build sources recovered exactly. Full analog exports and NOR readback remain local; their hashes or byte-for-byte verification records are retained. Later recovery or a successful A/B comparison must be added as a separate evidence checkpoint rather than rewriting these bytes.

## Archival tool

`archive-script.py` is offline-only. It accepts an explicit JSON configuration and validates all selected inputs before publishing. Without `--write`, it validates and prints the plan without creating archival records. With `--write`, it creates files exclusively and refuses to overwrite any different bytes. Repeat publication of identical bytes is permitted.

Configuration schema:

```json
{
  "schema": 1,
  "date": "2026-10-17",
  "scope": "Describe only experiments actually recorded.",
  "builds": [
    {"id": "receiver-id", "directory": "tmp/bringup/ACTUAL-BUILD/receiver"},
    {"id": "prefix-id", "directory": "tmp/bringup/ACTUAL-BUILD/staged"}
  ],
  "captures": [
    {
      "id": "actual-capture-id",
      "directory": "tmp/bringup/ACTUAL-CYCLE/cold",
      "receiver_build": "receiver-id",
      "prefix_build": "prefix-id",
      "programming_cycle_directory": "tmp/bringup/ACTUAL-CYCLE",
      "outcome": "failed",
      "outcome_note": "Bench owner's actual finding; not inferred from file presence."
    }
  ],
  "extra_files": []
}
```

Paths are repository-relative or absolute within the repository. Each capture's explicit outcome is `completed`, `failed`, or `partial`. A completed entry requires an intact completed frame, matched timing/RAM events, passing rail validation, matching receiver/prefix manifests, and full byte-for-byte programming verification. A repeat capture can reference the earlier programming cycle that installed its image. An optional `logic_directory` selects a standalone Logic export. Failed or partial entries preserve whatever records actually exist, with missing timing or verification explicitly reported; they do not acquire invented timing or visual success.

An optional capture `visual_review` object must contain `status`, `reviewer`, and `provenance`, supplied explicitly by the person who viewed the image. The unchanged RAM result is preserved and hashed separately. Without this object, the archive records that no visual assertion was supplied. `extra_files` entries use `source` and `archive` fields; these are copied beneath `extra/` and can retain final power-release or analysis records.

The archive retains exact compact RAM dumps, including the PHY status ring, event/error buffers, sensor/memory status and traces; raw result JSON; digital edges and configuration; rail-validation records; programming, maintenance and verification JSON/logs; and build manifests. Frame pixels, full NOR dumps, analog streams and Saleae sessions are excluded. Sources are content-addressed and verified against each manifest. Existing exact source objects are referenced from previous evidence folders where possible, including historical bytes whose working copy has since changed. Missing historical sources are explicitly identified. Vendor license records are retained.

`archive-index.json` hashes every archived or referenced input and every derived ledger/provenance/review record except itself. This README remains outside that immutable index so the interpretation can link later evidence without changing the archived checkpoint. Run the repository's `verify_evidence.py` after publication.
