# Early GPIO recovery guard

This offline builder adds a small recovery guard to the exact tested v25 prefix.
It copies the receiver unchanged. It does not program the board or operate any
instrument. The user connected a diode sink on October 17. The powered pin matrix
and v34b normal/recovery boot selection have now passed. The v34b recovery park
retained ROM's enabled instruction cache, so the maintenance checker correctly
refused it. Revision **v34c** disables and invalidates that cache only on the
recovery branch. Its normal capture, requested recovery, and autonomous NOR
maintenance have now passed; see the
[diode and recovery evidence](../evidence/2026-10-17-diode-recovery-smoke/).

The earlier approximately-0-V source-power blocker and the then-uninstalled
candidate are historical preparation results, superseded by the powered tests
and v34b installation. Their original records remain in
[preparation evidence](../evidence/2026-10-17-recovery-preparation/summary.json)
and the [initial diode checks](../evidence/2026-10-17-recovery-preparation/diode-followup.json).

The [guard qualification](../evidence/2026-10-17-diode-recovery-smoke/guard-qualification/)
established both v34c paths:

- With OUT0 high, the guard recorded normal state 2, PE1 high and 40,002 elapsed
  DWT cycles. Capture reached stage 40 with one complete frame and passed image
  integrity checks.
- With OUT0 low before a cold start, it recorded parked state 3, reason 1, PE1
  low and 40,004 elapsed cycles. Debug access worked; the exact live prefix and
  park PC `0x3418078C` matched, `CCR=0x201` confirmed both caches disabled, and
  XSPI was idle. The low-SRAM NOR INFO operation succeeded.
- In that same early recovery session, real erase/program operations changed the
  sector from v34c to v34b and then back to v34c. Both full 65,536-byte readbacks
  matched their intended images. Each operation reported result 0, flags `0x2F`,
  changed/erased/completed mask `0x3`, 22 programmed pages and 24 write-enable
  commands. No boot-jumper change was needed.
- After restoring v34c, another discharged cold boot captured a recognizable
  room image with matching byte integrity. The guard recorded PE1 high and
  40,002 elapsed cycles. The power session closed cleanly; its original settings
  were restored, then the GPIO supply was deliberately set to 3300 mV and OUT0
  high for the next normal boot. Reopening the JS110 confirmed those settings,
  and an MCU input read confirmed PE1 high. Target power remained on in auto
  range. The final image and raw waveforms remain local; compact evidence is
  in the qualification directory.

These tests qualify the GPIO escape and flash-maintenance path. They do not add
the separate delayed-data-receiver D-PHY fix: this guarded image retains the
v25 camera receiver unchanged. A later final-state record, rather than this
qualification sequence, establishes which image and output settings are left
on the board.

PE1 on **CN15 pin 24** is an input with its internal pull-up enabled. With the
input unconnected or released, execution continues through the original normal
flash-boot path. Pulling PE1 low before a cold start requests recovery. Use an
open-drain sink referred to target ground to prevent a separately powered output
from feeding an unpowered MCU. The [JS110 interface](../../boot-timing/js110-recovery-output.md)
supports a small NMOS or the user's diode connection (PE1 anode, OUT0 cathode).
Select the matching host-helper polarity: diode OUT0 low requests recovery and
OUT0 high releases it; the NMOS option uses the opposite polarity. Keep the shared
GPIO supply at **3300 mV** for diode control. Four powered combinations passed:
pull-up/OUT0-low read low, pull-up/OUT0-high read high, and both pull-down
combinations read low. These are functional input readings, not analog-margin
or leakage measurements.

Commanding the shared supply off with retained OUT0 low **failed to release
PE1**: its input still read low with its internal pull-up enabled. The remaining
supply-off combinations were skipped after that failure. Do not use bank-off as
the normal-boot setting. The helper restores its starting settings, which in
these tests were bank-off/OUT0-low; successful restoration can therefore leave a
recovery request for the next boot. Before ending a session intended to leave
normal boot selected, deliberately establish and verify **3300 mV / OUT0 high**.

The guard is the first C action after the existing minimal vector entry. It
enables the GPIOE clock, configures only PE1 as input/pull-up, and starts the DWT
cycle counter. Existing volatile debug opening and marker-pin initialization
then execute while the pull settles. Immediately before the original DWT reset
and `raw10_memory_init`, the guard waits until at least 40,000 DWT cycles have
elapsed. This is **100 nominal microseconds at the existing 400 MHz ROM clock**,
not a clock-independent guaranteed delay. A missing/nonadvancing counter reaches
the recovery park after at most 100,000 polling iterations. It never converts a
timer failure into permission to boot the experiment.

A low sample, failed timer, or unexpected CPU context selects an awake,
IRQ-masked branch-to-self called `recovery_gpio_park`. Normal execution is
privileged Thread mode with CONTROL=0, IPSR=0 and PRIMASK=1. The guard records
these values; an unexpected context is retained for inspection and does not
become a maintenance authorization. Debug opening uses the existing volatile
BSEC settings. **Recovery is a firmware debug park, not the ROM's BOOT1
development mode.** There is no reset, ROM jump, OTP write, WFI, or BKPT.

On v34c's recovery branch, `SCB_DisableICache()` executes the CMSIS barrier and
instruction-cache invalidation sequence before entering the park. It clears only
the instruction-cache enable; it does not disable or clean an unexpectedly
enabled data cache. Host validation still rejects enabled data cache. Normal
capture skips this cache operation. The earlier v34b park selected the right
branch but had `CCR=0x20201`, so it was not authorized for uncached maintenance.

The recovery path precedes expanded-SRAM initialization, sensor setup, receiver
setup, DMA and the application's NOR read. A maintenance controller must still
verify the exact live prefix bytes, exact park PC/instruction, CPU context,
caches and idle XSPI state before using the reviewed NOR helper. A status word
or an asserted input alone does not prove safe maintenance.

## October 19 proposed ST-LINK VCP recovery

The user reports target power restored through JS110, ST-LINK USB connected and
the SD breakout wired, but the OUT0 recovery wire no longer reaches. They
specifically prefer an ST-LINK-controlled signal. This is a proposed replacement
control route; **the installed v44 guard still checks PE1**. No new firmware,
serial stimulus, target reset or instrument operation was performed for this
review.

The MB1940 C02 schematic and ODB connectivity establish this existing route:

```text
PC virtual COM port → ST-LINK PG14 / STLK_VCP_TX
                    → R24 (33 ohms) → target PE6 / USART2_RX
```

PE6 is also available at CN15 pin 2 through SB34. No added jumper or diode is
needed for a boot-prefix detector on PE6: it would use the already-connected
receive signal, not connect PE6 to PE1. It does not conflict with the selected
SDMMC2 lines.

Recommendation: retain the qualified PE1 guard and add an independently tested
VCP recovery request path. A host-sent repeating UART pattern could be detected
early, potentially within the existing nominal 100-microsecond guard interval.
Idle-high/no request should continue normal capture. Repeated zero bytes at
115200 baud are a candidate stimulus, not a qualified protocol: at 8N1 each byte
occupies about 86.8 microseconds, but USB/bridge gaps and boot alignment must be
measured. A single GPIO sample is not sufficient. Either validate bounded
activity detection or decode a defined request, documenting any additional
normal-boot latency and accidental-trigger behavior. Keep this VCP reserved from
unrelated host traffic during selection. Preserve the existing cache/context/
idle-XSPI maintenance checks.

Do not assume host RTS/DTR changes drive a usable output. This V3EC board exposes
debug, reset and VCP signals, not the GPIO bridge of a standalone V3SET/MODS.
ST reports that ST-LINK firmware ignores `SET_CONTROL_LINE_STATE`; that is
separate from UART `SEND_BREAK`, whose support on the installed version remains
unverified. A sustained TX-low BREAK would simplify selection if actual hardware
tests prove it works, but a successful serial API call alone is not evidence of
that waveform. NRST cannot substitute as a boot-sampled low input while the CPU
is held in reset.

This route retains an independently powered debugger-to-target UART connection.
It does not establish powered-off isolation or zero backfeed. Qualify target
power-off behavior, actual normal/recovery selections, unchanged capture and
maintenance access before retiring the external recovery method. No new wiring
instruction or automatic fallback is implied by this proposal.

Sources: [MB1940 C02 schematic, sheets 3/13/14](https://www.st.com/resource/en/schematic_pack/mb1940-n657x0q-c02-schematic.pdf),
[ST TN1235 overview](https://www.st.com/resource/en/technical_note/tn1235-overview-of-stlink-derivatives-stmicroelectronics.pdf),
and [ST employee explanation of VCP control-line handling](https://community.st.com/stm32-mcus-boards-and-hardware-tools-26/stlink-v3mods-rts-cts-rts-dtr-156036).

## Build and provenance

```powershell
python firmware/capture-timing/recovery_gpio/build.py `
  --base tmp/bringup/capture-raw10-trim-os-v25-20261017 `
  --output tmp/bringup/capture-recovery-pe1-new
```

The input sector must have SHA-256
`c43721b29f437546d3090632495f4527f4ba34d4af773a23214cdd86a0adb817`.
All frozen source hashes and the exact receiver bytes are checked. Only the
bytes occupied by the new boot prefix may change. The output manifest records
the guard source hashes, generated prefix hashes, status layout and exact
`fee7` park instruction address. The archived receiver manifest remains
byte-identical and continues to reference the frozen original source files.

| Revision | Raw prefix | Wrapped ROM image | Status |
|---|---:|---:|---|
| v25 baseline | 4,008 bytes | 5,056 bytes | Original capture baseline |
| v34b | 4,400 bytes | 5,440 bytes | Normal capture and requested park passed; enabled I-cache prevented maintenance authorization |
| v34c | 4,432 bytes | 5,472 bytes | Normal capture, requested uncached park, NOR INFO and real verified erase/program round trip passed |

The v34c full-sector SHA-256 is
`14b6015e0c5705ce5bde655470977851e32cce01fa0164ccda163b892dca3222`;
its raw prefix SHA-256 is
`b22939a1b6c2d30a18043c4c7cfc7f6ac63e53ea15acd9368bf2e1039bc73abe`.
Its park remains `0x3418078C`. The receiver and all bytes after the new prefix
remain identical to v25. The prefix is still below the 8 KiB receiver offset.
Source size is not a measured boot-time cost.

## Status schema

Recovery status is 24 little-endian 32-bit words at **0x341F7000**, in memory
already available to the prefix. The magic is `0x52475031`, schema is 1, and the
word count is 24. After `raw10_memory_init` succeeds, normal boots copy the record
to **0x343F7000** before the frame overwrites the low-memory original. The normal
trace's original DWT reset is retained after the guard check.

| Word | Meaning |
|---:|---|
| 0–2 | Magic, schema, word count |
| 3 | State: 1 begun, 2 normal, 3 parked |
| 4 | Reason: 0 normal, 1 low pin, 2 timer failure, 3 unexpected CPU context |
| 5 | Pin encoding: `0x00040001` = port E, pin 1 |
| 6–7 | Nominal clock Hz and required settle cycles |
| 8–11 | Start cycle, sample cycle, elapsed cycles, poll iterations |
| 12–15 | GPIOE IDR, MODER, PUPDR; RCC AHB4ENR |
| 16–17 | CoreDebug DEMCR and DWT CTRL |
| 18–20 | CONTROL, IPSR, PRIMASK |
| 21–22 | BSEC DBGCR and AP_UNLOCK readback |
| 23 | Reserved, zero |

`check_park.py --build PATH/TO/staged --out NEW_DIRECTORY` checks an explicitly
allowlisted prefix and its live bytes/status before halting. It then requires the
exact parked PC, privileged IRQ-masked Thread context, disabled caches, no lazy
FP context, clocked/released XSPI and an empty idle XSPI FIFO. It writes no RAM
and issues no NOR commands. A passed check permits the existing low-SRAM NOR
helper's INFO operation; its own checks still precede a separately guarded write.
Do not run the normal high-SRAM post-capture cache helper in this early park.

Pin and pull specifications: [UM3417 Rev4, Table20](https://www.st.com/resource/en/user_manual/um3417-stm32n6-nucleo144-board-mb1940-stmicroelectronics.pdf)
maps CN15.24 to PE1; [DS14791 Rev11](https://www.st.com/resource/en/datasheet/stm32n657x0.pdf)
places PE1 on VDD and specifies internal pulls of 30–50 kΩ (Table68).
The nominal 100 µs settle is 50 µs at the MCU's 800 MHz maximum; harness
capacitance and the actual transition must still be checked on the bench.

## Making this protection permanent

Future experimental firmware must preserve the reviewed early recovery guard;
receiver experiments should reuse the qualified guarded prefix and retain its
startup ordering. v34c's normal, recovery and maintenance paths have been
qualified on this bench. Historical frozen builds are immutable evidence and
may lack the guard; restoring one must be an explicit choice.

The dedicated builder inserts and validates the hooks. The generic prefix
builders and NOR programming workflow do **not yet enforce** guard presence for
every new image. Adding that enforcement remains implementation work; until it
exists, review the source, manifest and exact programmed image before each new
experiment rather than assuming the guard survived a rebuild.

This cannot recover a corrupt boot header, missing/overwritten guard, failure
before the guard or debug opening, failed hardware, or a closed security
lifecycle. Recovery still requires a working target power cycle and a verified
external pin sink. It protects later experimental firmware failures, which are
the observed source of manual BOOT1 intervention.
