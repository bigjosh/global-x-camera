# Native SD storage driver

`sd_card.c` provides synchronous, single-owner block access through native
one-bit SDMMC2 at 3.3 V. PIO and hardware IDMA share the same card-ready and
ownership checks. The normal `sd_write_blocks_dma()` API retains its existing
chunked behavior: at most 1024 sectors per transaction, reduced to 16 at 100 kHz.
It does not send ACMD23.

## Opt-in whole transaction with preannouncement

`sd_write_blocks_dma_preerase(card, lba, buffer, count)` accepts **2-4096
sectors at 12.5 or 25 MHz** and never splits the request. The complete immutable
source, including final-sector padding, must already exist. The caller must own
the entire destination range; announced but unwritten sectors can become
undefined if a write fails or is interrupted.

The successful sequence is:

1. Establish fresh READY/TRANSFER with CMD13, DAT0 high and an idle host.
2. Send `CMD55(RCA)` followed immediately by `ACMD23(count)` with the exact
   upcoming sector count. Validate both application responses.
3. Issue one `CMD25(lba)` and transfer the entire buffer through IDMA.
4. Require DATAEND, no transfer errors and an idle data state machine; issue
   **CMD12** even though ACMD23 supplied a count.
5. Require fresh CMD13 READY/TRANSFER, DAT0 high and idle host state before
   reporting success.

This is ACMD23's preparation hint, not CMD23's fixed-count transfer mode. A
rejected or unsupported announcement returns an error; the driver does not
silently retry without the hint. It does not enable a card write cache, issue a
cache flush, or establish arbitrary power-loss safety for the card's internal
translation layer.

The source must satisfy the existing IDMA rules: secure AXI SRAM, word alignment,
D-cache disabled with no dirty aliases, secure/privileged CID1 SDMMC2 master and
a secure SDMMC2 configuration port. The caller retains responsibility for SRAM
bank clocks and access policy. Failed cleanup can retain controller/buffer
ownership; an error is never permission to reset or remove power. `sd_sync()`
and `sd_deinit()` require independently observed idle state.

The [RAW slot layer](../raw-slots/README.md) can use this API for exactly 3730
payload sectors, with PARTIAL and FULL headers written separately. Existing
chunked PIO/IDMA callers remain available. See `sd_card.h` for detailed contracts
and the integrated capture evidence for hardware measurements.

## Progressive publication within one multiblock write

`sd_write_blocks_stream_preerase(card, lba, buffer, count, stream)` retains
one exact-count ACMD23 announcement and one CMD25 for the entire allocation.
The callback publishes a monotonically increasing, immutable byte prefix;
the driver rounds that prefix down to complete 512-byte sectors. It waits for
at least one sector before announcing the write. The end marker and final
padding must not be published until the producer has validated the image.

When the full buffer is already published at launch, the existing IDMA path
handles the write. Otherwise the CPU feeds the FIFO using PIO. With the
cycle-aligned, one-bit configuration and `HWFC_EN` set,
[RM0486 section 30.7.1](https://www.st.com/resource/en/reference_manual/dm00769900.pdf)
specifies that an empty transmit FIFO stops SDMMC_CK and freezes the card-side
state machines while the AHB FIFO interface stays available. More published
data can then resume the same transaction. No unread producer memory is
prefetched and no second CMD25 is issued. This costs CPU work compared with
IDMA; the mode is recorded explicitly for timing and energy comparisons.

An unavailable IDMA linked-list node cannot implement this waiting mechanism:
its clear ABR bit raises a transfer error and disables hardware flow control
(RM0486, linked-list buffer ownership and error management). The driver does
not use this rejected mechanism, or toggle IDMA ownership during an active
data state machine. The immutable whole-image IDMA API remains available.

The producer has a three-second deadline from API entry; the active data phase
has the existing five-second software deadline. A callback error, regressing
prefix, timeout, or SD error aborts the transfer through the established bounded
CMD12 path. Success still requires the full data count, no SD errors, CMD12,
and fresh READY/TRANSFER. `sd_stream_t` records the mode, initial publication,
published/queued bytes, callback count, producer faults and observed waiting.
The `sd_card_t` ABI is unchanged. DWT waiting counters are nominal400MHz cycles,
not independent instrument timings. On failure, non-idle ownership is retained.

Healthy publication and `sd_progress()` service should return promptly (the
service target is 50 ms). A bounded camera fault check may spend seconds in a
stop or I2C timeout, including from the progress hook during card initialization.
The owner must latch that fault and return, never park while SD owns a command.
Both callbacks must avoid SD reentry, sleep, and SD clock/cache changes. The
producer deadline is rechecked immediately after every callback, before accepting
its prefix. A late callback cannot trigger IDMA or send additional FIFO words;
an active transaction follows the normal CMD12/idle-proof cleanup. Simulation
covers 3.1-second callbacks both before CMD25 and after a partial prefix was sent.

## SCR and explicit whole-card erase

`sd_read_scr(card, &scr)` is a read-only CMD55/ACMD51 operation. It returns
the eight SCR bytes in wire order and decodes `DATA_STAT_AFTER_ERASE` (bit55)
to an erased byte value of `0x00` or `0xFF`. It validates SCR structure and both
application acknowledgments. It does not change the normal card block length,
run automatically during initialization, or prove that any sector was erased.

`sd_erase_all(card, timeout_ms, &proof)` explicitly destroys the entire card
using CMD32(start0), CMD33(last address), and ordinary CMD38(0). No initialization,
read, capture, or write API invokes it automatically. It accepts a timeout from
one second to ten minutes and polls card status using an extended DWT count so
ordinary CYCCNT wrap does not prematurely end a long erase. Before CMD38, with
the card and controller idle, it selects the qualified 100 kHz divider and sets
the hardware busy timer to the software timeout plus one second. Even the
600-second maximum then fits the 32-bit timer (60,100,000 clock periods). The
previous clock and timer are restored only after fresh card and controller idle
proof; a failed or uncertain operation retains 100 kHz and ownership. Its separate proof
reports whether CMD38 might have started, whether fresh card-ready was observed,
the exact range, elapsed time and final status. A timeout or uncertain command
response leaves `media_idle=0`; the driver does not send CMD12, reset the card,
or treat that as permission to remove power. Erase is neither secure sanitization
nor arbitrary power-loss protection. The caller must validate erased contents
and the intended slot format separately.

The first hardware erase attempt exposed a missing R1b timer configuration:
CMD38 inherited the preceding SCR read's 50,000,000-cycle timer, just two seconds
at 25 MHz. The subsequent 600-second software wait ended with card status
`0x900` and physical DAT0 high, but host `DPSMACT`, `BUSYD0` and `DTIMEOUT` still
set. RM0486 Table220 specifies that R1b timeout leaves the host busy until CPSM
Abort. More status polling cannot clear that condition. This finding does not
mean the card took 600 seconds to erase. The simulation now reproduces that
latched state and checks the longer timer, multiple DWT wraps, clock restoration,
and retention of the slow clock after uncertain failures. Historical v17c build
artifacts preserve the original driver; this correction affects future builds.

The new protocol tests model delayed publication/FIFO starvation, exact3730-sector
content, rejection of unpublished partial sectors, producer failures, SCR values,
full erase ranges, deadline expiry and timer wrap. They establish software
behavior; electrical flow control, long-exposure capture and real-card erase
still require independent hardware qualification.

Host tests exercise the real driver against modeled registers, including exact
command order/count, range/security/cache checks, rejected announcements and
mandatory stop/ready error handling. They do not access hardware:

```powershell
python -m unittest discover -s firmware/sd-storage -p "test_*.py"
```
