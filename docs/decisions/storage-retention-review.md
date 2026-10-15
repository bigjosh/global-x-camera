# Storage retention review

October 14, 2026. **Ten-year room-temperature retention and 1,000 complete reuse cycles are approved.** After settling the [failure response map](failure-response-review.md), the user accepted the retention recommendation: “yes lets lock in 10 years at room temp with no power or refresh needed.” The subsequent reuse approval was: “yes lets lock in 1000 complete reuse cycles.” ECC/CRC-32C, damaged-photo recovery and block retirement were subsequently accepted in the [read policy](ecc-read-error-review.md).

## Discussion order

1. Unpowered retention — **settled: ten years at room temperature, no power or refresh needed**.
2. Expected erase/reuse lifetime — **settled: 1,000 complete fill/download/explicit-erase cycles**.
3. USB photo-transfer and deletion — **settled: PTP with explicit per-photo deletion**; see the [USB access review](usb-photo-access-review.md).
4. [ECC and read-error handling](ecc-read-error-review.md) — **settled:** ECC/CRC-32C, recoverable damaged-image export and permanent block retirement.
5. Damaged-image warning — **settled:** `_RECOVERED` filename suffix plus EXIF UserComment.
6. **Settled:** each host image-data request freshly reads/checks the original NAND image in RAM; no relocation/refresh. Predictive media errors retire its slot without deleting it.
7. **Settled:** [single stored photo object](storage-redundancy-review.md), including pixels and photo attributes, with no object-content duplication. Storage-control redundancy depends on implementation; journaling remains provisional.
8. **Settled, D-32:** best-effort USB retrieval and explicit deletion of PARTIAL objects, with EXIF and/or PTP warnings.
9. **Provisional allocation, D-33:** circular FREE-and-GOOD search. The detailed page/block layout, off-NAND allocation-table option and retention/wear qualification remain open; D-37 settles only the initial firmware approach and readiness to optimize.

Discuss one item at a time. This review does not change the accepted RAW10/capacity, configurable payload readback, explicit-erase, USED/DONE or USB error-reporting policies.

## Accepted retention requirement

Require **10 years of retention at room temperature (approximately 25°C as the reference), fully unpowered, with no refresh needed**. Successfully committed photos and the metadata needed to identify, decode and verify them must remain recoverable using the selected device's required ECC. No periodic wake, battery power, USB connection or maintenance write may be required during that retention interval. Removing or exhausting the batteries must not itself shorten this storage requirement; maintaining the running RTC clock is a separate matter.

This is an accepted requirement, not demonstrated compliance. Qualification must cover the agreed erase/reuse lifetime and temperature history; the acceptance must not silently apply only to new, uncycled memory. Sustained hot-car storage is not covered by this room-temperature requirement. No image relocation or refresh is selected. The accepted read policy checks the whole original image in RAM only on host image-data requests, reports current-read warnings and retires a slot from future writes on predictive media errors. Retired images stay in place until host deletion; later reads may deteriorate. Retirement alone does not restore retention, so exact-part qualification must account for vendor marginal-data requirements.

## Evidence checked October 14

- Alliance's [AS5F series announcement](https://www.alliancememory.com/new-1-8v-and-3v-spi-nand-flash-memory-alliance-memory-as5f-series/) includes **AS5F14G04SND-10LIN** and publishes **10-year retention** and **60,000 program/erase cycles** for the series. These headline figures are not proof that maximum cycling and ten-year retention apply simultaneously at every temperature. The [exact product page](https://www.alliancememory.com/as5f14g04snd/) lists the original part and a separate C variant; do not treat revisions as interchangeable without their documentation. The exact purchased part remains unconfirmed.
- Kioxia's [retention explanation](https://blog-us.kioxia.com/post/2025/11/26/understanding-nand-flash-memory-data-retention-key-considerations-for-reliable-designs) explains that higher temperature and accumulated program/erase cycles reduce retention and that supplier characteristics are needed for a lifetime assessment. This supports qualifying a temperature/wear profile; it does not quantify the Alliance candidate's behavior.
- The earlier [project reliability conversation](../../research_notes/Global%20X%20Camera%20decision%20review/chat_sources/6aa5d95a-b2e8-83ea-933a-5f18d637cad3.md) raised loss of previously written photos and error rates without approving a retention duration. Existing [Macronix endurance/retention evidence](../../datasheets/memory/Macronix_AN0339_NAND_endurance_retention.pdf) is family-level context, not qualification of the proposed Alliance or Micron parts.

## What remains before claiming compliance

Confirm the exact part's retention conditions, required ECC, supported temperature profile and cycling history against vendor documentation/qualification evidence. Protect allocation/index/commit metadata as well as pixels. Prototype write/read and power-cut tests can validate the storage implementation, but cannot by themselves establish a ten-year retention guarantee; an appropriate supplier-backed accelerated-retention qualification is needed.

## Accepted erase/reuse lifetime

Require a storage lifetime of **1,000 complete fill/download/explicit-erase cycles**, while retaining the accepted ten-year room-temperature unpowered requirement for photos saved at the end of that rated usage. At the accepted minimum capacity of 200 photos, this represents **200,000 photo saves** across the storage lifetime; it is not a guarantee of battery life or mechanical shutter life.

This is an accepted workload, not 1,000 lifetime downloads or an assertion that every physical NAND block sees exactly 1,000 erases. Partial downloads do not consume an erase cycle, while allocation/retirement metadata, retries and recovery can concentrate physical wear. Qualification must cover worn memory and avoid metadata wear hotspots; headline NAND endurance alone does not prove simultaneous ten-year retention. Exact part, ECC, wear distribution and room-temperature retention after this usage remain to qualify.

No exact storage part or additional redundancy scheme is selected by the retention/reuse approvals. Subsequent decisions settle PTP/per-photo deletion and ECC/CRC-32C with damaged-photo recovery and retirement. The `_RECOVERED`/EXIF warning is also selected. Request-driven RAM reads with no relocation or refresh and predictive-error slot retirement are settled. D-30 provisionally selects journaling; D-31 stores each photo object and its attributes once, leaving storage-control redundancy to implementation. D-32 approves PARTIAL-object USB recovery/deletion and EXIF and/or PTP warnings. D-33 provisionally chooses circular allocation. D-37 selects C/STM32CubeN6/HAL for bring-up with readiness for measured bare-metal optimization; exact storage layout, off-NAND tables and retention/wear qualification remain open.
