# Four-bit 25 MHz qualification after CLK damping

The tested setup passes the recorded capture/save/readback trials at **25 MHz, four bits**, with **NEGEDGE**, GPIO speed 3, and unchanged I/O compensation. The **27 Î© series resistor is approximately midway along the CLK wire**. All six SD signal probes were removed; only NRST, PE6 recovery UART and ground remained. No CRC, completion or storage-idle guard was relaxed.

This is qualification of the observed bench operations, not proof of production electrical margin or a definitive analog root cause. The earlier signal failures and probe/loading limitations remain in the frozen signal reports.

## Capture and image checks

| Test | Slot | Actual write path | Verification |
|---|---:|---|---|
| Pattern written with SD probes; reread after removal | 5 | Progressive PIO | Every image byte equals retained source RAM |
| Normal-exposure RAM scene, write/read without SD probes | 6 | Progressive PIO | Every image byte equals retained source RAM |
| 230.597 ms exposure RAM scene, write/read without SD probes | 7 | Progressive PIO | Every image byte equals retained source RAM; all 20 LINE snapshots pass |
| Autonomous awake cold flash capture | 8 | IDMA, observed mode 1 | Every image byte equals retained source RAM |
| Three normal cold flash saves through Standby | 9â€“11 | IDMA-configured profile with PIO fallback; telemetry lost | Full slot retrieval, valid markers, independent PNG sample decoding, attributed SBF |

Each full slot is 3,730 sectors: GXR2, 152 reserved metadata bytes, 1,909,600 packed RAW10 image bytes and GXRE. Each readback used eight checked READ operations. The source comparisons for slots 5â€“8 cover every image byte; the Standby trials cannot retain that comparison because high SRAM is lost.

In the long exposure test, writing started **9.434 ms before FRAME**. Twenty immediate 512-byte LINE tail snapshots matched final source RAM (10,240 sampled bytes). This supports the conservative streaming boundary empirically; it is not an architectural AXI-drain guarantee. The separate awake cold IDMA test measured **169.826 ms** from first write to payload completion using the 400 MHz DWT clock.

## Three normal cold cycles

| Cycle | Slot | Current onset â†’ plateau (ms) | Energy (mJ) | Attributed Standby / full image read |
|---|---:|---:|---:|---|
| cold01 | 9 | 419.916 | 230.023 | Pass / pass |
| cold02 | 10 | 410.282 | 225.653 | Pass / pass |
| cold03 | 11 | 419.518 | 229.913 | Pass / pass |

Median: **419.518 ms / 229.913 mJ**.

Each slot had a blank first sector before its cycle. After each measurement, warm PE6 recovery reached the exact early park and SBF was read without an intervening power-off. SBF attribution also relies on the reviewed CSSF-clear path and the bench ownerâ€™s recorded chronology; no live pre-WFI flag observation is claimed.

The energy window is branch-current onset to the qualified Standby plateau, with the separate one-second confirmation excluded. Thresholds and native-sample integration follow the earlier baseline. No phase or rail probe was present, so no new per-phase energy, rail-good timestamp or physical WFI timestamp is inferred. See the [energy summary](cold-cycles/energy-summary.json) for exact intervals and comparison arithmetic, and [replay instructions](cold-cycles/README.md) for the compact native-sample evidence.

Clock, phase, resistor, probe loading, scene, card state and slot position all changed from the earlier runs. These are observed configuration differences, not isolated causal gains. The energy covers the JS-fed Nucleo branch and is not an isolated-MCU or production-battery figure.

## Exact selected firmware

- Capture SHA-256: `29b8ad5823ad45b7acce77222747b43b7077e1f82ec46059dea1c12eb3a82cd7`
- Recovery prefix SHA-256: `6858d267f89814ba87326dde34e3c763b0fb6a2c5c82ab437ea3bf19a0eaf5b7`
- Complete 64 KiB NOR sector SHA-256: `79c7c4ef3fb7d06baf3c2fb16dccaae4cd7f585c2319af7065f939bd006a39cd`

The programmed sector read back byte-for-byte and the following 4 KiB remained unchanged. Early load remains 15,804 bytes. Relative to v23, the 5,140-byte prefix changes only the two required CRC literals; recovery instructions and all 20 recovery literals remain unchanged. The frozen source validation passed 158 offline tests.

The exact profile retains progressive PIO for an incomplete frame and polling IDMA for a complete slot; DMA-WFI remains disabled. The separate awake cold test establishes observed IDMA operation. The three Standby runs do not retain individual stream-mode telemetry.

`no-probe-qualification.json` binds the source records by hash and contains the detailed limits. Completion markers do not establish pixel checksums or arbitrary SD power-loss safety. The original pre-resistor and observed-resistor records remain unchanged.

## Final target state

At **05:40:21 UTC**, the target remained powered in the **awake, idle RAM READ terminal after slot 11**, not Standby. No fourth normal boot was performed. The Joulescope session closed with range 128 preserved; the COM port was closed and BREAK released. CN10 remained connected, Logic 2 remained running, and no hardware helper was active.
