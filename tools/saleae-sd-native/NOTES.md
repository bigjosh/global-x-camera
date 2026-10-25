# Native SD analyzer decisions

## 2026-10-25  Decode native SD with a raw-channel analyzer and independent CMD/DAT timelines

**Why:** the camera uses native one-/four-bit SDMMC, not SPI/QSPI. Exact DAT0
busy timing requires raw transitions even when CLK stops. Our archived final
stop trace starts busy before CMD12's response and carries a CMD13 PRG
response while DAT0 is still low. The protocol core therefore parses CMD
and DAT independently. Two selectable analyzer views retain true overlapping
times while respecting Logic's sequential-frame constraint; all-event CSV
retains summaries and diagnostics that cannot fit the waveform track.

**Rejected:** wrapping the SPI analyzer in a high-level analyzer; measuring
busy only at clock edges; moving busy to after the response; requiring
DAT1–DAT3 high during native write status; interpreting native status `110`
as SPI's write-error token. ACMD23 is a pre-erase hint, not CMD23's explicit
transfer length or proof of a completed save.

**Evidence:** [implementation and scope](README.md),
[protocol tests](tests/decoder_tests.cpp), and
[raw recorded fixtures](tests/fixtures/README.md), including final busy
sample interval 159918394–160132045 at 250 MS/s. The Saleae SDK lacks a
reliable end-of-capture sample API: complete-recording truncation ends at the
last observed CLK/DAT0 edge and is labeled a lower bound; live mode must not
treat a temporary lack of transitions as final input.
