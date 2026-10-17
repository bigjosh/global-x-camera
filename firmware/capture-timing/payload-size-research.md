# Capture payload and staged-load opportunities

October 17, 2026. Offline build analysis only; these particular builds have not
been executed on the bench. Root controls all hardware. Numbers below concern
the native 1120 × 1364 RAW8 test, not a complete product firmware image.

## Measured build sizes

All builds use the pinned camera checkout
`e9441cdbb5072a6d3bcef1a5ca4e4d80f850283a`, GCC 12.3.1, `-Os`, section garbage
collection, fast-boot sensor silicon only, and ROM clocks. The v7 profile uses
the conservative 150 MHz I²C timing `0x10831A27`, minimal SystemInit, strobe
instrumentation, 50 µs polling and the corrected CSI DPHY interrupt-mask macro.

| Variant | Raw bytes | Change versus v7 | Estimated ROM transfer saved |
| --- | ---: | ---: | ---: |
| v5, fixed 100 kHz and no old-silicon patch arrays | 24,476 | — | — |
| v7, conservative Fast-mode Plus | 24,716 | Baseline | — |
| Exact v7 sources, `-flto` | 21,444 | 3,272 fewer | 0.837 ms |
| Same LTO objects, CSI/DCMIPP-only clock function | 14,968 | 9,748 fewer | 2.494 ms |

Transfer estimates use the root bench's approximately 0.262 ms/KiB payload
slope. They are predictions, not observed timing improvements. Header/payload
alignment may shift the exact byte count in 32-byte steps. The frame buffer is
NOLOAD/BSS and contributes no 1.5 MB transfer; ELF file size and aggregate BSS
must not be confused with the boot payload.

The offline outputs are:

- `tmp/bringup/capture-fixed100k-v5-20261017/`
- `tmp/bringup/capture-fastplus-v7-20261017/`
- `tmp/bringup/capture-lto-research-v7-20261017/` — manifest, sources, ELF, map,
  disassembly and boot image; generated sources match v7 hashes.
- `tmp/bringup/capture-direct-clocks-research-20261017/` — replacement `clocks.c`,
  ELF, raw binary and map, linked against the preceding LTO objects, replacing
  only `01_clocks.o`. This isolated link has no boot image and is not a
  programming recommendation.

## Largest unnecessary cost

In v5, `HAL_RCCEx_PeriphCLKConfig` occupies **6,400 bytes**. LTO leaves it at
6,396 bytes: the generic peripheral selection branches do not disappear.
The application only needs its CSI and DCMIPP branches. Replacing this call
with those operations removes 6,476 bytes from the LTO build, including call
scaffolding. The exact operations from the pinned HAL are:

```c
MODIFY_REG(RCC->IC18CFGR, RCC_IC18CFGR_IC18SEL | RCC_IC18CFGR_IC18INT,
           RCC_ICCLKSOURCE_PLL1 | (59U << RCC_IC18CFGR_IC18INT_Pos));
LL_RCC_IC18_Enable();
MODIFY_REG(RCC->IC17CFGR, RCC_IC17CFGR_IC17SEL | RCC_IC17CFGR_IC17INT,
           RCC_ICCLKSOURCE_PLL1 | (3U << RCC_IC17CFGR_IC17INT_Pos));
LL_RCC_IC17_Enable();
__HAL_RCC_DCMIPP_CONFIG(RCC_DCMIPPCLKSOURCE_IC17);
```

This assumes the already observed 1200 MHz ROM PLL1 output and results in
20 MHz CSI and 300 MHz DCMIPP. It does not reprogram the PLL, CPU or system
clocks. Preserve a check of the actual ROM clock configuration; this is not a
general clock initializer.

## Next small-image opportunities

1. **Direct fixed-profile sensor controls.** The remaining division helper
   `__udivmoddi4` is 740 bytes plus its ABI wrapper. Disassembly finds its sole
   caller in `VD6G_GetLineTimeInUs`. Direct coarse-exposure, unity analog gain
   and unity digital gain writes avoid the current repeated limit/line-time
   reads and can discard this dependency. First preserve the current 1428-line
   exposure for an equivalent A/B test; correct the exposure conversion in a
   separately identified variant. The product's potentiometer conversion can
   later use a reduced rational calculation with bounded integer inputs.
2. **Specialized sensor register sequence.** Keep model/revision checking,
   readiness/command ACK checks and actual transfer errors. Replace generic
   mode/PLL searching with prequalified values for this exact sensor, clock,
   geometry and lane arrangement. The generic mode table alone is 252 bytes.
   Contiguous documented writes can reduce bus transactions independently of
   the code reduction. Snapshot/read back the resulting configuration before
   removing checks from the timing path.
3. **Smaller receiver error handlers.** In the direct-clock LTO build,
   CSI_IRQHandler is 1,624 bytes and DCMIPP_IRQHandler 560 bytes. A narrow
   RAW pipe-0 implementation could reduce them, but preserve real error
   reporting and first-frame qualification. This has lower immediate benefit
   than the clock or sensor-control changes.
4. **Known-clock calculations.** SystemCoreClockUpdate remains 528 bytes;
   source/PLL frequency helpers and inlined cases remain too. Replacing them
   with a guarded known-ROM profile can save more, but retaining observation
   of the real clock state has value while validating instrumentation.

Removing diagnostic event storage can make a final image smaller, but should
not come before the timing and image-validity questions are resolved.

## When staging helps

The existing reviewed reader documents **indirect-read XSPI1 routed to XSPIM
port 2**, not a configured memory-mapped aperture. Do not assume a memcpy from
`0x70000000` works merely because that is the programmer's flash address. A
second stage should first reuse a small bounded indirect reader, preserving
the verified ROM clock, routing and NOR protocol. No frozen maintenance helper
needs to be modified to implement a distinct application reader.

There are two useful staged designs:

- **Tiny reset-release prefix, then load the remaining capture code.** Assert
  valid I/O supply state and release sensor XSHUTDOWN immediately after the
  small prefix starts. Read the rest while the sensor reaches READY_TO_BOOT.
  This overlaps code loading with sensor startup even if the entire sensor
  driver remains in the second stage. It is the simpler staging experiment.
- **Sensor-start prefix, late receiver/storage code.** Include I²C and the
  minimal sensor configuration in stage one. Fetch receiver code during
  sensor waits, or start exposure before fetching it if the receiver is
  demonstrably ready before the first CSI packet. The latter requires an
  actual first-packet deadline; exposure length alone does not prove that
  enabling the receiver later is safe. Very short production exposures make
  that dependency more demanding. NAND/USB code can remain late regardless.

At the same 32 MHz single-line transfer rate, staging does not eliminate the
total bytes to read. Its primary gain is hiding the transfer inside independent
sensor delay. For prefix transfer `P`, late transfer `L`, sensor readiness `R`
and subsequent serial setup `C`, the simplified critical path changes from
`P + L + R + C` to `P + max(L, R) + C`, plus loader overhead. The maximum gain
from that overlap is `min(L, R)`, not the entire second-stage transfer time.
Faster post-ROM NOR reads could improve this further but require their own
verified setup; they are not implied by the existing ROM path.

After small-image cuts, approximately 15 KiB at the measured slope is only
3.8 ms of payload transfer. A tiny prefix may still remove a material fraction
of the remaining startup latency, but its benefit must be compared with the
new measured readiness delay, reader overhead and the desired near-minimum
confidence bound. The known tiny GPIO marker bounds the ROM portion only;
it does not prove the physical minimum of reset-to-exposure.

## Source trail

- Pinned HAL `stm32n6xx_hal_rcc_ex.c`, CSI/DCMIPP branches at lines 651–694.
- Pinned VD6G driver, `VD6G_GetLineTimeInUs`, `VD6G_SetExposureTime`, gain
  setters and initialization/start call graph.
- ELF symbol sizes and disassembly in the above offline build directories.
- [ROM optimization constraints](../boot-timing/experiments/optimization-limits.md).
- [Preserved-ROM indirect reader](../boot-timing/experiments/rom-nor-read/README.md).
- [Sensor startup research](sensor-startup-research.md).

No board power, firmware, probe, instrument, fuse or lifecycle state was changed
by this analysis.
