# Independent second v24 cold start

This compact supplement records a second discharged cold cycle of the same v24 RAW8 image, without reprogramming. First exposure strobe was 23.67008 ms after NRST release; first frame completed at 45.52640 ms. The root bench controller personally inspected the image and confirmed a discernible LED panel. The three observed rails passed discharge/restoration validation.

The timing, RAM records and digital traces are byte-identical to `tmp/bringup/capture-opt-v24-os-cold-02`; `archive-index.json` records their hashes. Images, analog streams, NOR contents and Saleae sessions are omitted. The ledger references the exact receiver and prefix manifests already preserved in [the v17–v24 archive](../2026-10-17-v17-through-v24/README.md). The separate visual assertion leaves the original result's pre-review field unchanged. `archive-script.py` performs offline extraction only.

This repeat supports basic autonomous reproducibility on this bench; two runs do not establish production worst-case timing or resolve the persistent startup D-PHY state-sequence flag.
