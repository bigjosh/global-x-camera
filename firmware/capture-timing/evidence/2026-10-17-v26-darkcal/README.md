# Dark-calibration-off diagnostic

This isolated v26 RAW8 experiment changes only the v24 size-optimized prefix's sensor setup: write `DARKCAL_CTRL 0x0340 = 0` and verify it before START. The receiver is unchanged. Normal profiles retain automatic dark calibration.

START completion at 18.75248 ms was followed by the first exposure strobe at 24.04896 ms: **5.29648 ms**, essentially unchanged from the calibrated profile. The first frame completed at 45.89008 ms. Root-controller inspection confirmed the LED panel, but the gray pedestal increased: byte minimum 113 versus approximately 15 in ordinary captures. This setting provided no useful startup improvement and was not retained.

The archive contains unchanged timing/results/digital traces, compact RAM records, programming verification, exact manifests and newly needed source bytes. `source-provenance.json` references identical content-addressed source objects in the prior v17–v24 archive to avoid duplicating vendor code. All source hashes matched. Separate visual assertions preserve the raw result's original pending-review field. No images, full NOR dumps, analog streams or Saleae sessions are included. Hardware operations and image inspection were performed by the root controller; archival work was offline.
