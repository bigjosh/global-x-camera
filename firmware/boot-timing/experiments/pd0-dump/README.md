# PD0 diagnostic dump

This separate fallback exports internal state through the already-probed PD0 pin when SWD cannot attach after normal flash boot. PE0 stays high. It preserves every original baseline byte through both marker stores, then takes a read-only TIM2/CPU snapshot and sends a delayed pulse-width serial stream. Both ROM trace buffers are sent **before any debug-control writes**, preserving them if those later accesses fault.

Two normal-flash captures, `opt-gpio-trace-01` and `opt-gpio-trace-02`, passed decoding on October 17, 2026: each contained all 153 CRC-valid packets and both complete 2,048-byte traces. Their streams lasted 4.963 and 4.955 seconds. HDPLSR read `0x51`, CONTROL was zero, and DBGCR/AP_UNLOCK changed from zero to the intended `0xB451B400`/`0xB4`. The bench controller then obtained access using explicit HOTPLUG `ap=1`. This does not establish why earlier connection attempts failed: revision 2 had not been tested with an explicit AP1 selection after its normal boot.

DBGMCU_CR read back zero in both dumps despite attempted debug-clock/Sleep-bit writes; RCC_MISCENR read `0x41` and RCC_MISCLPENR read `1`. Do not claim the DBGMCU bits took effect. TIM2's snapshot was CNT `0`, PSC `299`, with its RCC enable bit set; this snapshot is not elapsed boot time.

The intended build is `tmp/bringup/pd0-dump-context-20261017`: its boot image is 2,240 bytes; the full-sector programming buffer is `first_gpio_dump_sector_0.bin`, SHA-256 `b7fea08c0a192c97964d6c58fc84e49a26df4d4dc1d99e421c402a70fc2d57e5`. Earlier `pd0-dump-20261017*` outputs lack the final context fields and are superseded.

An alternative that omits TIM2 register reads is in `tmp/bringup/pd0-dump-context-skip-tim2-20261017`. Its full-sector buffer SHA-256 is `98e6d74e43dab1124b4555a35e3a5110d9baf5fd98b45198f76f8dbf6cc6c90e`. Both builds retain the original marker instructions and addresses. Both full-sector buffers preserve saved bytes following the selected image, and include an exact restoration copy with SHA-256 `9fde1c8206eb450b06b74a56cb6e36b220ed2e0d1188fb6a55031171eae3409a`. See [restoration instructions](../README.md#exact-restoration).

## Snapshot and transmission order

The entry shim reads RCC_APB1ENR1 immediately after the original marker path. If its TIM2 enable bit is set, it reads TIM2 CNT and PSC; otherwise those fields are `0xFFFFFFFF`. `--skip-tim2` always uses those sentinels. The shim then reads CPU CONTROL with MRS. It does not configure, enable, reset or stop TIM2. These raw timer values are not milliseconds without confirming timer frequency, origin and continuity. CONTROL bit 0 describes privilege; CONTROL does not identify secure versus nonsecure state.

After a loop-defined initial high interval, the stream contains:

1. RCC_APB1ENR1, TIM2 CNT, TIM2 PSC, and CPU CONTROL as four little-endian words.
2. Secure ROM trace bytes `0x341037F0..0x34103FEF`, then nonsecure ROM trace bytes `0x241077F0..0x24107FEF`, each 2,048 bytes in 64-byte chunks. A read-pending packet precedes every chunk.
3. A trace-complete checkpoint, BSEC clock enable, and read-only BSEC_HDPLSR (`0x56009E94`), BSEC_SR (`0x56009E40`), DBGCR and AP_UNLOCK values.
4. Checkpoints around the individual debug unlock writes, with register readback after each, then further HDPLSR/SR readbacks.
5. RCC/DBGMCU debug-clock setup, the seven debug-status words described in the main experiment README (magic `0x44424733`), and a final completion checkpoint.

The two trace addresses/sizes match ST's example, pinned in the [ROM trace provenance](../rom-trace/README.md#optional-st-event-names-and-provenance). Only those factual addresses are used; the vendor parser is not copied into this firmware. Pinned CMSIS static assertions verify peripheral addresses and offsets.

Memory access can still fault if the ROM leaves a region inaccessible. The fallback deliberately has no exception-recovery mechanism. A completed read-pending packet identifies the next attempted access; earlier CRC-valid packets remain usable. If the initial optional TIM2 read faults, no serial output follows; the skip-TIM2 build isolates that case. Neither build writes OTP, lifecycle state, flash, HDPL or RDCR. All debug configuration occurs after trace transmission.

## Wire format and decoder

PD0 idles high. Every packet begins with low for 12 delay units and high for 4. Each data bit is low for 1 unit (zero) or 3 units (one), then high for 1 unit; bytes transmit least-significant bit first. This self-clocked format does not require a known UART baud rate. Delay loops use 5,000 iterations per unit; the initial high delay is 8,192 units. At the documented nominal 400 MHz ROM CPU clock, the complete stream is expected to take several seconds, but this estimate is not a measured timing guarantee. Allow 30 seconds after boot for the first capture.

The header is `BTD1`, type (`u8`), sequence (`u16`), address (`u32`), payload length (`u16`), followed by 0–64 payload bytes and CRC32 of the header plus payload. Multibyte fields and CRC are little-endian. CRC uses polynomial `0xEDB88320`, initial/final XOR `0xFFFFFFFF`, matching Python `zlib.crc32`.

| Type | Meaning |
| --- | --- |
| `1` | Checkpoint: address `0x100` means both traces sent; `0xFFFFFFFF` means complete; 1–5 identify debug stages |
| `2` | Four-word immediate timer/CONTROL snapshot |
| `3` | Pending read at the header's address |
| `4` | Seven-word debug status |
| `5` | Single-register readback at the header's address |
| `0x10` | Secure trace chunk |
| `0x11` | Nonsecure trace chunk |

Run the offline decoder on Logic's digital export:

```powershell
python firmware/boot-timing/experiments/pd0-dump/decode.py CAPTURE/digital.csv --output CAPTURE/pd0-decoded
```

The output folder must be new. `decode-report.json` includes CRC-checked packets, register values and missing chunks. Complete buffers become `secure-trace.bin` and `nonsecure-trace.bin`, suitable for the separate [ROM-event decoder](../rom-trace/decode_trace.py). Numeric decoding needs no vendor reference; optional names use `--reference tmp/boot-rom-reference/rom_trace_parser.c`, retrieved and hash-checked by [fetch_reference.py](../rom-trace/fetch_reference.py). Incomplete traces remain as individual packet data in the JSON; missing bytes are never fabricated. A later debug-stage failure can make the overall verdict fail while leaving both complete trace files available.

The standard latched-marker analyzer will reject intentional PD0 data pulses; use the first marker edge for latency and this decoder for the subsequent stream. The decoder checks packet sequence, CRC, both trace lengths, final completion and PE0 remaining high. `selftest.py` checks full recovery with pulse jitter and rate drift, CRC corruption, truncated completion, and a partial dump.

Rebuild locally with `build.py --output NEW_DIRECTORY --snapshot SAVED_SECTOR`; add `--skip-tim2` for the alternate build. The linker keeps the 1 KiB stack and rejects payload overlap. GCC reports a maximum nested static stack use below 256 bytes for this source. The scripts never connect to or operate hardware.
