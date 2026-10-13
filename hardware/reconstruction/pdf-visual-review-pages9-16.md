# Schematic PDF visual review: pages 9–16 - final pass

**Final result: PASS for the assigned visual-review scope.** Current `hardware/kicad/global-x-camera.pdf` has 16 A3 pages, SHA-256 `a9190dcb1ab2176ff0297f2d11b931b7d1d7e7b25a31d6da4b121ef7a0572b51`.

Initially rendered and visually inspected all pages9–16 plus enlarged camera, MCU-unused, RTC, and title-block regions. After regeneration, rendered and visually rechecked changed pages9,10,13,14, and checked the revised title text on every page9–16. No remaining clipped text, overlapping symbols, or unreadable key labels was found in this scope.

## Resolved findings and final checks

- The revision field now reads `A` and fits its title-block cell. Reconstructed status remains in the existing comments.
- Page14 now displays C72 `100nF`, C73/C74 `1uF`, R30/R31 `10kohm`, and R32 `100kohm`. These suffixes agree with raw Flux value/unit metadata. The earlier missing-unit finding is resolved.
- Page10's moved CSI tuning resistor R17 appears as `200ohm` between CSI_REXT and GND, with readable labels and adequate separation. J3/CAM1 contacts31–34 still each display GND; both complete symbols remain clear.
- Page13's moved USB tuning resistor R18 appears as `200ohm` between USB_TX_RTUNE and GND, clear of neighboring CC pull-downs.
- Page9 camera rails, regulator labels, supporting passives and title block remain clear after regeneration.

The initial review used PDF SHA-256 `409288117cf0cda68d0baa4315659baecca62ef536fcd4f6b9c8fea11f0fe653`; its two findings were revision overflow and lost unit suffixes. Both are resolved in the final hash above.

## Page results

| Page | Final result |
| --- | --- |
| 9 Camera power | U9/U10 reference, MPN, pin labels, NC mark, rail names and supporting passives readable; no overlaps or clipping. |
| 10 Camera and CSI-2 | U1G, J3 and CAM1 labels readable; all J3/CAM1 numbers1–34 are visible. J3 and CAM1 contacts31–34 each have individual GND stubs. CAM1 GPIO4/5 and second-lane positions have NC marks. No collision between contacts, labels or body. |
| 11 Boot NOR flash | U5 exact W25Q128JVPIQ label and IQ note readable; pins3/7 display IO2/IO3, EP9 visible and grounded. No overlaps or clipping. |
| 12 Raw NAND storage | U6 MPN, all48 numbered terminals, NC marks and controls readable. Dense block has enough spacing; no overlaps or clipping. |
| 13 USB-C and USB High-Speed | J1 grouped physical labels and shell contacts readable; D1/U4/U1H and passives separate. No overlaps or clipping. |
| 14 RTC and orientation | U8 long MPN and U11/U12 labels fit; RTC/accelerometer stubs clear. Value-unit fix verified; no geometric overlaps or clipping. |
| 15 Unused MCU terminals | U1L and U1K terminal names, ball numbers and individual NC markers readable in enlarged review. No hidden or clipped names visible. |
| 16 Unused MCU terminals, continued | U1J long oscillator pin labels fit within the body; terminal numbers and NC markers readable. No overlaps or clipping. |

J3 is displayed as a functional symbol with sequential halves1–17/18–34, not a mechanical top-view drawing. Its visible numbering and GND contacts are correct for the reconstruction; no conclusion about footprint orientation, land geometry, routing or actual netlist continuity follows from this visual inspection. Root performs the separate connectivity check.

Rendering scratch is under `tmp/pdfs/pin_review_visual/`, with regenerated pages in `final/`. The generator and source PDF were not edited by this review. Core/snubber placement on pages1–8 and netlist/ERC validation are covered by root separately, not by this visual-review record.
