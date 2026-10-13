# Reconstruction pin-map review

Checked the recovered native maps for U1, U5, U6, J2, J3, and CAM1 against archived manufacturer documents. **No physical pin renumbering is required for the checked device maps.** Two corrections matter to schematic interpretation: the exact NOR variant uses IO2/IO3, and the exact camera module has six unconnected connector positions. Four camera ground contacts are absent from the logical model.

This review changes no source schematic, netlist, or footprint. [pin-map-review.json](pin-map-review.json) supplies KiCad `pin_types` for existing U5/U6/J2/J3/CAM1 pins, document-proven U5 name corrections, and separate recommended additional ground contacts. The original native export SHA-256 is `6da7be0451f25cee64d67e8072e4fb0b201687bf9c56cfb6292dd439a3d16aac`.

| Part | Evidence and result |
| --- | --- |
| U1 STM32N657X0H3Q | DS14791, Figure 13, PDF p87: extracted all 264 populated VFBGA264 cells and compared every ball/function with native data. **264/264 match** after normalizing duplicated supply suffixes and line-break artifacts. CSI clock T3/U3, lane0 T5/U5, lane1 T4/U4, VDDCSI R4 and CSI_REXT P5 match. No numerical correction. |
| U5 W25Q128JVPIQ | Winbond Rev M, PDF pp6,10,17,71,76–77: WSON package P pins1–8 match. Exact IQ fixes QE=1, so rename pin3 `IO2` and pin7 `IO3`; WP#/HOLD#/RESET# labels imply unavailable functions. IO0–3 are bidirectional. Native pin9 `EP` is a footprint convention: center metal is internally unconnected, permitted floating or tied GND; use passive, not power input or no-connect. |
| U6 MX30LF2G18AC-TI | Macronix PM2129 v1.4, pp9,11: **48/48 match** the TSOP pinout. Pin7 R/B# is open drain (`open_collector` in KiCad); PT38 and controls are inputs, IO0–7 bidirectional. Keep VCC1/VSS1 as power pins despite optional internal bonds; manufacturer recommends the designated supply connections. |
| J2 TC2030-IDC-NL | Tag-Connect drawing pp1–2: six native logical pin numbers and cached footprint top-view positions match. Odd row1/3/5 is opposite even2/4/6 with the asymmetric locating holes correctly placed. Three `None` pads are NPTH alignment holes, not extra pins. All six connector contacts are passive. The cable is straight through to IDC1–6; the drawing does not mandate this project's SWD signal assignment. |
| J3 BM28B0.6-30DS/2-0.35V(51) | Native terminal UUIDs uniquely resolve positions1–30 despite all names being `~`. Treat each contact as passive. Four existing footprint copper contacts31–34 lack logical pins; see below. The Hirose reference drawing identifies power contacts but does not give numerical signal orientation, so this limited review does not certify signal-pad orientation. |
| CAM1 CAM-5G0-079CLR | Exact ST module schematic Rev1, June2024, p1: all30 native position names agree, but **15/17 (GPIO4/5),19/21,22/24 (second data lane) are internally NC**. Assign `no_connect` to these module pins. GPIO0–3 are bidirectional, SCL/CLKIN/XSHUTDOWN inputs, SDA bidirectional, first CSI data pair and clock outputs; sensor DS13170 Rev10 p10 supports these types. |

## Missing camera ground contacts

The exact module schematic explicitly ties connector pins31–34 to GND. Hirose drawing EDC-363044-51-00 p1 calls the corresponding end features power contacts. Native J3's footprint already has four numbered copper pads31–34, but J3 and CAM1 logical symbols stop at30. Add four passive J3 contacts and four module ground pins, all on GND, as an explicit documented reconstruction correction. The exact geometric ordering of the four contacts is not established by the unnumbered Hirose drawing; it has no electrical consequence when all four are GND. Do not silently omit them as non-electrical mounting holes.

## Remaining limits

- J2's native cached datasheet URL incorrectly references TC2070-IDC-NL. Use the archived TC2030 drawing for the selected six-contact cable.
- J3's raw cached lands (0.127 × 1.1176 mm signal pads) differ from the recommended Hirose reference layout (0.18 mm width and 0.31 mm length inferred from the 1.8/1.18 mm outer/inner row dimensions). Its footprint geometry needs a separate manufacturing check; this review authorizes no pad edits.
- Logical no-connect intent is different from a manufactured NC pin. Keep J3 unused contacts passive, while marking only the actual unconnected CAM1 and NAND terminals `no_connect`.
- This validates pin identities, not the complete circuit. The native export's single-pin net fragments still require the existing EDIF/native reconciliation. No MCU alternate-function allocation, debug-adapter compatibility, supply-sequence, layout, or impedance signoff is implied.
