# ROM-configured NOR maintenance: read-only first version

This version extends the successful 16-byte indirect NOR reader to repeatable
reads of up to 64 KiB. **Only READ is implemented**; no command can write-enable,
erase or program NOR. Code stays unchanged between reads; change the command in
RAM and explicitly re-enter the same entry point. It does not poll for commands
or automatically repeat them. The reserved input buffer is unused.

Build with `python firmware/boot-timing/experiments/rom-nor-maintenance/build.py`.
No build command accesses hardware. The default output directory is
`tmp/bringup/rom-nor-maintenance-readonly-20261017`, containing the binary, ELF,
disassembly, symbols, linker map, stack-usage report, manifest and an example
20-byte `command-read-sector0.bin`. Build provenance checks the pinned vendor
commit and rejects modified CMSIS sources. The initial binary is 728 bytes,
SHA-256 `d6b63e6e993a9cb872cfe482c0fd4f8954f8edc398a7dfb1db25982b9e255b5d`.

| Region | Address / range |
| --- | --- |
| Code; Thumb entry | `0x341B0000`; `0x341B0001` |
| Command: five 32-bit words | `0x341B4000..0x341B4013` |
| Status: 26 words | `0x341B4100..0x341B4167` |
| Fresh stack top | `0x341B8000` (MSPLIM explicitly cleared) |
| Input reserved, not accessed | `0x341C0000..0x341CFFFF` |
| Readback, up to 64 KiB | `0x341D0000..0x341DFFFF` |
| Initial binary's awake completion loop | `0x341B0252/0x341B0254` |

All these ranges lie within the documented 1 MiB secure AXISRAM2 alias
`0x34100000..0x341FFFFF` (`stm32n657xx.h`, SRAM2_AXI_BASE_S). They do not overlap
the GPIO boot image at `0x34180400`, cache-prep at `0x34190000`, or the earlier
16-byte reader at `0x341A0000`. The linker limits code below the command block;
the compiled function uses eight stack bytes. Physical SRAM range membership
does not alone prove access permissions: this experiment uses the already
working secure privileged AP1/CPU context and never changes memory security.

Command words are magic `0x4E4F5244`, sequence, opcode `1`, byte count, and NOR
offset. Byte count must be 1..65536; the entire range must fit within the 24-bit
address window `0..0xFFFFFF`. The example command reads 65536 bytes at offset 0,
sequence 1. No destination pointer is accepted from the command. The sequence
is echoed for freshness; it does not suppress an explicitly repeated command.

For the reviewed bench sequence:

1. Halt through the working HOTPLUG AP1 session. Require secure privileged
   thread mode and D-cache off. Download and verify `read.bin` at `0x341B0000`
   without an external loader or boot header. This first load uses fresh code
   RAM. Future code changes at this address require instruction-cache coherency
   or a fresh boot; repeated reads with this unchanged binary do not.
2. Write the five command words at `0x341B4000` while halted (or download the
   example command file there). Set PC=`0x341B0001`, XPSR=`0x01000000`, then
   **`-run`**. Entry disables interrupts, clears MSPLIM, sets the separate MSP,
   and executes exactly one command. It never returns to the interrupted image.
3. Reconnect/halt and read the status. Require DONE=`0x444F4E45`, result 0,
   requested count=read count, matching sequence/opcode/offset, IPSR=0, and final
   SR completion with BUSY/FIFO clear. Upload the requested bytes from
   `0x341D0000` and compare all 65536 bytes against the saved current NOR sector
   image before considering any write-capable successor.
4. For another read, leave code unchanged, update the command/sequence while
   halted, and repeat step 2. A command change alone does not launch a read.

The full-sector result must be established on hardware; compile success and
the prior 16-byte result do not establish it. Initial header comparison expects
`53 54 4D 32` followed by twelve zero bytes, but this prefix alone cannot verify
the sector contents or firmware identity.

Preconditions match the proven small reader: XSPI1/XSPIM clocks enabled, no
reset, XSPIM_CR=2, CR=`0x10000001`, DCR1=`0x001F0000`, DCR2=1,
CCR=`0x01002101`, TCR=8, IR=`0x0B`, and no initial BUSY/FIFO data. This reuses
the ROM's XSPI1→Port 2 single-line indirect-read setup and its clocks/pins.

The only peripheral writes are FCR=3, DLR=length-1 at **offset `0x40`**, and
AR=offset to start the addressed read. DR is read as bytes only when FIFO data
is present. An eight-million-iteration total budget bounds both data and
completion polling. There is no HAL/SysTick/DWT dependency, memory-aperture
load, clock/reset/cache/security/OTP change, NOR mode command, or NOR write
command. No BKPT is used. The loop budget is not a calibrated time limit and
does not recover a CPU bus fault or an indefinitely stalled register access.

After a transaction, DLR/AR/final flags remain available for diagnosis. A failed
or timed-out read stops awake without retry, abort or restoration writes. Only
the reported byte count is valid; preflight refusal leaves the old data buffer
unchanged. Inspect the final controller state before another command.

Status words at `0x341B4100`:

| Word | Meaning |
| --- | --- |
| 0–5 | Magic, result, requested bytes, read count, total polls, last SR |
| 6–10 | CONTROL, IPSR, CPU CCR, original MSP, original MSPLIM |
| 11–13 | RCC_AHB5ENR, RCC_AHB5RSTR, XSPIM_CR |
| 14–17 | Initial CR, DCR1, DCR2, SR |
| 18–22 | Initial CCR, TCR, IR, DLR, AR |
| 23–25 | Command sequence, opcode, NOR offset |

Results: 0 success; 1 D-cache enabled; 2 incorrect CPU context; 3 missing clock;
4 controller reset; 5 mux mismatch; 6 controller configuration mismatch;
7 BUSY/FIFO not idle; 8 transfer error; 9 premature completion; 10 polling
timeout; 11 extra FIFO data; 12 invalid command or range. RUNNING magic is
`0x52554E4E`; only DONE indicates a finalized result. Directly verify D-cache is
off before use because a D-cache refusal may hide the RAM record from debug.

Primary references: UM3234 Rev 5 section 3.4.5/Table 14; RM0486 Rev 4 section
28.4.10; pinned `stm32n657xx.h` at vendor commit
`e9441cdbb5072a6d3bcef1a5ca4e4d80f850283a`. Future NOR programming must separately
validate device identity, write protection/status, command timing, bounded
completion, failure flags, readback and restoration of ROM-read configuration.
