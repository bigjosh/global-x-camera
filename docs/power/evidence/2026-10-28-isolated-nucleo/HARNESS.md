# Isolated Nucleo RAM power harness

This is an experimental RAM program, not installed camera firmware. The owner
operates the bench; importing the runners or executing their `__main__` only
checks local frozen build identities. Camera and SD are physically disconnected
for this campaign. No NOR or SD writes occur in the harness.

## Measurement

All current is measured at the board's 5 V input, so neither phase isolates the
MCU die or eliminates regulator/peripheral/board overhead. GPIO PD12 encodes
11 = busy begin, 12 = busy end, 13 = shallow-sleep begin, 14 = sleep end, with
nominal pulse widths of twice the event ID in microseconds. Use the native
Joulescope GPIO timestamps for wall time; DWT can pause in sleep.

Each run performs three 10 ms awake SysTick checks, about 200 ms of a deterministic
integer/volatile-SRAM workload, and about 200 ms of WFI with a 100 Hz SysTick
wake. The sleep result includes these periodic interrupts. Both intervals keep
LEDs off, the selected CPU divider, and the same selected cache/RAM controls.
The workload's checksum can be independently replayed with `check_workload.py`.
Use paired runs from the same binary: changed code placement changes uncached
instruction-fetch costs even when the workload source is unchanged.

## Frozen versions

| Version | Change and qualification |
|---|---|
| v1 | 400 MHz finite wake; refused the disabled pending TCM_ECC IRQ before measurement. |
| v2 | Added CPU dividers and RCC inventory; not executed. |
| v3 | Records and clears only disabled pending interrupts; refused missing SRAM sleep-clock permissions before measurement. |
| v4 | Explicit paired setup/restoration of required SRAM/RIF/bus/BSEC sleep permissions. Successfully measured at 400/200/100/50 MHz. |
| v5 | Flag 2 gates only unused AXISRAM1/2/3 RUN clocks; restores them before park. |
| v6 | Flag 4 enables instruction cache only, then disables/invalidates it before park. Data cache stays off. |

The versioned directories freeze source, binary, linker map/disassembly and hash
manifest. `probe.c` and `build.py` describe the newest candidate; never overwrite
a versioned directory. `run.py` and `run_v1.py` remain available to the separate
MDIO helper. Newer `run_vN.py` admits a hash allowlist of earlier successful
programs when making a reviewed upgrade.

The first v6 I-cache observation exposed a host-only mask error: Cortex-M55's
CMSIS `core_cm55.h` defines CCR.IC at bit17 (0x20000) and CCR.DC at bit16
(0x10000). Firmware used the correct CMSIS symbol; the original Python check
had the masks reversed. The failed observation is retained. Only `run_v6.py`
was corrected, six negative regression cases were checked, and a new
`cacheon01/reobserve/` qualified the unchanged firmware/code/proof. See
`v6-cache-validator-regression.json` and `test_v6_cache.py`.

## Controls and restoration

`divider` 1/2/4/8 selects 400/200/100/50 MHz by changing only the IC1 integer
divider; PLL1 and bus/peripheral dividers stay unchanged. Flag 1 explicitly
clears DBG_SLEEP during the intervals. The first qualified v4 control already
had DBG_SLEEP clear, so its flag-0 measurement is not debug-emulated sleep.
Flag 2 gates AXISRAM1/2/3 RUN clocks, without erasing, resetting, or powering
down RAM. Flag 4 selects I-cache. Flags may be combined in v6.

Code/vectors are at 0x34300000, workload at 0x34310000, stack within
0x343AF000..0x343B0000, request at 0x343C1F00, and 1024-byte proof at
0x343C2000. SRAM4/5/6 remain accessible; TCM clocks are never gated.
Required sleep permissions are explicitly enabled and their original values
restored. Final state is awake at the exact self-branch park, 400 MHz, caches
off, SysTick off, interrupts masked, original DBG_SLEEP/SCR/RCC values restored.
The harness's vector table remains installed. Hardware verification checks
complete immutable code, stable proof, final context and live fault registers.

No UART interrupt listener is installed. Existing autonomous recovery depends
on ST-LINK's experimentally observed reset response and the flash prefix's
polled C0 detector. Finite SysTick wake and an awake final park avoid depending
on that mechanism to exit sleep. The earlier unbounded-WFI experiment failed
live observation and required cold recovery; it is not qualified proof of a
specific sleep state. Disabled TCM_ECC pending was observed and later cleared
without immediate reassertion; its origin remains unresolved and this is not
a memory-health qualification.

## Root-only invocation

Prepare from a fresh exact initial early park or from the previous successful
`verified.json`, start the current logger, launch once, wait for the recording
to end, and only then observe. Do not poll ST-LINK during the measurement.

```python
b, session = runner.prepare(build, new_directory, flags=4, divider=1,
                            prior=previous_verified)
# Root starts the native JS logger here.
runner.launch(b, session)
# Root waits for the logger to stop before accessing the target again.
result = runner.observe(b, session)
```

This campaign measures synthetic active-work and periodic shallow-sleep costs.
It does not qualify camera timing, capture/save energy, retention, production
shutdown, or direct battery operation.
