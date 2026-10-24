# Packed RAW SD slots — October 24, 2026

The user selected direct packed RAW10 storage in consecutive SD logical sectors,
replacing PNG/FAT32 for the next prototype. The goals are shorter capture/save
cycles and lower energy, with image conversion deferred to the host. Existing
card contents may be replaced. Four-bit SDMMC and a faster card are planned,
but the current native one-bit, 25 MHz wiring remains in use.

## Format and allocation

Each fixed slot contains one CRC-protected header and 3730 payload sectors.
The 1120 × 1364 image occupies 1,909,600 packed bytes; only its final 352 bytes
need copying into a zero-padded sector. A valid FREE header is claimed as PARTIAL
before payload writes, then marked FULL only after complete capture validation,
sensor STOP and successful card-ready checks. Allocation scans one header per
slot, skipping FULL and PARTIAL. Photos are never silently overwritten.

Explicit FREE records replace the proposed all-blank heuristic. An SD card is a
managed block device: an apparently blank or torn sector is not proof of a clean,
unused image slot. Formatting writes a new generation and all FREE headers,
publishing the READY volume only after that operation completes. Unknown,
inconsistent or damaged headers fail closed. This is not secure erasure or a
guarantee against sudden power loss inside the card's translation layer.

The complete format is specified in [raw-slots](../../firmware/raw-slots/README.md).
The read-only host utility lists slots and reconstructs either packed RAW files
or 16-bit grayscale PNGs with each sample shifted left six bits. PTP/USB export,
per-photo deletion and interrupted-write reclamation remain future firmware work.

## Transfer and power choices

The camera fills a linear RAM buffer once. SDMMC IDMA reads immutable published
prefixes directly; transmitted storage is not reused while capture is active.
The full frame buffer remains necessary because camera delivery is substantially
faster than the current card interface. Transfers use large multiblock commands,
with a smaller first request when only a prefix is available.

The optional LINE producer holds back one full 64-line group. Its hardware test
poisons RAM before capture and snapshots each newly published tail immediately,
so a slow SD reader cannot hide premature publication. This is an engineering
margin with bench evidence, not an explicit cross-master AXI visibility guarantee
in the reference manual. Full-frame validation and sensor STOP precede FULL.

Normal saving performs no image compression, conversion or full-frame software
checksum. Link CRC and header CRC remain, but they do not independently detect
all retained pixel corruption. This prototype supersedes the prior PNG path's
end-to-end pixel checks during every save; full readback comparison is used for
qualification. Durable pixel checksums remain a separate future design decision.

Storage code is loaded from NOR after receiver arming so the larger implementation
does not consume the camera's critical startup budget. The exact early UART
recovery guard remains mandatory. Card deinitialization and the established
peripheral teardown precede MCU Standby; regulator-controlled battery power-off
and complete power isolation remain unqualified.

## Discovery: SDMMC DMA security

An initial IDMA test reported successful SD writes but stored zeros. Full image
readback caught the discrepancy. RIFSC's SDMMC2 configuration-port security
setting overrides the DMA master's security attribute; the configuration port
was nonsecure despite a secure/privileged CID1 master setting. SRAM protection
therefore rejected the reads. Both attributes are now explicitly checked and
configured without relaxing SRAM protection. The corrected deterministic image
matched all 1,909,600 camera bytes after SD readback.

See the [implementation and qualification record](../../firmware/capture-raw/README.md)
for tested builds, measurements, limitations and the final bench state.

## Selected implementation and deferred optimizations

The selected flash image is RAW v15 with hardware IDMA, conservative LINE
publication, asynchronous sensor STOP and final Standby. Three complete cold
cycles of the preceding v12 implementation provide the baseline. Those
cycles measured median 0.793888 s / 0.441400 J on the JS-fed Nucleo branch,
against 2.057802 s / 1.061503 J for the preceding PNG v66c baseline using the
same threshold criteria. Card/image variability and unmeasured supply bypasses
remain; this is not production battery energy or a controlled isolation of each
optimization. Full source-frame comparisons passed in the separate pattern and
awake cold-scene trials. Standby destroys the frame, so later slot readback is
not falsely described as comparison against that lost original.

Shallow CPU sleep during IDMA is **disabled in the selected build**. The first
trial refused missing sleep clocks before entering WFI. A revised trial with
explicit memory/security/interconnect/SD clocks and debug sleep emulation
removed stalled and lost debug access. Warm reset did not recover it. A single
authorized interruption and power restoration returned to the unchanged
working flash image. Two attempted slots remained PARTIAL and were skipped.
The exact cause is unresolved; BSEC sleep-clock retention and Cortex-M55 local
power controls are hypotheses, not established fixes. Future work should first
qualify one WFI with the card idle, then resume active-transfer experiments.

The cold card's 111–118 ms initialization finishes after the ~22 ms frame
acquisition. Consequently the selected cold runs do not overlap payload writes
with acquisition, despite the tested producer supporting that overlap when SD
is ready sooner. The separate preinitialized-card experiment proves actual
before-FRAME writes. The current full frame buffer acts as a bounded producer/
consumer queue; it is retained because the camera is faster than one-bit SD.

Four-bit SDMMC and faster cards can reuse the slot format and producer/transport
interface. Their wiring, negotiation and throughput are not enabled or qualified
by this change. Allocation currently scans from slot zero and therefore grows
with occupancy; an allocation hint and deletion/reclamation are future work.
PNG/PTP export remains host-side/future firmware work. The read-only extraction
utility already reconstructs 16-bit PNGs with the agreed `sample << 6` mapping.

Final review found a retained-RAM freshness bug in early failure handling:
the previous boot's late-loader success marker could survive a warm reset.
V15 clears that marker before initialization, keeping the early load size and
UART recovery instructions unchanged. Executable regression checks cover stale
marker values. A separate cold v15 smoke run passed SBF, UART recovery and full
slot-8 readback/PNG reconstruction, measuring 0.778143 s / 0.424945 J. This is a
single follow-up measurement, not a replacement for the three-run v12 baseline.

## October 24 follow-up: ACMD23 and one whole-image transaction

The user requested a comparison of `CMD55 + ACMD23` followed by one multiblock
write for the whole image against the current implementation. V16 provides
`--whole-image-preerase`: the exact announcement is 3730 payload sectors,
including the padded final sector and excluding both PARTIAL/FULL header writes.
It sends CMD25 immediately after the accepted hint, then explicitly terminates
with CMD12 and requires fresh READY/TRANSFER, DAT0 high and an idle controller.
Both application-command acknowledgments are checked; there is no silent
fallback after a rejected hint. ACMD23 is not a cache-flush guarantee.

The full image is validated before submission. The original guard is checked
before its location becomes zero padding; a distinct post-padding guard remains
intact through transfer and commit. Only 160 padding bytes are written by the CPU.
No full-frame copy, compression or checksum was added. The previous chunked LINE
path remains available, since a future faster-initializing card could benefit
from before-FRAME streaming. With the current card, SD initialization already
finishes after FRAME, so this experiment does not delay the first payload.

Three fresh v15 runs had median 796.377 ms / 435.297 mJ; three v16 runs had
780.385 ms / 426.796 mJ on the same JS-fed Nucleo branch. The payload median
improved from 633.320 to 626.438 ms. The observed total saving is about 2%, but
SD initialization also varied by about 9.6 ms between group medians. Later slot
scan positions and unknown card state confound this chronological comparison;
do not claim statistical significance or attribute the entire gain to the hint.
This test changes both preannouncement and transaction grouping together.

Keep v16 selected for this prototype, retaining the prior chunked option. Its
early load remains 15,804 bytes and recovery instructions remain unchanged;
DMA-WFI stays disabled. Separate pattern and normal cold-scene readbacks matched
every saved byte to the captured RAM image. Standby and warm UART recovery passed
for all six comparison cycles. See the
[experiment archive](../../firmware/capture-raw/evidence/2026-10-24-preerase/README.md)
for per-run measurements, full slot readbacks, firmware identities and final state.

## October 24 follow-up: erased-card magic slots and progressive whole-slot writes

**Decision:** The user selected a simpler prototype layout and authorized erasing
the existing card to establish it. This supersedes the earlier explicit FREE /
PARTIAL / FULL header and generation choice for the new prototype. The earlier
implementation and its parser remain available to interpret the recorded v12–v16
evidence. This entry records the design and implementation under qualification;
it does not claim that the new format has been installed, the physical card has
been erased, or a new timing/energy result has passed.

The complete card is explicitly erased once through the SD erase protocol,
waiting for successful card readiness before use. The expected erased byte comes
from SCR `DATA_STAT_AFTER_ERASE`: value 0 means `0x00`, value 1 means `0xff`.
Firmware never guesses that polarity from arbitrary card contents and never
silently formats on boot or after a read error. The previous format's operation,
which wrote FREE headers without erasing payloads, is insufficient commissioning
for this layout. An interrupted erase must be completed successfully before the
card is admitted to normal capture. With no on-card format-completion record,
successful commissioning and its card identity must be retained externally.

Each slot begins at **LBA `slot_index * 3730`**, including slot zero at LBA 0.
There is no superblock, format generation, allocation table or separate header
sector. Each 1,909,760-byte slot contains exactly:

| Offset | Bytes | Contents |
| --- | ---: | --- |
| 0 | 4 | Leading magic `GXRS` |
| 4 | 1,909,600 | The unchanged 1120 × 1364 packed RAW10 image |
| 1,909,604 | 4 | Trailing completion magic `GXRE` |
| 1,909,608 | 152 | Zero padding to 3730 logical sectors |

Allocation reads the first sector of each slot, scanning from slot zero, and
examines its first four bytes. Only four copies of the reported erased byte mean
FREE. Valid leading magic means used, and any other non-erased word is also
reserved/occupied and skipped; malformed magic is never permission to overwrite.
A read error stops allocation rather than presenting the slot as free. The card
still transfers a full 512-byte read sector even though only four bytes determine
occupancy. The first FREE slot is selected; a full card preserves existing photos
and stops. Unused sectors after the final complete slot are not allocatable.

The leading magic is placed in RAM before acquisition. Camera DMA writes directly
after it, with no image move or full-frame CPU processing. DCMIPP Pipe0 requires
a 16-byte-aligned destination, so the planned addresses are image `0x34000010`
and slot buffer `0x3400000C`, which still satisfies SDMMC's word alignment.
The original image-boundary guard is checked before its bytes become the trailing
magic/padding; a separate guard protects the end of the complete slot allocation.
The last sector is withheld until complete capture validation and successful
sensor STOP permit writing the trailing magic. This keeps the completion marker
in the same forward pass, without rewriting the leading block or adding another
sector transaction.

The transport announces **3730 sectors** with `CMD55(RCA)` / `ACMD23(3730)` and
opens one CMD25 at the selected slot LBA. It begins as soon as at least one
complete, safely published sector exists, then sends newly available sectors in
order within that same transaction. The single command is closed with CMD12;
successful data completion and fresh card readiness still precede deinitialization
and shutdown. An incomplete producer uses a progressive PIO path with SDMMC
hardware flow control so unavailable bytes are never supplied. If the complete
validated object is already published at launch, the existing hardware IDMA path
can transfer it directly. These are two implementations of the same on-media
format and one-command transfer contract, not separate per-chunk CMD25 requests.

The software must **not** assume that SD initialization finishes after FRAME.
That happened in the recent short-exposure measurements, but longer exposures
or a different card can reverse the order. Producer availability, immutable
prefix ownership, final-marker withholding, and bounded failure handling are
required in both cases. The existing conservative LINE publication rule remains
an engineering margin to qualify on the actual camera/SD/bus combination; a CPU
barrier alone cannot drain a separate DMA master's outstanding writes. Failure
handling must return control to an active SD transaction for bounded cleanup,
rather than park inside a camera callback while the card still owns a transfer.

The new layout writes **3730 sectors once each**, instead of 3730 payload sectors
plus two writes of the former PARTIAL/FULL header. It also uses one fewer logical
sector per slot. These are logical-I/O savings, not a guarantee of reduced NAND
program operations inside the card. Erase establishes the card's specified
logical read value; it does not expose physical NAND placement. ACMD23 gives the
card a preparation hint, not a physical reservation, a fixed mapping to erased
NAND, or a power-loss-safe commit. No SD FTL atomicity, secure erasure, arbitrary
power-loss protection or production battery-energy claim follows from this layout.

Two valid markers identify a nominally complete object; they do not checksum its
pixel bytes. A missing trailing marker identifies a partial object when the
leading magic survives, while an unknown non-erased leading word remains occupied.
Readback/extraction can recover image bytes with an explicit warning for partial
or damaged objects. Corruption that leaves both markers intact can remain
undetected. Power interruption during a logical-sector update can also defeat
assumptions about which bytes survive; this prototype does not qualify that case.

The user-selected layout stores **no exposure, timestamp, orientation, capture
identifier or other image metadata** beyond the two magic words. Slot position
and fixed geometry are known externally. The host utility can reconstruct RAW10
or grayscale PNG16 (`sample << 6`), but cannot recover metadata that was never
stored. Adding metadata, checksums, reclamation/deletion or an allocation hint
is explicitly deferred rather than silently expanding this prototype object.

The specification and new C/host interfaces are in
[the magic-slot section](../../firmware/raw-slots/README.md#magic-slot-format-selected-october-24).
Offline tests exercise allocation, failure handling and extraction while retaining
the legacy format tests. Physical erase, short- and long-exposure streaming,
complete image readback, recovery, shutdown and time/energy comparison remain
qualification work at the time of this decision entry. Later evidence must state
which of those passed and preserve any failures rather than rewriting this history.

## October 24 implementation follow-up: magic slots qualified through awake capture

**Decision:** Select the implemented v17d magic-slot prototype and retain the
earlier v12–v16 header-format measurements as historical evidence. The new
Standby flash image is installed with sector SHA-256
`2ad7168302fe05b928b2b1aa62ef9732dfeab0d61e6092de2c086412d4485880`.
It is byte-identical to the v17c flash image because the v17d change affects
explicit erase, which is linked only into the RAM maintenance build. Early
loading remains 15,804 bytes, the boot-fresh late-loader guard remains intact,
and the exact PE1/PE6 recovery instructions and literals are preserved.

The implementation uses the selected layout exactly: slot zero at LBA 0,
3730 sectors per slot, and `4 + 1,909,600 + 4 + 152` bytes for leading `GXRS`,
packed image, trailing `GXRE`, and zero padding. No superblock, generation,
separate header write or image metadata was added. Camera DMA writes at
`0x34000010`, with its leading magic four bytes earlier, satisfying both the
camera's 16-byte and SDMMC's word-alignment requirements. The complete buffer
remains allocated until saving finishes; the 256 KiB maintenance readback buffer
is separate and is not a circular capture FIFO.

The first usable producer watermark remains **89,600 image bytes**, from the
conservative 64-line holdback. The first submitted prefix is 175 complete slot
sectors, including the leading magic. Starting as soon as the first individual
512-byte image block arrives would need a finer, independently qualified DMA
visibility mechanism and is not claimed by this implementation. A complete
object at launch uses IDMA; an incomplete object uses PIO with hardware flow
control inside the same announced CMD25. FRAME validation, successful sensor
STOP and both guard checks precede publication of the trailing magic. Returning
camera failures hand control back to the SD owner for bounded cleanup.

**Discovered erase constraint:** The first explicit whole-card erase inherited
the SCR read's 50,000,000-cycle SDMMC timer, which expires after two seconds at
25 MHz. The ensuing software wait timed out after 600 seconds even though the
card reported READY/TRANSFER and DAT0 was high: SDMMC had retained
`DPSMACT`, `BUSYD0` and `DTIMEOUT`. This was a host R1b busy-state problem,
not evidence of a ten-minute card erase. The failed FORMAT record remains
failed. A separately bounded host recovery proved idle without reset or power
cycling and did not retroactively qualify that FORMAT.

V17d selects the qualified 100 kHz clock before CMD38 and configures the hardware
busy timer for the requested software timeout plus one second; even the maximum
ten-minute request then fits its 32-bit register. It restores the former clock
and timer only after fresh card and host idle proof. An uncertain operation
retains ownership and the slow clock. The corrected explicit erase completed
over LBAs 0–122,507,263. Twenty probes across initial slots and distant card
locations matched the SCR-reported erased value. Those probes are sampling,
not verification of every logical block, physical NAND erasure or secure
sanitization. See the [driver explanation](../../firmware/sd-storage/README.md#scr-and-explicit-whole-card-erase).

**Verified functional paths:** Deterministic slot 0, long-exposure slot 1 and
normal awake-flash scene slot 2 each passed complete SD-to-original-camera-RAM
byte comparison and independent PNG/sample decoding. The long diagnostic used
coarse exposure 30,000, frame length 32,000 and a nominal 230,597 µs integration.
Its 400 MHz DWT record places first write submission 9.451 ms before FRAME and
card readiness 213.447 ms before FRAME. Twenty immediate LINE tail snapshots
also matched the final frame. This verifies before-FRAME writes with the new
four-byte offset; it is not a normal cold-boot speed or energy result. The run
did not exhaust its published prefix, so prolonged physical FIFO starvation
remains a hardware qualification item despite passing modeled starvation tests.

The first cold cycle of the installed Standby image passed warm UART recovery
and an independent SBF check. At this checkpoint, the new three-cycle comparison,
per-cycle image qualification and final handoff are still in progress. Do not
reuse v16's medians as v17d measurements or treat this entry as a completed
three-run baseline. The [new evidence archive](../../firmware/capture-raw/evidence/2026-10-24-magic-slots/README.md)
will retain successful paths, the original erase failure and its recovery,
exact firmware identities, and the later measurement qualification.

**Limits retained:** Both markers can survive pixel corruption, so they are not
an image checksum. Logical erase and ACMD23 do not reserve physical NAND or
establish power-loss atomicity. No arbitrary power-loss, isolated-DUT or
production battery-energy claim is made. The agreed object still contains no
exposure/time/orientation metadata; those fields, deletion/reclamation,
allocation hints and on-camera PNG/PTP export remain deferred. Host extraction
continues to support both formats and the agreed PNG16 `sample << 6` mapping.

## October 24 final qualification: magic slots complete, no measured speed gain

**Decision:** Retain v17d as the current prototype after successful capture,
storage, Standby and recovery qualification. The new format reduces logical
writes and removes the separate slot-header updates, but the fresh comparison
does not demonstrate a shorter complete cycle.

Three cold cycles per build used the same current-onset to stable-Standby
measurement boundary on the Joulescope-fed Nucleo branch:

| Metric | Header-format v16 | Magic-format v17d |
| --- | ---: | ---: |
| Median duration | 997.516 ms | 998.118 ms |
| Duration range | 796.301–1041.987 ms | 983.274–1016.510 ms |
| Median energy | 549.897 mJ | 536.883 mJ |
| Energy range | 444.034–582.389 mJ | 528.532–546.401 mJ |

The median duration increased 0.602 ms (0.060%), while median measured energy
decreased 13.014 mJ (2.367%). The whole card was erased between groups, so card
state, scan position and the small sample size confound attributing either
difference to the container change. This is not a statistical performance
claim or a measurement of isolated DUT or production battery energy. The
earlier v16 median of 780.385 ms belongs to a separate historical experiment
and is not substituted for this comparison's fresh v16 baseline.

All six comparison cycles passed warm UART recovery, independent SBF checks
and complete saved-object readback. Candidate slots 3–5 passed independent
PNG/sample decoding and visual inspection, showing the discernible LED panel
and bench. Original camera RAM was lost in Standby, so their image checks
compare PNG decoding against retrieved SD bytes rather than the original
frame. The separately qualified awake captures retain the complete original
RAM comparison. Deterministic slot 0 was reread after the later captures and
still matched every original byte. The strict pulse decoder identifies events
1–9; the final pre-WFI pulse remains unidentified rather than being relabeled
from position. SBF establishes Standby independently.

The final extra normal cold boot left the target powered at the low-current
plateau, **4.892311 V / 8.075647 mA**, at 17:56:22.939300 UTC. Its expected
slot 6 and SBF were not reread, so this handoff is not another qualified sample.
JS110 stopped cleanly and restored range 128, COM8 was closed and BREAK
released; v17d remains installed. Final wiring and instrument ownership are
recorded in the project checkpoint. The [evidence archive](../../firmware/capture-raw/evidence/2026-10-24-magic-slots/README.md)
contains the comparison, per-cycle qualification, preservation check, original
erase failure and recovery, and final bench state.

**Limits retained:** Neither the observed image checks nor the two magic words
qualify arbitrary power loss or detect every possible pixel corruption. The
long-exposure overlap test remains distinct from normal-cycle benchmarking;
it demonstrated before-FRAME writes but did not exhaust the published prefix.
On-media exposure/time/orientation metadata, reclamation/deletion and finer
than 64-line producer publication remain deferred.
