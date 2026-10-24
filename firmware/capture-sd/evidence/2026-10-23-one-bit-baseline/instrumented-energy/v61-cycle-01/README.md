# Instrumented v61b current and energy

This single instrumented Standby trial measured **1.302542515 J over 2.734223 s**
from observed current onset to the selected low-current plateau. The plateau
averaged **8.17674 mA / 40.0012 mW**; its separate one-second confirmation tail
used 0.040004623 J. These are the JS110-fed branch measurements, excluding any
remaining CN8/debugger bypass paths. The source voltage is JS IN+, not the target
5 V rail. The peak and source dip retain the instrument's range/suppression
behavior and are not independently qualified analog measurements.

The explicit firmware sector is
`cc49159990ecd7aab9b0ab9c9055b3c230cc2ef639b1c295c511bea4a8be943f`.
The context binds its build and safe-start proof. Do not pool this run with the
three unchanged-v59 baseline recordings or attribute their difference to marker
overhead. Raw logging finalized with zero dropped chunks and contiguous native
2 MHz samples; initial nonfinite current samples precede this analysis window.

All completion and terminal-state qualification flags remain false. A later
guarded SBF observation is retained in `context/`, separately from the energy
boundary. The selected plateau includes possible settling and is not an exact
WFI timestamp. No image-integrity claim is made here. The original strict pulse
width decode failed and remains in `record/`; any separately justified ordered
edge interpretation is a different timing analysis. Saleae and Joulescope
clocks are not synchronized, so this archive makes no phase-specific energy
claim.

`compact.json.gz` preserves every included sample's signed sums and extrema in
bins whose edges include every integration boundary. `python replay.py --out
NEW_DIRECTORY` verifies the manifest, native-log metadata bindings and all four
energy integrals. Add `--figures --plot-deps PATH_TO_MATPLOTLIB` to rerender
`power.png` and `power.svg`. NumPy is required. The original raw float streams
remain local; this compact replay cannot rerun the onset/plateau detector or
reconstruct within-bin sample order. No image or SD file bytes are included.
