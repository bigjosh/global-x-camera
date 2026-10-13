# Footprint load and pin coverage: PASS

KiCad 10.0.6 `pcbnew.FootprintLoad` loaded 147 of 147 generated footprints.

Compared copper pad numbers against `schematic-connectivity.json`: 703 expected physical pins across 147 host-PCB components. CAM1 is excluded; J3 contacts 31–34 are included.

Missing pins: 0. Unexpected copper pad records: 0. Component mismatches: 0.

Ignored records are classified by actual KiCad attributes and layers, not by their names. NPTH mechanical holes are excluded, as are pads with no copper layers. A `~` or blank-number pad on copper is reported as an extra.

- 5 ignored: non-plated mechanical hole.
- 9 ignored: no copper layers (mask/paste or other aperture).

## Exceptions

No parsing or physical-pin coverage exceptions.

## Multiple pad records for one physical pin

None.

Non-pad copper graphics found: 0. Custom-pad primitives belong to their pad and are not counted as separate graphics.

This validation does not sign off land dimensions, polarity/orientation, courtyard shape, solder-mask or paste rules, board clearances, or manufacturing suitability. File hashes and per-footprint results are recorded in `footprint-load-validation.json`.

Re-run with KiCad’s bundled Python: `python tools/validate_footprints.py`.
