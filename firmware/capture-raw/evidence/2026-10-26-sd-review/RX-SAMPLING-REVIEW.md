# SDMMC2 receive sampling review

October 26, 2026. Offline primary-source review after the bench owner reported that 50 MHz receive CRC failures persisted with PIO and IDMA and the separately tested slew/compensation profiles. No register change or hardware operation was made for this review.

## Conclusion

The existing `SELCLKRX=00` is the documented receive-clock choice for native 3.3 V Default Speed and High Speed without an external transceiver. It already feeds back the **SDMMC_CK pad**, rather than sampling against an unrelated internal divider. `NEGEDGE` controls transmission, not receive sampling. There is no documented single-bit setting that changes this native-HS receiver to the opposite sampling edge.

`SELCLKRX=01` is not an alternate edge: it selects a dedicated external `SDMMC_CKIN` signal. RM0486 Rev4 Table206/p1371 lists that signal for SDMMC1 and explicitly omits it for **SDMMC2**, the controller used by this board hookup. Selecting it cannot substitute for an absent physical feedback input.

`SELCLKRX=10` selects the DLYB tuned feedback path. The hardware can delay an RX clock at50 MHz, but that is not a documented drop-in replacement for the present DS/HS plus in-transfer hardware flow control. The manual assigns tuned feedback to SDR50/DDR50/SDR104/HS200 and requires different flow-control handling when it is selected. A phase sweep without satisfying those conditions would test a new operating regime, not repair a proven configuration mistake.

## Primary evidence

| Source | Relevant constraint |
|---|---|
| [RM0486 Rev4](../../../../datasheets/processor/STM32N6_RM0486_reference_manual.pdf), Table206, p1371 | SDMMC2 supports variable delay but does not implement external CKIN or external transceiver direction pins. |
| RM Table209, p1376 | `sdmmc_io_in_ck` is internally connected to the SDMMC_CK pin and is designated for DS/HS. Tuned `sdmmc_fb_ck` is designated for SDR50/DDR50/SDR104/HS200. |
| RM pp1377–1378, p1400/Fig240 | Default receive feedback derives from the clock pin. DLYB can tune that feedback; DS/HS without an external driver uses `sdmmc_io_in_ck`. Change receive-clock source only while CPSM and DPSM are idle. |
| RM pp1425–1426, sections30.7.1/30.7.2 | In-transfer clock-stopping flow control requires cycle-aligned receive data. The text directs tuned-feedback users to block-gap flow control; examples explain delays beyond one cycle, but do not grant an exception for a small tap in native HS. |
| RM p1433, CLKCR | `SELCLKRX=00` internal pad feedback, `01` external CKIN, `10` tuned feedback, `11` reserved. `BUSSPEED=0` includes DS/HS; `BUSSPEED=1` names SDR50/DDR50/SDR104/HS200. |
| RM pp1460–1463, DLYB | DLL lock range50–208 MHz; RX tap resolution1/32 period, nominally0.625 ns at50 MHz. Pure-delay bypass lacks voltage/temperature compensation. Delay configuration requires lock/selection acknowledgement; the anti-glitch bit is enabled at reset. These capabilities alone do not qualify an SD operating mode. |
| [DS14791](https://www.st.com/resource/en/datasheet/stm32n657x0.pdf), SD timing section; local Rev10 pp202–204 | HS host input setup3 ns and hold1.5 ns relative to clock. Slew, loading, voltage and compensation conditions apply. The diagram references receiving input timing to the clock edge; output launch selection is a separate characteristic. |
| [ES0620](https://www.st.com/resource/en/errata_sheet/es0620-stm32n6-series-device-errata-stmicroelectronics.pdf), Rev5 section2.5 | The listed SDMMC erratum concerns unchecked end bits, not an alternate RX phase or a documented50 MHz CRC workaround. |
| Pinned ST `stm32n6xx_hal_sd.c`, `SD_UltraHighSpeed()`/`SD_DDR_Mode()` | Tuned feedback is selected in the UHS/SDR104 path; external CKIN is selected in the DDR50/transceiver path. Ordinary50 MHz High Speed does not use these selectors. |

The generic H7 application note [AN5200](https://www.st.com/resource/en/application_note/dm00525510.pdf) also describes tuning, but an H7 delay-block recipe is not an N6/SDMMC2 native-HS qualification. N6-specific clock routing and flow-control constraints take precedence.

## What the failures do and do not establish

The parent reports that changing the receive transport to IDMA did not eliminate CRC failures. That weakens the hypothesis that CPU FIFO-drain gaps alone cause them; it does not prove an analog mechanism. Likewise, a digital analyzer's narrow pulse or omitted nibble does not identify ringing, threshold crossing, skew, or a sampling-window violation without suitable analog evidence. Delaying sampling could conceal one marginal data edge while leaving clock glitches or card-side timing uncorrected.

The documented choices at this point are to retain the qualified lower-frequency link, characterize clock/data integrity and setup/hold at the MCU/card with suitable probing, or treat a different clock frequency as an explicit, separately qualified experiment. A DLYB experiment would first need a complete reviewed clock/flow-control/tuning and ownership design; merely trying arbitrary `SELCLKRX` or tap values is not justified by these sources.
