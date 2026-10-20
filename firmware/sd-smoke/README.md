# Read-only native SDMMC2 smoke helper

This RAM diagnostic checks the seven-pin SD breakout without modifying any card
sector, filesystem, NOR image, boot configuration or recovery-prefix byte.
It is separate from image acquisition firmware. On October 20, after wiring
corrections and the receive-completion fix described below, v3 identified the
card and passed the 100 kHz read test. A subsequent run read LBA0 and LBA1 at
100 kHz, 12.5 MHz and 25 MHz: all six 512-byte reads passed controller CRC/error
checks, uploaded-buffer CRC32 checks, and byte-for-byte comparison across speeds.
The card reports 122,507,264 sectors (62,723,719,168 bytes). Both runs reached the
exact verified terminal park with SDMMC2 disabled. No card write/erase command was
sent. See the [hardware evidence](../capture-timing/evidence/2026-10-20-vcp-sd-smoke/README.md).

This establishes short native one-bit reads on the current wiring. It does not
establish sustained throughput, write speed, capture/save behavior, analog signal
margin, energy consumption or long-term reliability.

Wiring is the [canonical one-bit plan](../../docs/prototype/sd-breakout-benchmark.md):
PC2/PC3/PC4 AF11 for clock/CMD/DAT0, PE4 input/pull-up for unused DAT3, at 3.3 V.
The absent external bias on unused DAT1/DAT2 remains the documented carrier
limitation. This helper never selects four-bit, high-speed or UHS mode.

## Preconditions and memory ownership

Only the bench owner may run it, after checking the actual rails, current wiring,
and an exact verified awake early recovery park with both CPU caches disabled.
The target must not be performing NOR or card writes. Do not use this helper
as a means of escaping an unknown active capture or storage operation.

- Code: `0x341E0000`, entry `0x341E0001`, under 64 KiB.
- Stack: top `0x341B8000`, limit cleared by entry.
- Request: `0x341B4000`, four words.
- Result: `0x341B4100`, schema and length in the manifest.
- Command records: `0x341B4400`, up to 64 records of 12 words.
- Six 512-byte read buffers: `0x341C0000`.

This is the **same low-SRAM working area used by the NOR helper**. They cannot
be active together. Re-read/reload the exact helper image and verify its bytes
before executing. A reset/re-entry into the verified recovery park is required
before later NOR work; this diagnostic's final park is not the boot-prefix park.
It neither loads expanded SRAM nor modifies the prefix at `0x34180400`.

## What it does

1. Requires the measured nominal ROM clock profile: 400 MHz CPU, PLL1 1200 MHz,
   IC2 300 MHz, HCLK 150 MHz. It refuses to guess unknown clocks.
2. Refuses an enabled SDMMC2 controller, active/output PC2–4 or PE4, or the
   1.8 V selection for VDDIO5. Enables only the relevant GPIO/PWR bus clocks.
3. Sets CMD, DAT0 and unused DAT3 to input/pull-up and enables VDDIO5 supply-valid
   at its already selected 3.3 V range. After 1 ms it requires all three inputs
   HIGH before attaching SDMMC2. This verifies digital levels, not analog margin.
4. Selects HCLK for the SDMMC2 kernel, initializes one-bit rising-edge sampling,
   starts a 100 kHz clock, and allows 10 ms before CMD0.
5. Uses CMD8, CMD55/ACMD41, CMD2, CMD3 and CMD9 to identify a modern SD card.
   Records OCR, raw CID/CSD, RCA and capacity. Legacy cards without CMD8 are
   intentionally outside this initial diagnostic.
6. Selects the card, requires ready/TRANSFER state, and reads LBA0 and LBA1 using
   native CMD17 with the controller's command and data CRC checks. It never
   issues a write, erase, bus-width or voltage-switch command.
7. Optionally repeats these same two reads at 12.5 MHz and 25 MHz, comparing
   every byte with the 100 kHz baseline and storing CRC32 for all read buffers.
   These are short connection checks, not throughput, sustained reliability,
   retention, power-loss or write-performance measurements.
8. Stops/resets only SDMMC2, restores its previous kernel-mux bits, disables its
   bus clock and leaves CLK input/pull-down, CMD/DAT0/DAT3 input/pull-up.
   Relevant GPIO/PWR clocks and VDDIO5 supply-valid remain enabled. Restores the
   prior DWT control settings and parks awake in a branch-to-self instruction.

All waits have DWT timeouts plus bounded iteration limits. Interrupts remain
disabled. The code has no HAL/SysTick dependency. No DMA is used in this first
smoke test; this does not constrain the eventual IDMA write implementation.

## Offline build and interpretation

```powershell
python firmware/sd-smoke/build.py --out tmp/bringup/sd-smoke-readonly-v3-20261020 --max-hz 100000
```

The reviewed v3 binary is 3120 bytes, SHA-256
`790b240b4246d61daf6361da67cb2bca6084d666897902e0bfd1dc9555c03db6`;
its park is `0x341E05E4`, containing `fee7`. Choose a new output directory if
rebuilding after this recorded build already exists.

The default stops after the two slow reads. `--max-hz 12500000` or `25000000`
only changes the four-word request; the executable stays identical. The image
uses pinned STM32Cube CMSIS register definitions and the installed ARM compiler.
Use a new output directory for each build; the builder refuses to overwrite an
existing output so a recorded run keeps its exact executable and manifest.
The generated manifest gives exact addresses, byte hash, park address and result
field order. `request.bin` has magic `0x53445244`, max clock, zero, zero.

`run.py` validates the reviewed binary allowlist offline by default. The current
bench owner may add `--execute` only after independently checking ownership and
the actual rails. It invokes the exact recovery guard immediately before RAM
loading, verifies the complete helper readback, clears and verifies the status,
verifies the new request, and executes the Thumb entry. It uses bounded polling
before checking the exact final park and idle XSPI controller. It never resets,
switches power, programs NOR or writes a card sector, and never retries a failed
run automatically. All terminal states, including failures, retain result
evidence. A fresh early recovery entry is needed before another run.

```powershell
python firmware/sd-smoke/run.py --build tmp/bringup/sd-smoke-readonly-v3-20261020 `
  --recovery-build <exact-reviewed-capture-build> --out tmp/bringup/sd-read-01 `
  --max-hz 100000
```

Without `--execute`, that command is an offline plan check only. Runtime output
is restricted to the repo's ignored `tmp` tree because it includes user sectors.

```powershell
python firmware/sd-smoke/inspect.py --build tmp/bringup/sd-smoke-readonly-v3-20261020 `
  --status <saved-status.bin> --records <saved-records.bin> --data <saved-data.bin>
```

The inspector checks buffer CRC32s and reports identity/capacity without dumping
the user's stored sector contents. Preserve raw dumps locally with the evidence;
sector bytes can contain user data and should not be pushed to the public repo.
It separates `device_reported_pass` from `host_data_verified`; a full
`read_smoke_pass` requires both, including uploaded data, matching target CRC32s
and byte-for-byte equality of all speed repeats. Run `test_inspect.py` for the
negative-evidence checks.

## Receive-completion correction

The earlier v2 helper received all 128 words of LBA0, with `STA=0x100`
(`DATAEND`) and no data error, but incorrectly timed out while also waiting for
`DBCKEND` and a post-transfer `RXFIFOE`. This was a helper bug, not a failed card
read. RM0486 Table 220 describes receive `DATAEND` as the complete transfer with
good CRC, zero remaining data and an empty FIFO, as the DPSM moves from Wait_R
to Idle. Receive `DBCKEND` instead describes a nonfinal `RWSTART` suspension
with more transfer data remaining. ST's `HAL_SD_ReadBlocks` also waits for
`DATAEND` or a data error, without requiring `DBCKEND`.

V3 recognizes `DATAEND` with an idle DPSM before attempting another FIFO read,
then requires exactly 128 received words and no data errors. It does not require
the active-receive FIFO flags to remain asserted after completion. The protocol,
read-only command whitelist and cleanup behavior are unchanged.

Local successful run records are
`tmp/bringup/vcp-install-20261019/sd-read-100k-05/report.json` and
`tmp/bringup/vcp-install-20261019/sd-read-25m-01/report.json`; both report
`device_reported_pass`, `host_data_verified` and `read_smoke_pass` true.
Raw sector data stays in ignored local storage; the public evidence records
verification results without publishing those contents.

## Implementation references

- Pinned `STM32N6xx_HAL_Driver/Src/stm32n6xx_hal_sd.c`: native single-block read
  ordering (`DCTRL` with DPSM initially disabled, `CMDTRANS`, CMD17), command/data
  status handling.
- Pinned `stm32n6xx_ll_sdmmc.c`: response types, error flags, RCA/CID/CSD commands.
- [RM0486](https://www.st.com/resource/en/reference_manual/rm0486-stm32n647657xx-armbased-32bit-mcus-stmicroelectronics.pdf):
  SDMMC, RCC and GPIO/PWR configuration.
- [SD Association simplified specifications](https://www.sdcard.org/downloads/pls/):
  native identification, SDHC block addressing and CSD capacity.
