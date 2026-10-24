# NOTES bootstrap — October 24, 2026

The user requested the migration and delegated candidate selection without an
approval round. [Root NOTES.md](../NOTES.md) describes the append-only convention
and maps each decision to its owning folder. This is a historical-source review,
not a new hardware qualification. No instrument, firmware, SD contents, schematic,
related checkout or immutable measurement archive was changed.

## Curation and authority

Include explicit decisions that rejected an alternative, experimentally discovered
constraints likely to be forgotten, and conscious deferrals. Record why and the
actual rejected path, with local evidence and original decision date where known.
Every reconstructed entry identifies its provenance. Dates follow contemporaneous
records: some use local Eastern dates while detailed captures use UTC. Migration
date does not replace decision date.

Current behavior stays in README/specification; exact experiments stay in their
evidence archives. Routine pin tables, every firmware checkpoint, shopping lists,
transcripts and redundant summaries do not become new notes. One rationale has
one home; related folders link to it. Historical entries can be superseded by a
later entry, not silently rewritten. The first RAW format and its deliberate
replacement are both retained as an example.

Direct user choices establish intent; exact build/evidence records establish what
was implemented or tested. An assistant recommendation, imported component role,
order announcement or timing model is not a user selection or measured result.
Latest accepted direction takes precedence over older proposals. An unqualified
product requirement remains a requirement, not a claim that today's prototype
meets it. In particular, product retention/ECC/PTP policies are distinct from the
current experimental SD format and its unqualified arbitrary-power-loss behavior.

## Repository coverage

Reviewed the 119-commit project history through
`18299c29757c29ed587657f8cd2763d5dbbf9704`, including substantive commit bodies,
against the following source families. Reasons were checked against the owning
documentation and relevant implementation/evidence; this was not a rerun of
every archived test or a fresh electrical audit of every binary/PDF.

| Source family | Use in the bootstrap |
|---|---|
| Root README, AGENTS, spec, power and hardware/firmware interface | Source hierarchy, settled behavior versus installed experiments, cross-cutting workflow |
| `docs/decisions/` and consolidated review | Accepted/rejected product choices, NAND policy, fault handling, RAW and PNG evolution |
| `docs/power/`, `docs/prototype/`, `docs/manufacturing/`, storage comparison reports | Regulator/rail choices, leakage and isolation boundaries, optics, wiring, supply/assembly deferrals |
| `firmware/boot-timing/` and `firmware/capture-timing/` | ROM loading, cold-start measurement, recovery, PHY failures and rejected optimizations |
| `firmware/capture-packed/`, `capture-raw/`, `raw-slots/`, `sd-storage/` | Packing, buffer publication, transport ownership/security, format changes, completion and failed DMA sleep |
| `firmware/capture-sd/` and `png-encoder/` | Earlier PNG/FAT32 implementation, compression decisions, optional checks and Standby constraints |
| `hardware/reconstruction/`, `hardware/README.md`, design-review findings, reconstruction tools | Physical identity versus EDIF aliases, documented inferred endpoints, ERC/footprint limits, generator/history hazards |
| `imports/flux/2026-09-05/` and original audit | Historical hardware provenance and the absence of a recovered firmware/chat archive |
| Initial decision-review research archive | Earlier native/cloud chat evidence, source inventory and known missing Claude coverage |

The [initial review archive](../research_notes/Global%20X%20Camera%20decision%20review/README.md)
already preserves repository inventories, the four original Flux exports and
their audit, 19 native chat/subagent records, six substantive cloud conversations,
screened background, and October 12–13 consolidation evidence. Those records were
reused with their original dates and limitations, not overwritten with current
claims. Source PDFs support the recorded findings; no current stock, vendor
revision or new datasheet interpretation is asserted by this migration.

The pre-existing untracked `reports/Low power camera MCU alternatives.md` and its
`research_notes/Low power camera MCU alternatives/` sources were considered as
research context and left untouched/uncommitted. Their Alif/ESP32 suggestions do
not supersede STM32N6. The working-tree status is explicitly distinguished from
committed project evidence.

## Related chats

Used the app's project/thread listings and read tools, the existing portable
chat exports, and a read-only local thread index to find project and adjacent
conversations. The local query returned 226 metadata records. Of these, 138
available relevant native logs were parsed for user messages and final assistant
answers; 17 indexed rollout files were unavailable, seven records belonged to
unrelated chats/subagents, and 64 internal approval-review records were excluded.
Reasoning, system/developer instructions and tool output were not imported as
decision evidence. After inherited-message deduplication, the corpus had 953
messages, including 233 direct user messages from seven available top-level
camera conversations. The direct-user corpus was screened for missed decisions;
relevant final summaries were cross-checked against repository evidence.

The missing native files include the original September 5 root transcript; its
portable source copy and initial coverage audit remain available in the repo.
Parsing a log is not new verification of its engineering claims. Subagent
conclusions corroborate evidence; they are not independent user approvals.

| Conversation | Scope and disposition |
|---|---|
| **Consolidate project decisions**, `01a131cc-8e83-74b2-b473-d33f16f2559a` | Full available native user/final history plus current app read; product decisions, bench evolution, sensor and NAND choices. Later choices and evidence take precedence over earlier recommendations. |
| **Consolidate project decisions - SD card sidequest**, `01a15716-3ee1-7b01-9225-e85c60f21573` | Current conversation and available native history through this request; SD, PNG, low power, RAW, metadata and notes selection. |
| **Consolidate project decisions - remove 5v**, `01a1481f-598f-7542-930d-381adef2786f` | App's latest ten turns plus full available native history. Direct user statement at 2026-10-18 22:35:51 UTC: USB is not needed on battery power. Lower-voltage/custom-board and alternate-MCU research remains unselected. |
| **mechanical spring?**, `01a132e1-f117-75c0-990c-b9b09b8e610c` | Complete returned history and native record, distinguishing inherited context from three new research turns. Thinness, winding and spring/governor/generator explored; energy/capacitor estimates are not a qualified design. |
| **Explain SD block lifecycle**, `01a16e6a-bb9c-7060-b61c-14857d08ee58` | All six returned turns and native record. Logical blocks/FTL, erase versus discard, erased data value and pre-erase announcement constraints. Not evidence of the card's internal physical state. |
| Earlier shutter-energy/storage and PCBA branches, `01a07f5a-2a41-7b53-9287-ba5851c5f7f5` and `01a0eafd-e9c3-72a2-8ba2-d007afd9dc5d` | Available native histories plus initial portable exports; considered earlier alternatives and manufacturing recommendations without adopting them retrospectively. |
| [Compare SD Cards](https://chatgpt.com/c/6ad6749b-fed8-83ea-9d9f-433ae6ae2652) | Both turns. User prioritizes write speed and predictability, needs more than 1 GB, and does not prioritize read speed. Named cards and four-bit/50 MHz suggestions were not a qualified ranking or new hardware selection. |
| [NAND Failure Rates Tracking](https://chatgpt.com/c/6acf1b05-834c-83ea-bc62-025337d55fa9) | Complete one-turn discussion of historical Macronix NAND; corroborates bad-block/table concerns, not current Alliance geometry or a per-photo failure probability. |
| [ESP P4 Boot Time](https://chatgpt.com/c/6acd448f-ce58-83ea-b480-586df31b8561) | Complete one-turn research inquiry. Reported custom-boot timing is not a measured replacement-platform result for this camera. |
| [Review Project Sources](https://chatgpt.com/c/6acd3d37-72b4-83e9-acf3-c755b661a6e9), [VD5943 Prototyping Promodules](https://chatgpt.com/c/6acd261d-d2f0-83ea-bac0-a86e92a61bc2), prior flash/light-sensor/NAND/Rust discussions | Existing readable source copies and initial coverage register; explicit STM32N6 direction preserved, questions/recommendations kept distinct from accepted choices. |

Misfiled DWL stage/filesystem chats and an unrelated capacitor/audio inquiry were
screened out rather than treated as camera evidence. Full private conversations,
images and raw machine histories are not newly published. Relevant findings are
preserved in this coverage record and the linked notes.

One conflicting assistant summary said that the card stayed powered in Standby.
The circuit-derived [peripheral shutdown record](../firmware/capture-sd/low_power/peripherals.md)
and implementation show its VCC switches off while the MCU I/O bank remains
powered. The [owning notes](../firmware/capture-sd/NOTES.md) preserve the resulting
no-retained-pulls constraint; the stale summary was not promoted.

## Related repositories

Read the relevant histories, READMEs, bring-up/design reports and source records
from the two predecessor camera repos, plus their referenced vendor SDK. Exact
HEADs, dirty-state flags and 21 inspected file hashes are preserved in the
[source manifest](notes-bootstrap-sources-2026-10-24.json). These checkouts were
not modified, committed, cleaned or fetched.

| Repository | Inspected revision and scope |
|---|---|
| `D:/Github/CwtCam` | HEAD `e11a1fb7af3dbb057487290b750d169b784844a8`; six-commit history, no configured remote, modified/untracked later FSBL/timing research. STM32N6570-DK with IMX335 and display. |
| [VD56G3-HIMAX-Camera](https://github.com/bigjosh/VD56G3-HIMAX-Camera) | HEAD `97b36b9bf48cdab471fc222879d0acc89ddb0dfe`; four-commit history and newer dirty RAW10 reports/code. Those working-file findings cannot be cited as if all existed at HEAD. |
| [Seeed_Grove_Vision_AI_Module_V2](https://github.com/HimaxWiseEyePlus/Seeed_Grove_Vision_AI_Module_V2) | Pinned SDK HEAD `d3265e20d75fe20faccbf185d24454ad08b2fda8`; referenced README/FAQ and local VD56G3 experiment, not a new audit of the whole upstream SDK. |
| `D:/Github/notes-system` | Convention/bootstrap/template revision `bdf194057922f705b1bc12c506d59f2bdf91cd10`; user-delegated vetting replaces its normal owner review stop for this task. |

CwtCam illustrates why irrelevant demo initialization should be removed and the
real flash boot tested separately from RAM execution. Its reported 1057→99 ms
path ends at a complete IMX335 frame and starts in application code; it is not
this project's cold button/reset-to-exposure timing floor. Shortening a fixed
delay merely moved some waiting to frame completion. Its standalone header fault
and power-under-load failure support test methodology, not transplanting its
addresses, supply jumpers, sensor table or USB-current assumptions.

The Himax investigation retained standard packed RAW10 while advertising datatype
`0x2A` to its opaque-byte receiver. Direct 896×1364 capture was verified; its
full-width result used 44 sequential ROIs and can contain motion seams. Wider
stream corruption and a hypothesized downstream bandwidth limit were not solved
by the current N6 work. Slowing its MIPI stream also produced sensor overflow in
the tested mode. These are historical receiver-specific findings, not reasons
to replace the N6's independently qualified `0x30` opaque-byte path with Himax's
`0x2A` workaround, or adopt tiling. The reusable lesson is to
check transport, optical content and decoded output independently, retaining
the exact sensor/receiver/clock/memory configuration with each result.

## Claude and other coverage limits

The original [Claude/Flux audit](../research_notes/Global%20X%20Camera%20decision%20review/claude_sessions.md)
remains authoritative for its extensive October 12 search. This pass refreshed
the import-registry and project-directory checks and inspected predecessor
project metadata. No related imported transcript was identified by the project,
STM32N6, CwtCam, VD56G3 or Himax names. CwtCam's local `.claude` file contained
permissions, not conversation history. The initial generic **Import from
Claude** chat supplies no engineering archive. We did not discover or claim
access to an unlocated cloud archive, another device or another account.

The user previously accepted the unavailable Claude conversations as nonblocking.
Their absence from the checked stores does not prove they never existed. Related
repo artifacts can preserve useful Claude-era work without establishing the
missing conversation or its approvals. Missing logs, private captures and live
vendor availability were not reconstructed by guesswork.

## Validation and continuation

Validation passed for **94 entries in 13 NOTES files**, with chronological
headings and all four provenance fields. All **220 local links/anchors** and
**67 referenced project commits** resolved; whitespace checks passed. No firmware or hardware tests
are warranted for these documentation-only additions. Historical evidence and
the installed v18/card/bench checkpoint remain unchanged.

Future work reads the root and owning notes first, updates current behavior in
its normal documents, and appends a note only when there is a durable reason to
retain. The existing decision register remains the current policy index; this
migration does not reopen settled choices or finalize deferred implementation.
