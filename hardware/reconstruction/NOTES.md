# Hardware reconstruction notes

## 2026-09-05  Resolve physical pins from native identities and geometry, not EDIF suffixes

**Why:** duplicate logical names produced unstable EDIF aliases at J3 and LED1. Native terminal UUIDs, canonical anchors and independently matched IPC copper coordinates establish the physical map. This disproved an apparent LED polarity reversal; blindly interpreting alias suffixes would change valid connectivity. Native route fragments alone did not establish the compiled circuit either.
**Rejected:** suffix-as-pin-number mapping, generic native `Net N` fragments as authoritative nets, or treating the camera module as an additional host-PCB component. CAM1 is external; the source and host terminal counts deliberately differ.
**Evidence:** [physical reconciliation](connectivity-evidence.md); [source export audit](../../imports/flux/2026-09-05/export-audit.json); [reconciler](../../tools/reconcile_flux_connectivity.py); initial project commit `cf9302c9` preserves the earlier work.
**Provenance:** reconstructed on 2026-10-24 from the September 5 reconciliation record. The date is the documented recovery date, not the later root-repo commit date.

## 2026-09-05  Keep inferred additions separate from recovered connectivity

**Why:** three optional DNP switch endpoints had design intent but no compiled connection evidence. Their assignments were explicit reconstruction choices. Connector/module ground contacts 31–34 were added using physical footprint and camera documentation. Keeping the unchanged source map separate from the drawn map makes intentional additions auditable.
**Rejected:** claiming every schematic endpoint was recovered unchanged, or silently inferring optional-switch pin assignments from symmetric contacts. Later selected parts and circuit corrections must be deliberate revisions, not backdated reconstruction facts.
**Evidence:** [explicit reconstruction decisions](README.md#explicit-reconstruction-decisions); [source map](connectivity.json); [drawn map](schematic-connectivity.json); [enumerated additions](reconstruction-decisions.json); commit `cf9302c9`.
**Provenance:** reconstructed on 2026-10-24 from the September 5 decision/evidence files. These were documented engineering reconstruction choices, not separate user circuit approvals.

## 2026-09-05  Clean ERC and loadable footprints are recovery checks, not fabrication approval

**Why:** ERC needed correct electrical modeling of internally common outputs, address-mode pins and passive discharge paths. Power flags declare intended sources but do not prove rail sequencing or capacity. Footprint loading and matching pad numbers likewise cannot validate land geometry, orientation, mask/paste or assembly suitability; the review still found design and footprint defects.
**Rejected:** changing wires or disabling checks merely to silence ERC, accepting the J3 cached lands without comparing the manufacturer drawing, converting U7 mask/paste apertures into copper, or inferring a routed/manufacturable PCB from zero ERC violations.
**Evidence:** [ERC modeling and remaining work](README.md#erc-modeling); [footprint coverage](footprint-load-validation.md); [47-item design review](../../docs/DESIGN-REVIEW.md); [implementation status](../README.md); commit `cf9302c9`.
**Provenance:** reconstructed on 2026-10-24 from the original modeling rationale and explicit validation limits. No new ERC, routing or manufacturing qualification was performed in the notes migration.

## 2026-09-05  Rebuild missing U8 geometry from terminal identity and the solder-pad view

**Why:** U8 lacked an embedded footprint payload. Its native effective pads and IPC positions agreed with the manufacturer's recommended lands after converting native `(x,y)` to KiCad `(x,-y)`. The nearby package drawing is a bottom view and would mirror a top-side footprint if copied directly. Pin 1 must remain even though CLKOUT is electrically unused.
**Rejected:** using the bottom-view package picture as the land pattern, inferring pin numbers from `padN` labels, dropping an NC pad, or retaining source-machine-only 3D paths in portable libraries. Courtyard and marker additions remain reconstruction choices.
**Evidence:** [U8 construction and source pointers](generated-footprints/README.md); [geometry checks](generated-footprints/U8-evidence.json); [portable library record](README.md#libraries-and-remaining-work); commit `cf9302c9`.
**Provenance:** reconstructed on 2026-10-24 from the September 5 pad/datasheet comparison; fabrication-rule validation remains separate.

## 2026-10-13  Preserve editor history and manual edits independently of regeneration

**Why:** the original root folder had no Git repository, but KiCad had its own nested save history. A verified complete bundle preserves that evidence without replacing the working design. Reconstruction scripts overwrite generated schematic/library files, so subsequent manual changes must be preserved before intentionally rerunning them.
**Rejected:** treating editor saves as prior project-wide commits, importing them over the current files merely to inspect history, or assuming generator reproducibility makes manual edits disposable.
**Evidence:** [portable save history](kicad-save-history.md); [reproduction behavior](README.md#reproduction); [hardware workflow](../README.md); commit `cf9302c9`.
**Provenance:** reconstructed on 2026-10-24 from the consolidation and existing generator warnings. The bundle remains historical evidence; no schematic regeneration or history rewrite occurred during this migration.
