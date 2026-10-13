# Schematic reconstruction record

> **Historical reconstruction record:** the validation below establishes recovery of the September source circuit, not correctness of the selected October prototype. Later CAM-6G3-073CLR/VD56G3 and LTC3621 decisions are recorded in the [current specification](../../spec.md); the unchanged schematic and outstanding corrections are summarized in the [hardware index](../README.md). Preserve this record as provenance when implementing intentional changes.

Built 2026-09-05 with KiCad 10.0.6 from the unchanged [Flux snapshot](../../imports/flux/2026-09-05/README.md). The editable project is [global-x-camera.kicad_pro](../kicad/global-x-camera.kicad_pro); the complete [PDF](../kicad/global-x-camera.pdf) contains 16 functional sheets. Global labels carry named connections between sheets. U1 is split into functional units while retaining every physical ball number.

## Validation

| Check | Result |
| --- | --- |
| Source connectivity reconciliation | 729 native terminals accounted for; all 518 connected host pad locations independently agree with IPC geometry. |
| Reconstructed KiCad netlist | 148 components, 737 terminals, 550 connected endpoints, 187 isolated no-connects, 81 named nets. All 539 directly recovered connected endpoints preserved. |
| Component values | All 148 values checked, including Flux's separately stored engineering units. |
| KiCad ERC | Zero violations. No global check disabling or excluded findings. |
| Footprint load/pin coverage | All 147 footprints load; 703 host copper pads match 703 expected pins. Five NPTH holes and nine mask/paste-only records correctly excluded from electrical pin counts. |
| MCU package mapping | All 264 balls agree with manufacturer DS14791 Figure 13. |
| PDF review | All sheets rendered and visually reviewed; title-block overflow and lost unit suffixes corrected. |

Evidence: [validation.json](validation.json), [erc.json](erc.json), [connectivity-evidence.md](connectivity-evidence.md), [pin-map review](pin-map-review.md), [auxiliary review](aux-pin-map-review.md), and [footprint load report](footprint-load-validation.md).

## Explicit reconstruction decisions

The original source is retained separately in [connectivity.json](connectivity.json). [schematic-connectivity.json](schematic-connectivity.json) is the actual drawn baseline. [reconstruction-decisions.json](reconstruction-decisions.json) enumerates each added endpoint.

- Added J3 and external CAM1 ground contacts 31–34. The native host footprint already contains these copper contacts; the exact ST camera module schematic documents their GND connection. This adds eight explicit terminals without adding physical components.
- Reconstructed three optional switch endpoints from the stored component intent: SW2.2 to 1V8, SW3.1 to NRST, SW3.2 to GND. SW2.1 to BOOT0 is directly recovered. SW2/SW3 remain DNP and excluded from BOM. Their two-terminal contact polarity is interchangeable; these three endpoint assignments are explicitly inferred, not recovered compiled netlist evidence.
- Used native UUID/pad geometry to resolve J3 and LED1 EDIF aliases. The misleading EDIF suffixes were not treated as physical pin numbers. LED1 physical pad 1 is cathode on STATUS_LED_K and pad 2 is anode on STATUS_LED_A; the apparent reversal in an initial alias-based review was disproved.
- Named U5 pins 3/7 IO2/IO3 for the exact IQ flash variant. Marked the camera module's truly unconnected positions appropriately. Restored raw per-property units, including C72–C74 and R30–R32.
- Corrected the J2 datasheet link to the archived TC2030 drawing; the cached native link referenced TC2070.

## ERC modeling

Electrical types were assigned from the manufacturer reviews, not copied blindly from mostly unspecified Flux terminal fields. No wires were changed merely to silence ERC.

- Internally common switch terminals use one `power_out` representative and passive duplicate contacts: U2.1 drives with U2.2/.3 passive; U1.J1 drives with J2–J6 passive. Assertions require the source nets to remain common.
- U12 QOD is a passive analog discharge terminal with internal resistance, as documented for the direct VOUT connection in TPS22918 section 8.3.2.
- U11 SDO/SA0 is modeled as an address input in this I2C configuration; CS and VDD are both tied to ACCEL_1V8_SW. The generator checks this mode assumption.
- Power flags identify external BAT_PLUS, BAT_CELL1_TAP and USB_VBUS sources, ground, and intended power paths through passive elements: SYS_IN, 3V3, 1V8 and VCORE_0V81. These are ERC source declarations, not proof of startup, regulation or load capacity.

## Libraries and remaining work

The project carries all required symbols and 147 footprints locally. Passive footprints follow each instance's selected metric package, rather than a cached generic 0603 default. U8 was rebuilt from verified native/IPC pad geometry; [its evidence](generated-footprints/README.md) is preserved. Unavailable source-machine 3D paths are recorded in [external-model-references.json](external-model-references.json) and removed from the portable footprint copies. Original Flux assets and KiCad library material retain their respective source licenses.

Footprint load and pin coverage do not validate manufacturing geometry. Prioritize J3 land dimensions/orientation, U7/U10 effective pad shapes and mask/paste, crystal lands, and battery contact mechanics before placement. Cached J3 lands differ from the manufacturer's recommended drawing. U7's original KiCad payload contains mask/paste-only aperture records; those must not become extra copper. U10 custom copper remains in its source footprint. The saved Flux board corrections remain available for the upcoming footprint comparison; no corrected PCB layout was created here.

Electrical design review remains necessary for power hold/startup, rail compatibility and sequencing, boot/alternate-function allocation, oscillator values, decoupling, NAND use and camera behavior. The [hardware/firmware baseline](../../docs/hardware-firmware-interface.md) allows that review to proceed while firmware is integrated. Final four-layer stackup, BGA escape, impedance widths/gaps and PCB routing remain pending.

## Reproduction

Run `tools/reconcile_flux_connectivity.py`, then `tools/build_schematic.py` with Python. Export the root schematic through `kicad-cli sch export netlist --format kicadxml`, placing the output at `hardware/reconstruction/kicad-netlist.xml`, then run `tools/validate_schematic.py`. Run `kicad-cli sch erc --format json --severity-all` for the ERC report and `kicad-cli sch export pdf` for the review PDF. `tools/validate_footprints.py` requires KiCad's bundled Python with `pcbnew`; `tools/render_schematic.py` uses the bundled document runtime.

The initial generator assumes the installed current-user KiCad 10.0 path on Windows. It overwrites generated output files; preserve subsequent manual schematic edits before regeneration. The generated KiCad project, libraries and PDF themselves can be copied together and used independently of these scripts.
