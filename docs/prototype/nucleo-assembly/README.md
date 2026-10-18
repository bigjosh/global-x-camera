# Nucleo C02 rework location diagrams

These figures locate the parts and connector pins used by the consolidated Nucleo modification guide. They are derived from ST's actual MB1940 revision C, N657X0Q C02 assembly drawings, not a generated board photograph. The top is viewed from the component side with CN10 / ST-LINK USB at the top; the bottom is viewed directly from underneath after flipping the board left-to-right, keeping the ST-LINK end at the top.

- `rework-overview.png` / `.svg`: top and bottom locations for D2, R23, R88, R89, SB24, and U24.
- `rework-details.png` / `.svg`: close-ups of the six parts. SB24 is on the bottom; all five other parts are on the top.
- `header-connections.png` / `.svg`: exact connector-pad locations for the 5 V input, 1.8 V feed and Arduino NAND signals.
- `power-wiring.png` / `.svg`: conceptual electrical connections, including the user-confirmed DC1863A at 5 V. Regenerate with `tools/build_nucleo_power_wiring.py` from the repository root; requires Pillow.
- `mb1940-c02-assembly.pdf`: source assembly pages 16-17 extracted from the official C02 schematic pack, retaining ST's drawing titles and revision information.
- `locations.json`: physical coordinates, PDF annotation coordinates, exact ODB++ pad records and source hashes.
- `build_diagrams.py`: regenerates the PNG/SVG diagrams from the two local input files; requires Python, PyMuPDF, Matplotlib and NumPy. Run from any directory with `python build_diagrams.py` using its full path.

The guide, not a diagram alone, determines the rework order and electrical prerequisites. The diagrams separate the basic five-part work from U24 Ethernet removal. **R32/R33 and the U14 regulator circuit are not modification targets.** The generic manufacturing pick-and-place file includes unfitted parts and must not be used as proof of C02 population; use the C02 BOM, schematic and actual board inspection.

## Sources and coordinate verification

Downloaded on October 18, 2026 over certificate-verified HTTPS:

1. [Official Nucleo product and CAD-resource page](https://www.st.com/en/evaluation-tools/nucleo-n657x0-q.html#cad-resources).
2. [MB1940-N657X0Q-C02 schematic pack](https://www.st.com/resource/en/schematic_pack/mb1940-n657x0q-c02-schematic.pdf), pages 16-17, top/bottom assembly, revision C. Full original SHA-256 is in `locations.json`.
3. [MB1940 manufacturing archive](https://www.st.com/resource/en/board_manufacturing_specification/mb1940-manufacturing.zip): `MB1940C/Assembly/MB1940C_PickandPlace.txt` supplies component centers; `MB1940C/ODB++/MB1940C.tgz`, `odb/steps/pcb/layers/comp_+_top/components`, supplies connector pad centers and pin numbers.
4. [C02 bill of materials archive](https://www.st.com/resource/en/bill_of_materials/mb1940-bom.zip), for separate population checks.

For the top view, the physical-coordinate-to-PDF transform was calibrated against the actual drawn centers of CN9 pins 1, 2 and 5. Their 2.54 mm pitch establishes both axes and scale. The resulting component-center overlays were visually checked on D2, R23, R88, R89 and U24. SB24's location was independently taken from its bottom-view component rectangle and checked visually; no assumed page-mirroring transform was used. Header markers use the ODB++ pin centers, cross-checked against the assembly's pin-1/end-number markings.

| Part | Side | X, mm | Y, mm | Role |
|---|---|---:|---:|---|
| D2 | Top | 16.0786 | 111.3097 | Remove target-to-debugger power diode |
| R23 | Top | 22.7330 | 111.2525 | Remove power-LED series resistor |
| R88 | Top | 40.0050 | 79.6295 | Remove 3.3 V I2C pullup |
| R89 | Top | 40.0050 | 81.9155 | Remove 3.3 V I2C pullup |
| SB24 | Bottom | 38.7320 | 75.9014 | Open VDDIO4 supply bridge |
| U24 | Top | 36.8280 | 34.1655 | Separate Ethernet-load removal stage |

Coordinates use ST's PCB origin, in millimetres. They are for reproducible annotations, not instructions to measure from a casually chosen board corner. Source reference material is copyright STMicroelectronics and supplied under its [Open Platform License Agreement](https://www.st.com/opla); the extracted source pages retain ST attribution. Annotations and the rendering script were added for this project.

## Limitations

This is a board-revision-specific location guide. It does not confirm the user's board revision or record any physical modification. The diagram's component outlines are assembly geometry, so a designator may appear inside a body outline even if the real silkscreen is elsewhere. Use magnification and the adjacent landmarks, then confirm the reference and connections before removing a part. No board, instrument, power setting, or firmware was changed to make these figures.
