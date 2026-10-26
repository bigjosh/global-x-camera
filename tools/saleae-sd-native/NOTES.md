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

## 2026-10-25  Check API instance identity when a configured analyzer appears missing

**Why:** the directory was correctly saved and the DLL present, but the API on
10430 still belonged to a background Logic instance started October 19. The
user's visible-window restart had not restarted that instance. A fresh visible
instance on 10431 loaded the same DLL and replayed the saved recording with
both views. Preserve other sessions instead of assuming they are disposable.

**Rejected:** repeatedly asking the user to re-enter an already correct path;
force-closing all Logic processes; treating an old process's missing-analyzer
message as proof of a broken DLL.

**Evidence:** [real Logic integration](VALIDATION.md#logic-2-integration-completed)
and [export hashes and intervals](tests/fixtures/logic2-integration.json).

## 2026-10-26  Separate decoder sampling artifacts from actual card CRC rejection

**Why:** sampling CMD exactly at captured CLK transitions corrupted startup
annotations in the user's new recording. A +12 ns offset recovered genuine
commands, but independent raw decoding still found the card rejecting block
3 with status 101 and the host aborting via CMD12. Outgoing lane CRCs passing
at a logic analyzer does not establish what the card sampled. The decoder
also accepts initial CMD-low as a frame start, producing a phantom CMD63
across a startup clock gap; startup resynchronization remains unimplemented.

**Rejected:** treating every analyzer CRC error as a firmware/card command
error; declaring the three-block transaction a full image; claiming the
27-ohm resistor or a decoder offset guarantees reliability; globally changing
the default offset without checking both clock rates and sample rate.

**Evidence:** [saved-capture analysis](VALIDATION.md#october-26-user-recording-command-sampling-and-write-abort)
and [source/export hashes](evidence/2026-10-26-session2.json). No live hardware
operation or DLL replacement was needed to establish these findings.

## 2026-10-26  Recheck sampling phase when the firmware launch phase changes

**Why:** restoring the historical12.5MHz/default-phase profile completed a
full3,730-block write, but the earlier rising+12ns setting produced2,379
false bad-data annotations while every card status was positive. Sampling
the same recording at rising+32ns recovered all four lane CRCs on every
block. Raw DAT0 busy boundaries did not move. A slower clock alone does not
select a suitable analyzer sampling instant.

**Rejected:** globally reusing the25MHz/NEGEDGE capture's offset, interpreting
these decoder CRC annotations as card rejection, or hiding invalid frames.
The startup phantom CMD63 remains explicitly invalid.

**Evidence:** [full capture and export identities](evidence/2026-10-26-sd125.json),
local `tmp/bringup/sd125-probed-20261026/decoded-offset8/`. Hardware/firmware
selection rationale belongs in [RAW capture notes](../../firmware/capture-raw/NOTES.md).
