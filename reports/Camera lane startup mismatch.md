# Sequence clock and data receivers separately

Research and bench evidence, October 17, 2026: NUCLEO-N657X0-Q, CAM-6G3-073CLR, VD56G3 revision `0x3110`.

**A working startup sequence enables the clock receiver early and the data receivers after sensor START acknowledgment and STREAMING.** Three cold starts captured the **first** native RAW10 image with no recorded startup or through-frame CSI errors. Exposure began in **24.610–25.077 ms** after reset; complete images arrived in **46.471–46.938 ms**. Every image showed a recognizable workshop scene and passed integrity checks. Lane-1 ECTRL still occurs during later sensor shutdown. This is a working candidate on this board, not proof of the exact offending electrical transition. ([v33 evidence](../firmware/capture-timing/evidence/2026-10-17-v33-delayed-data/README.md))

## Independent lane enables make the sequence possible

The STM32 exposes separate clock/data receiver controls. Before releasing PHY digital reset, v33 uses `CSI_PCR=0x03`: clock enabled, both data modules shut down. After sensor readiness it sets only the data-enable bits, producing `PCR=0x0F`, qualifies data Stop, arms capture, and requests one exposure. The existing error masks and handler remain unchanged. ([RM0486 §§40.9.2, 40.10.1](https://www.st.com/resource/en/reference_manual/rm0486-stm32n647657xx-armbased-32bit-mcus-stmicroelectronics.pdf), [implementation](../firmware/capture-timing/late_phy/README.md#v33-clock-lane-early-data-lanes-after-streaming))

| Control or observation | What it establishes |
| --- | --- |
| `CSI_CR.CSIEN` | Host processing enable; not PHY reset |
| `CSI_PRCR.PEN=0` | PHY digital section held in reset |
| `CSI_PCR.CLEN` | Independent clock receiver enable |
| `CSI_PCR.DL0EN/DL1EN` | Independent data-module enable/shutdown |
| Sensor STREAMING | Firmware state; no explicit LP-11 guarantee |
| Receiver Stop flags | Presently recognized states, not transition history |

Clock-active status remains clear in the clock-only snapshots and first appears after data enable. **We observed successful sequencing, not an earlier measured clock lock.** Sensor readiness likewise does not establish an electrical state independently of the receiver observations. ([Sensor command states](https://www.st.com/resource/en/user_manual/um2602-how-to-integrate-and-configure-the-vd56g3-vd66gy-and-vd16gz-devices-from-a-hardware-and-software-perspective-stmicroelectronics.pdf), [raw v33 evidence](../firmware/capture-timing/evidence/2026-10-17-v33-delayed-data/README.md))

## Comparisons separate startup from image transfer

The experiments preserve native geometry, gain and exposure, using documented I²C follower operation.

| Experiment | Result |
| --- | --- |
| [v30d: whole receiver early, continuous clock](../firmware/capture-timing/evidence/2026-10-17-v30d-phy-sequence/README.md) | Startup lane-1 error; valid first image |
| v30d: whole receiver late | No startup error, but no frame or clock-active indication |
| [v31: noncontinuous clock](../firmware/capture-timing/evidence/2026-10-17-v31-phy-sequence/README.md) | Same contrast: early works with warning; late loses first image |
| [v32: late receiver, second trigger](../firmware/capture-timing/evidence/2026-10-17-v32-second-trigger/README.md) | First image lost; second received after clock/data Stop, without receiver reset or rearming |
| [v33: clock early, data late](../firmware/capture-timing/evidence/2026-10-17-v33-delayed-data/README.md) | Three first-image successes; no recorded startup/transfer errors |

The older v21 trace also places ECTRL before FSYNC, so the exposure trigger is unnecessary for the startup error. In v33, every nonzero error snapshot lies between the before-stop and after-stop records, after image completion. **Shutdown remains a separate unresolved transition.** The original ST-based smoke application already saw the same error class. ([v21 timing](../firmware/capture-timing/evidence/2026-10-17-v17-through-v24/captures/v21-follower-cold/timing.json), [original comparison](../firmware/capture-timing/csi-startup-errors.md), [v33 phase checks](../firmware/capture-timing/evidence/2026-10-17-v33-delayed-data/extra/analysis/phy-v33-phase-verification.json))

## The electrical mismatch remains an inference

The sensor specifies camera pins low in reset, but does not document their complete transition into qualified D-PHY Stop or expose an explicit force-LP-11 control. Normal high-speed entry, in receiver `(P,N)` order, is `11 → 01 → 00 → HS-0 → synchronization → data`. Observing only part of initialization or an unexpected intermediate state could explain ECTRL. The comparisons support that explanation, but **do not establish sensor noncompliance or a particular invalid edge**. Physical pair polarity must be verified before interpreting `01` versus `10`. ([VD56G3 datasheet](https://www.st.com/resource/en/datasheet/vd56g3.pdf), [UM2602](https://www.st.com/resource/en/user_manual/um2602-how-to-integrate-and-configure-the-vd56g3-vd66gy-and-vd16gz-devices-from-a-hardware-and-software-perspective-stmicroelectronics.pdf), [NXP D-PHY explanation](https://www.nxp.com/docs/en/application-note/AN13573.pdf))

The STM32 names D-PHY v1.2; the complete normative specification is member-only. No explicit sensor PHY version was found. Public manufacturer material supports diagnosis rather than a compliance conclusion. Three trials on one unit also do not qualify every exposure, board, temperature or power sequence. ([STM32 datasheet](https://www.st.com/resource/en/datasheet/stm32n657x0.pdf), [MIPI access policy](https://www.mipi.org/specifications/d-phy))

## Probing can explain the edge but is optional for integration

The LP8 can observe nominal 0/1.2 V LP states using its **1.2 V family, approximately 0.6 V threshold**, rather than our existing 3.3 V setting. With USB 3 and analog disabled it supports four digital channels at 500 MS/s or eight at 100 MS/s. Each input adds **10 pF**, however, and genuine high-speed signaling also reads as `00`. A digital trace cannot establish LP-only behavior. Attachment requires verified access/polarity and an unprobed/attached comparison. No MIPI probes were added. ([Saleae specifications](https://downloads.saleae.com/specs/logic_pro_8_data_sheet.pdf), [thresholds](https://www.saleae.com/support/specifications-hardware/electrical-characteristics/supported-voltages))

The DS1054Z can inspect LP ramps/skew, but its 50 MHz bandwidth and passive probes cannot qualify the 804 Mb/s eye. The AD3 was unnecessary for these software experiments. ([Rigol specifications](https://www.rigol.com/dam/global/downloads/brochures/en/data-sheet/oscilloscopes/DS1000Z_DataSheet_EN.pdf))

The initial diagnostic access stall was fixed with reset/clock guards, and debugger access recovered without jumper changes. Finally, the **original v25 baseline was restored byte-for-byte**, cold-capture checked, and left powered/debugger-accessible. JS110 ownership was released with physical rail verification; Logic 2 remains running. The working v33 candidate is preserved for integration, not installed as the selected baseline. ([Recovery evidence](../firmware/capture-timing/evidence/2026-10-17-v30d-phy-sequence/README.md#recovery-evidence), [final bench state](../firmware/capture-timing/evidence/2026-10-17-phy-sequence-final-state/README.md))
