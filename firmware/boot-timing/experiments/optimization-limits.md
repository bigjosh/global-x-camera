# Limits of the reversible cold-boot optimization tests

This note records the source-supported scope of the October 17, 2026 tests on
the NUCLEO-N657X0-Q, STM32N6 revision B, and MX25UM51245G boot NOR. It does not
declare an absolute startup floor. Measured comparisons and current bench state
belong in [the experiment results](../optimization-results-2026-10-17.md).

The relevant observed normal-boot state is XSPI1 mapped to physical XSPIM port 2,
single-line SPI read command `0x0B`, the nominal ROM clock configuration, CPU
I-cache enabled/D-cache disabled, and `RCC_RDCR=0x06000000`. The ROM traces report
the default-location image and a first-image boot. These observations agree
with the documented configuration below; they do not establish the duration of
every internal ROM phase.

## Supported options and their limits

| Candidate | Source-supported conclusion |
| --- | --- |
| Quad, octal or 16-bit initial NOR load | ROM's serial-NOR configuration uses instruction/address/data on one line, 24-bit addresses, eight dummy clocks and command `0x0B`. Its XSPI kernel is 64 MHz, divided by two. No documented header field selects a wider/faster sNOR transfer. Wider XSPI modes can accelerate code/data loaded **after** handoff. |
| HyperFlash boot | This is a different device protocol and boot-source selection, not an octal-mode switch for the installed serial NOR. Boot-source selection uses OTP11. Changing the NOR's mode alone does not change ROM's documented protocol. |
| Smaller header or removed alignment padding | N6 header version 2.3 requires payload alignment to file offset `0x400`. The independently checked ST image has a 576-byte header plus 448 leading payload-alignment bytes. Removing the padding extension is not a supported way to move the payload earlier. FSBL start/end also require 32-byte alignment. |
| Different entry/load fields or code placement | ROM loads the FSBL before jumping to its header entry point. No documented field was found that bypasses that load or provides a faster handoff. Flash offset zero already uses the first image location; fallback is at `0x40000`. Entry-instruction and cache-line placement changes concern the small post-handoff path, which the tiny-marker test investigates. |
| Cache configuration | ROM enables I-cache early and keeps it enabled for this normal unlocked FSBL boot scenario. There is no documented image-header cache switch. Changing caches in the FSBL cannot recover time spent before handoff. |
| Removing the five-millisecond external-access delay | `RCC_RDCR.EADLY` is software writable, but resets to five milliseconds on power-on. A write after handoff can affect a later powered reset; it cannot eliminate the delay from the same fully discharged cold start. The separate minimum-reset-duration field, MRD, already defaults to zero. |
| Avoiding ROM PLL setup | `no_cpu_pll`, OTP11 bit 1, selects the cold-boot clock policy: nominal 400 MHz CPU versus 64 MHz HSI. It is not a documented header setting. Writing a shadow register is not a persistent reset workaround: shadowed fuses reload on both cold and warm BSEC reset. No fuse change is part of these tests. |
| Faster power startup | A faster supply ramp or retained-power design is a hardware/architecture investigation. Current-board power ramp and ROM startup overlap; their durations cannot simply be subtracted. The FSBL cannot configure the board's initial power ramp before its own execution. |

The trace parser's `OSPI_TryingDualMode` label alone is not evidence of a
supported two-line, quad or octal fast-boot configuration. Protocol claims above
come from the ROM manual, not interpretation of an isolated event name. Header
version/antirollback fields must not be varied as timing experiments.

## Trace and reset qualifications

Two exported secure traces contain an interval of **5,020 raw ticks** between
unknown codes `0x00002900` and `0x00000152`; the latter has argument `0x1388`
(5,000). This is compatible with the documented five-millisecond EADLY setting.
The pinned ST parser does not name either event, however, and timestamp
continuity/alignment to the external supply or NRST edges has not been verified.
The interval is not proof of named delay-start/end events or a demonstrated
removable five milliseconds. ROM's documented TIM2 initialization at 1 MHz does
not make a later counter read a continuous power-on stopwatch.

Powered-reset experiments are a separate category from autonomous cold boot.
In addition to the different retained state, ES0620 section 2.2.22 documents a
software-reset clock-switch limitation. Its prescribed default clock selections
and live source clocks must be respected before such a reset. This note does not
propose a warm-reset measurement as a substitute for a discharged power cycle.

## Defensible stopping criterion

Finish repeated baseline/size/tiny comparisons with baseline runs bracketing
the changes, verified NOR contents, complete power discharge/restoration, and
comparable measured rail ramps. Establish the payload-size slope and observed
run-to-run variation. If the smaller marker path does not produce a repeatable
improvement beyond that variation, the conclusion may be scoped to **no
remaining documented reversible firmware setting demonstrated to materially
shorten cold boot on this board and ROM revision**.

That conclusion would not establish an absolute silicon minimum, exclude
undocumented ROM behavior, predict an optimized custom board, or qualify the
50 ms button-to-exposure requirement. Remaining work still includes sensor
startup and application sequencing. Staging later firmware after sensor startup
remains useful even when the minimal ROM-loaded bootstrap is already small.

## Primary references and local cross-checks

- [ST UM3234, revision 5](https://www.st.com/resource/en/user_manual/um3234-how-to-proceed-with-boot-rom-on-stm32n6-mcus-stmicroelectronics.pdf):
  sections 3.4.5–3.4.7 and Tables 14–15 (sNOR/HyperFlash protocols), 3.12.1 and
  Table 26 (clock sources), 3.12.3 (boot pins used for flash), 3.12.4 (1 MHz TIM2),
  3.5.3 (image search),
  3.9.2 Figure 8 (code at `0x34180400`), 3.2.2 and Table 4 (alignment/cache),
  4.1 (header fields), and 5.1 (load/authentication/handoff). The earlier Figure 4
  labels a code boundary at `0x34180240`; it must not override the later alignment
  instructions and independently checked ST-generated image.
- [ST UM2543, revision 7, page 4, `--align`](https://www.st.com/resource/en/user_manual/um2543-stm32-signing-tool-software-description-stmicroelectronics.pdf):
  payload alignment at `0x400` is required for N6 header version 2.3.
- [ST RM0486, revision 4](https://www.st.com/resource/en/reference_manual/rm0486-stm32n647657xx-armbased-32bit-mcus-stmicroelectronics.pdf):
  section 14.10.106, RCC_RDCR (EADLY/MRD and power-on reset domain);
  sections 4.3.3–4.3.5 (BSEC resets, shadow loading/writes); OTP Table 18,
  OTP11 (boot source and `no_cpu_pll`).
- [ST ES0620, revision 5, section 2.2.22](https://www.st.com/resource/en/errata_sheet/es0620-stm32n6xxxx-device-errata-stmicroelectronics.pdf):
  peripheral-clock state before software reset.
- [Local boot-header evidence](../header-evidence.md) records pinned ST source,
  an independently inspected ST-generated binary, and the exact header,
  alignment, checksum and vector cross-checks. [ROM trace tooling](rom-trace/README.md)
  records the pinned event-name mapping and decoding limitations.

This note was prepared offline from the existing primary-reference extracts and
recorded evidence. It changes neither hardware nor the executed RAM helper.
