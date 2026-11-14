# Independent normal-controls audit — 2026-11-13

Offline only. This reviewer made no shared source edits, instrument calls, resets, NOR writes or SD operations. Final combined-artifact review remains pending until the owning agents freeze it.

## Primary-source findings

- MB1940 C02 sheet10 confirms exposure A0/PF5 LOW, A1/raw PC10 -> buffered PA9/ADC1 channel10, A2/PF6 HIGH; ASA A4/PC12 HIGH, physical GND LOW, A5/raw PH2 -> buffered PG15/ADC1 channel7. Endpoint channels are A0/PA8/ch5, A2/PA10/ch11 and A4/PF3/ch16. D8/PD12 remains HOLD; PA2/PA12 remain untouched.
- DS14791 identifies PC10/PC12/PH2 as VDDIO4. ES0620 2.2.29 forbids relying on that domain's nonfunctional PVM indication. Stock3.3V range and explicit SV isolation release are required. RM0486 15.3.16 requires secure ADC12 to close secure GPIO analog switches; mutate only its RIF SEC2 bit0 and restore the prior value after the battery-only batch.
- ST's Cube vd6g.c uses SW_STANDBY for clock/line/frame configuration after BOOT. ST's Linux driver defines applied coarse0x0064/u16LE, analog0x0068/u8 and digital0x006A/u16LE. DS12968 p9 defines analog gain32/(32-code), code0..28.
- UM2602 13.2/13.3 permits line1280 above the10-bit minimum1236, with a modest readout/retention tradeoff. READ_OFFSET0x0444 stays18; the calculated frame offset stays69. Table51 lists margin0x0946 default34, conflicting with Cube's minimum68 gate. Record actual margin and validate frame >= coarse+margin+7 rather than inventing a register override. Table51 also lists MAX_AG_CODED0x0960 default24, so8x/code28 needs explicit limit handling and applied readback.

UM2602 source (indexed official sections; full PDF download timed out): https://www.st.com/resource/en/user_manual/um2602-how-to-integrate-and-configure-the-vd56g3-vd66gy-and-vd16gz-devices-from-a-hardware-and-software-perspective-stmicroelectronics.pdf
ST Linux source provenance: firmware/capture-timing/sensor-startup-research.md, commit aff46eb958f4e8dbab4a8b00abbe285421953cb4. Register facts only; no GPL implementation copied.

## Numerical checks completed

The real capture_controls_map.c was compiled into a standalone host harness. All65536 normalized exposure positions are monotonic from1000 to500000us;96025 endpoint/raw/gain combinations satisfy the coarse/frame bounds and unity digital gain. Total LUT-versus-ideal exponential error including integer rounding is at most0.166526%; this excludes sensor line quantization. map-audit.json binds the source SHA.

At line1280 and160.8MHz, requested500000us becomes62813 coarse lines =500003.980us; frame64813 includes2000 reserve lines and fits16bits. At unchanged1236 the same reserve would require frame67049, which overflows. Capping to63535 would give488366.045us and must not be called500ms.

## Address/ABI findings

- Slot buffer34000004..341D2404; image340000A0..341D2400. Selector/helper34200000/34200100 and control record343F9400..343F9480 are outside the frame.
- Selector overlaps the dedicated READ helper buffer34200000..34240000, so its helper may only be invoked before storage-read ownership. Normal new boot reloads it.
- Existing fixed stage1 I2C functions: write_value341806D9(reg,value,bytes), read_reg34180619(reg,bytes,u32pointer). The planned BL replaces only34181332; manual-pointer literal341816A4 changes to343F9440. Ordinary AAPCS must be preserved, including callee-save registers and stack alignment.
-128-byte typed CRC record fits the152-byte first-sector reservation;24 remaining bytes are zero. Leading GXR2, image offset156, stride3730 and GXRE remain unchanged. Freeze state3/configured or state4/applied before first nonzero publication, then never rewrite it. Late applied verification may update only the separate RAM record.
- Legacy GXRS and zero-metadata GXR2 remain readable; metadata failure must not change occupancy or image offsets. Current host parser exposes opaque bytes until a decoder is intentionally added.

## Still required before flash

Exact selector/helper linker placement and8KiB NOR fit; hook tail remains within34182000 with unchanged early HOLD/UART guard; CRC-bound source/record agreement; gain-limit handling; cleanup failures cannot report ADC_READY; all timeout origins include the half-second exposure; full-image and knob-endpoint bench qualification remains parent-owned.
