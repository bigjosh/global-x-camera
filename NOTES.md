# Notes

This file, and any `NOTES.md` deeper in the tree, records *why* this project
is the way it is: decisions, the alternatives they rejected, and constraints
learned the hard way. README and code describe the current state; these files
hold the reasoning. Entries are dated, appended in order and never rewritten;
a later entry supersedes an earlier one. A decision lives in the folder that
owns the code that would regress it; cross-cutting ones live here. Read the
relevant file before changing a folder, and append an entry when you reject an
alternative, learn a non-obvious constraint, or remove something. The entry
shape is a dated heading, then **Why**, **Rejected**, **Evidence**, plus
**Provenance** when reconstructed after the fact. Convention: the
`notes-system` repository, revision `bdf194057922f705b1bc12c506d59f2bdf91cd10`
at this bootstrap.

## Find the owning notes

| Area | Notes |
|---|---|
| Product preservation, retention, ECC, retrieval and storage policy | [Product decisions](docs/decisions/NOTES.md) |
| Battery, RUN/HOLD, rail sequencing and measurement boundaries | [Power](docs/power/NOTES.md) |
| Camera, optics, assembly, controls and storage wiring choices | [Prototype](docs/prototype/NOTES.md) |
| Recovered source, pin aliases, ERC and footprint limitations | [Hardware reconstruction](hardware/reconstruction/NOTES.md) |
| ROM loading, cold-boot evidence and NOR maintenance | [Boot timing](firmware/boot-timing/NOTES.md) |
| Sensor/PHY sequencing and autonomous recovery | [Capture timing](firmware/capture-timing/NOTES.md) |
| Packed sensor data and validation | [Packed capture](firmware/capture-packed/NOTES.md) |
| Current RAW streaming, publication and shutdown | [RAW capture](firmware/capture-raw/NOTES.md) |
| Exposure control ADC bring-up and input isolation | [Control diagnostic](firmware/control-smoke/NOTES.md) |
| On-media object format and host interpretation | [RAW slots](firmware/raw-slots/NOTES.md) |
| Native SD transport, DMA and card completion | [SD storage](firmware/sd-storage/NOTES.md) |
| USB mode selection, native PTP and transfer ownership | [USB photo access](firmware/usb-ptp/NOTES.md) |
| Release publication, immutable assets and install guidance | [Releases](release/NOTES.md) |
| Earlier PNG/FAT32 integration and low-power qualification | [Capture to SD](firmware/capture-sd/NOTES.md) |
| Encoder choices and rejected compression candidates | [PNG encoder](firmware/png-encoder/NOTES.md) |
| Native SD logic decoding and raw DAT0 busy timing | [Saleae SD analyzer](tools/saleae-sd-native/NOTES.md) |

The [bootstrap coverage record](docs/notes-bootstrap-2026-10-24.md) identifies
reviewed histories, related repos/chats, exclusions and gaps. Notes are curated
reasons, not another full transcript or a replacement for immutable evidence.

---

## 2026-10-12  Continue the STM32N6 design; the Himax project is historical research

**Why:** the user explicitly clarified that this project is the STM32N6 design and that Himax is abandoned. Related repos remain useful experimental evidence, but their board, sensor, receiver and boot paths differ. Their performance figures and register workarounds cannot silently become requirements or qualified results here.
**Rejected:** treating a similarly named camera repo as the active architecture; assuming the Himax RAW10 workaround or a Discovery/IMX335 timing result applies to this Nucleo/VD56G3. Later Alif/ESP32 research did not approve a platform switch.
**Evidence:** [direct clarification in Review Project Sources](research_notes/Global%20X%20Camera%20decision%20review/chat_sources/6acd3d37-72b4-83e9-acf3-c755b661a6e9.md); [D-01](docs/decisions/2026-10-13-project-baseline.md); [related-repo coverage](docs/notes-bootstrap-2026-10-24.md#related-repositories).
**Provenance:** reconstructed on 2026-10-24 from the explicit October 12 instruction. The user did not state a complete reason for abandoning Himax; predecessor constraints are context, not an invented explanation for that decision.

## 2026-10-13  Keep the repository sufficient to resume without the chat account

**Why:** the user asked to consolidate every decision and discovery into the repo, then explicitly requested initializing and publishing it. Later accepted decisions supersede proposals; historical imports, estimates and shopping suggestions must remain distinguishable from implementation and measurement. The repository is the durable record, while chats and Page copies are working sources.
**Rejected:** leaving rationale only in chat; interpreting a Flux component, recommendation or placed order as approval/receipt of every suggested part; treating missing Claude transcripts as recovered evidence. The user accepted that archive gap as nonblocking.
**Evidence:** commit `cf9302c9` and public-remote record `94611286`; [baseline source hierarchy](docs/decisions/2026-10-13-project-baseline.md); [review transcript](research_notes/Global%20X%20Camera%20decision%20review/chat_sources/2026-10-12-13-current-review.md); [Claude coverage](research_notes/Global%20X%20Camera%20decision%20review/claude_sessions.md).
**Provenance:** reconstructed on 2026-10-24 from explicit consolidation/publication instructions and the contemporaneous coverage record. No unavailable conversation has been attributed a decision.

## 2026-10-14  Start with CubeN6 C support and preserve the path to smaller bare-metal code

**Why:** vendor drivers provide a practical bring-up starting point, while startup latency and capture energy may justify LL/direct-register code and staged loading. The user accepted the starting point while explicitly retaining the option to switch to bare metal. Compare equivalent complete workloads before attributing savings to a framework change.
**Rejected:** a frozen HAL-only architecture, an assumed Rust/Embassy or RTOS commitment, or a wholesale rewrite merely because HAL exists. HAL does not itself require an RTOS; selected capture, storage and shutdown behavior still applies after optimization.
**Evidence:** commit `d0788825`; [D-37 and firmware starting point](docs/decisions/2026-10-13-project-baseline.md); specific measured loader and capture changes belong in [boot notes](firmware/boot-timing/NOTES.md) and [capture notes](firmware/capture-timing/NOTES.md).
**Provenance:** reconstructed on 2026-10-24 from the explicit October 14 approval and its documented scope, not inferred retrospectively from the current bare-metal experiments.

## 2026-10-16  Operate the shared bench through instrument APIs with explicit ownership

**Why:** the user requested API-only access to the JS110 and Logic Pro 8. Repeatable commands and saved traces support autonomous experiments, but multiple chats can share the same physical instruments. The JS110 permits one client; Logic 2 remains the Saleae automation backend. Ownership changes must preserve instrument settings and target power.
**Rejected:** GUI automation for these instruments, force-closing an application with possible unsaved data, or assuming a successful power command proves the rail changed. A stale chat checkpoint is not proof of current wiring or exclusive access. The user's later permission to overwrite this experimental DUT removes unnecessary approval stops; it does not establish another process is idle.
**Evidence:** commit `9c7cbdd7`; [bench APIs](firmware/boot-timing/README.md); [ownership and current checkpoint](AGENTS.md); [power-boundary notes](docs/power/NOTES.md). The October 24 user explicitly authorized clobbering experimental memory/flash/SD as needed.
**Provenance:** reconstructed on 2026-10-24 from the API-only request, later exclusive-use authorization and observed single-client/rail failures. Recovery and active-storage transaction guards have their specific homes in the firmware notes.

## 2026-10-24  Adopt append-only notes with one home for each durable reason

**Why:** the growing experiment history makes rejected approaches and hard-won constraints easy to lose among current-state descriptions. The user authorized this bootstrap and delegated candidate selection without an approval round. Notes preserve the reason and evidence at the owning folder; README/specification describe current behavior, and measurement archives retain exact results.
**Rejected:** copying every checkpoint into notes, rewriting historical evidence to match today's design, turning unapproved research into decisions, or duplicating the same rationale in several folders. Missing sources and unqualified results remain explicit rather than filled in by inference.
**Evidence:** this request in Consolidate project decisions - SD card sidequest, thread `01a15716-3ee1-7b01-9225-e85c60f21573`, 2026-10-24; [coverage and curation](docs/notes-bootstrap-2026-10-24.md); convention revision named above.
**Provenance:** recorded contemporaneously. Earlier entries were reconstructed from the cited records with user-delegated vetting; future changes append a later entry when superseding a decision.

## 2026-10-26  Preserve exact evidence bytes when committing measurement archives

**Why:** frozen experiment manifests bind hashes to source copies, operation records and instrument logs. The repository's normal LF text policy can change CRLF source copies when staging, invalidating those hashes on a fresh checkout even though the working archive verifies. Evidence-specific `-text` attributes preserve the recorded bytes; normal source and documentation retain their existing text policy.

**Rejected:** rewriting historical evidence hashes to accommodate normalization, claiming working-tree verification proves Git contains identical bytes, or disabling normalization for the whole repository.

**Evidence:** the scoped rules in [.gitattributes](.gitattributes), local archive attributes and SHA256SUMS manifests in [the active25MHz evidence](firmware/capture-raw/evidence/2026-10-26-sd25-active/README.md), and staged-blob comparison during the promotion commit.

## 2026-11-11  The custom PCB spin exists to execute every power-saving strategy

**Why:** asked what the next board spin is for, the user answered that its purpose is to execute all of the possible power-saving strategies, including power-efficient storage, probably raw NAND. The goal behind it is running from standard CR2032 cells, which the present Nucleo prototype cannot do. This sets the priority when choices conflict: the lowest-power arrangement wins over staying electrically close to the Nucleo that the firmware was developed on.
**Rejected:** a board that copies the Nucleo's rails and voltages to minimise firmware change, which the review had first recommended; treating the SD card as the storage for this spin's coin-cell path. Not decided here: the exact power tree, serial versus parallel NAND, the NAND part, or whether an SD footprint remains as a bring-up fallback.
**Evidence:** direct user reply, November 11, in the PCB readiness review; [punch-list items PL-02, PL-03 and PL-07](docs/review/2026-11-10-pcb-readiness-punch-list.md); [peak-power exploration](docs/power/custom-pcb-peak-power.md). No NAND firmware exists yet, and the exploration's figures are estimates, not measurements. No hardware, firmware or CAD change.

## 2026-11-11  Try DipTrace for the custom PCB

**Why:** asked how the design would be checked, the user answered that if at all possible they would love to do this board in DipTrace rather than KiCad, and that DipTrace is installed on their local machine. The recovered design and its tools are KiCad, and the review environment can run neither program, so the checking tool is whichever the user runs.
**Rejected:** nothing yet. KiCad is not ruled out; DipTrace is the preference if a workable exchange exists. DipTrace's documentation describes a "DipTrace XML" text format for import and export in all modules and publishes a PCB specification, but the review could not read it and no file has been exchanged, so feasibility is untested.
**Evidence:** direct user note, November 11, in the PCB readiness review; [punch-list item PL-05](docs/review/2026-11-10-pcb-readiness-punch-list.md). The format facts come from search summaries of DipTrace's site, not from the specification itself. No hardware, firmware or CAD change.


## 2026-11-14  Exempt immutable calibration/build evidence from whitespace lint

**Why:** the newly committed November 13 calibration and controls archives bind
hashes to exact CRLF source/log bytes, including vendor code. Normal Git
whitespace checking treats those preserved line endings as errors. Scoped
`-whitespace` attributes leave evidence bytes unchanged while current source
and documentation continue to receive normal checks.

**Rejected:** normalizing frozen archives or rewriting their hashes to satisfy
style checks; disabling whitespace checks for current source or the whole repo.

**Evidence:** `.gitattributes` scopes exactly the two new archives. The staged
blob audit validates every SHA256SUMS entry, independently of working files.

## 2026-11-25  PCB planning ignores pull request #1's firmware and installer changes

**Why:** in the open-questions review the user was shown pull request #1: a collaborator's Mac installer fixes, a 1/8 s exposure cap, a 1/6000 s floor and ASA fixed at 100, with the only hardware results so far for the r2 knob firmware. The user answered that the firmware and installer can be ignored for the board. The PCB requirements therefore stay as already settled: 0.5 s longest exposure and a manual gain control. The one point the user carried into PCB work is the control part: which thumbwheel replaces the hobby wheel, whose form the user likes.
**Rejected:** treating the pull request's 1/8 s cap or fixed ASA as PCB requirements; making its review or merge a precondition for schematic capture. Not decided here: whether the pull request is merged. Its bench observations that could touch copper have no established cause and are carried as cautions, not as facts about the new board: an ASA knob that reads only its end values (open-questions item 30), exposures above about 220 ms failing after the settings verify (set aside as firmware), and the MCU apparently staying powered on battery with the ST-LINK attached (items 9 and 14).
**Evidence:** direct user reply, November 25, in the open-questions review; pull request #1's description as read that day (head `fceb1456`); [open questions, item 1](docs/review/2026-11-25-open-questions.md). No hardware, firmware or CAD change.

## 2026-11-25  The first custom board is a beta: LiPo, SD card, KiCad, ST-LINK

**Why:** working through the open-questions list, the user redefined the first custom board as a beta and simplified it. In the user's words: KiCad "for simplicity"; "this beta will run ONLY on a small lipo"; "we are switching from NAND to SD"; unordered power-down is fine, "if it is good enough for the vendors own board it is good enough for us"; "no FRAM in this ver"; an ST-LINK connector on the parts side "will be the only way to program/debug"; two potentiometers, with the ASA steps made in software; and the boot flash is the reviewer's call: "pick an available part that will work". For this board these answers replace the November 11 purpose, which was to execute every power-saving strategy on coin cells with raw NAND and no fallback.
**Rejected:** DipTrace, the November 11 preference, whose file exchange was never tried; coin-cell holders, raw NAND and FRAM on this board; hardware that enforces ST's power-off order; any programming route other than the ST-LINK connector. Not decided here: the cell, the boot flash part, the regulators. The coin-cell and NAND work is not withdrawn as a later direction; the user said only what this beta carries.
**Evidence:** direct user replies, November 25, in the open-questions review ([status table](docs/review/2026-11-25-open-questions.md)). Details live with their owners: [power](docs/power/NOTES.md), [storage](docs/decisions/NOTES.md), [controls](docs/prototype/NOTES.md). No hardware, firmware or CAD change.
