# Experimental LINE watermark

This optional path publishes completed prefixes of the existing linear packed
frame. It does not wrap or reuse frame memory. The normal default remains a
validated full-frame boundary. Hardware qualification is required before relying
on a LINE prefix for image data; offline tests establish software bounds only.

RM0486 Rev4 page 1898 says Pipe0 LINE is generated after each configured group of
dumped lines, measured at the pipe end close to the memory output, for stripe
processing. Pages 1916 and 1922 describe the final partial-group event and
`P0PPCR.LINEMULT`. This does **not** explicitly promise that every corresponding
AXI write response has returned. A CPU DMB/DSB orders CPU work and cannot flush a
separate camera DMA master.

The implementation therefore uses 64-line events and holds back one complete
group. At the second event (128 lines observed), the first 64 lines become
eligible: **89,600 bytes, exactly 175 sectors**. The first event publishes nothing.
The maximum pre-FRAME prefix is 20 groups, **1,792,000 bytes**. Event 22 can mean
only the final 20 lines, so it does not increase this prefix. FRAME freezes LINE
publication; full byte count, frame count, camera error and guard validation
releases the remainder. The existing source order handles FRAME before LINE
when both flags occur in one HAL interrupt. Lost/coalesced LINE interrupts reduce
the available prefix rather than inventing progress.

RM0486 page 1889 lists 5120 total FIFO bytes and up to 16 outstanding bursts of
128 bytes. An 89,600-byte holdback is substantially larger than those buffers;
that is a conservative engineering inference, not a documented cross-master
visibility guarantee. It must be checked with the actual SRAM/bus configuration
and simultaneous SDMMC IDMA traffic. `P0DCCNTR` is never used as a live producer
pointer.

The consumer selects the smaller of its configured chunk size, currently
published whole sectors minus those already submitted, and the remaining 3729
whole sectors. With no new complete sector it waits, servicing camera completion
outside SD calls. The final 352 bytes remain reserved for the padded-tail and
FULL-header operation. FULL requires complete-frame validation and sensor STOP;
a camera error leaves the slot PARTIAL and prevents further submission/commit.

`storage_call_depth` covers the SD driver and slot-layer calls. In every profile,
`raw_capture_poll()` defers the full post-frame checks while that depth is nonzero,
so a validation failure cannot strand an active SD DMA operation. The
already-started asynchronous sensor STOP polling remains permitted: its errors
are recorded and checked only after the current SD call returns. Camera IRQs
publish progress/errors without I2C, SD calls, blocking waits or error parks.

Before enabling LINE interrupts, firmware clears only the old Pipe0 LINE flag;
the HAL enable function does not do that itself. This ensures a stale flag cannot
count as the first group and consume the holdback. The first real group still
publishes zero bytes. CPU-visible availability is monotonic, published after the
optional snapshot, and rejected on a fault. An interrupt can still arrive after
a consumer checks availability; the current SD transfer then finishes before the
error is handled, and complete-frame validation prevents committing that slot.

Capture failure cleanup runs after the outer SD call returns. It disables only
camera IRQs, holds CSI/DCMIPP in their dedicated RCC resets, and drives camera
RESET (PO5) low. This bounded failure reset does not wait for a frame or sensor
I2C, and does not read a clock-gated camera peripheral. SD deinitialization keeps
its existing independent ready/idle checks; uncertain SD remains owned and
powered, and the image stays PARTIAL. Camera reset is neither successful STOP
nor proof of SD idle or outstanding AXI writes draining. Early FLASH failures
before the verified late load bypass storage cleanup because no SD operation has
begun and that code is not loaded yet.

A separate 16-word `CAB1` record at `0x343FD300` records the failure cleanup:
magic/schema/state, failure reason/site/detail, SD call depth, start/end cycles,
RCC reset before/after, PO5 MODER/ODR/IDR, reserved, and error bits. State2 means
both receiver reset bits and the LOW sensor-reset pin were observed; state15
means a cleanup condition was refused. Error bits identify unexpected nested SD
(1), ISR context (2), unavailable GPIO clock/reset (4), pin readback mismatch (8),
or receiver reset readback mismatch (16). This record never grants a successful
maintenance gate or Standby entry. Failure reset remains to be fault-injected on
hardware; software tests cannot qualify its physical effect.

## Diagnostic build

```powershell
python firmware/capture-raw/build.py --out tmp/line-pattern-test `
  --pattern diagonal --transport idma --chunk-sectors 1024 --async-stop `
  --line-stream --preinit --snapshot --poison
```

The final four options are opt-in. `--preinit` initializes SD before sensor START
so real overlap can be tested even though this card's cold initialization takes
longer than frame capture. `--poison` fills the frame with `0xa5` before START;
it must never run in the receiver's critical START-to-arm interval. Snapshot,
poison and preinitialization are RAM-diagnostic options and are rejected for a
FLASH build. These timings are not cold-start results.

With `--snapshot`, the LINE ISR copies the **last 512 bytes of each newly
publishable prefix immediately**, before publishing its availability. It stores
up to 20 snapshots at `0x343D0000` (10,240 bytes), separate from the frame, high
stack, proof records and chunk log. This is stronger than SD readback alone:
a slow SD consumer could otherwise read the final bytes only after the camera
had caught up and hide an early-publication problem. The producer's 416-byte
telemetry record contains event cycles/prefix lengths and each snapshot's source
offset/length. The build manifest identifies that record's BSS address. Snapshot
copies and logging add ISR work and are not production energy measurements.

Hardware acceptance requires all of the following:

- At least one payload submission starts before FRAME; chunk records contain
  the availability captured **before** its SD call, not after it returns.
- Every submitted range fits that pre-call watermark, with no gaps, overlap or
  access to the final partial sector.
- Every ISR tail snapshot exactly equals the corresponding bytes in the final
  deterministic-pattern frame, with the initially poisoned RAM eliminated.
- The complete SD image payload matches the retained frame byte-for-byte,
  and independent decoding matches the expected sensor pattern.
- Camera byte count, first-frame count, all camera/SD errors, canaries,
  allocation/commit state, card idle/deinit and recovery checks pass.

The pure C producer tests cover delayed/fast consumers, event coalescence,
FRAME-before-LINE ordering, final partial groups/tail, excess events, runt frames,
second frames and camera/guard errors. Slot-layer tests independently establish
that incomplete or failed writes remain PARTIAL. The runtime keeps the two
conditions joined at its mandatory complete-frame/STOP gate before `finish()`.

Source: [ST RM0486](https://www.st.com/resource/en/reference_manual/rm0486-stm32n647657xx-armbased-32bit-mcus-stmicroelectronics.pdf),
especially pages 1889, 1898, 1916 and 1922; the pinned local copy is
`datasheets/processor/STM32N6_RM0486_reference_manual.pdf`.
