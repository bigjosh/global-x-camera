# ST CSI driver issues and upstream fixes

Research checked October 17, 2026. Read-only GitHub REST API inspection included complete issue bodies/comments, current commits, source, and file history. No hardware or firmware changed.

## Does a public issue report our error or a related driver defect?

### Takeaway

There is an independently reported, ST-acknowledged issue for the exact duplicate E3 register write we found. It remains open and uncorrected upstream; neither the report nor ST's reply establishes that it causes the startup ECTRL flag.

### Cited Findings

- [HAL issue #7](https://github.com/STMicroelectronics/stm32n6xx-hal-driver/issues/7), September 18, 2026: duplicate E3 write, proposed low-byte E2 correction, no measured ECTRL impact. [ST acknowledged September 21](https://github.com/STMicroelectronics/stm32n6xx-hal-driver/issues/7#issuecomment-5761729608); [September 22](https://github.com/STMicroelectronics/stm32n6xx-hal-driver/issues/7#issuecomment-5774767031) supplied internal reference `b2632d2083abc7902ea7dbb0ecda1e5f`. Still open October 17.
- The current HAL main commit is [d88071ed0adc1991a5daed6f20ab311f80bb33b7](https://github.com/STMicroelectronics/stm32n6xx-hal-driver/commit/d88071ed0adc1991a5daed6f20ab311f80bb33b7), committed June 8, 2026, release v1.4.0. Its [lines 734–737](https://github.com/STMicroelectronics/stm32n6xx-hal-driver/blob/d88071ed0adc1991a5daed6f20ab311f80bb33b7/Src/stm32n6xx_hal_dcmipp.c#L734-L737) still contain the duplicate E3 write.
- The camera demo's current main is still our pinned [e9441cdbb5072a6d3bcef1a5ca4e4d80f850283a](https://github.com/STMicroelectronics/x-cube-n6-camera-capture/commit/e9441cdbb5072a6d3bcef1a5ca4e4d80f850283a), September 9, 2026, v2.0.1. The full public [demo issue list](https://github.com/STMicroelectronics/x-cube-n6-camera-capture/issues?q=is%3Aissue) contains only power-consumption and Nucleo-project-code questions; the inspected [CubeN6 issue list](https://github.com/STMicroelectronics/STM32CubeN6/issues?q=is%3Aissue) has no CSI state-sequence report.
- A separate [STM32N6/IMX219 forum report](https://community.st.com/t5/stm32-mcus-products/stm32n6-imx219/m-p/839041/highlight/true) explicitly reports lane 0 and 1 control flags immediately upon enabling streaming, but with no image data. ST replies with IMX219-specific lane/bitrate setup guidance. This is the same symptom class on N6, a different sensor and failure outcome, not confirmation of our cause. The forum researcher should supply the full-thread context.

### Inferences

- Public issue #7 independently corroborates a concrete code defect; it is not a ready-made fix for our warning. Our already-recorded isolated E2/E3 correction did not remove ECTRL, so causation must remain unproven. [Local experiment record](../../firmware/capture-timing/csi-startup-errors.md#phy-setup-issues-found-in-the-source).

### Gaps

- Searches of GitHub issues for `ECTRLDL1`, `ECTRL STM32`, and `DPHY_CTRL STM32` returned no results. That is a scoped search result, not proof that nobody has encountered our exact VD56G3 startup case. No direct issue with our sensor, usable first frame, and pre-exposure lane-1 timing was found in this search.

## Are the power-down naming issue and other HAL defects fixed?

### Takeaway

The power-down issue was a misleading register name/documentation problem, now corrected, rather than a demonstrated electrical startup fix. The upstream interrupt-disable register mistake and hardcoded CCFR remain present.

### Cited Findings

- [HAL issue #2](https://github.com/STMicroelectronics/stm32n6xx-hal-driver/issues/2) opened September 11, 2025, asks whether setting `CSI_PCR_PWRDOWN` powers the receiver down. ST's [October 28 reply](https://github.com/STMicroelectronics/stm32n6xx-hal-driver/issues/2#issuecomment-3455789593) says the bit description is under revision and will be renamed `NPWRDOWN`, with 1 meaning not powered down. ST [closed it July 2, 2026](https://github.com/STMicroelectronics/stm32n6xx-hal-driver/issues/2#issuecomment-4864328592), identifying firmware v1.4.0 as the release containing the correction. Internal reference 217473 was posted September 15, 2025.
- The actual [v1.4.0 commit diff](https://github.com/STMicroelectronics/stm32n6xx-hal-driver/commit/d88071ed0adc1991a5daed6f20ab311f80bb33b7) changes the two lane-enable expressions from `CSI_PCR_PWRDOWN` to `CSI_PCR_NPWRDOWN`; it does not add a new power-up sequence or delay there. Other DCMIPP changes in that release concern correctly replacing the capture-mode bit field.
- Current [lane-0 handler line 3130](https://github.com/STMicroelectronics/stm32n6xx-hal-driver/blob/d88071ed0adc1991a5daed6f20ab311f80bb33b7/Src/stm32n6xx_hal_dcmipp.c#L3124-L3144) and [lane-1 handler line 3252](https://github.com/STMicroelectronics/stm32n6xx-hal-driver/blob/d88071ed0adc1991a5daed6f20ab311f80bb33b7/Src/stm32n6xx_hal_dcmipp.c#L3246-L3266) still call `__HAL_DCMIPP_CSI_DISABLE_IT`, which [writes IER0](https://github.com/STMicroelectronics/stm32n6xx-hal-driver/blob/d88071ed0adc1991a5daed6f20ab311f80bb33b7/Inc/stm32n6xx_hal_dcmipp.h#L1580). The separate [DPHY disable macro writes IER1](https://github.com/STMicroelectronics/stm32n6xx-hal-driver/blob/d88071ed0adc1991a5daed6f20ab311f80bb33b7/Inc/stm32n6xx_hal_dcmipp.h#L1716). Thus this bug is not fixed by updating to current upstream HAL.
- Current [PHY setup lines 724 and 740](https://github.com/STMicroelectronics/stm32n6xx-hal-driver/blob/d88071ed0adc1991a5daed6f20ab311f80bb33b7/Src/stm32n6xx_hal_dcmipp.c#L723-L741) still write hardcoded CCFR `0x28`, alongside the duplicate E3 writes.

### Inferences

- Do not clear NPWRDOWN in pursuit of issue #2: ST explicitly says setting it releases power-down. That issue supplies no evidence for the source of our ECTRL transition. [ST explanation](https://github.com/STMicroelectronics/stm32n6xx-hal-driver/issues/2#issuecomment-3455789593).
- An upstream refresh alone is not a justified repair for our warning: the relevant source defects persist in the inspected release, and the fixed naming issue does not change the receiver's intended power state. [Current setup](https://github.com/STMicroelectronics/stm32n6xx-hal-driver/blob/d88071ed0adc1991a5daed6f20ab311f80bb33b7/Src/stm32n6xx_hal_dcmipp.c#L723-L750).

### Gaps

- No public ST acknowledgment specifically addressing the incorrect IER0 disable macro or hardcoded CCFR was found in the inspected issue lists. Direct source evidence establishes current behavior, not ST's private investigation status.

## Does ST's Linux CSI driver reveal a known remedy or alternative sequence?

### Takeaway

ST's MP25 driver supports the E2/E3 and clock-derived CCFR corrections as vendor implementation precedent. It supplies no documented repair for this particular N6 startup warning, and cannot automatically qualify a change on N6.

### Cited Findings

- At the latest commit affecting that source on `v6.6-stm32mp`, [6d1d1c4c6647a0160114fbd4dbc91699b42ea687](https://github.com/STMicroelectronics/linux/commit/6d1d1c4c6647a0160114fbd4dbc91699b42ea687), March 23, 2026, [PHY setup](https://github.com/STMicroelectronics/linux/blob/6d1d1c4c6647a0160114fbd4dbc91699b42ea687/drivers/media/platform/st/stm32/stm32-csi.c#L576-L618) uses a 1 µs test-clock pulse, computes CCFR from the configuration-clock rate, writes low byte E2/high byte E3, enables lanes, releases power-down, enables PHY, and clears forced-state settings. It retains E4 `0x11`. These are implementation observations, not a documented N6 erratum workaround.
- Its [interrupt handler](https://github.com/STMicroelectronics/linux/blob/6d1d1c4c6647a0160114fbd4dbc91699b42ea687/drivers/media/platform/st/stm32/stm32-csi.c#L1119-L1147) reads SR0/SR1, acknowledges error flags through FCR0/FCR1, and increments per-error counters. It does not mask the corresponding error after first occurrence or automatically reset the link there.
- The [June 25, 2025 lane-merger fix](https://github.com/STMicroelectronics/linux/commit/908d8a4fd19794ff30a10ea994094f0b919362f1) requires configuring unique routing for every lane, including disabled lanes. Its commit message does not identify ECTRL as the symptom. The other broadly titled [CSI driver fix](https://github.com/STMicroelectronics/linux/commit/f8f3f63664439904b7a51be934aed589c97cfa0f) fixes an ARM32 integer-division link error, not PHY initialization.

### Inferences

- Counting repeated raw error events without masking is a useful diagnostic precedent for further experiments. The Linux counter implementation itself does not prove startup control errors are benign. [Linux handler](https://github.com/STMicroelectronics/linux/blob/6d1d1c4c6647a0160114fbd4dbc91699b42ea687/drivers/media/platform/st/stm32/stm32-csi.c#L1119-L1147).

### Gaps

- No inspected Linux commit documents a cure for a transient pre-exposure lane-1 ECTRL on VD56G3. The MP25 implementation is supporting evidence for code review, not interchangeable silicon qualification.
