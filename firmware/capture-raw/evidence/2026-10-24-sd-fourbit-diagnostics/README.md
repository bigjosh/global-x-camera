# Four-bit SD diagnostics: reads pass at 25 MHz; full pattern save passes at 12.5 MHz

This archive freezes the recorded facts through **2026-10-25 03:47 UTC** (October 24 locally), before the subsequent GPIO-speed experiment. It supplements the immutable [initial CMD8 failure record](../2026-10-24-sd-fourbit-bringup/README.md). It is an incremental bring-up result, **not the requested three-cycle speed/energy comparison**.

| Experiment | Recorded result |
|---|---|
| Four-bit READ at 25 MHz after attaching CLK/CMD probes | First sector and two 64-sector ranges matched the earlier one-bit slot-0 bytes exactly; all three operations ended idle with accepted four-bit negotiation |
| Physical CMD0/CMD8/R7 trace | Selected command/response packets had valid CRC7 and the expected `0x1AA` CMD8 echo |
| First full pattern save at 25 MHz | Progressive PIO write failed with data CRC error; cleanup also reported a command CRC error and the host remained active |
| Isolated 12.5 MHz pattern save | One complete 3730-sector slot saved; full readback matched all 1,909,600 original camera-RAM bytes and independently decoded PNG samples |

## Probe condition and unresolved initial failure

The successful READs used unchanged v19b RAM firmware after Saleae **CH2 was attached to breakout CLK and CH3 to CMD**. No breakout supply probe was added; **CH5 was not moved**. The observed change from failed CMD8 to successful identification has no established root cause. Contact changes or probe loading are possibilities, not a demonstrated fix. Any later comparison must retain this changed probe condition in its limitations.

The three reads covered LBA 0/count 1, LBA 0/count 64, and LBA 64/count 64. These are known-data checks over part of the existing slot; they do not constitute a complete preservation readback. Accepted width telemetry recorded SCR widths `5`, ACMD6 response `0x920`, four-bit CLKCR and negotiated width 4. The native command clock began at 100 kHz before data operation at 25 MHz. OCR/R3 responses do not carry CRC7; the trace claim applies to the selected CMD0/CMD8/R7 packets rather than every decoded response.

## The 25 MHz write failure stayed a failure

The first deterministic camera acquisition completed without recorded camera errors, then progressive PIO CMD25 for slot 3 failed after 408 FIFO words had been submitted. Its first data error status was `0x5002`, with driver error 14; CMD12 returned `0x800C00`, including `COM_CRC_ERROR`. Later CMD13 returned READY/TRANSFER `0x900`, but the host status remained `0x5042`, `media_idle=0`, `controller_owned=1`, and cleanup error 10. READY alone did not establish successful cleanup.

The card may contain a partial slot 3 even though the completed-sector counter is zero. No completion or image-integrity claim is made for it. The root bench owner used the user's existing explicit experimental-board clobber and reset/erase authorization for one measured warm UART/BREAK recovery. The [compact diagnostics](diagnostics.json) preserve that authorization and explicitly retain the non-idle failure. The resulting exact v18 early park recorded eight good pulses and no bad pulses.

## The isolated 12.5 MHz test

The 12.5 MHz RAM build changes only two literal words relative to the 25 MHz pattern executable: the divider `3 → 6` and requested clock `25,000,000 → 12,500,000`. The driver and abort path were unchanged. The same 25 MHz option rebuilt byte-identically to v19b.

One capture saved **slot 4** as `GXR2` + 152 reserved metadata bytes + 1,909,600 packed RAW10 bytes + `GXRE`, totaling **3730 sectors / 1,909,760 bytes**. Full SD readback equaled the retained original camera RAM; all markers and independent PNG sample decoding passed. The deterministic RAW payload SHA-256 is:

`5edaa1705f76b8434993271c86e71d5d83bce1c0ec7272caeec9564594279c1e`

The successful operation used progressive PIO (`stream.mode=2`), not a newly qualified IDMA write. Its first-write-to-commit interval was **321.870 ms** by the recorded nominal 400 MHz DWT counter. This is a RAM diagnostic interval; it is **not** power-on-to-shutdown time or an energy result. A single successful slower-clock operation does not establish the electrical cause of the faster-clock failure or production reliability.

| RAM executable | SHA-256 |
|---|---|
| 25 MHz scene/read v19b | `9a541fbe00de3a2c3d92b5fbe48aafe7f3ed4b770aedc3da1275a0c2ca662a52` |
| 25 MHz pattern v19b | `11dd2b0ce63aeef0a0811cb3ee0870314c31ba6108aaed42e2c47fe24e8a0dd4` |
| 12.5 MHz pattern v20 | `9e0e901bc8283dfa2e66620c39a68ec33f8e7d6de8d6d7f4a5f4d8ac837e50ed` |

## Frozen scope and replay

No NOR programming occurred in this diagnostic pass. The installed v18 recovery prefix remained `9401bed4076d6e9e4d2e4f9236661faf7b8f0e051cb332ea4dcbba09da336eba`; no fresh complete NOR-sector verification is asserted. After the full readback, [another early recovery at 03:47 UTC](post-readback-recovery.json) passed with nine good pulses and no bad pulses, before the next GPIO-speed experiment. These are historical checkpoints, not instructions describing the present bench state.

Run `python check.py` in this folder to verify artifact hashes, source-selector bindings, the recorded failure/success distinctions, negotiated widths, complete image-verification flags and the isolated build change. It performs no hardware access. Pixel comparisons and physical trace decoding were performed against private local data; this archive rechecks their recorded, source-bound results, not the omitted bytes.

[diagnostics.json](diagnostics.json) contains selected numeric/error/result fields; [source-selector.json](source-selector.json) records the original private source hashes and relative paths. The checker and [index.json](index.json) bind the public files. No image pixels, sector payloads, raw SRAM, native instrument arrays, card identifiers or absolute local paths are included. The original failure archive remains unchanged. Cold capture/Standby qualification and the requested three-cycle energy comparison remain outstanding at this frozen boundary.
