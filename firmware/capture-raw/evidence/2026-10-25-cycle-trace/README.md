# Fixed RAM logger — October 25 qualification

One cold capture at four-bit SDMMC2 / 25 MHz / NEGEDGE produced **101 fixed
timestamps**, with 17 defined coarse counters. Full slot 12 readback matched
all 1,909,600 original camera-RAM bytes. The host-decoded PNG matched every
RAW10 sample shifted left six bits, and visual inspection showed the patterned
illuminated scene. First-attempt UART recovery reached the exact early park
with nine good pulses and no bad pulses.

The [phase table and usage instructions](../../CYCLE_TRACE.md) describe the
intervals, overlap and overhead. [timings.json](timings.json) contains the
original decoded CTL1 values; [prefix-telemetry.json](prefix-telemetry.json)
contains the existing boot/sensor/load records from the same run.

| Measured interval | ms |
|---|---:|
| Complete SD initialization | 227.395003 |
| CMD55/ACMD41 negotiation inside initialization, 62 attempts | 203.689445 |
| Slot scan, 13 first-sector reads | 11.325615 |
| Full slot write, one CMD25 / 3,730 sectors | 161.803048 |
| CMD25 acknowledgement through DATAEND observation | 159.402875 |
| Final readiness after CMD12 | 2.164930 |
| Prefix DWT zero through logger finalization | 412.364838 |

These are nominal 400 MHz DWT intervals from one instrumented run. Rows are
nested and overlap; they must not be summed. The data phase includes card and
controller pacing. It does not isolate physical wire time or internal flash
programming. No timestamp covers power/reset/ROM before prefix DWT zero, and
this awake diagnostic does not measure Standby entry or a new energy baseline.

## Identity and validation

- Receiver SHA-256: `0681708de7474c31159eb7125d8ed0a7d0d72844868bdfc6c184714fc2709380`.
- Prefix SHA-256: `0e37d33e1ede9008525feffb7f20c81112daf2169171f7130f68798366a4eec0`.
- 64 KiB sector SHA-256: `9c9b65f023bb0c36e5c5149fddf8fbe2922c07294d25e859511b4cff9139810b`.
- Full physical NOR readback and the unchanged following 4 KiB passed after
  installation. Exact CRC-only prefix review preserved all recovery code,
  referenced literals and the 15,804-byte early load.
- Logger occupies 1 KiB at `0x343FB000`. Markers compile to a CYCCNT load and
  fixed volatile store, plus address setup; no per-marker call or barrier.
  Initialization performs 288 clearing stores plus header setup once. Instrumentation adds 1,144 loaded
  bytes in the late segment and leaves 124 bytes spare in the fixed early range.
- An uninstrumented control rebuild is byte-identical to the prior awake
  image. Normal source defaults are unchanged. Relevant offline suites passed:
  128 RAW/integration tests, 14 SD-driver tests and 13 recovery-bridge tests.
- The initial host decoder rejected receiver event 2's reported 64 MHz. This
  is the startup `SystemCoreClock` value before `SystemCoreClockUpdate`, while
  the hardware remains on the checked ROM 400 MHz clock. The decoder now
  accepts only this exact `207 → 2 → 3` bracket with successful prefix and ROM
  clock evidence, retaining both reported and qualified clock values. No
  firmware change or repeated capture was needed.

`FREEZE.json` binds the measurement data, original RAM records, event headers,
exact firmware binaries, image validation and displayed PNG. Run
`python firmware/capture-raw/evidence/2026-10-25-cycle-trace/verify.py` for
offline replay. The raw acquisition/readback buffers, full instrument streams
and host command logs remain in the private `tmp/bringup/cycle-trace-20261025`
and `tmp/bringup/sd25-crc-20261025/trace-cold01` records. Hash reports attest the
full source comparison; the public archive does not independently recreate
that comparison from omitted RAW buffers.

## Final bench state

The original qualified Standby sector
`79c7c4ef3fb7d06baf3c2fb16dccaae4cd7f585c2319af7065f939bd006a39cd`
was restored and independently read back; the following 4 KiB remained
unchanged. One subsequent normal cold boot returned to the familiar low-current
plateau. At **06:26:10 UTC**, JS110 closed cleanly, restored range 128 and left
target power on at **4.892731 V / 8.188210 mA**. This final observation is a
current signature, not a new attributed SBF measurement or image readback;
slot 13 is only the expected next image. Instrumented slot 12 is verified.
COM8 is closed, BREAK released, Logic 2 remains running, no helper is active,
and the wiring/jumpers/probe map are unchanged.
