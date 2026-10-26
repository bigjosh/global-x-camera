# Final Standby capture: independent SD wire verification

October 26, 2026. Offline parsing of the saved six-channel digital export passed for **slot 28, LBA 104440**, using the reviewed four-bit 12.5 MHz startup profile. No live instrument or board API was used. [Complete hash-bound report](final-standby-waveform.json).

- All **237 host commands** had valid CRC7 and the expected order. Decoding agreed at rising-edge offsets from 0 through 32 ns. The card received one CMD55/ACMD23 announcing **3,730 sectors**, one CMD25 at the correct LBA, then CMD12 and readiness polling.
- All **3,730 data packets**, **14,920 lane CRC16 values**, start/end bits and **3,730 accepted status tokens** passed independent reconstruction from the raw transitions.
- All **1,909,760 wire bytes** exactly matched the subsequently retrieved complete SD slot, including GXR2, 152 zero metadata bytes and GXRE. Slot SHA-256: `9d8fbd5e82e2692fef219b5073a0e4b4a19202be854d211a9ab22ec6c358f037`.
- CMD12's exposed DAT0 busy lasted **1.834004 ms**. Two CMD13 responses still reported programming; the next reported READY/TRANSFER (`0x900`) after DAT0 rose. CMD25 start to that response's end was **323.042560 ms**.
- The contiguous initial train contained **108 CMD-high clocks** before CMD0. One isolated CLK transition during cold rail startup preceded the train and was excluded from its count.

**Original camera RAM was lost in Standby.** This proves wire-to-SD equality, not another comparison with the original sensor frame. Digital timing has 4 ns acquisition resolution and does not establish analog margins, energy, power-loss atomicity or independent Standby-entry attribution. Data-packet window and busy durations overlap other reported boundaries and must not simply be added together.

Replay: `tmp/bringup/sd50-reviewed-20261026/analyze_final_standby.py`. Sources are the saved `final-standby-cold/binary/` exports and `final-standby-readback/slot.bin`; their hashes and the readback/boot records are bound in the JSON report. The [experiment README](README.md) owns the overall installation and qualification status.
