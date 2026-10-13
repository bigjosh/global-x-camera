# Decision review research archive

This directory preserves the **initial October 12, 2026 source audit**, before the subsequent prototype decisions made during the consolidation discussion. It is supporting evidence, not the current project specification or decision queue. The project repository is the source of truth: start with the [current specification](../../spec.md), [power implementation](../../power.md), [hardware and firmware contract](../../docs/hardware-firmware-interface.md), and [maintained consolidated review](../../reports/Global%20X%20Camera%20decision%20review.md).

## What each record establishes

| Record | Scope and use |
| --- | --- |
| [repository.md](repository.md) | Initial review of the repository corpus and its contradictory statuses. Interpret “current,” candidate rankings and open questions as of that audit, before later approvals. |
| [project_chats.md](project_chats.md) and [session manifest](project_chat_coverage.csv) | Prior-session evidence located for the initial review: 19 native records and six substantive cloud conversations, plus screened background. They do not include the later decisions made within the consolidation conversation. |
| [claude_sessions.md](claude_sessions.md) and [coverage record](claude_flux_coverage.json) | Searches for relevant Claude transcripts and inspection of the 11 Flux import files. No project Claude transcript was located in the checked stores; this remains a coverage limit, not a blocker. |
| [report-page.md](report-page.md) | **Original report body snapshot**, preserved before the discussion changed the prototype baseline. Despite its filename, it is not a synchronized mirror of the current Page or report. Do not reuse its VD55G0 recommendation or unresolved-question list as current decisions. |
| [current-cad-evidence.json](current-cad-evidence.json) and [exported netlist](current-schematic-netlist.xml) | October 12 connectivity/value comparison showing that the then-current schematic matched the September review baseline. This is not a fresh ERC, board test, fabrication signoff or a claim that all later edits will match. |
| [file manifest](repository-file-manifest.json), [PDF index](repository-pdf-index.json), [JSON index](repository-json-index.json), [script index](repository-script-index.json) | Inventories of the source corpus at audit time, excluding new research/report outputs. Counts and hashes are historical snapshots, not a live index. |
| [Flux component properties](flux_native_roles.json) | Extracted historical component rationale; it does not establish user approval or working firmware. |
| [chat_sources](chat_sources) | Local readable session exports plus catalog metadata. These make the original decision evidence available without relying solely on external conversation links or a specific computer's session store. |
| [October 12–13 review evidence](chat_sources/2026-10-12-13-current-review.md) and [export manifest](chat_sources/2026-10-12-13-current-review.json) | User messages and assistant final answers from the current review, added during October 13 consolidation. The [decision register](../../docs/decisions/2026-10-13-project-baseline.md) identifies which proposals became accepted decisions. |

## Reading historical claims

The initial audit correctly distinguished the recovered VD55G0 circuit from unimplemented candidates. Later decisions selected CAM-6G3-073CLR/VD56G3, LTC3621, a 200-photo minimum, an exposure-start deadline and additional behavior; see the maintained documents above for the complete current set. Leave the original evidence intact and record accepted changes in maintained project documents rather than rewriting history.

Some source excerpts and audit links retain absolute paths or original session line numbers as provenance. The readable copies in `chat_sources/` are the portable navigation route; original paths do not need to exist on another machine for those copies to be useful. Vendor observations, stock snapshots and calculations retain their original dates and assumptions. None of this archive demonstrates measured prototype performance.
