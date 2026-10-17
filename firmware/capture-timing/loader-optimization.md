# Read-only stage-one loader optimization

October 17, 2026. Research and offline code work by the sensor-startup agent; physical experiments remain under the root controller. Frozen NOR maintenance helpers were not changed.

## Current safeguards and options

The prefix accepts only the measured ROM clock/security/XSPI profile, performs one finite `0x0B` read within the first 64 KiB, compares the entire copied image's IEEE CRC32 with its build-time value, checks vector bounds, invalidates instruction cache, and then branches. Errors remain awake with diagnostics. No retry, abort, flash write, OTP change, or global clock reset is performed.

- `STAGE1_WORD_READS=1`: pop four bytes only when XSPI FIFO level is at least four, store an aligned word, maintain byte order in CRC, and handle a possible final byte tail. Progress snapshots occur every 256 polls. RM0486 Rev4 §28.7.10 explicitly permits word/halfword/byte reads; checking FIFO level avoids an indefinitely stalled DR access.
- `STAGE1_INLINE_CRC=1`: identical nibble-table CRC arithmetic with forced inlining, removing four function calls per word. Prefix `-O2` is an independent build choice.
- `STAGE1_ENABLE_ICACHE=1`: record CCR before/after and enable instruction cache if needed, keeping data cache off. Actual v19/v20 entry CCR was already `0x20201`: M55 instruction-cache bit17 was set. This option should not improve those runs.
- `STAGE1_EARLY_SENSOR=1`: call the independently reviewed bounded sensor initializer after all loader guards, before starting the read. Sensor failures return prefix error17. This allows receiver code loading during START-to-strobe latency.
- `STAGE1_XSPI_64MHZ=1`: requires word reads and exact CLKP→HSI64 source, HSI-ready, PN1/2/3/6 AF9, push-pull, and highest slew. Change DCR2 from1 to0 only while idle; restore1 after completed, empty-FIFO transfer before CRC/vector acceptance and handoff. An active failed transfer is left inspectable rather than forcibly aborted.

All options default off. Cold-ROM prefix code remains immutable through each run. Shared maintenance helpers retain their existing instruction-cache constraints.

## Observed software bottleneck

The retained v19 `capture-result.json` reports 14,188 copied bytes, 3,553 loop polls, start3994/end2162310 DWT cycles, and instruction cache already enabled. Only about six polls did not deliver a complete word. This indicates a CPU-limited loop, approximately152 nominal cycles/byte, rather than a serial bus waiting loop. Four out-of-line CRC calls and eight uncached AXI table loads occur per word in its disassembly.

Root reported v20's 11,532-byte copy at1,754,615 DWT cycles (4.3865 nominal ms) with receiver ready at1,794,955 cycles after START completion against a1,800,000-cycle guard. A successful first image confirms the tested ordering, but the roughly12µs nominal deadline margin is insufficient for a robust final choice. First isolate forced CRC inlining and prefix `-O2`; if that remains CPU-bound, hardware CRC is the next candidate. A faster XSPI clock alone cannot fix a CPU-limited reader.

**Resolved by v22:** the inline-CRC/O2 trial copied the same11,532 bytes in1,154,811 cycles, 2.8870 nominal ms. The32MHz single-line wire minimum is2.8830ms before command overhead, so the new loop is effectively bus-limited. The external copy interval was about2.915ms. Receiver readiness was about2.987ms after START completion, leaving approximately1.513ms against the4.5ms guard. The first visible LED image's strobe was24.50592ms after NRST. These facts support retaining the32MHz path and deferring64MHz/hardwareCRC: faster loading is now hidden inside sensor START latency and would not advance exposure.

Frozen build: `tmp/bringup/capture-early-inline-v22-20261017/manifest.json`; capture: `tmp/bringup/capture-opt-v22-inline-cycle-01`. Prefix raw4188bytes, compiled `-O2 -flto -mfloat-abi=soft -mgeneral-regs-only`; `STAGE1_SKIP_SENSOR_RESET=1`, `STAGE1_WORD_READS=1`, `STAGE1_INLINE_CRC=1`, `STAGE1_EARLY_SENSOR=1`, `STAGE1_XSPI_64MHZ=0`. Stage2 is the unchanged11,532-byte receiver image with CRC0x03C817C4. This was a combined optimization experiment (inlining plusO2), so it does not isolate the contribution of each compiler change.

## 64 MHz source support and electrical limit

[UM3234 Rev5](https://www.st.com/resource/en/user_manual/um3234-how-to-proceed-with-boot-rom-on-stm32n6-mcus-stmicroelectronics.pdf), Tables14/24/26, documents ROM single-line NOR reads with8 dummy cycles and an HSI64-derived kernel divided by2. [RM0486 Rev4](https://www.st.com/resource/en/reference_manual/rm0486-stm32n647657xx-armbased-32bit-mcus-stmicroelectronics.pdf) §28.7.3 permits idle-only prescaler changes; value0 bypasses the divider. Actual register selectors are checked, not inferred solely from a nominal clock constant.

[Macronix PM2183 Rev1.6, March13,2026](https://www.macronix.com/Lists/Datasheet/Attachments/9241/MX25UM51245G,%201.8V,%20512Mb,%20v1.6.pdf), Tables5/24 and §10-12, supports `0x0B`, 24-bit address, 8 dummy clocks, up to133MHz in the1.65–2.0V range. The experiment changes no memory configuration or opcode.

The MCU-side limit is less certain. V18 SVMCR3=0x200 leaves VDDIO3VRSEL0, the degraded1.8V mode. DS14791 Rev10 Table70 specifies maximum highest-slew frequency60MHz at20pF or85MHz at10pF, with I/O compensation enabled. Table90's much higher XSPI rating assumes HSLV and compensation. Actual board load/compensation margin has not been qualified. Root authorized64MHz solely as a bounded, read-only, CRC-gated bench trial; a pass is not production electrical qualification. No OTP, voltage-range, compensation, or pad setting changes are included.

## Hardware CRC groundwork, deferred after v22

RM0486 §26.3.3 and §26.4.3 permit 32-bit and final byte writes. For little-endian RAM words, use polynomial0x04C11DB7, initial0xFFFFFFFF, bit-reverse the full input word (REV_IN3), bit-reverse output (REV_OUT1), and XOR output with0xFFFFFFFF. Final byte writes use REV_IN1 without resetting the accumulator. RTYPE_IN/OUT remain0.

On STM32N6, REV_OUT is a two-bit field: `CRC_CR_REV_OUT_0` (0x80) enables bit reversal; setting the entire field mask0x180 selects3 and does **not** reverse output. The word/byte control profiles are respectively0xE0/0xA0.

`crc_hw_model.py` checks this arithmetic against zlib for the `123456789` known answer0xCBF43926, deterministic lengths0–257, and the exact v19/v20 payloads. Those offline checks pass. A future implementation still needs an actual peripheral known-answer test and independent comparison before accepting code; software modeling alone is not hardware validation.

## Added STATUS layout at 0x341F3000

Existing indices0–37 retain their meanings. New words:38 read width;39 early sensor result;40 CCIPR6;41 CCIPR7;42 HSICFGR;43 RCC_SR;44 GPION MODER;45 OSPEEDR;46 OTYPER;47 AFRL;48 SVMCR3;49 applied DCR2;50 restored DCR2;51 CCR before optional cache enable;52 CCR after. Unused conditional fields remain zero. New failure codes:17 early sensor;18 XSPI source;19 XSPI pads;20 prescaler verification.
