# Native SD protocol and clock review

October 26, 2026. Offline review of the actual CMSIS driver and primary device/card documentation. This is not a 50 MHz hardware qualification. The root-owned [12.5 MHz experiment](README.md) supplies the physical baseline; this reviewer did not operate instruments. Code references name functions because concurrent reviewed-profile work can move line numbers.

## Findings and disposition

| Priority | Finding | Disposition |
|---|---|---|
| Required before 50 MHz | The existing 150 MHz kernel cannot produce 50 MHz using the integer `kernel/(2*CLKDIV)` divider. Truncating `150/(2*50)` selects 75 MHz. | The isolated review profile owns unused IC5 at PLL1/12 = 100 MHz, then uses CLKDIV=1. CPU, HCLK, NOR and camera clocks remain unchanged. |
| Required before 50 MHz | Native SD High Speed must be selected with CMD6. ACMD6 changes bus width only. | Check and switch function group1 to1 while still at25 MHz; validate the complete status block before acceleration. No 1.8 V/UHS switch. |
| Required timing choice | The HS output-valid specification is referenced to the preceding **rising** SDCLK edge. A falling launch at50 MHz would leave only a half-cycle for output propagation and card setup. | Use the post-rising launch option (`NEGEDGE=0`) for the HS operating phase, keeping the qualified falling-edge12.5 MHz baseline separate. This is a timing-budget decision; wire and readback qualification remain required. |
| Required ownership rule | ES0620 warns that a nondefault SDMMC clock mux can prevent ROM operation after software reset. | Restore SDMMC2SEL=0 with both clock sources running, then disable IC5. Uncertain failures retain ownership and require cold recovery rather than an unqualified warm reset. |
| Correctness fix | CMD7 can return R1b before any data API has programmed DTIMER. Reset DTIMER=0 gives an unusable busy allowance. | Reviewed profile sets the identification timeout before CMD7; bounded failure remains failure. |
| Correctness fix | A receive-abort drain limited to64 words does not cover the N6's256-word FIFO. | Reviewed profile drains at most256 words, then follows the manual's legal FIFO-reset/inactive checks. It never relabels the original read successful. |
| Correctness fix | CMD12 response completion does not prove its DAT0 busy interval has finished. Changing DCTRL fields during active DPSM is forbidden. | Keep configuration intact until fresh card/controller readiness; inspect sticky data/DMA errors before clearing them. |
| Qualification gap | The prototype has a27-ohm resistor midway along CLK, flying leads and probe-dependent historical failures. | Digital CRC/readback tests cannot establish analog/PVT margins. Preserve slew/compensation initially to isolate clock/protocol, then test those separately if needed. |
| Deferred discrepancy | RM prescribes DTMODE=3 for open-ended CMD18/CMD25, but ST HAL and the qualified driver use fixed DLEN with DTMODE=0, followed by CMD12. | Retain mode0 now; an isolated mode3 experiment must compare normal and abort behavior. No demonstrated image corruption has been attributed to this difference. |

## CMD6 High Speed contract

`high_speed_status_read()` issues ordinary CMD6, not CMD55/ACMD6, after proving TRAN/ready. The intended sequence is `CMD6(0x00FFFFF1)` check followed by `CMD6(0x80FFFFF1)` switch. Function group1 requests High Speed; other groups request no change. Both commands return R1 and exactly64 bytes of data. `DLEN=64`, `DBLOCKSIZE=6`, receive direction, and CMDTRANS match that transaction. CMD16 is unnecessary: switch-status length is fixed independently of the ordinary block length. Capability should be established from SCR SD_SPEC or the CSD switch-command class before issuing CMD6.

The checked fields are in **wire-byte order**, following the SD switch-status table:

| Bytes | Field and required interpretation |
|---|---|
| 0–1 | Maximum current in mA, big endian. Zero explicitly means error. The proposed200 mA ceiling is this prototype's conservative supply budget, not a universal SD limit. The specified current is averaged over one second; it does not establish the instantaneous peak. |
| 12–13 | Function group1 support bitmap. Bit1 must be present. |
| 14–16 | Six selected-function nibbles. Any `0xF` in switch mode cancels **all** requested switches; do not trust a favorable group1 result if another group failed. |
| 16 low nibble | Must equal1. In check mode this means the requested function is supported and ready to switch; in switch mode it identifies the resulting function. Merely seeing the support bitmap is insufficient. |
| 17 | Data-structure version0 or1. Reject reserved versions. |
| 28–29 | Version1 group1 busy bitmap, big endian. Bit1 must be clear before switching. For version0 this field is not defined and must not be interpreted. |

The parser review confirmed the original byte offsets, selected-function semantics and busy-bit location. It identified the need to reject error nibbles in all groups, explicitly label the current budget, and gate command support. Those findings were sent to the driver owner before bench use.

Data CRC, response CRC/index, exact word count, DATAEND, inactive DPSM and zero DCOUNT must all pass. The status is preserved in SRAM for independent decoding. An unsuccessful or ambiguous switch must not raise the clock or silently assume the card remained in its previous state. A busy result may be treated as a bounded initialization failure for this experiment; future general card support can add a bounded mode0 recheck rather than blindly repeating a mode1 switch.

After successful switch status, preserve at least eight SD clocks before increasing frequency. One microsecond at the still-running25 MHz clock supplies25 clocks; PWRSAV remains clear. A fresh CMD13 at25 MHz also consumes more than eight clocks, but the explicit delay documents the requirement. Native3.3 V HS retains `BUSSPEED=0`, `DDR=0`, and `SELCLKRX=0`; BUSSPEED is not the ordinary High Speed50 MHz selector.

## Clock ownership and electrical timing

`sd_clock_profile.h` accepts only the frozen PLL1/CPU/HCLK topology, with PLL1 and HSI enabled and ready. It refuses an already enabled IC5, any other selector using IC5, a nondefault prior SDMMC2 mux, or an enabled SDMMC2 controller. The direct competing selectors are MCO1, PER, and SDMMC1. Rejecting PER also protects every indirect PER consumer, including one that might be enabled later. MCO2 selector5 names IC15, not IC5.

The helper writes only the unused IC5 divider/gate and SDMMC2 mux. It verifies writes and bounds enable/disable polling to4096 iterations. Release switches back to the live default HCLK source before gating IC5, restores the previous IC5 register, and retains ownership on an uncertain restoration. The128-byte `sd_review_clock_proof` records before/after configuration, stage, original failure, cleanup failure and poll counts. All inspection is through RCC; no gated peripheral register is read. Failed initialization must either obtain a fresh idle proof and release this clock or explicitly retain ownership. Entry APIs also need to reject an off controller gate before accessing SDMMC registers, including a retry after partially completed deinitialization.

RM0486 describes NEGEDGE as **transmit phase**, not an input sampling-edge selector. With a100 MHz kernel/50 MHz SDCLK, NEGEDGE=0 launches on the kernel falling edge5 ns after SDCLK rises. DS14791 Rev10 Fig42 measures High Speed output-valid/hold relative to rising SDCLK; Fig43 measures default-mode output timing relative to falling SDCLK. Therefore it is incorrect to apply the HS6.5 ns output-valid number as a guaranteed falling-edge propagation delay. The local Rev10 diagram was directly rendered and inspected; the current Rev11 numerical timing table was independently checked online.

A representative card's HS requirements give6 ns input setup and2 ns hold, and up to14 ns card output delay. Combining the latter with the STM32's3 ns input setup at a20 ns clock period leaves about3 ns for interconnect/skew before additional effects. This is a budget illustration, not a guaranteed margin for the installed SanDisk. CLK/DAT output slew, return-path integrity, threshold crossing and load matter. A250 MS/s digital analyzer has4 ns sample spacing, so it can validate packets and expose gross edge defects but cannot certify those margins or diagnose analog ringing.

ST characterizes50 MHz with CLK OSPEEDR01 and data OSPEEDR00, rather than the prototype's uniform speed3. ES0620 also documents an I/O-compensation edge-distortion workaround. Neither is silently combined with the first clock/protocol experiment: the existing profile is retained initially, and separately controlled trials can follow. A production/PVT claim would need compliant loading, applicable compensation configuration, voltage/temperature coverage and analog timing evidence.

## Fixed length, STOP and overlap

The SD card sees an open-ended CMD25: ACMD23 is a preerase hint, not an automatic transaction terminator. The host knows the exact3730-sector length through DLEN, sends every block with its hardware CRC, then issues CMD12 and waits for fresh TRAN/ready plus physical DAT0 high and inactive host/DMA. The final saved marker and wire acceptance remain distinct from full SD/source-RAM equality.

RM0486 pp1416–1417 prescribes DTMODE11 for this open-ended protocol; p1440 calls mode00 block-count termination. However, ST's HAL_SD_WriteBlocks sets `SDMMC_TRANSFER_MODE_BLOCK` (zero) even when it issues CMD25. The current driver follows that vendor path and has complete qualified wire/readback evidence. The manual explicitly documents a mode11 distinction for suppressing the SDIO interrupt period after the last block until CMD12; SDIO interrupts are disabled in this memory-card path. The documentation does **not** establish complete mode equivalence.

The distinction cannot simply be resolved by saying the host knows its length: the manual's prescribed mode3 procedure explicitly stops at DATALENGTH too. Table228/p1414 describes predefined-count transfers by the card's behavior, where normal completion does not need CMD12. Our ACMD23 preerase hint does not create that card-side termination. This is a documentation discrepancy with unresolved practical effect in the present memory-card configuration, not evidence that the qualified HAL-style path is corrupting data.

Mode3 does not imply DATAEND on every sector: p1443 defines DATAEND at DATACOUNT=0 with no error/hold; Table220 distinguishes complete transfer end from per-block status. Any later mode3 trial should keep fixed DLEN, unchanged frequency/phase/slew, and CMDTRANS initiation, and verify exact packet count, CRC tokens, final busy, abort behavior and full readback. Do not use DTEN initiation with mode3.

Host IDMA moves memory to the FIFO; hardware serializes the four lanes and waits through each card-exposed busy interval. CPU and camera capture can overlap that work, and the card may internally overlap programming with later reception. The host cannot transmit into a DAT0-busy interval as though it were an extra free buffer. Existing transfer counters include these stalls; subtracting them from a wall-time total does not isolate physical flash programming time. At25 MHz the measured transfer was already close to the framed wire limit, so frequency and overlap with capture are more promising than removing short command setup calls. Required ready/CRC/ownership checks remain until their redundancy is proved at the same transaction boundary.

## Verification boundary

### Receive flow control and the isolated IDMA-read experiment

RM0486 section30.7.1 (pp1424–1426) explicitly stops SDMMC_CK and freezes its serial state machines when the receive FIFO cannot accept data. AHB-side reads continue, and reception resumes when the FIFO becomes half empty. This is valid for the current BUSSPEED0, cycle-aligned Default/High Speed path. Variable-delay/UHS modes require different block-gap behavior; changing BUSSPEED or DLYB merely to alter pauses would change the electrical protocol and is not this experiment.

The retained PIO read path drains16 words on each half-full pass, while the N6 FIFO holds256 words and RM p1399 recommends draining until empty. Repeated full/half-empty gating is therefore plausible at50 MHz. The root reported intermittent DCRCFAIL and digitally observed narrow CLK pulses; neither proves that hardware flow control itself generates a glitch. A logic-analyzer one-sample pulse at250 MS/s is not an analog pulse-width measurement. Normal flow-control pauses should preserve legal clock edges and data alignment, rather than authorize malformed short pulses.

SD Physical Layer section4.4 explicitly permits clock stopping during data transfer to avoid underrun/overrun. Its completion restrictions still apply, including eight clocks after a completed transaction, continuous identification clocks or sufficiently frequent ACMD41 polling, and a clock edge to release DAT0 busy. IDMA does not remove those requirements or guarantee a perfectly continuous bus under arbitrary memory contention.

The separate `SD_IDMA_READ=1` reviewed RAM profile retains HWFC and replaces only the `sd_read_blocks()` receive transport with single-buffer IDMA. It supports CMD17 for one sector and CMD18/CMD12 for multiblock reads, splitting requests at512 sectors (16 at100 kHz). Thus a262,144-byte host read becomes one transaction rather than eight64-sector PIO transactions; payload alone is10.486 ms at four-bit50 MHz. Reduced command count is an additional changed variable and must be disclosed in throughput comparisons.

The implementation checks an enabled controller gate before any SDMMC register access, word-aligned secure AXI destination extent using64-bit arithmetic, disabled D-cache and both SDMMC configuration-port/master security prerequisites. The owner must supply enabled writable SRAM outside live code, proofs and retained original pixels. It configures receive direction, fixed DLEN, IDMABASER and IDMAEN before CMDTRANS. DMA/data errors take precedence over DATAEND. Success requires DATAEND, inactive DPSM and zero DCOUNT before releasing IDMA; multiblock completion then requires checked CMD12 and fresh card/controller readiness before clearing DCTRL/status. CPU code never accesses the receive FIFO while IDMA owns it. A failed abort retains ownership and does not validate partial destination data.

ST's pinned `HAL_SD_ReadBlocks_DMA()` supplies an independent matching setup reference. RM pp1401–1404 specifies single-buffer memory completion, and section30.6.2 supplies the IDMA-owned abort behavior. Offline tests execute the actual driver with modeled DMA destination writes and cover1/2/64/512/513-sector exact contents and guards, command/CRC/DMA/timeouts, DATAEND-plus-error precedence, residual DCOUNT, stuck abort, late CMD12 errors, end-of-card address exception, DWT wrap and rejected cache/security/gate/range conditions. These are implementation tests; sustained physical readback and source-image equality remain the bench owner's next qualification.

`test_sd_clock_profile.py` passes actual-helper RCC ownership/failure/write-order tests and ARM compilation with the real pinned CMSIS header. These cover rejected source profiles and consumers, refused divider/mux/gate writes, bounded timeouts, cleanup retries and retained ownership. Driver command/model tests separately exercise protocol and failure branches. Simulated registers do not establish silicon behavior or wiring quality.

The physical admission sequence is: prove one readable sector after High Speed negotiation; compare complete pattern and camera slots to retained source RAM; test long-exposure progressive PIO independently of completed-frame IDMA; inspect complete bus/CRC/final-busy behavior; then measure repeat cycles and energy. Failed attempts remain evidence. A successful write alone does not qualify reads, a single clean capture does not establish production reliability, and an awake diagnostic does not qualify Standby recovery.

## Final error and shutdown review

The reviewed paths retain the first operation error even when a later abort obtains idle and deinitializes successfully. PIO abort owns CPU FIFO draining/reset only while IDMA is off; IDMA abort leaves FIFO handling to hardware and waits for inactive DPSM before disabling IDMA. An unsuccessful cleanup keeps controller ownership explicit. A ready flag means quiescence, not valid image bytes.

`complete_storage()` does not reenter an unreturned SD call. `terminal()` enters Standby only on a zero-result capture, and `raw_storage_shutdown_ready()` additionally requires complete camera/slot accounting, successful deinit, released controller/timer ownership, fresh ready status, and no operation or cleanup errors. A failed initialization or transfer therefore cannot become successful low-power completion merely because cleanup worked. The new startup cache is invalidated on those errors and supplies no replacement for these guards.

This offline review found no new blocker in the error-to-shutdown contract. The fixed-length mode0 versus RM mode3 discrepancy remains explicitly deferred above; the manual's mode3 recipe also uses DATALENGTH, so known host length alone does not resolve it. Six failed 50 MHz read-profile trials were reported by the bench owner, including receive IDMA. No startup optimization or successful write should be presented as resolving that physical read-link qualification.

## Primary sources

- [STM32N6 RM0486](../../../../datasheets/processor/STM32N6_RM0486_reference_manual.pdf), Rev4: clock Fig59 and IC5/CCIPR8 registers; SDMMC Table211/p1377 and NEGEDGE/p1433; Table220/p1394; stop procedure pp1416–1417; DCTRL pp1439–1440; status p1443.
- [STM32N6 DS14791, current official revision](https://www.st.com/resource/en/datasheet/stm32n657x0.pdf), Rev11 September2026, section5.3.21 and HS timing figure; [local Rev10](../../../../datasheets/processor/STM32N657X0_DS14791_datasheet.pdf), pp202–204, Tables93–95/Figs42–43 used for direct diagram inspection.
- [STM32N6 ES0620 errata](https://www.st.com/resource/en/errata_sheet/es0620-stm32n6-series-device-errata-stmicroelectronics.pdf), Rev5 sections2.2.19–2.2.22: supply/access prerequisites, I/O compensation and SDMMC mux/reset requirement. Local searchable copy: `tmp/hardware-review/mcu/STM32N6_ES0620_errata.txt`.
- [SD Physical Layer Simplified Specification5.10](https://www.sdcard.org/cms/wp-content/themes/sdcard-org/dl.php?f=Part1_Physical_Layer_Simplified_Specification_Ver5.10.pdf), section4.3.10; [version6.00](https://www.sdcard.org/cms/wp-content/themes/sdcard-org/dl.php?f=Part1_Physical_Layer_Simplified_Specification_Ver6.00.pdf), function selection and native3.3 V HS. The locally readable version2.00, `tmp/hardware-review/sd-breakout/SD-Physical-Layer-v2-research.pdf`, printedpp31–39, was independently checked for exact status-bit layout, zero-current error and all-groups cancellation semantics.
- [Kingston SDCIT timing specification](https://www.kingston.com/datasheets/SDCIT-specsheet-8gb-32gb_en.pdf), pp15–16: representative default/HS card timing; not the installed SanDisk's product qualification.
- Pinned ST source: `tmp/bringup/x-cube-n6-camera-capture/STM32Cube_FW_N6/Drivers/STM32N6xx_HAL_Driver/Src/stm32n6xx_hal_sd.c`, `HAL_SD_WriteBlocks` and `SD_SwitchSpeed`; corresponding LL header defines `SDMMC_TRANSFER_MODE_BLOCK=0`.
