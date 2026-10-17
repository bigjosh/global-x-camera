# VD56G3 transmitter startup contract and mismatch hypotheses

Research date: October 17, 2026. Scope: CAM-6G3-073CLR / VD56G3 revision `0x3110`, original ST-based smoke application, and installed v25 native RAW10 capture. This is read-only source research; no hardware or instrument settings were changed.

## What does the sensor actually guarantee?

### Takeaway

The documentation establishes reset levels and software command ordering, but does not establish the electrical lane state throughout the standby-to-stream transition. **Sensor `SW_STANDBY` and D-PHY `Stop State` must not be treated as synonyms.** The important missing evidence is the actual two-wire transition immediately before the receiver's lane-1 error.

### Cited Findings

| Topic | Published sensor contract | Consequence for this investigation |
| --- | --- | --- |
| Reset | Table 7 assigns **Low** to the CSI data and clock pins' reset state. | Reset does not promise LP-11. [DS12968 Rev 12, p19](https://www.st.com/resource/en/datasheet/vd56g3.pdf) |
| LP electrical levels | High = 1.1–1.3 V; low = −50 to +50 mV; LP transmitter output impedance minimum 110 Ω. | Probe threshold/loading matter. [DS12968, table 20, p35](https://www.st.com/resource/en/datasheet/vd56g3.pdf) |
| HS electrical levels | Common mode 150–250 mV; differential amplitude 140–270 mV; maximum single-ended high 360 mV. | An LP digital trace will not describe HS traffic or its analog quality. [DS12968, table 19, p35](https://www.st.com/resource/en/datasheet/vd56g3.pdf) |
| Startup commands | Rails/CLKIN valid before XSHUTDOWN release; READY_TO_BOOT allows I²C; BOOT precedes SW_STANDBY configuration; START_STREAM precedes STREAMING. | Command-state ordering only. [UM2602 Rev 8, §§4–5](https://www.st.com/resource/en/user_manual/um2602-how-to-integrate-and-configure-the-vd56g3-vd66gy-and-vd16gz-devices-from-a-hardware-and-software-perspective-stmicroelectronics.pdf) |
| Clock mode | DPHYTX_CTRL `0x0956`: default `0x1C` continuous; `0x0C` noncontinuous, with LP clock during interframe. | Continuous mode does not specify the first enable transition. [UM2602 §16](https://www.st.com/resource/en/user_manual/um2602-how-to-integrate-and-configure-the-vd56g3-vd66gy-and-vd16gz-devices-from-a-hardware-and-software-perspective-stmicroelectronics.pdf) |
| Output configuration | OIF_CTRL selects lane count, physical mapping and pair inversion; table 47 defaults to two lanes. | Do not hypothesize that lane 1 is disabled by the documented standby default. [UM2602 §§16.1, 19.4](https://www.st.com/resource/en/user_manual/um2602-how-to-integrate-and-configure-the-vd56g3-vd66gy-and-vd16gz-devices-from-a-hardware-and-software-perspective-stmicroelectronics.pdf) |
| Exposure correlation | GPIO STROBE describes integration; VSYNC modes describe readout. | Neither directly marks transmitter power-up. [UM2602 §18](https://www.st.com/resource/en/user_manual/um2602-how-to-integrate-and-configure-the-vd56g3-vd66gy-and-vd16gz-devices-from-a-hardware-and-software-perspective-stmicroelectronics.pdf) |

The sensor has separate system/output PLL functionality and supports 250–1500 Mbps/lane, nominal 804 Mbps. No inspected sensor table supplies transmitter PLL lock-to-LP-state timing. [DS12968 §§3.3, 9.8](https://www.st.com/resource/en/datasheet/vd56g3.pdf)

### Inferences

- A both-low-to-both-high transmitter wake transition is a plausible place to investigate. Unequal wire rise times, receiver readiness, or an intermediate state could matter. This is **not** evidence that the sensor generates an illegal sequence: reset exit and protocol initialization have their own rules, and the wire transition has not been measured.
- A delayed receiver enable could avoid observing an initialization transition without explaining why it is flagged. First-frame reception and raw error monitoring must remain enabled; merely masking/clearing the indication is not an electrical repair.

### Gaps

UM2602/DS12968 do not specify LP-00/LP-11/Hi-Z throughout READY_TO_BOOT, BOOT or SW_STANDBY; when START applies output inversion; first-clock timing; T_INIT/LPX/HS-prepare/HS-zero guarantees; or a public transmitter-ready indication. No explicit VD56G3 D-PHY version was located. Another sensor's stated PHY version must not be substituted. [Documents inspected: UM2602](https://www.st.com/resource/en/user_manual/um2602-how-to-integrate-and-configure-the-vd56g3-vd66gy-and-vd16gz-devices-from-a-hardware-and-software-perspective-stmicroelectronics.pdf), [DS12968](https://www.st.com/resource/en/datasheet/vd56g3.pdf)

## How do the actual configurations and physical names compare?

### Takeaway

Both software paths deliberately invert all three differential pairs and use two data lanes without exchanging lane identities. The optimized firmware overlaps receiver initialization with sensor startup; the original smoke test initialized the receiver first. Their shared error class therefore cannot be attributed solely to the optimized ordering. [Local retrospective](../../firmware/capture-timing/csi-startup-errors.md)

### Cited Findings

- ST's pinned middleware configures `datalane_nb=2`, `clock_lane_swap_enable=1`, both data-pair swap enables = 1, and lane-mapping-swap = 0. The driver builds `OIF_CTRL=0x02CA`: bit 9 = lane-1 polarity inversion, bits 8:7 = physical lane 1 carries logical lane 1, bit 6 = lane-0 inversion, bits 5:4 = physical lane 0 carries logical lane 0, bit 3 = clock inversion, bits 2:0 = two lanes. This is an arithmetic decoding of the inspected driver. [Pinned ST middleware](https://github.com/STMicroelectronics/x-cube-n6-camera-capture/blob/e9441cdbb5072a6d3bcef1a5ca4e4d80f850283a/Lib/Camera_Middleware/sensors/cmw_vd56g3.c#L268-L272), [driver setup](https://github.com/STMicroelectronics/x-cube-n6-camera-capture/blob/e9441cdbb5072a6d3bcef1a5ca4e4d80f850283a/Lib/Camera_Middleware/sensors/vd6g/vd6g.c#L725-L762)
- The selected v25 generated `stage1_sensor.c` writes that same `0x02CA`, 804 Mbps, RAW10 format 10 and data type `0x2B`, before START at `0x0201`. Its receiver uses physical lane mapping and the 800-Mbps HAL range. Code loading and receiver initialization follow the START write; START acknowledgment is polled afterward. The current generic source is a generator input and can show RAW8, so use the archived selected build to audit the installed image. [Selected build evidence](../../firmware/capture-timing/evidence/2026-10-17-native-raw10-v25), [results](../../firmware/capture-timing/optimization-results-2026-10-17.md)
- The best measured run records START completion 18.02192 ms, receiver configuration 21.22256 ms, receiver armed 21.23136 ms, lane-1 ECTRL callback 22.97216 ms, STROBE 23.32416 ms, first VSYNC 34.55216 ms and frame completion 45.18208 ms after reset release. The callback is 352 µs before STROBE, not a wire-edge timestamp. [Selected build evidence](../../firmware/capture-timing/evidence/2026-10-17-native-raw10-v25)
- The original smoke test recorded `0x8000` but not the physical lane or timestamp. Longer delays, receiver-first setup and three discarded settling frames did not eliminate the historical error class. [Retrospective and original-log references](../../firmware/capture-timing/csi-startup-errors.md)
- Fresh retrieval of the official module schematic resolves to **Rev 2, August 2026**, although the search index still describes Rev 1. It exposes the sensor pairs directly: J1 DATA1P/N pins 10/12, CLKP/N 16/18, DATA2P/N 22/24. The newest drawing labels VCORE 1V15. The module's DATA2 naming identifies its second pair; the complete adapter/Nucleo route must establish which physical test point is STM32 lane 1. These are connector identities, **not an instruction to clip probes onto those miniature contacts**. [Module schematic, p1](https://www.st.com/resource/en/schematic_pack/cam-6g3-073clr-schematic.pdf)

### Inferences

- Polarity needs to be annotated in terms of the **receiver's P/N pins** before interpreting LP-01 versus LP-10. Otherwise, a perfectly valid physical sequence can be labeled backwards. Successful packet reception reduces the likelihood of a permanently wrong mapping but does not prove startup analog behavior.
- The roughly 1.74 ms between receiver arming and the recorded error argues against calling this merely the immediate effect of enabling a receiver while a line is already active. A later transmitter transition is plausible, but sticky-status latency and internal initialization remain alternatives.

### Gaps

- No source found specifies whether pair-inversion changes affect LP and HS simultaneously at the configuration write, at START, or at another internal transition. Do not prescribe toggling polarity live as a cure.
- The module connector list alone does not establish accessible solder pads, cable orientation, or this board's end-to-end polarity. Probe placement requires the exact adapter and Nucleo schematics.

## Which mismatch hypotheses should the measurements discriminate?

### Takeaway

Prioritize a **transmitter startup transition observed before the first exposure**, while separately testing receiver initialization and analog integrity. The evidence does not identify a particular invalid LP transition yet. Receiver ECTRL means an incorrect lane-state sequence; later stop-state bits do not reconstruct the offending sequence. [RM0486 §40.9.15](https://www.st.com/resource/en/reference_manual/rm0486-stm32n647657xx-armbased-32bit-mcus-stmicroelectronics.pdf), [recorded raw status](../../firmware/capture-timing/csi-startup-errors.md)

### Cited Findings

- The common startup class persists in the original demo path and after isolated PHY programming corrections, noncontinuous clock, and changed bitrate. First images remain usable. [Experiment record](../../firmware/capture-timing/experiments.md), [original comparison](../../firmware/capture-timing/csi-startup-errors.md)
- RM0486 requires the CSI lane merger to be configured with CSIEN clear and the D-PHY receiver not streaming/providing a clock. That is an actual sequencing constraint, but the START command timestamp alone does not establish whether it was violated. [RM0486 §40.6.2](https://www.st.com/resource/en/reference_manual/rm0486-stm32n647657xx-armbased-32bit-mcus-stmicroelectronics.pdf)

### Inferences

| Priority and hypothesis | Useful discriminating observation | What would weaken or falsify it |
| --- | --- | --- |
| 1. Transmitter startup/Stop-State entry presents a transient to an already-active receiver | Record both wires of lane 1, clock activity, receiver-enable marker, raw-error marker and START marker. Determine whether the first rise to stable LP-11 occurs immediately before ECTRL. | A long stable LP-11 interval preceding the error, with no coincident transition, or an error that moves only with receiver enable. |
| 2. Receiver becomes ready during a sensor transition or has not finished settling | Keep sensor setup identical; vary receiver enable relative to START. Preserve first-frame/error evidence. | Error remains tied to the same transmitter edge with receiver ready substantially earlier; note original demo already weakens a simple late-enable explanation. |
| 3. Startup polarity application creates an unexpected intermediate LP state | Annotate physical receiver P/N; compare lane 0 and lane 1 through configuration and START. | Correct ordering and stable levels on both pairs at the error, with no observable polarity-related transition. |
| 4. Lane-merger setup occurs while a clock is supplied | Observe clock state at the exact merger writes; record CSI enable/status. Compare setup-complete-before-START variant. | The clock is demonstrably absent during those writes and the error still occurs. Original smoke evidence makes this unlikely to be the sole explanation across both paths. |
| 5. Analog imbalance or threshold crossing looks like a bad state | Scope both wires with comparable low loading; inspect amplitude, skew, ringing and repeated threshold crossings at ECTRL. Compare probe-free error counts. | Clean valid receiver-input waveforms within documented tolerances, stable across minimally perturbing probing. |

These are experiment proposals, not facts about the root cause. Avoid judging protocol validity from a digital LP trace alone: HS can appear as both wires low, and threshold/loading can create or hide intermediate states. Preserve unprobed control runs and do not present disappearance after probe attachment as a software cure.

### Gaps

Actual lane waveforms, applicable complete MIPI version-specific initialization requirements, precise receiver input filtering, and the point at which the sensor applies polarity/PHY controls remain unknown. A guaranteed electrical explanation needs those observations or vendor clarification. The sensor contract alone cannot certify the warning as benign.
