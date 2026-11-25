# Boot timing notes

## 2026-10-17  Keep the ROM-loaded image small and retain the required header alignment

**Why:** the matched boot matrix measured about 0.262 ms/KiB of extra initial image, consistent with ROM loading the complete image through 32 MHz single-line NOR before handoff. Later code belongs in a staged loader when it can overlap useful work. N6 header 2.3 requires payload offset `0x400` and 32-byte start/end alignment; the independently inspected ST image confirms the padding.
**Rejected:** selecting quad/octal initial reads through an undocumented header field, or deleting header padding as a supported size optimization. The 64-byte tiny-image reduction did not establish an overall speed gain beyond baseline variation.
**Evidence:** commit `0156f088`; [size matrix](optimization-results-2026-10-17.md); [header cross-check](header-evidence.md); [documented limits](experiments/optimization-limits.md).
**Provenance:** reconstructed from the October 17 measurements and primary-source cross-checks on 2026-10-24; these reasons were recorded in those sources.

## 2026-10-17  Treat the cold ROM delay as outside this reversible software optimization

**Why:** `RCC_RDCR.EADLY` returns to five milliseconds at power-on; writing it after handoff cannot recover that delay in the same discharged cold boot. Boot clock/source alternatives involve different hardware or OTP policy. The optimization pass deliberately retained the delivered ROM/fuse configuration.
**Rejected:** claiming a later register write removes the current cold-start delay, treating a powered reset as an equivalent cold result, or interpreting a trace label as an undocumented faster boot protocol. No OTP experiment was performed.
**Evidence:** commits `fcc04289`, `0156f088`; [ROM limits and references](experiments/optimization-limits.md); [ROM and reset assessment](../capture-timing/rom-and-reset-floor.md).
**Provenance:** reconstructed from the October 17 scoped optimization decision and cited manuals on 2026-10-24.

## 2026-10-17  Qualify cold boot with external rails instead of a reset edge alone

**Why:** NRST released while main VDDIO was still rising; measured ramp and ROM work overlap. The matrix therefore checked sustained discharge/restoration on all three probed rails and excluded debugger commands during measured startup. Rail threshold crossings are bench reference points, not PGOOD. Unprobed core, AON and flash supplies remain outside that qualification.
**Rejected:** subtracting the entire rail ramp from reset-to-marker time, treating commanded power-off as proven discharge, or using a later TIM2 count or unknown ROM-event interval as a continuous power-on stopwatch. Fixed JS110 range did not demonstrate faster startup in its matched pair.
**Evidence:** commit `0156f088`; [boot matrix, range comparison and trace limits](optimization-results-2026-10-17.md); [trace decoder provenance](experiments/rom-trace/README.md).
**Provenance:** reconstructed from the recorded external captures and rejected interpretations on 2026-10-24.

## 2026-10-17  Preserve ROM peripheral state for normal-boot NOR maintenance

**Why:** the standard external loader's full initialization stalled and eventually left the debugger transport unresponsive. A small bounded RAM helper succeeded by preserving the already-working ROM clocks, XSPI1-to-port-2 routing and single-line read setup. Read-only identity/full-sector checks preceded write qualification; current contents and complete post-write readback remain essential.
**Rejected:** repeatedly rerunning the failing external-loader initialization, assuming cache disable proved its root cause, or restoring an unguarded non-debug image merely to reproduce a historical baseline. The original exact backup remains evidence.
**Evidence:** commit `0156f088`; [programmer qualification](evidence/nor-programmer-20261017/README.md); [read-first helper](experiments/rom-nor-maintenance/README.md); [cache experiment](experiments/cache-prep/README.md).
**Provenance:** reconstructed from the successful and failed October 17 maintenance experiments on 2026-10-24; the external-loader failure cause remains unresolved.

## 2026-10-17  Use explicit RAM execution and verify architectural context

**Why:** CubeProgrammer `-g` without an address selected `0x08000000` despite an earlier PC write and produced a HardFault. The reviewed RAM workflow sets PC/XPSR then uses `-run`, ending in an awake branch loop. CubeProgrammer disconnect may resume execution, so a halt-dependent operation must share the connection that establishes halt.
**Rejected:** treating a prior halt as persistent, using BKPT as a safe no-debug terminal, or rewriting PC/XPSR as an architectural exception return. Cache-safe, privileged Thread context still has to be verified; see the [camera maintenance note](../capture-timing/NOTES.md#2026-10-17--early-recovery-must-prove-a-safe-maintenance-context).
**Evidence:** commits `fcc04289`, `0156f088`, `1affc642`; [cache-prep failures and revised entry](experiments/cache-prep/README.md); [diode test connection discipline](js110-recovery-output.md).
**Provenance:** reconstructed from observed programmer behavior and the revised helper procedure on 2026-10-24.

## 2026-10-17  Recover the exact ST-LINK interface before requesting a cable intervention

**Why:** aborting/resetting this debugger's three WinUSB bulk pipes recovered the observed `DEV_USB_COMM_ERR`; a bounded AP1 register read then confirmed transport recovery. The shared hub also carries measurement hardware, so a hub-wide reset would disturb unrelated devices.
**Rejected:** treating successful pipe API calls alone as recovered debug access, repeatedly retrying the failed flash loader, or resetting the whole shared hub. The helper is not a proven electrical debugger power cycle or cure for every hang.
**Evidence:** commit `0156f088`; [recovery method and guarded identities](stlink-recovery.md); [actual pipe recovery log](evidence/stlink-recovery-20261017/pipe-recovery.jsonl).
**Provenance:** reconstructed from the October 17 incident and bounded recovery design on 2026-10-24.

## 2026-10-17  Do not equate JS110 GPIO supply-off with a released recovery input

**Why:** with the user's PE1-anode/OUT0-cathode diode, powered 3.3 V OUT0 LOW/HIGH selected recovery/release correctly. Commanding the GPIO bank to 0 mV while retaining OUT0 LOW still held PE1 LOW against its pull-up. Restoring the helper's starting settings could therefore reassert recovery.
**Rejected:** using bank-off as a floating output or normal-boot selection. The functional input tests did not measure analog margin, leakage or powered-off isolation; the later VCP route supersedes this external control for the current bench, not the finding.
**Evidence:** commits `54cddd3e`, `1affc642`; [diode matrix and failed release](js110-recovery-output.md); [qualified guard](../capture-timing/recovery_gpio/README.md).
**Provenance:** reconstructed from the two powered matrices and failed supply-off row on 2026-10-24.

## 2026-10-24  Require fresh WIP and WEL completion evidence after NOR writes

**Why:** the old helper checked WEL in the same cached status byte that first reported WIP clear. The device's documented completion sequence calls for fresh status reads until both are clear. V2 retains bounded polling and full readback, and preserves the original failure status before cleanup.
**Rejected:** requiring that software observe WIP become set, clearing WEL to manufacture success, or retrying program/erase inside completion polling. The successful v2 run saw no WIP-clear/WEL-pending samples, so it did not reproduce or prove the cause of the earlier failures.
**Evidence:** commit `24627360`; [v2 rationale and hardware follow-up](experiments/rom-nor-programmer-v2/README.md); [preserved incidents](../capture-sd/evidence/2026-10-24-normal-profile/nor-maintenance/README.md).
**Provenance:** reconstructed from the October 24 UTC incident record, device documentation and qualified replacement helper on 2026-10-24.

## 2026-11-25  Beta board boot flash: Winbond W25Q128JWPIQ

**Why:** the user left the boot flash to the reviewer: "pick an available part that will work". The pick is the Winbond W25Q128JWPIQ: 1.8 V, 128 Mbit, 8-pad WSON 6 x 5 mm. Its datasheet is stored, DigiKey search snippets showed about 15,000 to 20,000 in stock, and the boot ROM needs nothing it lacks: UM3234 reads a serial NOR on PN1, PN2, PN3 and PN6 with command 0Bh on one line, a 24-bit address and 8 dummy cycles, with no device set-up, and the project's stage-1 loaders reuse that read. The Nucleo's Macronix MX25UM51245GXDI00 was the first choice for zero new tooling, but the same snippets showed none in stock at DigiKey's US site, and a BGA-24 with twelve nets cannot be swapped in after layout.
**Rejected:** the Nucleo's part, kept only as an alternate if it can be bought; the 256 Mbit Macronix sibling, which is out of stock too and loses the exact-part match; a BGA-24 footprint that would take either maker's part, as a hedge that costs twelve nets.
**Costs accepted, none done yet:** a new loader for a blank board, since ST's stock loader covers only the Nucleo's part; the NOR helpers and installer check the Macronix ID C2 80 3A and security register 2Bh and must change to EF 60 18 and Winbond's status registers (a healthy part reads QE = 1); the WSON-8 part has no reset pin, so loaders must stay in single-line reads, avoid chip erase, and recover a busy flash by a power cycle. A blank flash gives SWD access only in development boot, so BOOT1 (PA6) and BOOT0 need pads, which adds to "ST-LINK connector only".
**Evidence:** UM3234 Rev 5 pages 10 to 16 and 28 and the stored W25Q128JW datasheet, read by a researcher and re-read by a second checker; stock figures are undated search snippets, because DigiKey's pages cannot be opened from the review environment. Nothing was run on hardware. The live DigiKey listing should be looked at before layout.
