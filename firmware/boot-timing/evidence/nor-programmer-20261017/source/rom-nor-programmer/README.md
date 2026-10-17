# ROM-configured RAM NOR maintenance helper

This bench helper identifies the MX25UM51245G and, with an explicit WRITE
command, replaces only changed 4 KiB sectors in the first 64 KiB. It reuses the
observed normal-boot XSPI1/XSPIM-P2 setup. It does not initialize clocks, pins,
caches, resets, option bytes, security, or the NOR's operating mode. This avoids
the installed external loader's broad initialization, which hung in this boot
context. The cause of that loader failure is still unproven.

Build offline with `python firmware/boot-timing/experiments/rom-nor-programmer/build.py`.
The default output is `tmp/bringup/rom-nor-programmer-20261017/`, containing the
binary, ELF, disassembly, stack-usage report, manifest and INFO command. The
builder checks the pinned CMSIS revision, unresolved symbols, code bounds,
entry address, absence of BKPT, and CRC equivalence to Python's zlib. No build
step accesses hardware. Source and binary hashes are in the manifest.

The reviewed build is 2936 bytes, SHA-256
`2dd98e8facd32426b622cb4dc023f4efac5315a7f5d336379066bda43db06909`,
with ready loop at `0x341E0846`. The root controller's initial INFO test
(`tmp/bringup/nor-info-01`) passed: ID `C2803A`, status/security zero, flags
`0x27`, DWT advancing, three SPI transactions and zero WREN commands. This
executed binary is frozen for reuse on that boot; an edit/rebuild must not
silently replace it at a previously cached address.

## RAM layout and execution

| Purpose | Address / range |
| --- | --- |
| Immutable reader from the preceding experiment | `0x341B0000` (preserve) |
| Eight-word command | `0x341B4000` |
| 56-word status | `0x341B4100` |
| Stack top | `0x341B8000`, MSPLIM cleared to zero |
| Desired 64 KiB input | `0x341C0000..0x341CFFFF` |
| 64 KiB readback | `0x341D0000..0x341DFFFF` |
| New helper | `0x341E0000`, Thumb entry `0x341E0001` |

All regions are within the 1 MiB secure AXISRAM2 window. The new helper uses a
fresh instruction address because the observed CPU has I-cache enabled and
D-cache disabled. Do not overwrite its code after execution without a deliberate
cache-coherency procedure or a fresh cold boot. Reuse the same code for later
commands by rewriting the command/input and setting PC to its entry.

The root bench controller owns hardware execution. Load only into a verified
halted, privileged secure Thread-mode context (`CONTROL=0`, `IPSR=0`). Set PC to
`0x341E0001`, xPSR to `0x01000000`, and use the programmer's **`-run`**, not an
addressless `-g` (which previously ran its unrelated default address). Entry
masks interrupts, clears MSPLIM and sets the reserved stack. Completion stays
awake in a plain branch loop; no BKPT or debugger reset is used.

Poll status via AP1 without halting while a write is underway. Match both DONE
and the requested sequence before halting. Keep input and command RAM unchanged
until completion. A host timeout is not evidence that flash programming stopped;
inspect status without resetting, removing power or killing an unknown writer.
Allow at least 30 seconds at the host level. The helper itself bounds all polling.

## Command and acceptance

The eight little-endian 32-bit words are:

1. Magic `0x4E4F5244`.
2. Host sequence number (choose a new value each operation).
3. Opcode: `2` INFO, `3` WRITE.
4. Length: `0` INFO, exactly `65536` WRITE.
5. Flash offset: exactly zero.
6. Permit: zero INFO, exactly `0x57524954` WRITE.
7. Expected current first-64-KiB CRC32 (WRITE only).
8. Expected desired-input CRC32 (WRITE only).

CRCs use the reflected IEEE algorithm, polynomial `0xEDB88320`, initial/final
XOR `0xFFFFFFFF`, matching `zlib.crc32`. INFO never sends WREN, WRDI, program,
erase or configuration commands. It first checks status idle/WEL clear, then
security and JEDEC ID. A protected/busy/failing part is refused rather than
unlocked. Expected ID is `C2 80 3A`; status BP mask `0x3C` and security mask
`0xEC` (suspend, program/erase failure, WPSEL) must be clear. Security bit zero
is factory OTP information and is not treated as proof of current OTP mode.

WRITE checks identity/protection and the desired-input CRC, reads the current
64 KiB and verifies its expected CRC **before any WREN**. It builds a 16-bit
changed-sector mask. Each changed sector is erased once, checked entirely FF,
then its non-FF 256-byte pages are programmed once and read back individually.
There are no retries. Unchanged sectors receive no erase or program commands.
Finally all 64 KiB are reread and checked by CRC and byte comparison. Only
after any own write activity and confirmed idle does cleanup send WRDI and
verify WEL clear. Keep an exact backup and independently reread the programmed
region and following sector using the immutable reader before cold booting.

## Timing and failure handling

Preflight requires the exact observed ROM controller, mux and clock values
recorded in `programmer.c`. The clock snapshot corresponds to a 400 MHz core.
DWT CYCCNT is enabled reversibly and must advance in a finite probe before any
NOR transaction. Each transaction finishes with TCF, BUSY clear and an empty
FIFO, followed by at least 400 core cycles (1 microsecond) before another
command. The controller's original clock and CS timing registers are retained.

Small controller transfers and page-program WIP polling get 10 ms; reads over
256 bytes get 100 ms (64 KiB takes about 16 ms at the observed 32 MHz SPI clock).
4 KiB erase WIP polling gets 1 second. All use unsigned DWT elapsed arithmetic
well below its approximately 10.7-second wrap, plus finite polling backstops.
The flash need not be observed with WIP set: quick completion is valid if WEL
clears, failure bits remain clear, and readback matches.

A transfer failure makes controller/flash state uncertain, and no more SPI
commands are sent. A WIP timeout permits one additional bounded, status-only
wait; WRDI is sent only if idle is then confirmed. If still busy, the helper
reports the busy status and does not restore transaction registers or reset
anything. Partial programming may leave the boot image unusable; DONE means
the helper ended, not that programming succeeded.

On an idle, known completion, cleanup restores original CR/CCR/TCR/IR/DLR,
without writing AR (which would trigger a read). DCR1/DCR2, mux and clocks are
never changed. FCR clears transaction flags; original AR and SR are deliberately
not restored. DWT CTRL and DEMCR are restored. IRQ masking and the reserved
stack remain in place for bench control.

## Status

The complete word order is generated in `manifest.json` from the C enum.
Words 0..3 are magic/result/sequence/command. Magic is RUNNING `0x52554E4E`
or DONE `0x444F4E45`. Result zero means success. First failure stage, address
and opcode are retained separately from the latest transaction. Cleanup has
its own result, so a prior failure cannot hide a cleanup failure.

Flag bits: `1` controller idle, `2` flash confirmed idle, `4` ROM transaction
configuration restored, `8` WREN attempted, `16` uncertain state, `32` DWT
restored. Normal INFO expects `0x27`, successful actual writing `0x2F`.
Successful unchanged WRITE has no WREN and normally `0x27`.

Result codes: 1 bad command, 2 context, 3 D-cache on, 4 clock mismatch,
5 mux mismatch, 6 controller mismatch, 7 controller not idle, 8 no DWT timer,
9 transfer error, 10 transfer timeout, 11 short transfer, 12 extra data,
13 ID mismatch, 14 protected/suspended/failure status, 15 WIP/WEL not idle,
16 unexpected WEL, 17 input CRC mismatch, 18 current CRC mismatch,
19 erase verification, 20 page verification, 21 final verification,
22 timer stopped. No automatic recovery/reset is implied by any result.

## Provenance

CMSIS and HAL sequence reference: ST's
[X-CUBE-N6-CAMERA-CAPTURE](https://github.com/STMicroelectronics/x-cube-n6-camera-capture),
commit `e9441cdbb5072a6d3bcef1a5ca4e4d80f850283a`,
`STM32Cube_FW_N6/Drivers/STM32N6xx_HAL_Driver/Src/stm32n6xx_hal_xspi.c`,
`XSPI_ConfigCmd()` and `HAL_XSPI_Receive()`. Register addresses/offsets are
compile-time checked against its `stm32n657xx.h`.

RM0486 Rev 4 section 28.4.10 describes indirect transfers and AR/IR triggering;
UM3234 Rev 5 section 3.4.5, Table 14 describes ROM's XSPI1/XSPIM-P2 SPI read
configuration. Macronix's
[MX25UM51245G PM2183 v1.6](https://www.macronix.com/Lists/Datasheet/Attachments/9241/MX25UM51245G,%201.8V,%20512Mb,%20v1.6.pdf)
(13 March 2026), printed pages 16–18, 29, 32, 55–58, 96–97 and 102, specifies
the SPI commands, status/security meanings, 40 ns minimum CS deselect time,
and maximum page-program/4-KiB-erase times (0.75 ms / 400 ms). The chosen limits
include engineering margin; they are not substituted datasheet specifications.
