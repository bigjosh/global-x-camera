# First native RAW10 cold capture: v24b

October 17, 2026. The root bench controller captured and inspected a discernible LED-panel image at native **1120 × 1364, 10 bits per pixel**. The first exposure strobe occurred **24.66704 ms after NRST release**; the first complete image reached RAM at **46.52496 ms**. This is one observed run, not a worst-case timing guarantee or a completed minimum-delay search.

The 3,055,360-byte, right-aligned 16-bit RAM representation passed exact MCU/host checksum comparison, the receiver's exact byte-count check, and its overflow canary check. All sample upper six bits were zero, all four low-two-bit combinations occurred, and sample values spanned 61–639. The fixed display conversion was RAW10 >> 2, without adaptive gain. The separate [visual-review record](visual-review.json) attributes image inspection to the root controller; the original result's pending-inspection field remains unchanged.

## Timing-analysis correction

The original wrapper exited with an error **after successful capture and rail verification**, because the digital trace contained a 160 ns NRST high bounce during initial power removal, plus the actual boot release at 20.54475776 s. The raw trace was not changed and no additional hardware operation was used to resolve this. Reanalysis with `--after-s 10`, inside the verified discharged interval, selected the actual next boot. All 40 PE0 transitions matched all 40 RAM events exactly. See [the contemporaneous correction note](capture/analysis-note.json), [original wrapper log](capture/cold.log), [digital trace](capture/cold/logic/digital.csv), and [corrected timing](capture/cold/timing.json).

The three measured rails shared 13.360704 s below their off thresholds and returned to their expected levels. This does not directly probe every internal or always-on supply. The strobe is mirrored through an MCU interrupt, so its timestamp includes unbounded positive translator/interrupt/logging delay. The first strobe width was 10.98416 ms, and its falling edge preceded first VSYNC by 243.84 µs. A later strobe is retained separately in the ledger; it is not substituted for the first exposure.

One D-PHY control-sequence error was recorded before exposure, about 0.35 ms before its first rising edge. No additional callback occurred during the first frame, but the HAL disables the corresponding interrupt after its first occurrence. The image and checks passed; this archive does not claim an error-free CSI startup or prove the flag harmless in every condition.

## Contents and provenance

- [Ledger](ledger.json): derived timing, first and later strobes, error phases, and applied sensor-clock readbacks.
- [Capture result](capture/cold/ram/capture-result.json): unchanged acquisition result, byte/sample statistics and memory/format records.
- [Archive index](archive-index.json): original paths, byte lengths and SHA-256 for all 52 copied files.
- [Source provenance](source-provenance.json): every manifest-declared source was copied only after its hash matched the frozen build.
- `builds/`: original receiver and prefix manifests; their pre-execution status is intentionally unchanged.
- `source-objects/`: content-addressed exact source bytes; `licenses/` preserves applicable vendor notices.
- `tools/`: snapshots of the isolated builder and offline analysis utilities. The one-off archive script assumes its original `tmp/capture-research` location; this archived copy is provenance, not directly runnable from this directory.

The programmed first-sector SHA-256 was `63b6bfe42e5ccf77de03000110768ef6ec3393998d721595b9927e0c1464b3a6`. Receiver SHA-256 was `deafa0f588d18e55b8b1ae47a1ff559857db45994e2cdb700afe47132a92124b`. The captured image SHA-256 was `58442df2cdedbcc418dd3a09e7fa382196df0fb2bd79a7b7d1af7e9a49c4c976`.

Images, raw frame bytes, NOR dumps, large analog traces and Saleae recordings remain outside this compact archive. Evidence inherits `../.gitattributes` with text conversion disabled to preserve exact bytes across Git checkouts.
