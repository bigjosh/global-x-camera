# Footprint and assembly spot check

No major inherited body-size, pitch, pin-grid, locating-hole or mounting-slot defect was found in **U1, J1, J2 or SW1**. Two concrete items remain: U1's copper/paste lands differ slightly from ST's recommendation and its NSMD opening is inherited from future board settings; J2's mandatory routing keepout is drawn but not enforced. Neither is evidence of an already misrouted or unassemblable board.

This bounded check inspected the generated `hardware/kicad/GX.pretty/*_Recovered.kicad_mod` files through KiCad 10.0.6 `pcbnew.FootprintLoad`, extracted pad dimensions/locations, and visually compared archived manufacturer drawings. It supplements the 147-footprint parse/pin-coverage validation. J3 is covered by the camera/connector review. LED1 polarity was not reopened. No footprint or schematic was edited.

## U1 — STM32N657X0H3Q, VFBGA264

| Feature | Generated footprint | Manufacturer reference | Result |
|---|---|---|---|
| Body | 14.00 × 14.00 mm F.Fab outline | 14.00 × 14.00 mm | Match |
| Grid pitch | 0.800 mm X/Y | 0.800 mm | Match |
| Outer pad-centre span | 12.800 × 12.800 mm | 12.800 × 12.800 mm | Match |
| Physical pads | 264 unique pads | 264 balls | Match |
| Central vacant area | Rows G,H,J,K,L; columns 7–11 absent | Central 5×5 vacancy | Match |
| A1/top-view orientation | A1=(-6.4,-6.4); A17=(6.4,-6.4); U1=(-6.4,6.4) | A1 top-left in component/top view | Match; bottom-view drawing was not copied directly |
| Pad centres versus ball identifiers | All264 follow the correct row/column formula | 17×17 grid, omitted I/O/Q/S letters | 264/264 match |
| PCB copper diameter | 0.394 mm | Recommended 0.400 mm | 0.006 mm smaller |
| Paste aperture diameter | 0.394 mm before board/stencil overrides | Recommended 0.400 mm | 0.006 mm smaller |
| Solder-mask aperture | F.Mask included; no explicit local expansion | Typical 0.470 mm NSMD opening | Depends on board settings; not yet established |
| Package ball diameter | Not represented as PCB copper | 0.38–0.48 mm,0.43 mm typical | Do not confuse ball diameter with recommended land diameter |

Source: [ST DS14791 Rev10, pp255–257, Figure73 and Tables137–138](https://www.st.com/resource/en/datasheet/stm32n657x0.pdf#page=255), archived as `datasheets/processor/STM32N657X0_DS14791_datasheet.pdf`.

**Specific action, low severity:** normalize the 0.394 mm copper/paste lands to ST's 0.400 mm recommendation unless an assembly process intentionally approves the existing value. The diameter deviation is 1.5%, approximately 3% in area; this is not proof of a soldering failure. Establish the 0.470 mm mask opening explicitly: nominal radial expansion is0.035 mm with 0.400 mm copper, or0.038 mm with the existing0.394 mm copper. The footprint has no local mask override, so a future zero-expansion board setting would not reproduce ST's NSMD recommendation. There is no PCB mask output yet to condemn. ST also recommends0.100 mm stencil thickness; this belongs in the assembly specification.

For the board feasibility discussion only, the provisional 0.50 mm via pad between four 0.8 mm-pitch balls has nominal diagonal copper clearance≈0.119 mm using 0.394 mm lands, or≈0.116 mm using 0.400 mm lands. This barely exceeds the provisional 0.10 mm clearance and leaves little process/placement allowance. It is a geometric bound, not a completed BGA escape or four-layer routing validation.

## J1 — GCT USB4105

Coordinates below use the footprint origin at the centreline of the front shell-stake pair; +Y points toward the connector opening.

| Feature | Generated footprint | GCT drawing | Result |
|---|---|---|---|
| Shell/body envelope | 8.94 × 7.35 mm | 8.94 × 7.35 mm | Match |
| Signal contacts | Eight 0.30 × 1.15 mm lands ; 0.50 mm central pitch | Eight 0.30 × 1.15 mm lands ; 0.50 mm pitch | Match |
| Combined power/ground contacts | Four 0.60 × 1.15 mm lands at X=±2.40 and±3.20 mm | Same dimensions/positions | Match |
| Contact-row Y | -4.755 mm centre; forward edge=-4.18 mm | 1.15 mm land extending from the4.18 mm datum | Match |
| Signal ordering left→right | B8,A5,B7,A6,A7,B6,A8,B5 | Same component-side order | Match |
| Locating holes | Two NPTH Ø0.65 mm at(±2.89,-3.68) | Ø0.65,5.78 mm separation,3.68 mm offset | Match |
| Rear shell slots | Two 0.60 × 1.70 mm plated slots,1.00 × 2.10 mm lands, X=±4.32,Y=-4.18 | Same | Match |
| Front shell slots | Two 0.60 × 1.40 mm plated slots,1.00 × 1.80 mm lands, X=±4.32,Y=0 | Same | Match |
| Shell-stake span | 8.64 mm | 8.64 mm | Match |

Source: [GCT USB4105 drawing RevB4, p1](https://gct.co/files/drawings/usb4105.pdf), archived as `datasheets/connectors/USB4105_drawing.pdf`.

No definite inherited land or hole error found. Plated slots must remain plated slots in fabrication output. The drawing distinguishes0.60/0.95/1.20 mm stake-length ordering options; the default USB4105-GF-A option has0.95 mm stakes. Confirm the exact order code and intended soldering method with the assembly purchase, rather than assuming a1.6 mm PCB requires stakes to protrude completely through it. Final PCB edge and enclosure geometry must preserve the drawing's mating clearance; they are not contained in a standalone footprint.

## J2 — TC2030-IDC-NL

| Feature | Generated footprint | Tag-Connect drawing | Result |
|---|---|---|---|
| Contact lands | Six Ø0.787 mm | Ø0.787±0.076 mm | Match |
| Contact spacing | 1.270 mm columns and rows | 1.270 mm | Match |
| Numbering | Bottom row 1,3,5; top row 2,4,6 in component view | Same | Match |
| Alignment holes | Three NPTH Ø0.991 mm | Ø0.991±0.076 mm NPTH | Match |
| Hole coordinates | (-2.54,0),(2.54,-1.016),(2.54,1.016) mm | 5.080 mm X span,±1.016 mm Y offset | Match |
| Paste | No F.Paste on contact lands | No solder paste | Match |
| Probe-body envelope | 9.906 × 6.096 mm F.Fab | 9.906 × 6.096 mm | Match |
| Central no-track/via region | Two overlapping Dwgs.User polygons only | Mandatory shaded routing keepout | Not enforced by the footprint |

Source: [Tag-Connect TC2030-IDC-NL drawing RevB, pp1–3](https://www.tag-connect.com/wp-content/uploads/bsk-pdf-manager/2019/12/TC2030-IDC-NL-Datasheet-Rev-B.pdf), archived as `datasheets/connectors/TC2030-IDC-NL_datasheet_footprint.pdf`.

**Specific action, medium severity:** implement the manufacturer's central track/via prohibition as a real board/footprint rule area, and enforce the 0.020 inch (0.508 mm) exclusion for other tracks/signals around contact pads. The present Dwgs.User polygons are documentation graphics and contain no KiCad `keepout` zone/rule. This is a confirmed constraint omission, not evidence of a current violation. Preserve paste exclusion and NPTH alignment holes. The probe/clip also needs physical access on the appropriate board sides.

The project's SWD signal assignment is custom. This mechanical check verifies pad numbering against the cable drawing, not compatibility with an arbitrary standard debugger adapter. The existing MCU/interface report owns the wiring.

## SW1 — Omron B3U-3000P

| Feature | Generated footprint | Omron p3 recommended PCB pad | Result |
|---|---|---|---|
| Contact lands | Two 0.80 × 1.70 mm | Width (4.2−2.6)/2=0.80 mm; height 1.70 mm | Match |
| Pad centres | X=±1.70 mm,Y=0 | 3.40 mm centre spacing | Match |
| Inner gap | 2.60 mm | 2.60±0.10 mm | Match |
| Outer span | 4.20 mm | 4.20±0.10 mm | Match |
| Boss hole | None | None for selected non-“-B” variant | Match |
| Ground terminal | None | None for selected 3000 variant | Match |
| Body/plunger sketch | 3.0 × 2.5 mm body plus side actuator | Matching nominal body/side-actuator plan | No assembly mismatch found |

Source: [Omron B3U datasheet, p3, B3U-3000P(M) without ground terminal/boss](https://omronfs.omron.com/en_US/ecb/products/pdf/en-b3u.pdf#page=3), archived as `datasheets/controls/B3U_switch_datasheet.pdf`.

The manufacturer says terminal numbers are not marked on the switch. The two isolated SPST contacts are electrically interchangeable, so reversing 1/2 on the footprint is not a polarity defect. The inherited footprint has no F.CrtYd outline; add an actuator/body courtyard when integrating the board so placement checks protect the actual mechanical envelope. This is an assembly-constraint improvement, not a wrong pad pattern. The switch's electrical latch interaction is covered separately in PWR-001.

## Reproducibility and limits

Extracted pad records are in `_footprint-work/U1-pads.json`, `J1-pads.json`, `J2-pads.json` and `SW1-pads.json`; rendered manufacturer pages used for the comparison are alongside them. Footprint SHA-256 values reviewed:

| Ref | SHA-256 |
|---|---|
| U1 | `6ede8fbfc1b2fd02bbb89d19c4045613230feb53996ea3ca7701f4faa00b48d4` |
| J1 | `389fe3138f244e06baf607e02f75763c9be9a4565043e82a29ec248ce73479d7` |
| J2 | `024ea80fca3742fdf92c41a57b1be4ad7d9eb2ba5e6fe8ebf3fd368ee75e77fc` |
| SW1 | `bb7f58840a68cd2c7cd9b8f35e0639def298eb0dc19ad18479b7bf60501a7c47` |

This is a four-component spot check against archived drawings. It does not sign off final copper clearances, stencil outputs, solder-mask registration, tolerances, placement, panelization, connector mating clearance or assembly process. The identified matches are specific dimensional checks, not a blanket manufacturing approval.
