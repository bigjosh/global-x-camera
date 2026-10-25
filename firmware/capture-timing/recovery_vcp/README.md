# ST-LINK VCP recovery prefix

**October 24 troubleshooting follow-up:** host UART write success did not prove
that C0 pulses reached PE6. During the SanDisk baseline, a measured bytes-only
115200-baud reconfiguration followed by 1 Mbaud restored the waveform and exact
v18 recovery without a jumper change. Use physical pulse evidence and a bounded
retry from a safe/explicitly authorized state; the cause is unproven. See the
[owning decision and evidence](../NOTES.md#2026-10-24--verify-the-physical-uart-stimulus-before-blaming-the-recovery-detector).
The v45b installation statements below describe the historical first qualification;
[AGENTS.md](../../../AGENTS.md) identifies the current firmware and bench state.

The installed v45b image adds a PE6 pulse detector to the previous v44 image while
retaining PE1 recovery, the existing debug-unlock sequence, the early awake
park, cache handling, and the **byte-identical v44 camera receiver**. This
directory contains offline build and test tools only. No firmware programming,
instrument access, power switching, SD commands, or target resets occur here.

The complete first 64 KiB sector was programmed and read back successfully;
the following 4 KiB remained unchanged. **PE6-only recovery has now passed
exact park verification after a cold cycle and a subsequent warm reset using
`0xC0` at 1 Mbaud.** A read-only NOR INFO operation also passed from recovery.
These are specific measured successes, not a reliable-selection guarantee:
three earlier warm-reset requests failed to restore AP1 access, and normal
camera capture remains unqualified for this exact image.

## Request and timing

Open/configure ST-LINK VCP at **1,000,000 baud, 8N1** and repeatedly send **`0xC0`**
while booting. This produces approximately **7 microseconds LOW / 3 microseconds
HIGH** per byte, giving more HIGH sampling margin than the original `0x00`
proposal's 9 microseconds LOW / 1 microsecond HIGH. The existing v45b pulse
thresholds already accept both patterns; the successful test required no
firmware change. PE6 is configured as input/pull-up alongside PE1. The detector
requires three complete HIGH→LOW→HIGH pulses:

- LOW: 2,400–5,200 DWT cycles, nominally 6–13 microseconds.
- Intervening HIGH: 100–1,600 cycles, nominally 0.25–4 microseconds.
- At least three consecutive valid LOW pulses; a bad width or gap resets the
  running count. A recognized request remains latched.
- All accepted samples precede the existing 40,000-cycle deadline, measured
  from the same timestamp used for PE1 settling. There is no extension to wait
  for a byte, pulse, or host USB gap.

A static LOW, static HIGH, lone transition, partial first LOW, or one/two
complete pulses cannot select VCP recovery. This is a deliberately recognizable
electrical pulse signature, not full UART decoding, authentication, or a unique
binary command. Do not send unrelated serial traffic during this boot window.

The earlier measured 1 Mbaud **zero-byte** waveform has 8.96–9.12 microsecond LOW pulses, usually
about 1 microsecond HIGH gaps, and occasional gaps up to 104.64 microseconds.
Such a gap can occupy the entire observation window. The user accepts bounded
reset/retry; the host must verify the exact park before maintenance. It must
never issue recovery resets during active or uncertain storage writes.

**BREAK controls NRST on this measured ST-LINK-V3EC firmware; it does not hold
PE6 LOW.** The host can transmit the byte stream while BREAK holds reset, then
release reset with data still pending. Releasing BREAK and verifying the final
NRST/PE6 levels remain mandatory host cleanup.

The observation deadline is unchanged, but total boot time is not proven
unchanged. The wrapped prefix grows from 5,696 to 6,176 bytes and adds
diagnostic record stores/copies. ROM transfer time therefore increases. New
diagnostic initialization occurs inside the original settle interval. The
successful cold `0xC0` test recorded 153 polls over 39,216 cycles from its first
sample through the final sample: **about 0.641 microseconds per poll on average**
at the nominal 400 MHz clock. This is slower than the offline 0.4 microsecond
sampling model and does not bound the longest interval between polls.
The false-selection rate, repeated-request reliability and total startup cost
remain unqualified; the polling model below does not establish them.

## Hardware checkpoint — October 20

The [compact evidence archive](../evidence/2026-10-20-vcp-sd-smoke/README.md)
preserves the build, programming, park records and failure summaries. Full
working evidence remains under `tmp/bringup/vcp-install-20261019/`; that
directory name identifies the session, not the local date of every operation.

| Operation | Observed result | Working evidence |
| --- | --- | --- |
| Development-mode programming | Complete 65,536-byte readback matched the v45b sector; following 4,096 bytes unchanged | `development-nor/verified.json` |
| Normal cold boot | AP1 access unavailable afterward; camera capture was not qualified | `normal-cold-01/`, `normal-inspect-01/` |
| First two warm recovery requests, zero bytes | AP1 access unavailable after each request | `recovery-request-01/`, `recovery-request-02/`, corresponding park attempts |
| First warm `0xC0` request | AP1 access unavailable afterward | `recovery-request-c0-01/`, `recovery-park-c0-01/` |
| Cold `0xC0` request | Exact early recovery park passed; PE1 HIGH, source bits 2, nine valid pulses, 19 edges, no rejected LOW pulses | `recovery-cold-c0-01/`, `recovery-park-cold-c0-01/result.json` |
| NOR INFO from that recovery state | Result 0; JEDEC/status reads completed, zero WREN, zero pages programmed, no erase | `recovery-nor-info-01/status.json` |
| Subsequent warm `0xC0` request | Exact early recovery park passed again; PE1 HIGH, source bits 2, nine valid pulses | `recovery-request-c0-02/`, `recovery-park-c0-02/result.json` |

Both successful park checks observed PC `0x3418078c`, the exact live prefix,
interrupts masked, integer-only CPU context, instruction/data caches disabled,
and idle, clocked XSPI. The cold run recognized the request at DWT cycle 15,370,
about 38.41 microseconds after its begin cycle of 6. Its last observed LOW/HIGH
widths were 2,712/1,136 cycles, about 6.78/2.84 microseconds. The subsequent
warm run recognized at cycle 12,663 after begin cycle 11, about 31.63 microseconds;
its last widths were 2,952/1,136 cycles, about 7.38/2.84 microseconds.

The failed warm requests are retained as failures. These results do not
establish whether their cause was pulse sampling, reset/boot state, debug
access, or another condition. In particular, a cold success followed by a
warm success does not prove all warm resets are reliable. Use the verified
`0xC0` stimulus and bounded safe-state retries, with exact park verification
before maintenance.

The subsequent [read-only SD smoke helper v3](../../sd-smoke/README.md) passed
two reads at 100 kHz and six reads across 100 kHz, 12.5 MHz and 25 MHz, with
byte-identical data and no data CRC errors. Three early CMD8 timeouts persisted
through the first wiring correction; a second correction allowed identification.
V3 also corrected v2's completion check: DATAEND, idle, all 128 words and no
errors, without requiring DBCKEND. Reported card capacity is 62,723,719,168 bytes,
not a capacity validation. No SD writes, erases, throughput or energy
measurements were performed.

The target is now powered at the SD v3 helper's awake park, `0x341E05E4`,
which is distinct from the prefix recovery park. Re-enter exact prefix recovery
before another maintenance helper. The JS110 helper closed cleanly, restoring
its starting range 128; BREAK is released and COM8 closed. Only CH0/NRST and
CH6/PE6 are confirmed; CH1–5 were not moved or reverified. No further probe move
is needed for the completed SD smoke test. The NOR-installed v45b camera
receiver remains unchanged, and its normal capture/sleep path is unqualified.

## Records and host validation

The original 24-word `RGP1` record remains at `0x341f7000`, published on normal
boot at `0x343f7000`. Its formerly reserved word 23 now contains request-source
bits: **bit 0 = PE1 sampled LOW, bit 1 = PE6 pulse train recognized**. Requested
recovery still uses state 3 and reason 1. Timer/context failures retain their
distinct failure reasons and cannot authorize NOR maintenance.

The 32-word `VPC1` proof is at `0x341f7080`, published after expanded SRAM setup
at `0x343f7080`. Exact fields and constants are recorded in the build manifest.
It includes first/last sample cycles, observed edges, good/bad pulse counts,
maximum consecutive count, last widths, request cycle, initial/final levels,
source bits and poll count. Normal capture can overwrite low SRAM, so use the
published record after the normal path has initialized it.

The host must add this exact prefix/sector to its reviewed allowlist, validate
the new source-bit meaning and proof, verify both PE1/PE6 input/pull-up fields,
then retain all prior live-code, awake PC, integer context, disabled cache and
idle/clocked XSPI checks. VCP selection does not require PE1 LOW. Recovery
maintenance still uses the low-SRAM helper; it precedes expanded SRAM setup.

## Build and offline tests

```powershell
python firmware/capture-timing/recovery_vcp/build.py `
  --base tmp/bringup/capture-status-leds-v44-default-20261018 `
  --output tmp/bringup/capture-vcp-recovery-v45b-20261020

python -m unittest discover -s firmware/capture-timing/recovery_vcp -p test_vcp.py -v
```

The builder verifies exact v44 sector/prefix/receiver identities and every
frozen manifest source. Only `recovery_gpio.c` is replaced, with the added pure
detector header. It preserves all bytes beyond the new occupied boot prefix,
including the receiver and its offset. It refuses an existing output directory.

v45b build and readback identities:

| Item | Value |
| --- | --- |
| Raw prefix | 5,140 bytes |
| Wrapped prefix | 6,176 bytes |
| Prefix SHA-256 | `a8aebf4ed32d735d6352e9d5267759ed7b2c6733ac1a87bd4a0926a51c17e08a` |
| Complete 64 KiB sector SHA-256 | `2323caa6b0ef142a6f46adbfdb078f9070877f7665f97337145de75eec60b3d2` |
| Unchanged receiver SHA-256 | `478680d7ca87b19a0bcbab208535b36ab1fd985e141ce69a86b3602963a621ac` |
| Recovery park | `0x3418078c`, instruction `fee7` |

Seventeen tests compile and execute the actual pure-C detector on the host. They
exercise static levels, lone edges, an initial partial pulse, short glitches,
wrong widths/baud, missing/long HIGH gaps, three-pulse qualification, every
sample phase at a modeled 0.4 microsecond interval, timer wrap, a late request
that cannot extend the deadline, and preservation of bytes beyond the prefix.
The seven added `0xC0` checks cover all 4,000 signal phases at a modeled
0.641 microsecond mean interval, bounded timing jitter, static/partial pulses,
three-pulse qualification, deadline/wrap behavior and a compact measured
waveform excerpt. A deliberately adverse schedule misses every HIGH despite
a 0.625 microsecond mean interval, explicitly demonstrating that an average
poll interval is not a worst-case sampling bound.

Replaying the committed 1 Mbaud Saleae trace through that same C detector at
the modeled 0.4 microsecond interval selected recovery in **995 of 1,001 sampled
100 microsecond windows**. The longest 104.64 microsecond HIGH gap correctly
failed to select recovery. This is an offline waveform replay, not an observed
MCU detection probability or a bound on host/USB delays.

The earlier `capture-vcp-recovery-v45-20261020` build is superseded by v45b,
which moves diagnostic initialization inside the existing settle deadline.
