# Native Flux recovery assessment

The native export recovers the physical pin/ball map, embedded footprint sources, individual component properties, provisional placement, schematic symbol placement, and board correction rules that the EDIF export omitted. It is a useful source for reconstruction; the embedded library data has not yet been checked against every manufacturer drawing.

Source: `bigjosh-global-x-camera.flx`, SHA-256 `6da7be0451f25cee64d67e8072e4fb0b201687bf9c56cfb6292dd439a3d16aac`. This assessment does not modify that file or produce a KiCad conversion. [native-inventory.json](native-inventory.json) contains the extracted evidence, and [inventory_native.py](inventory_native.py) reproduces it.

## Coverage

| Data | Native export | Earlier EDIF/BOM |
| --- | --- | --- |
| Component instances | 148, all with cached part data | 146 EDIF instances; SW2/SW3 omitted |
| Terminals | 729; every terminal has a pin number; no duplicate pin numbers within a component | Logical port names, without package-number properties |
| Footprints | 147 board footprint instances; 24 unique embedded footprint payloads | Not included |
| Board data | 1,889 nodes; 699 mapped pad nodes; 10 board rule sets | Not included |
| Component values | Individual value, voltage rating, package, role, and exclusion properties | Grouped BOM merges several differing per-instance properties |
| Explicit no-connect records | 187 | Not explicitly preserved as no-connect intent |
| Placement | `symbol_placements.MAIN` and PCB position/rotation rules | No schematic/PCB geometry |
| PCB routes | `routes` is empty; 1,131 schematic-style route vertices exist | Connectivity only |

CAM1 is the one component with no board element/footprint instance; its 30 logical terminals remain in the native data. This accounts for 729 logical terminals versus 699 PCB terminal-pad nodes.

## Prioritized recovery examples

**U1:** all 264 native terminals have ball numbers, and the embedded BGA footprint has 264 numbered pads. Examples: `CSI_CKP=T3`, `CSI_CKN=U3`, `CSI_D0P=T5`, `CSI_D0N=U5`, `CSI_D1P=T4`, `CSI_D1N=U4`, `VDDCSI=R4`, `CSI_REXT=P5`. The raw footprint is a 0.8 mm grid; pad A1 is centered at (-6.4, -6.4) mm and is a 0.394 mm diameter circle. These are recovered source values, not a completed footprint signoff.

**U7:** `EN=1`, `PG=2`, `FB=3`, `GND=4`, `SW=5`, `VIN=6`. The embedded KiCad source has 15 pad records: six numbered electrical pads plus nine `~` records for separate mask/paste shapes. The native board has a correction rule named **U7 remove defective duplicate copper** disabling nine imported nonterminal nodes. Preserve the distinction between the original mask/paste-only shapes and Flux's corrected board representation; do not treat the cached source as the entire effective board footprint.

**U10:** `OUT=1`, `GND=2`, `EN=3`, `IN=4`, and the second GND/exposed pad is `5`. The embedded source retains custom polygon lands and a 0.52 mm square pad 5 rotated 135 degrees. Two board rule sets, **U10 XDFN pins 1 and 3 exact copper** and **U10 XDFN pins 2 and 4 exact copper**, preserve the corrective SVG contours and 0.26 by 0.39 mm rule dimensions. An importer must apply these board overrides as well as the source footprint.

**J3:** all 30 terminal names are `~`, but each terminal UUID has an unambiguous `pin_number` from 1 through 30. Thus the native data resolves the ambiguity of the repeated names in EDIF. The embedded `CONN30_HIR` source has 34 numbered pads: signal pads 1–30 and four additional copper mounting pads 31–34. Those mounting pads have no logical connector terminal and need explicit handling. Raw example geometry: pin 1 at (2.45, 0.7468) mm with size 0.127 by 1.1176 mm; row pitch along X is 0.35 mm. These dimensions should be checked against the selected Hirose drawing before use.

**D3:** native terminals explicitly map logical `1` to physical pad 1 and logical `2` to pad 2. The instance's `Role Details` says “Anode to latch pull-down, cathode to shutter sense node”. The footprint places pad 1 beside its cathode-side silk bar. Combined with the earlier EDIF connections, the recovered intent is **pad 1 = cathode = SHUTTER_SENSE; pad 2 = anode = LATCH_PULLDOWN**. The native record therefore resolves the earlier EDIF-only polarity ambiguity.

**SW2/SW3:** both exist with `B3U-3000P`, two physical pin numbers, source footprints, placements, and `Exclude from BOM=true`. SW2's role is **DNP Boot Switch**, with “Optional BOOT0-to-1V8 SPST footprint for recovery.” SW3 is **DNP Reset Switch**, with “Optional NRST-to-GND SPST footprint.” These role strings document intended connectivity; their native fragmented nets still need reconciliation before producing an authoritative connectivity export.

**Per-instance values:** C1 is 10 uF, 25 V, 0603; C10 is 10 uF, 6.3 V, 0603. Their individual records remove the ambiguity of the combined BOM row. Similar individual resistor/capacitor values and package selections survive throughout the export.

## Connectivity caveat

The native `nets` object contains **544 single-pin records**, only 81 of which have a nonempty `canonicalName`. The other 463 have generic names such as `Net 104`. These are not 544 verified electrical networks. The old EDIF contains 81 multi-pin nets and 538 endpoints. A simple union of native route-vertex connections does not recover the EDIF grouping, so this assessment deliberately retains native fragment records without guessing how to merge them.

Two native net fragments also have explicit no-connect markers: U1 PH9/D8 and U8 CLKOUT/1. Excluding those leaves 542 endpoint records, numerically equal to the EDIF's 538 plus the four optional-switch terminals. This is a count consistency observation, not proof that the native net connectivity matches EDIF. Use the original EDIF or a verified IPC-2581 export as the connectivity reference while reconciling native fragmentation.

## Source paths and import implications

- Physical mapping: `/elements/<element UUID>/part_version_data_cache/terminals/<terminal UUID>/pin_number`.
- Per-instance values: `/elements/<element UUID>/properties`; use these rather than cached library defaults.
- Terminal electrical types and duplicate pin-number check: `/subDocumentData/elements/<element UUID>__<terminal UUID>/properties`. All 729 repeated pin-number fields agree with the cached terminal mapping. Types such as U7 PG `openCollector` and J3 `passive` are present.
- Original footprint text: `/elements/<element UUID>/part_version_data_cache/pcbLayoutNodes/<footprint UUID>/pcbNodeRuleSet/asset/payloadAsBase64`. Decode as UTF-8 KiCad footprint text. Some embedded 3D model references are source-machine paths; their presence does not establish that the corresponding model is locally available.
- Board placement and effective overrides: `/pcbLayoutNodes` and `/pcbLayoutRuleSets`. Selector-based rules must be resolved; extracting only footprint payloads loses corrections.
- Schematic symbol locations: `/elements/<element UUID>/symbol_placements/MAIN`; the separate `diagram_position` entries are zero and should not be treated as final positions.
- Board shape/stackup: the single layout node specifies 85.6 by 53.98 mm, 3.18 mm corner radius, and an embedded custom four-layer stack. The decoded stack is included in the inventory; its label and constraints explicitly identify it as provisional.

The recovered data supports a hardware-first schematic/PCB reconstruction. Firmware integration is not a prerequisite for recovering the electrical and physical design, although named signal ownership and boot/debug intent should be retained.
