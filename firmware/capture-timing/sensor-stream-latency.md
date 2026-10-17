# Investigating sensor START to first exposure

Offline research, October 17, 2026. Proposed experiments remain hypotheses until a corresponding bench result is recorded. Preserve native 1120 × 1364 RAW8, manual gains, first-snapshot association, the visible LED panel, and all CSI error history.

The observed approximately 5.3 ms from the completed START_STREAM write to the first STROBE is not yet a proven sensor minimum. A repeatable delay can still depend on configuration or firmware sequencing.

## Source facts

[UM2602 Rev 8](https://www.st.com/resource/en/user_manual/um2602-how-to-integrate-and-configure-the-vd56g3-vd66gy-and-vd16gz-devices-from-a-hardware-and-software-perspective-stmicroelectronics.pdf) supplies these controls:

- Clock settings apply at START after standby configuration (§13.1). The permitted PLL input interval includes 12 MHz. Table 46 defaults are predivider 1, multiplier 67, postdivider 1 at 12 MHz; Table 13 instead recommends 2/134. Both calculate 804 MHz, with pixel clock 160.8 MHz using divider 5. The pinned driver deliberately selects an input strictly below 12 MHz: retain this disagreement when qualifying 1/67.
- Frame length sets frame period; its minimum depends on sensor readout height and timing offsets (§13.3). Output cropping does not shorten that readout.
- I2C follower mode starts each integration by command; its acknowledgement follows frame transmission (§13.5).
- DARKCAL_CTRL at 0x0340 supports automatic (1) and disabled (0) modes (p60).

[DS12968 Rev 12 §3.2](https://www.st.com/resource/en/datasheet/vd56g3.pdf) describes internally managed charge pumps and regulators. That makes analog startup a plausible hypothesis, not an established explanation of the measured delay. Neither retrieved text establishes a mandatory 5 ms START-to-exposure wait or a public command to pre-enable those analog circuits independently.

## Controlled experiment order

1. Change only frame length to 2168, 4336, and 8666 lines at fixed 1428-line exposure. These conservative candidates retain full readout and exposure margins. Compare START-write-end→first STROBE, not frame completion. A constant result rejects frame-period scheduling as the dominant cause over this range.
2. Change only coarse exposure to 650 and 1301 lines. Confirm applied exposure and external pulse width; the second value is approximately 10.0002 ms at the nominal sensor clock. The pinned driver's integer-microsecond conversion makes a 10000 µs request 1428 lines, approximately 10.9764 ms. This test also strengthens first-strobe qualification.
3. Try the documented 1/67 PLL setting, preserving 804/160.8 MHz and every other setting. Read applied clocks while streaming. A measurable difference implicates the PLL path; a successful picture alone does not establish broad operating margin at the input boundary.
4. If unexplained, test I2C follower mode, VT_CTRL 0x0309=2, delay 0x033A=0. Arm DMA before START. After START acknowledgement and STREAMING, issue 0x0202=2. Record command-write boundaries separately; do not wait for trigger acknowledgement before arming reception. This can distinguish leader scheduling from general startup, even if it is slower overall.
5. Optional diagnostic: disable dark calibration for one run. Check timing and first-image baseline/quality, then restore automatic mode if there is no useful improvement. A speedup bought through degraded image quality is not automatically acceptable.

Do not reduce line length below its documented minimum, overclock the sensor, alter undocumented analog registers, or treat a later frame as the first frame. Moving receiver initialization into the sensor's startup interval is independent of reducing the sensor delay itself; verify reception is ready before the first packet.

## Streaming readbacks

UM2602 p52 identifies the following read-only applied-status locations. Read them after the first frame and before STOP, so diagnostics do not postpone exposure.

| Address | Width | Meaning |
| --- | --- | --- |
| 0x0034 | 32 | External clock, Hz |
| 0x0038 | 32 | System PLL clock, Hz |
| 0x003C | 32 | Pixel clock, Hz |
| 0x0040 | 32 | Sensor MCU clock, Hz |
| 0x0044 | 8, mask 0x07 | Applied system predivider |
| 0x0045 | 8 | Applied system multiplier |
| 0x0046 | 8 | Applied system output divider |
| 0x0047 | 8 | Applied MIPI multiplier |
| 0x0048 | 8 | Applied MIPI output divider |

These are frequency/configuration reports, not documented PLL-lock bits. Compare the image, transport status, applied exposure, and timing as well. Treat external Saleae time as authoritative until the nominal STM32 DWT scale is reconciled.

## What supports stopping

The confidence claim must be conditional on this board, public supported settings, image format, and tested operating conditions. A defensible practical claim requires a measured critical-path budget, experiments that reject its plausible removable delays, repeated autonomous cold starts, and an actual first image for the winning configuration. An unexplained 5.3 ms sensor interval is larger than 10% of a roughly 30 ms path and cannot simply be declared immutable. If the only remaining paths require inaccessible sensor firmware details, record that specific limitation instead of inventing a physical lower bound.
