# Fixed RAM cycle timestamps

`--cycle-trace` adds inexpensive timestamps to the capture and SD code, leaving
the completed diagnostic run awake so ST-LINK can retrieve its RAM. It is
disabled by default. The normal build retains its prior executable bytes when
the option is omitted.

## Build and retrieve a diagnostic run

```powershell
python firmware/capture-raw/build.py --out tmp/bringup/raw-flash25-trace `
  --flash --cycle-trace --magic-format --async-stop --line-stream `
  --sd-bus-width 4 --sd-clock-hz 25000000 --sd-clock-negedge
```

Do not add `--standby`: the builder rejects that combination because Standby
loses this SRAM. The trace profile retains the usual CRC, capture, storage,
ownership and UART recovery checks. It changes the final behavior to the
existing awake diagnostic terminal; it does not measure entry into Standby.

Use the existing guarded awake inspection workflow in
[`inspect_flash.py`](inspect_flash.py). It verifies the exact build, live
immutable code, successful capture/storage records, card idle/deinitialization
and stable terminal proof before its first halt. It then reads the trace and
existing prefix telemetry from that same boot. The manifest binds the event
headers copied into the build to their SHA-256 hashes. Do not reset or enter
UART recovery before collecting the retained data, and do not use the log's
`DONE` marker as a substitute for the maintenance gate.

The standalone decoder can inspect an already saved 1 KiB binary without
accessing hardware:

```powershell
python firmware/capture-raw/cycle_trace.py path/to/cycle-trace.bin `
  --header path/to/build/cycle_trace_events.h `
  --header path/to/build/cycle_trace_sd.h `
  --require-complete --out path/to/cycle-trace.json
```

For identity-checked replay, supply `--header-sha256 PATH=SHA256` for both
headers using the values in the inspected build's manifest. Decoding alone
does not prove the live firmware, boot identity, image contents or safe state.

## Record and hook cost

The record occupies **1,024 bytes at `0x343FB000`**, outside the frame,
executable code and existing status records. Its schema is defined by
[`cycle_trace.h`](cycle_trace.h):

| Word range | Contents |
|---|---|
| 0–9 | `CTL1` magic, schema 1, size, nominal counter frequency, result, initialization/completion timestamps, event/counter counts, final `DONE` marker |
| 10–31 | Reserved |
| 32–159 | 128 fixed event timestamps; definitions in [`cycle_trace_events.h`](cycle_trace_events.h) and [`cycle_trace_sd.h`](cycle_trace_sd.h) |
| 160–191 | 32 coarse repeat counters |
| 192–255 | Reserved |

Initialization runs after the SRAM banks are available. Timestamp slots and
reserved words start at `0xFFFFFFFF`; repeat counters start at zero. Each mark
is an inline volatile read of `DWT.CYCCNT` followed by a store to that event's
fixed RAM word. Generated instructions also need address materialization when
the compiler cannot reuse an address register. There is no event-buffer cursor,
function call, text formatting, allocation or per-event barrier. Each slot has
one writer, so the IRQ and main paths do not share an incrementing log index.
Counters use a RAM read/increment/store at coarse loop boundaries; the SD data
poll/FIFO loops do not log every poll or transferred word.

This is small but nonzero overhead. No calibrated nanosecond cost per hook has
been established. Initialization clears the record once, and finalization
publishes the result with a barrier followed by `DONE`. In the first diagnostic
build, the receiver image grows from **27,024 to 28,168 bytes**: **1,144 bytes**.
The early NOR load stays **15,804 bytes**; the extra executable load is in the
late segment, which grows from **11,220 to 12,364 bytes**. Additional late-load
time and executed hooks are part of the instrumented run, not free overhead.

The boot prefix already records sensor initialization, START and early NOR
loading timestamps. Those records are reused rather than adding hooks to its
recovery-sensitive code. Only the reviewed receiver-CRC data literals change
when a new receiver is built. Prefix `CTP1`, `SEN1` and `S1OK` telemetry and the
new `CTL1` log share the unchanged nominal **400 MHz DWT counter**. Prefix code
zeros that counter after recovery selection; the new logger initializes later
without resetting it.

## First measured and verified trace

This table comes from one cold flash capture with the selected four-bit,
25 MHz/NEGEDGE profile. The decoded record is complete, reports result zero,
and records one IDMA transfer with no driver fault. Slot 12 passed full SD
readback, byte-for-byte equality with the original capture RAM, independent
PNG decoding and recognizable scene inspection. UART recovery passed on the
instrumented image. There are 101 observed timestamps and 17 defined counters.
It is a single instrumented run, not a replacement three-run baseline.

Source: [frozen trace and qualification](evidence/2026-10-25-cycle-trace/README.md);
RAM snapshot SHA-256
`bfdc012a20d0f280be584a402f38669f714c68f585e295c1a99cea63e6c6e78f`.
Durations below subtract the named timestamps from this same snapshot and
divide by the nominal 400 MHz counter rate. Names are exactly those emitted by
the decoder. Rounded values do not imply an independently calibrated clock.

| Step | Start → end event | Duration (ms) | Interpretation |
|---|---|---:|---|
| Runtime preparation | `RUNTIME_BEGIN` → `RUNTIME_READY` | 0.012335 | Diagnostic runtime setup |
| HAL initialization | `HAL_BEGIN` → `HAL_DONE` | 0.004360 | Existing HAL setup |
| I2C initialization | `I2C_BEGIN` → `I2C_DONE` | 0.013883 | Receiver-stage I2C setup |
| Receiver preparation | `RECEIVER_PREPARE_BEGIN` → `RECEIVER_PREPARE_DONE` | 0.139378 | Configuration before PHY startup |
| PHY Stop-state qualification | `PHY_STOP_QUALIFY_BEGIN` → `PHY_STOP_QUALIFY_DONE` | 0.783815 | Includes waiting until the required states qualify |
| Arm capture | `RECEIVER_ARM_BEGIN` → `RECEIVER_ARM_DONE` | 0.010543 | Software arming interval, not exposure duration |
| Late NOR load | `LATE_LOAD_BEGIN` → `LATE_LOAD_DONE` | 4.003635 | Load/validate late code while camera hardware progresses |
| Observe START acknowledgement | `START_ACK_BEGIN` → `START_ACK_DONE` | 0.065995 | One acknowledgement read |
| First LINE IRQ to FRAME IRQ | `FIRST_LINE_IRQ` → `FRAME_IRQ` | 9.928918 | IRQ observation span; excludes data before the first LINE callback |
| Essential frame handling | `FRAME_CHECK_BEGIN` → `FRAME_VALIDATED` | 0.396223 | Includes geometry/status checks, receiver stop and dispatching sensor STOP; asynchronous STOP acknowledgement is later |
| Sensor STOP command | `SENSOR_STOP_COMMAND_BEGIN` → `SENSOR_STOP_COMMAND_DONE` | 0.052515 | I2C command dispatch |
| Wait for sensor STOP acknowledgement | `SENSOR_STOP_COMMAND_DONE` → `SENSOR_STOP_ACK_DONE` | 34.768113 | 32 polls, interleaved with SD initialization; not a continuous CPU stall |
| Complete SD initialization | `SD_INIT_BEGIN` → `SD_INIT_DONE` | **227.395003** | Encloses the following SD init substeps and concurrent camera servicing |
| GPIO/rail settle delay | `SD_GPIO_SETTLE_BEGIN` → `SD_GPIO_SETTLE_DONE` | 1.020993 | Requested 1 ms delay plus software/service work |
| Initial SD clock train | `SD_CLOCK_TRAIN_BEGIN` → `SD_CLOCK_TRAIN_DONE` | 10.021018 | Requested 10 ms at identification clock |
| CMD0 | `SD_CMD0_BEGIN` → `SD_CMD0_DONE` | 0.550950 | Reset-to-idle command completion |
| CMD8 | `SD_CMD8_BEGIN` → `SD_CMD8_DONE` | 1.150103 | Interface-condition command completion |
| SD power-up negotiation | `SD_ACMD41_BEGIN` → `SD_ACMD41_DONE` | **203.689445** | **62 CMD55/ACMD41 attempts**, including intervening retry delays and camera service |
| CID/RCA/CSD and capacity | `SD_IDENTIFY_REGS_BEGIN` → `SD_IDENTIFY_REGS_DONE` | 5.270740 | CMD2/CMD3/CMD9 and validation |
| Select card | `SD_SELECT_BEGIN` → `SD_SELECT_DONE` | 2.401415 | CMD7 and fresh readiness |
| Run-clock selection | `SD_CLOCK_SWITCH_BEGIN` → `SD_CLOCK_SWITCH_DONE` | 1.070765 | Clock switch, settle and readiness |
| Four-bit negotiation | `SD_WIDTH_BEGIN` → `SD_WIDTH_DONE` | 2.173220 | SCR, CMD55/ACMD6 and host/card readiness |
| Storage SCR query | `STORAGE_SCR_BEGIN` → `STORAGE_SCR_DONE` | 0.172463 | Separate second SCR read for erased-byte handling |
| Find next slot | `SLOT_SCAN_BEGIN` → `SLOT_SCAN_DONE` | **11.325615** | **13 first-sector reads**, including the first free slot |
| First-sector wait | `FIRST_SECTOR_WAIT_BEGIN` → `FIRST_SECTOR_WAIT_DONE` | 0.010135 | Frame was already available; no significant producer wait |
| Complete slot write call | `SLOT_WRITE_BEGIN` → `SLOT_WRITE_DONE` | **161.803048** | Encloses the write substeps below; one CMD25 for 3,730 sectors |
| Initial write readiness | `SD_WRITE_READY_BEGIN` → `SD_WRITE_READY_DONE` | 0.048675 | Fresh CMD13/DAT0/host-idle proof |
| Preannounce full slot | `SD_PREANNOUNCE_BEGIN` → `SD_PREANNOUNCE_DONE` | 0.051283 | CMD55 + ACMD23(3730) |
| Configure transfer | `SD_WRITE_SETUP_BEGIN` → `SD_CMD25_BEGIN` | 0.000768 | Controller/IDMA setup |
| Start multiblock write | `SD_CMD25_BEGIN` → `SD_CMD25_DONE` | 0.026375 | Command response completion |
| Data phase | `SD_CMD25_DONE` → `SD_DATAEND` | **159.402875** | Data transfer plus hardware/card stalls until CPU observes DATAEND and inactive DPSM |
| Stop multiblock write | `SD_CMD12_BEGIN` → `SD_CMD12_DONE` | 0.025833 | Explicit stop command |
| Final write readiness | `SD_WRITE_FINAL_READY_BEGIN` → `SD_WRITE_FINAL_READY_DONE` | **2.164930** | Fresh readiness after CMD12; not an isolated internal-programming measurement |
| SD deinitialization | `SD_DEINIT_BEGIN` → `SD_DEINIT_DONE` | 0.043148 | Final sync and controller/pin release; card power remains applied |
| Awake terminal setup | `TERMINAL_BEGIN` → `TERMINAL_READY` | 0.014085 | Final diagnostic terminal preparation |
| Runtime through awake terminal | `RUNTIME_BEGIN` → `TERMINAL_READY` | **406.071098** | Includes nested/overlapping work; do not sum the rows above |

The logger initialization timestamp is **6.288895 ms after prefix DWT zero**;
its finalization timestamp is **412.3648375 ms after that zero**. The
initialization-to-finalization interval is **406.0759425 ms**. These figures
exclude the earlier power/reset/ROM/recovery interval and are not
power-on-to-Standby measurements. This trace has no new energy result.

## Derived per-sector transfer and wait breakdown

The same slot-12 write contains **3,730 sectors of 512 bytes**, or 1,909,760
bytes. At the configured four-bit, nominal 25 MHz SD clock, payload
serialization requires `512 × 8 / (4 × 25,000,000)` seconds per sector.
The table separates that calculation from the measured whole-transfer envelope:

| Quantity | Per 512-byte sector | All 3,730 sectors | Basis |
|---|---:|---:|---|
| Payload serialization | 40.960000 µs | 152.780800 ms | Calculated from bus width and clock; excludes protocol framing and pauses |
| Remaining data-phase envelope | 1.775355 µs average | 6.622075 ms | Measured envelope minus calculated payload time |
| Complete data-phase envelope | 42.735355 µs average | 159.402875 ms | `SD_CMD25_DONE` → `SD_DATAEND`; only the whole interval is measured |

Payload serialization accounts for approximately **95.846%** of this data-phase
envelope. The remainder combines framing, CRC, card acceptance/busy handling,
controller stalls and software observation overhead. **It is not a separately
measured card wait**, and no individual sector's transfer or busy timestamps
were retained. A collapsed repeated-block diagram can show these averages,
but must not imply that each block has an identical 1.775355 µs wait. Card
internal programming may also overlap later data reception.

After this repeated data phase, the separately measured **CMD12 interval is
0.0258325 ms**, followed by **2.164930 ms of final readiness checking**. The
driver's `ready()` checks CMD13, DAT0 HIGH and inactive host/IDMA state, with
1 ms delays between unsuccessful polls. That final interval includes polling
quantization and service work; it is neither a per-sector wait nor an isolated
measurement of internal programming latency. The full enclosing slot-write
call remains **161.8030475 ms**. See [`transfer_dma_write()` and `ready()`](../sd-storage/sd_card.c)
for the logged boundaries and readiness checks.

## Interpreting concurrency, repeats and missing events

The hardware receives the image while the CPU loads late code and initializes
the SD card. FRAME checks and asynchronous sensor STOP are serviced during that
SD initialization. Their intervals overlap the SD-init and ACMD41 envelopes;
they must not be added as if they were sequential phases. In this run, the
complete frame was available before the write began, so the selected branch
was IDMA. The progressive PIO branch is instrumented too, but
`SD_PIO_SELECTED` is absent in this particular log.

Each fixed slot keeps its **latest hit**. Separate first-event IDs cover first
LINE and first published prefix; coarse counters describe repeats. For
example, the latest generic read marks describe only the final header read,
while `SLOT_SCAN_BEGIN`/`SLOT_SCAN_DONE` enclose the whole thirteen-read scan.
SCR and sync slots likewise describe their latest call. A failed later call can
leave a previous DONE older than its new BEGIN; that pair is not a valid
duration. Never-hit events remain the unset sentinel, including
`SD_LAST_ERROR` in this successful driver record.

The logger does not observe each card-internal program operation. DATAEND
includes SDMMC/card pacing and busy handling; internal programming may overlap
subsequent data reception. Neither this interval nor final CMD13 readiness is
pure payload-wire time or pure flash-programming time. The repeated SD sector
transactions remain a hardware-managed loop rather than thousands of logging
calls.

Finally, all times assume the DWT stays running at nominal 400 MHz and the
interval is shorter than one 32-bit wrap, **10.73741824 seconds**. Subtraction
handles one numerical rollover; a multi-wrap interval cannot be reconstructed.
An event exactly at `0xFFFFFFFF` is indistinguishable from an unset slot.
Neither prefix nor new telemetry measures power arrival, reset release, ROM
boot or recovery selection before DWT zero. Sensor-command/IRQ timestamps are
host observations, not physical exposure edges. The awake profile deliberately
provides no peripheral-shutdown/Standby-entry interval, sleep duration or
energy measurement.
