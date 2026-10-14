# Storage retention review

October 14, 2026. **Proposal for discussion, not an approved requirement.** The user asked for a recommendation after settling the [failure response map](failure-response-review.md). The earlier reliability discussion did not select a retention duration, temperature profile or redundancy scheme.

## Discussion order

1. Unpowered retention duration and temperature basis — current item.
2. Expected erase/reuse lifetime and temperature excursions.
3. ECC, integrity checking and any optional USB-time refresh implementation.

Discuss one item at a time. This review does not change the accepted RAW10/capacity, configurable payload readback, explicit-erase, USED/DONE or USB error-reporting policies.

## Current recommendation

Target **10 years of retention at a 25°C reference storage temperature, fully unpowered, without periodic power-up or USB refresh**. Successfully committed photos and the metadata needed to identify, decode and verify them should remain recoverable using the selected device's required ECC. Removing or exhausting the batteries must not itself shorten this storage requirement; maintaining the running RTC clock is a separate matter.

This is a proposed design target, not measured compliance or an unconditional product guarantee. The target must ultimately be tied to the agreed erase/reuse lifetime and temperature history. Sustained hot-car storage is not covered by this room-temperature proposal. Optional maintenance during USB use must not be necessary to satisfy a fully-unpowered target.

## Evidence checked October 14

- Alliance's [AS5F series announcement](https://www.alliancememory.com/new-1-8v-and-3v-spi-nand-flash-memory-alliance-memory-as5f-series/) includes **AS5F14G04SND-10LIN** and publishes **10-year retention** and **60,000 program/erase cycles** for the series. These headline figures are not proof that maximum cycling and ten-year retention apply simultaneously at every temperature. The [exact product page](https://www.alliancememory.com/as5f14g04snd/) lists the original part and a separate C variant; do not treat revisions as interchangeable without their documentation. The exact purchased part remains unconfirmed.
- Kioxia's [retention explanation](https://blog-us.kioxia.com/post/2025/11/26/understanding-nand-flash-memory-data-retention-key-considerations-for-reliable-designs) explains that higher temperature and accumulated program/erase cycles reduce retention and that supplier characteristics are needed for a lifetime assessment. This supports qualifying a temperature/wear profile; it does not quantify the Alliance candidate's behavior.
- The earlier [project reliability conversation](../../research_notes/Global%20X%20Camera%20decision%20review/chat_sources/6aa5d95a-b2e8-83ea-933a-5f18d637cad3.md) raised loss of previously written photos and error rates without approving a retention duration. Existing [Macronix endurance/retention evidence](../../datasheets/memory/Macronix_AN0339_NAND_endurance_retention.pdf) is family-level context, not qualification of the proposed Alliance or Micron parts.

## What remains before claiming compliance

Confirm the exact part's retention conditions, required ECC, supported temperature profile and cycling history against vendor documentation/qualification evidence. Protect allocation/index/commit metadata as well as pixels. Prototype write/read and power-cut tests can validate the storage implementation, but cannot by themselves establish a ten-year retention guarantee; an appropriate supplier-backed accelerated-retention qualification is needed.

**Pending user decision:** adopt the proposed ten-year, room-temperature, fully-unpowered target, or choose a different duration/environment. No storage part, refresh strategy or redundancy scheme is selected by this proposal.
