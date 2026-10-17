# Native RAW10 capture memory plan

October 17, 2026. Offline design and build; hardware validation is separate. `build_raw10.py` creates an isolated build from hash-checked frozen receiver and prefix manifests. It does not modify the shared `capture.c`, `build.py`, original bring-up, or frozen NOR maintenance helpers.

## Why relocation is necessary

RM0486 Rev4 Table328 (p1815) and §39.5.5 (pp1843–1844) specify that DCMIPP Pipe0 expands monochrome/raw Bayer 10/12/14-bit samples into 16-bit memory words. Therefore native 1120 × 1364 RAW10 requires **3,055,360 bytes**, although its CSI wire payload uses 1,909,600 bytes. `P0PPCR.PAD` (p1922) selects alignment, not packed storage: clear it for right-aligned 10-bit samples in little-endian 16-bit words. There is no established RAW10-plus-BPP8 packed bypass in this investigation.

The previous RAW8 frame occupied 1,527,680 bytes below code at `0x3418...`/`0x3419...`. Merely enlarging it would overwrite executing code and diagnostics. Starting the padded frame at `0x34200000` also fails: SRAM3–6 offer 1.75 MiB, and adding SRAM7 only reaches 2 MiB.

## Isolated layout

Ranges are start-inclusive/end-exclusive.

| Object | Range or address | Lifetime |
| --- | --- | --- |
| Native padded RAW10 frame | `0x34000000..0x342E9F00` | Written by first snapshot; retained until host retrieval |
| Eight-word overflow canary | `0x342E9F00..0x342E9F20` | Written before capture and checked after first frame |
| ROM-loaded prefix | `0x34180400...` | Needed only before handoff; overwritten by later frame data |
| Prefix stack | top `0x34188000` | Needed only before handoff |
| Memory-bootstrap fallback | `0x341F5000`, 32 words | Available before high SRAM works; overwritten by image later |
| Receiver vectors/code/data/BSS | start `0x34300000` | All runtime functions, constants and vectors are relocated |
| Runtime stack | top `0x343B0000` | Within SRAM6, above code/data |
| Root's separate cache helper | `0x343C0000`, status `0x343C0400` | After capture; not part of this builder |
| Trace/events/error records | `0x343F0000` / `0x343F0100` / `0x343F1000` | SRAM7 |
| Prefix/sensor status | `0x343F3000` / `0x343F4000` | SRAM7 |
| Copied memory-bootstrap record | `0x343F5000`, 32 words | Survives frame capture |
| RAW10 format/bounds record | `0x343F6000`, 10 words | First-frame checks and sensor readbacks |

The prefix switches VTOR and MSP before entering the receiver; the receiver's own SystemInit uses its relocated vector symbol. No prefix function or constant may be used after DMA is armed. Frozen maintenance helpers in the old frame range can be reused only **after successful image retrieval**; writing them destroys part of the saved RAM frame.

The v24b bootstrap explicitly zeros and verifies the 148-byte reserved cache-helper region at `0x343C0000` and 64-byte status region at `0x343C0400`. This meets the host maintenance helper's “known bytes or all zero” guard without assuming newly powered SRAM is zero. Neither region overlaps the frame, stack, executable receiver, or diagnostic records. This supersedes the initial unexecuted v24 artifact.

## SRAM prerequisites

RAM3–6 are 448 KiB banks at `0x34200000`, `0x34270000`, `0x342E0000`, and `0x34350000`. They default to shutdown. RAM7 is the 256 KiB CACHEAXI storage at `0x343C0000..0x34400000`; it is available as RAM when CACHEAXI is disabled. [RM0486 memory map and §10.4](../../datasheets/processor/STM32N6_RM0486_reference_manual.pdf).

The bootstrap opens volatile debug access before memory setup. Its low-SRAM fallback remains writable if high SRAM fails. It requires the verified ROM clock profile, D-cache off, NPU interleaving off and CACHEAXI disabled. It enables the RAMCFG/SYSCFG/CACHEAXI register clocks before examining their controls. Enabling a register clock is separate from setting `CACHEAXI_CR1.EN`; the code never enables the cache.

For SRAM3–6, the required sequence is clear `RAMCFG_SRAMx_AXI->CR.SRAMSD`, read it back (the RM allows this in place of a 40 ns wait), then enable the corresponding RCC memory clocks. SRAM7 needs its separate `CACHEAXIRAM` memory clock. All four high banks are needed because the runtime stack is in SRAM6.

SRAM3–6 use `sysd_ck`; with the retained ROM system selection this comes from IC11. The parent measured IC11 `0x00030000` and DIVENR `0x00030423`: bit10 is set, and IC11 already selects PLL1/4, nominally 300 MHz. The bootstrap preserves that active matching channel and refuses to retune any active unknown configuration. Only if the channel is disabled does it select the same PLL1/4 setting and enable it. It does not change PLL1, CPU/system selections or XSPI clocks.

RISAF protection of the NPU SRAM is on interconnect ingress ports (RISAF4/5/6), not one instance per physical SRAM bank. Default regions permit secure, privileged, CID1 access; that matches the existing DCMIPP master attributes. The bootstrap does not broaden security permissions. Its sparse per-bank write/read/restore test proves CPU access, not DMA-master access; the first real frame and receiver error/status records must prove the latter. [RM0486 §7.3 and §§7.4.3–4](../../datasheets/processor/STM32N6_RM0486_reference_manual.pdf).

## Capture and host checks

The sensor prefix writes `0x030A=10` and `0x030F=0x2B`; the receiver selects CSI BPP10 and RAW10 together. The pixel count, exposure, frame period and first-frame snapshot policy remain those of the chosen frozen baseline. There is no reduced-resolution substitution.

The receiver caps Pipe0 at 763,840 32-bit words. After the first frame it records the byte counter, pixel-packer control, limit, CSI format, selected flow and receiver status; it checks the exact 3,055,360-byte count and canary, then verifies the sensor format readbacks. The ten RAW10 status words are: magic, dumped byte count, P0PPCR, P0DCLMTR, CSI VC0CFGR1, P0FSCR, CMSR2, canary mismatch mask, sensor bits-per-pixel, sensor data type.

The host manifest declares `pixel_format=raw10_le16`, `bytes_per_pixel=2`, `sample_bits=10`, `sample_alignment=right` and all relocated record addresses. The firmware byte-based FNV checksum remains unchanged, so the host can compare exact bytes before converting samples. The host must verify upper six sample bits are zero, inspect low-bit distribution, preserve exact sample values, and visually confirm the first LED-panel image. A preview scaled by shifting two bits is only a display aid.

No timing or image-validity claim is attached to the v24 build until the root bench controller completes those checks. The earlier RAW8 timing measurements remain explicitly RAW8 diagnostics.
