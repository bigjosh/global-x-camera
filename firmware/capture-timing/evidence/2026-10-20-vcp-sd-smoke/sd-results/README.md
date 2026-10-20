# SD connection verified through 25 MHz

After the user's second wiring correction and the receive-completion fix below,
the card identified and passed native one-bit SDMMC2 reads at **100 kHz,
12.5 MHz and 25 MHz**. LBA0 and LBA1 matched byte for byte across all three
clocks. The host independently checked uploaded buffer CRC32s. The controller
reported no command/data errors during these reads. No card write or erase
command was issued.

| Run | Outcome |
| --- | --- |
| `sd-read-100k-01` | CMD8 timeout; no identification or sectors |
| `sd-read-100k-02` | Same timeout after first wiring correction and warm recovery |
| `sd-read-100k-03` | Same timeout after a JS110 target power cycle |
| `sd-read-100k-04` | Second wiring correction: identification succeeded, 128 words received, but v2 falsely timed out on completion |
| `sd-read-100k-05` | v3 passed both 512-byte reads at 100 kHz |
| `sd-read-25m-01` | v3 passed six reads: both sectors at all three clocks, matching the slow baseline |

The card reports product name `SDU1 ` and capacity **62,723,719,168 bytes**
(122,507,264 sectors). This is reported capacity, not an all-capacity test or
manufacturer authentication. The user did not specify which connections were
corrected. Card VCC itself was not probed; only NRST and PE6 probe locations
were confirmed. No additional probe move was needed to obtain these results.

## Receive-completion correction

The v2 diagnostic incorrectly required DBCKEND and RXFIFOE alongside DATAEND
for the final single-block transfer. In run 04 all 128 words had arrived,
DATAEND was set, the data state machine was idle and no data error was set;
the extra completion conditions caused a software timeout.

RM0486 Table 220 and ST's `HAL_SD_ReadBlocks` support DATAEND as the final read
condition. v3 checks errors first, recognizes DATAEND plus idle DPSM before
another FIFO read, and requires exactly 128 words. It does not require DBCKEND
or a FIFO flag after the data state machine becomes inactive. The same wiring
then passed both the slow and faster tests.

| Build | SHA-256 | Final park |
| --- | --- | --- |
| v2, retained for failed-run provenance | `8e1c3995a2ed3dcb704067161398ff91f0452ca991242b78450077cfe5dac3b8` | `0x341E05E0` |
| v3, current runner allowlist | `790b240b4246d61daf6361da67cb2bca6084d666897902e0bfd1dc9555c03db6` | `0x341E05E4` |

The original `helper-manifest.json` and `helper-sd-smoke.bin` are v2.
The `helper-v3-*` files are the passing build. These binaries are compiled
test programs, not card contents. Sources and guarded host runner are in
[`firmware/sd-smoke`](../../../../sd-smoke/README.md).

## End state and limits

The target was left powered in the exact v3 awake park, instruction `fee7`,
with interrupts masked, CPU caches disabled and XSPI idle. Before another RAM
helper, enter and verify the boot-prefix recovery park again. ST-LINK BREAK
was released and COM8 closed. JS110 ownership was released cleanly with the
starting automatic range 128 restored; final input supply measured about
4.882 V. This is a diagnostic idle measurement, not camera energy consumption.

This verifies a short connection test. It does not establish sustained
throughput, card write performance, power-loss behavior, retention, full
capacity or image-save integration. No card filesystem was modified.

Raw sector dumps and full reports remain locally in
`tmp/bringup/vcp-install-20261019/`. The selected JSON here excludes sector
contents and card serials; its CRC32s retain the cross-clock comparison.
`source-index.json` records source and selected-output hashes.
`prepare_success.py` can reproduce only the selected successful reports,
compiled v3 helper and final JS cleanup from those local files. The parent
`verify_archive.py` checks this index as well as the VCP/NOR archive.
