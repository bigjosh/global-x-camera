# SD implementation and critical-path review

This is an offline review of the existing RAW save path and the explicit reviewed
50 MHz candidate. It is not a hardware qualification or a new energy result.
The physical results belong in this directory's main evidence record.

## What the current save already overlaps

The camera begins before the late storage code is loaded. Camera receive DMA and
interrupts continue while that code loads and while SD initialization polls.
`sd_progress()` services camera completion and asynchronous sensor STOP during
those polls. A long exposure can therefore continue through SD initialization.

The image buffer acts as an immutable-prefix producer. If the whole padded slot
is available at the first submission, the storage path starts one IDMA transfer
for all 3,730 sectors. If only a prefix is available, progressive PIO fills the
SDMMC FIFO only from published complete sectors, and hardware flow control
pauses the SD clock when the producer cannot keep up. Both paths announce the
full count with CMD55/ACMD23 and use one CMD25, followed by CMD12 and fresh
readiness. They do not restart DMA or send a software command for each sector.

The card's per-sector acceptance and DAT0 busy intervals are handled by SDMMC.
The card can internally pipeline reception and programming, but the host cannot
send a new block while the card explicitly holds the bus busy. Extra CPU
double-buffering does not remove that restriction. The existing full image RAM
buffer already avoids a source-buffer shortage for the normal completed-frame
IDMA path.

## Measured priorities

The reference numbers below come from the single retained
[25 MHz cycle trace](../../CYCLE_TRACE.md), not from a new run. Intervals nest
and overlap, so their rows must not be summed.

| Work | Reference time | Consequence / next controlled experiment |
|---|---:|---|
| SD initialization | 227.395 ms | Dominant cold-start work; includes camera servicing |
| CMD55/ACMD41 power-up negotiation | 203.689 ms, 62 attempts | Likely largely card startup, but command cadence contributes; measure before attributing it entirely to the card |
| Initial clock train | 10.021 ms | Candidate for a separate specification-bound reduction after supply-stability assumptions are explicit |
| Identification commands after power-up | 5.271 ms | A separate 400 kHz identification trial can reduce command wire time; it need not shorten the card's internal startup |
| Second SCR read | 0.172 ms | Reuse the validated initialization SCR within the same card session; clear the cache at every init and never reuse across a power cycle |
| Slot scan | 11.326 ms for 13 first-sector reads | Linear growth will matter on a fuller card; preserve the simple format now and separately design any validated search hint |
| Complete slot write call | 161.803 ms | Almost all of it is the data phase |
| Data phase | 159.403 ms | At 25 MHz, payload serialization alone is 152.781 ms, about 95.85% of this interval |
| Final write readiness | 2.165 ms | Required card completion boundary, not a removable fixed software delay |
| SD deinitialization | 0.043 ms | Its final fresh readiness check is small; do not remove it before proving an equivalent ownership boundary |

At 50 MHz, the payload-only lower bound becomes 76.3904 ms. This arithmetic
motivates the clock experiment but does not predict actual card busy time,
signal-integrity retries, whole-cycle time or energy. Raising the bus clock can
also make progressive PIO more sensitive to CPU service gaps; the long-exposure
preinitialized diagnostic is intended to exercise that path directly.

## Changes included in the first reviewed candidate

The opt-in profile initializes the hardware busy timeout before CMD7, permits
draining the full 256-word receive FIFO on an owned abort, verifies response
command identity and error handling, and confines the CMD12 end-of-media
exception to the specific valid read boundary. These correctness changes are
separate from throughput shortcuts. See the [state-machine review](STATE-MACHINE-REVIEW.md)
and [protocol/clock review](PROTOCOL-REVIEW.md) for their reasoning and limits.

High Speed support is explicitly checked and switched with CRC-clean 64-byte
CMD6 status blocks. A separately owned 100 MHz kernel produces exactly 50 MHz;
the old 150 MHz source cannot do so with an integer divider. The initial and
intermediate 25 MHz launch phase is falling; the 50 MHz launch phase is the
datasheet-backed default phase. Public entry guards reject an absent controller
clock before touching SDMMC registers. Failed initialization preserves its
original error, releases the experimental clock only after fresh idle evidence,
and retains ownership if cleanup is uncertain.

## Deliberately separate follow-ups

1. Measure the first 50 MHz profile before changing identification rate, clock
   training delay, GPIO slew, compensation or repeated readiness checks. This
   keeps failures attributable to a narrow change.
2. Test 400 kHz identification independently. Bind both software and hardware
   timeout calculations to the new frequency, including select-card R1b.
3. Bound the initial clock train from the actual card supply-stability event and
   the specified minimum clock/time requirement; elapsed CPU time alone does
   not prove the external rail was valid.
4. Cache the validated SCR within one initialization session. Its performance
   benefit is small and does not justify weakening card-state checks.
5. Revisit slot-search scaling when capacity, deletion and allocation-table
   design are settled. The current front metadata and completion markers remain
   unchanged by this experiment.
6. Starting SD initialization before the camera is armed would require a
   nonblocking initialization state machine or changing the early boot load.
   Neither is a free reordering: sensor deadlines and autonomous recovery must
   remain qualified. The current `--preinit` mode is a diagnostic that delays
   camera start, not a normal latency optimization.
7. CPU sleep during active SD DMA was previously rejected after a failed bench
   experiment. It is not reintroduced by the High Speed profile. A future energy
   trial needs separate peripheral/sleep-clock and recovery evidence.

## Offline verification and frozen candidates

The complete RAW suite passed 134 tests. The actual-driver suite passed 16 tests,
including reviewed and historical profiles, full 3,730-sector IDMA and
progressive PIO writes, card busy after CMD12, command/data CRC failures,
unsupported switch status, duplicate initialization, failed clock gates,
clock-release failures, and cleanup after an interrupted slow-clock erase.
The isolated clock-helper model and real CMSIS ARM compilation passed separately.

The first RAM scene binary is
`tmp/bringup/sd50-reviewed-20261026/ram-scene/capture.bin`, SHA256
`85c17427303e837c27f7d08c1b517db2415d94bbc523b9b196eed77b29b856d1`.
Its manifest binds all source hashes and proof layouts. No NOR promotion is
implied. Historical v23 default 12.5 MHz, qualified 25 MHz falling, and the new
12.5 MHz falling profiles all rebuilt with byte-identical capture binaries,
recovery prefixes and complete 64 KiB sectors; the local exact comparison is
`tmp/bringup/sd50-reviewed-20261026/historical-byte-identities.json`.
