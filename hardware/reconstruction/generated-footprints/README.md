U8 is the only native PCB component without an embedded footprint payload beyond TP1–TP13. The scan covers all 147 native PCB component instances; CAM1 is external to the host PCB. Test points are handled separately by the main generator.

`U8.kicad_mod` reconstructs RV-3028-C8-32.768kHz-1PPM-TA-QC from the eight effective native SMD pad records. Copper dimensions and spacing also match page 1 of the archived [Micro Crystal datasheet](../../../datasheets/sensors_timing/RV-3028-C8_datasheet.pdf): 0.27 × 0.70 mm rectangular lands, 0.54 mm pitch, 1.00 mm row-centre spacing, 0.30 mm gap between rows. Each pad has matching copper, paste and mask apertures, with no explicit mask or paste expansion override.

The footprint preserves physical pin numbers 1–8. Native pad labels (`pad1` etc.) are mapped through each node's explicit `terminalId`, independently checked against the terminal's `pin_number`. Pins are 1 CLKOUT, 2 INT, 3 SCL, 4 SDA, 5 VSS, 6 VBACKUP, 7 VDD, 8 EVI. Pin 1 remains present even though its schematic connection is intentionally NC.

Coordinate conversion is `KiCad (x,y) = native (x,-y)`. Pins 1–4 therefore lie at KiCad y=+0.50 mm, and pins 5–8 at y=-0.50 mm. This matches all eight IPC package locations after the Cartesian-to-KiCad Y conversion and the manufacturer's recommended solder-pad view. The adjacent manufacturer package drawing is a bottom view and must not be copied directly as a top-side land pattern.

Source pointers:

- Native JSON: `imports/flux/2026-09-05/bigjosh-global-x-camera.flx`, `/elements/7a93b60b-55a8-4684-8b64-768f9a82e0cc/part_version_data_cache/pcbLayoutNodes`. All eight cached pad rules match their board-instance rules; the footprint has no inherited local rule sets or pad geometry overrides.
- IPC: `imports/flux/2026-09-05/global-x-camera.ipc2581c`, `Package[@name='RV-3028-C8-32.768kHz-1PPM-TA-QC_68']/Pin`. Component U8 has no rotation or mirror and origin (80.80, -21.990002) mm.
- Manufacturer PDF: `datasheets/sensors_timing/RV-3028-C8_datasheet.pdf`, page 1, SHA-256 `09f2641f2388a92ecaa5473fe1faa5a454048b53a12d7e6028106025a0352e0f`.

The 2.0 × 1.2 mm nominal fabrication outline comes from the manufacturer. The pin-1 bevel and silkscreen marker are reconstruction annotations. The 2.50 × 2.20 mm courtyard is a reconstruction choice: 0.25 mm clearance around the greater of nominal body and copper extents. No machine-specific 3D model is referenced.

Validation: KiCad 10 `pcbnew.FootprintLoad` loads the file successfully. All eight physical pad numbers, centres and dimensions match the native and IPC sources; details are in `U8-evidence.json`. `u8-datasheet-review.png` is the rendered page used to inspect the package and land-pattern drawing. These checks verify reconstruction fidelity; final board fabrication-rule review remains a separate task.
