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

Host tests exercise the real driver against modeled registers, including exact
command order/count, range/security/cache checks, rejected announcements and
mandatory stop/ready error handling. They do not access hardware:

```powershell
python -m unittest discover -s firmware/sd-storage -p "test_*.py"
```
