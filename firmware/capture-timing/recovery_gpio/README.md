# Early GPIO recovery candidate

This offline builder adds a small recovery guard to the exact tested v25 prefix.
It copies the receiver unchanged. It does not program the board or operate any
instrument. Hardware qualification and the external sink connection are pending.

The October 17 bench attempt found approximately 0 V at the JS110 input and all
three monitored target rails throughout the requested off/on cycle. No firmware
was written. The power helper stopped cleanly with its initial automatic range
restored. The previous v25 image remains the last verified installed firmware;
the v34b guard is built and independently reviewed, but **not installed or
hardware-qualified**. Compact build and bench facts are in
[preparation evidence](../evidence/2026-10-17-recovery-preparation/summary.json).

PE1 on **CN15 pin 24** is an input with its internal pull-up enabled. With the
input unconnected or released, execution continues through the original normal
flash-boot path. Pulling PE1 low before a cold start requests recovery. Use an
open-drain sink referred to target ground to prevent a separately powered output
from feeding an unpowered MCU. The [JS110 interface](../../boot-timing/js110-recovery-output.md)
uses OUT0 to control a small NMOS, with a gate pull-down to preserve normal boot
when disconnected. Electrical qualification remains a separate step.

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

The recovery path precedes expanded-SRAM initialization, sensor setup, receiver
setup, DMA and the application's NOR read. A maintenance controller must still
verify the exact live prefix bytes, exact park PC/instruction, CPU context,
caches and idle XSPI state before using the reviewed NOR helper. A status word
or an asserted input alone does not prove safe maintenance.

## Build and provenance

```powershell
python firmware/capture-timing/recovery_gpio/build.py `
  --base tmp/bringup/capture-raw10-trim-os-v25-20261017 `
  --output tmp/bringup/capture-recovery-pe1-v34-20261017
```

The input sector must have SHA-256
`c43721b29f437546d3090632495f4527f4ba34d4af773a23214cdd86a0adb817`.
All frozen source hashes and the exact receiver bytes are checked. Only the
bytes occupied by the new boot prefix may change. The output manifest records
the guard source hashes, generated prefix hashes, status layout and exact
`fee7` park instruction address. The archived receiver manifest remains
byte-identical and continues to reference the frozen original source files.

The first v34 build is 4,400 raw prefix bytes versus 4,008 for v25: **392 extra
bytes**. Its ROM image including header/alignment is 5,440 bytes, still below the
8 KiB receiver offset. Source size is not a measured boot-time cost.

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

After both normal boot and externally requested recovery are measured, promote
the reviewed guard hooks to the maintained prefix builder and require recovery
metadata for newly generated experimental images. Historical frozen builds are
immutable evidence; rebuilding them does not automatically add this guard.
The NOR programming workflow should reject a new experimental image lacking a
reviewed guard unless the specific historical restoration is explicitly
intended. Receiver experiments should use an already validated guarded prefix
and retain its startup ordering.

This cannot recover a corrupt boot header, missing/overwritten guard, failure
before the guard or debug opening, failed hardware, or a closed security
lifecycle. Recovery still requires a working target power cycle and a verified
external pin sink. It protects later experimental firmware failures, which are
the observed source of manual BOOT1 intervention.
