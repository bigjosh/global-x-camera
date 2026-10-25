# Packed RAW capture to fixed SD slots

This integration captures the sensor's unchanged ten-bit samples as packed MIPI
RAW10 bytes, writes them directly to the native SDMMC2 interface, and retains
the existing UART recovery mechanism. It uses the container in
[raw-slots](../raw-slots/README.md); there is no FAT filesystem, image conversion,
compression or full-frame CPU checksum in the normal save path.

## Four-bit candidate: prepared, hardware qualification pending

`build.py --sd-bus-width 4` selects native four-bit SDMMC2 on the full-pin
carrier at the same 25 MHz. The default remains one bit. Separate 24-byte
negotiation telemetry records SCR support, accepted ACMD6, host CLKCR and
selected width; the RAM/awake bench rejects incomplete evidence. The
[driver contract](../sd-storage/README.md#explicit-four-bit-build) describes the
additional PC0/PC5/PE4 connections and failure handling.

The reviewed v19b candidate preserves the 15,804-byte early load, recovery
instructions, RAW layout and exposure. It is **not yet installed or hardware
qualified**. After the user restored target power, both the four-bit RAM reader
and the frozen, previously working one-bit reader failed at CMD8 during the
initial 100 kHz handshake, before width negotiation. Both received the same
invalid response with a command CRC error. A physical hookup/card check is
pending; the JS output is intentionally off. No four-bit image or time/energy
result exists yet. See [initial diagnostic evidence](evidence/2026-10-24-sd-fourbit-bringup/README.md)
and the latest [bench checkpoint](../../AGENTS.md) before proceeding.

## October 24 replacement-card baseline

The user-labelled SanDisk Extreme 32 GB has completed three cold capture/save
cycles on the **original seven-pin carrier, one-bit SDMMC2 at 25 MHz**, with
unchanged v18. Median complete cycle: **882.627 ms / 450.788 mJ**, current onset
to qualified Standby plateau on the JS-fed Nucleo branch. Median payload-to-card
ready was **632.854 ms (3.017 MB/s image payload)**. The old 64 GB card's same-v18
single recorded cycle was 780.173 ms / 411.753 mJ; its 116.164 ms initialization
was shorter than the SanDisk's 220.053 ms median. These small samples do not
establish general card rankings.

All three fresh slots 0-2 passed complete readback, markers/front metadata and
independent PNG decoding, with SBF=1 attributed to each cycle. Frames were near
black; original capture RAM was lost in Standby. Full results, reproducible
compact energy sums, recovery findings and limitations are in the
[SanDisk baseline archive](evidence/2026-10-24-sandisk-extreme32/README.md).
No NOR programming or four-bit change occurred. After readback, the board was
left powered at an idle RAM READ terminal, rather than another normal capture.

## Selected layout: v18 front metadata slots

The selected format moves the former 152 trailing padding bytes immediately
after the leading magic. It keeps the same **3730 sectors per image** and one
announced CMD25. The user prefers this simple fixed-slot format for its expected
mapping to future NAND storage, independently of the current SD timing result.

**V18 capture → front-metadata RAW slot → Standby is installed.** Its complete
64 KiB NOR sector readback matched
`174424c6792f96c72e336fc68e442474e9da665718552d3239a772d59ba73e2e`;
the following 4 KiB remained unchanged. Its exact recovery prefix is
`9401bed4076d6e9e4d2e4f9236661faf7b8f0e051cb332ea4dcbba09da336eba`.

| Slot byte offset | Contents | Bytes |
| ---: | --- | ---: |
| 0 | Leading `GXR2` magic | 4 |
| 4 | Reserved photo metadata | 152 |
| 156 | Unchanged 1120 × 1364 packed RAW10 image | 1,909,600 |
| 1,909,756 | Trailing `GXRE` completion magic | 4 |
| | Total | 1,909,760 |

The first sector therefore contains occupancy, all 152 metadata bytes and the
first 356 image bytes. A directory listing can read just this sector to obtain
occupancy and metadata. Completion remains unknown until the last sector is
read; a leading magic is not a successful-save indication. The metadata region
is opaque and explicitly zeroed before acquisition for now. Timestamp, date,
orientation and other field schemas remain deferred; zeros are not a valid
capture date.

`GXR2` identifies the new image offset. The host utility also recognizes the
previous `GXRS` format, whose image begins at offset 4. Both formats have the
same stride and may coexist on the card: allocation skips every non-erased
first word, including both markers and unknown values. This transition requires
**no erase or rewrite of existing photos**. The
[format and directory/extraction utility](../raw-slots/README.md#front-metadata-magic-slots-selected-october-24)
document the read behavior.

Camera DMA now writes at `0x340000A0`, 156 bytes after the word-aligned slot
buffer at `0x34000004`. No image copy is introduced. Metadata is prepared before
any prefix can be sent and remains unchanged through saving. Producer
publication includes the 156-byte prefix, but still withholds the final sector
until validated FRAME, successful sensor STOP and guard checks. The one-CMD25
PIO/IDMA choices and conservative 64-line holdback remain unchanged.

The trailer is now the final word of the slot. Consequently, the original
32-byte camera guard and persistent 32-byte end guard overlap by 28 bytes.
They use a consistent nine-word sequence: original guard words 0–7, end guard
words 1–8. Publishing `GXRE` replaces only word 0; the end guard remains intact.
Two independently initialized guards at these addresses would corrupt each
other.

**Qualification checkpoint:** The four generated capture/integration tests
pass, including ARM-linked allocation geometry, nonzero retained-SRAM metadata
initialization, arbitrary metadata preservation, final-sector withholding and
corruption of every distinct overlapping guard word. All twenty format/host
tests pass, including mixed-format extraction and one-sector directory reads.

The new RAM builds also passed full SD readback against original camera RAM:

| Path | Verified result |
| --- | --- |
| Deterministic capture, slot 7 | All 1,909,600 image bytes matched RAM; GXR2, 152 zero metadata bytes and final GXRE were valid |
| Long-exposure capture, slot 8 | The same full comparison passed; progressive PIO started before FRAME, and twenty immediate LINE snapshots matched final RAM |
| Existing GXRS photo, slot 0 | Full readback after the new captures remained byte-identical to its original deterministic image |
| Installed flash capture, slot 9 | Normal cold boot, first-attempt warm UART recovery, exact early park and independent SBF=1 passed; the complete saved scene reconstructed and was visually inspected |

Both deterministic payloads have SHA-256
`5edaa1705f76b8434993271c86e71d5d83bce1c0ec7272caeec9564594279c1e`.
The 230.597 ms exposure test submitted its first write **9.447 ms before FRAME**;
SD was ready 213.383 ms before FRAME. The twenty LINE snapshots cover 10,240
bytes and provide sampled memory-visibility evidence, not a hardware AXI-drain
guarantee. This run did not exhaust its published prefix, so it does not qualify
prolonged physical FIFO starvation. The card was not erased for the layout
change.

The slot-9 readback contains the expected markers and zero metadata, and
independent PNG decoding agrees with the saved RAW bytes. The image shows the
lit panel, cables and notebook. Original camera RAM was lost in Standby, so
this cold test does not claim the original-RAM equality provided by slots 7–8.
The UART recovery detector recorded nine good pulses and zero bad pulses;
Standby was established independently without an intervening power-off.

A separate directory test read exactly one sector each for slots 0, 7, 8 and 9
before the cold capture: old slot 0 and new slots 7–8 were occupied, all new
metadata bytes were available, and slot 9 was free. Completion correctly
remained unchecked by those first-sector reads.

See the [front-metadata evidence](evidence/2026-10-24-front-metadata/README.md)
for exact builds, readbacks and final bench state. This is functional layout
qualification, not a fresh time/energy comparison. The v17d measurements below
remain historical results, not a v18 speed or energy baseline.

The final extra normal cold boot left the target powered at the low-current
plateau, **4.892723 V / 8.078679 mA**, at 19:02:04.963439 UTC. Its expected
slot 10 and SBF were not reread. Events 1–9 decoded and the final pulse remained
unidentified; this handoff is not another image/Standby-qualified sample.
JS110 stopped cleanly and restored range 128, COM8 was closed and BREAK
released, Logic 2 was left running, and no bench helper remained active.

## Historical prototype and measurements: v17d magic slots

The preceding prototype was **v17d capture → magic RAW slot → Standby**, using
one announced multiblock write and the existing PE6 UART recovery guard. Its
installed 64 KiB sector is
`2ad7168302fe05b928b2b1aa62ef9732dfeab0d61e6092de2c086412d4485880`.
The flash executable is byte-identical to v17c: v17d corrects the explicit
erase operation in the RAM maintenance build, which flash capture cannot enter.
The early load remains 15,804 bytes; the recovery instructions and literals are
unchanged. See the [magic-slot evidence archive](evidence/2026-10-24-magic-slots/README.md)
for exact builds, readbacks, measurements, failure evidence and final bench state.

Each fixed **3730-sector** slot starts at `slot_index * 3730`, including LBA 0.
There is no superblock, generation, allocation table or separately written
PARTIAL/FULL header. The complete object is:

| Contents | Bytes |
| --- | ---: |
| Leading `GXRS` magic | 4 |
| Unchanged 1120 × 1364 packed RAW10 image | 1,909,600 |
| Trailing `GXRE` completion magic | 4 |
| Zero padding | 152 |
| Total | 1,909,760 |

The card is explicitly erased during commissioning. Allocation scans the first
sector of each slot and uses a slot only if its first four bytes all equal the
erased byte reported by SCR `DATA_STAT_AFTER_ERASE`. Any other word is occupied,
including malformed magic; a read error stops allocation. Normal boot never
formats, and a full card preserves existing images. The
[format and extraction utility](../raw-slots/README.md#magic-slot-format-selected-october-24)
retain support for the older header-based format.

Its capture/save sequence was:

1. Put `GXRS` at `0x3400000C`; arm camera DMA at the 16-byte-aligned
   `0x34000010`, immediately after it. Seed separate image-boundary and
   post-slot guards.
2. Load the remaining storage code after receiver arm, then initialize SD and
   scan for the first erased slot while acquisition continues.
3. Wait for a safely published complete sector. The present conservative
   64-line holdback first publishes **89,600 image bytes**, yielding 175 complete
   slot sectors (89,600 bytes including the magic). It does not yet start at
   the first 512 image bytes.
4. Send `CMD55 → ACMD23(3730) → CMD25(slot LBA)` once. If the entire validated
   object is already available, use hardware IDMA. Otherwise feed only published
   sectors with CPU PIO and SDMMC hardware flow control, continuing the same
   CMD25 as more data becomes available.
5. Validate FRAME, stop the receiver and sensor, and check both guards. Only
   then replace the original image-boundary guard with `GXRE` and 152 zero
   padding bytes, publishing the final sector. Camera errors return to the SD
   owner for bounded transfer cleanup; callbacks do not park inside CMD25.
6. Require complete data transfer, CMD12, fresh READY/TRANSFER, DAT0 high and
   idle host state. Check final guards, deinitialize SD, and enter Standby.

The entire approximately 1.91 MB slot buffer remains in RAM throughout capture
and saving. It is a linear producer/consumer buffer, not a small circular FIFO;
transmitted memory is never recycled during acquisition. The separate 256 KiB
buffer is for maintenance readback. DMA sleep remains disabled. The current
hardware is still one-bit SDMMC at 3.3 V; four-bit operation is future work.

The first explicit erase exposed an SDMMC R1b busy-timer error: CMD38 inherited
the preceding SCR read's two-second timer at 25 MHz. The card later reported
READY and DAT0 high, but the host retained its timeout/busy state. The original
600-second software timeout remains a failed erase record; it does not mean
the card required 600 seconds. A bounded host recovery established idle without
reset or power cycling. V17d sets 100 kHz and a hardware timer longer than the
requested erase timeout before CMD38, restoring the previous clock/timer only
after fresh idle proof. The corrected full-card erase completed; twenty sampled
sectors matched the SCR-reported erased byte. This is not a readback of every
sector or proof of physical NAND placement. Details are in the
[SD driver documentation](../sd-storage/README.md#scr-and-explicit-whole-card-erase).

Functional qualification:

| Path | Verified result |
| --- | --- |
| Deterministic RAM capture, slot 0 | Complete SD object equals the original camera RAM; PNG decoding matches every sample |
| Long-exposure RAM capture, slot 1 | Same complete comparison, plus twenty immediate LINE snapshots; progressive PIO began before FRAME |
| Normal awake flash scene, slot 2 | Complete SD object equals the retained camera RAM; independent PNG decoding passed |
| Standby flash, slots 3–5 | All three cold cycles passed warm recovery, independent SBF checks, full slot readback and PNG/sample decoding; original camera RAM was lost in Standby |

The long diagnostic used coarse exposure 30,000, frame length 32,000 and a
nominal 230,597 µs exposure. Recorded 400 MHz DWT timestamps put first write
submission **9.451 ms before FRAME** and SD readiness **213.447 ms before FRAME**.
This qualifies the overlap path; it is not the normal cold-cycle timing or
energy baseline. It did not exhaust the published prefix, so prolonged physical
FIFO starvation is still covered by the register model rather than this run.

Three fresh cold cycles per build were measured from current onset to stable
Standby plateau on the JS-fed Nucleo branch:

| Metric | Header-format v16 | Magic-format v17d |
| --- | ---: | ---: |
| Median complete cycle | 997.516 ms | 998.118 ms |
| Cycle range | 796.301–1041.987 ms | 983.274–1016.510 ms |
| Median measured energy | 549.897 mJ | 536.883 mJ |
| Energy range | 444.034–582.389 mJ | 528.532–546.401 mJ |

There is **no demonstrated speed gain**: the median increased by 0.602 ms
(0.060%). Median measured energy decreased by 13.014 mJ (2.367%). The card was
erased between groups, and scan positions and internal card state differed;
three samples do not isolate the firmware change or establish a statistical
advantage. These are board-branch measurements, not production battery energy.
The earlier v16 result below is a separate historical baseline.

All six comparison cycles passed warm recovery, independent SBF checks and
complete saved-image readback. Their PNG samples match the retrieved RAW bytes;
the original camera RAM was lost in Standby, so this is not an original-frame
comparison. Separate awake captures above provide that comparison. All three
candidate scenes were also visually inspected and showed the discernible LED
panel and bench. The strict decoder identifies events 1–9; the final pre-WFI
pulse remains unidentified, with Standby established independently. Slot 0 was
reread after the later saves and still matched its original deterministic image.

The final extra normal cold boot returned to the low-current plateau at
**4.892311 V / 8.075647 mA** at 17:56:22.939300 UTC. Its expected slot 6 and SBF
were not reread, so it is not another qualified comparison sample. JS110 stopped
cleanly and restored range 128, leaving target power on; COM8 was closed and
BREAK released. The v17d image remained installed at that checkpoint. The tables
below retain the earlier firmware measurements as historical evidence.

The two magic words are completion markers, **not a payload checksum or a
power-loss guarantee**. Logical erase and ACMD23 do not expose or reserve
physical NAND. The object stores no exposure, timestamp or orientation metadata;
exposure telemetry is currently retained only in RAM/evidence. Automatic
reclamation, deletion, allocation hints and on-camera PNG/PTP export remain
deferred. Host extraction reconstructs RAW or PNG16 with `sample << 6`.

## Historical measurements: v12–v16

The preceding prototype was **RAW v16, polling IDMA with whole-image ACMD23
preannouncement and asynchronous sensor STOP, followed by Standby**. Its
programmed 64 KiB sector is
`285fba4951f88deb12033e7b3c2948c802371862982da5a8e304c6cae35fb58f`.
The earlier chunked LINE path remains selectable. The new option waits for
validated FRAME before writing; on this card, cold SD initialization already
finishes after FRAME, so this adds no observed wait. Early receiver load remains
15,804 bytes and the recovery instructions are unchanged.

Three fresh cold runs per build gave the following medians, measured from
current onset to stable Standby plateau on the JS-fed Nucleo branch:

| Metric | Chunked v15 | ACMD23 + one CMD25, v16 |
| --- | ---: | ---: |
| Total cycle | 796.377 ms | 780.385 ms |
| Energy | 435.297 mJ | 426.796 mJ |
| Payload submission through final card readiness | 633.320 ms | 626.438 ms |

The observed total reductions are 2.01% in time and 1.95% in energy. The payload
improvement is 6.882 ms (1.09%). SD initialization also varied by about 9.6 ms
between group medians; scan positions and card internal state differed. Do not
attribute the entire cycle difference to preannouncement, or separate the hint's
effect from the single-transaction effect. See the
[preerase experiment](evidence/2026-10-24-preerase/README.md) for every run,
readback qualification and exact final bench state.

The following measurements describe the earlier RAW qualification.
The preceding v12 three-run baseline reached hardware-confirmed Standby and passed first-attempt
warm PE6 UART recovery. Separate deterministic and cold scene captures passed
complete SD-to-RAM byte comparisons. The forced-overlap LINE test also checked
each immediately published tail before SD could conceal premature publication.
See the [durable evidence](evidence/2026-10-24-raw-slots/README.md) for exact
builds, positive and failed experiments, and readback limits.

Final review found that fixed SRAM could retain the late-loader success marker
across a warm reset. V15 clears that marker before camera initialization; only
the current boot's verified loader can authorize late-code failure cleanup.
Its early load stays 15,804 bytes and its recovery instructions are unchanged.
A separate v15 cold smoke run passed Standby/SBF, first-attempt UART recovery,
and complete slot-8 readback with independent PNG decoding. It measured
0.778143 s / 0.424945 J using the same criteria. This single run is not a new
three-run baseline; its original sensor RAM was lost on entering Standby.

| Same measured boundary: current onset → stable Standby plateau | Previous PNG v66c | RAW v12 |
| --- | ---: | ---: |
| Median of three cold runs | 2.057802 s | 0.793888 s |
| Measured JS branch energy | 1.061503 J | 0.441400 J |

The observed reductions are 61.4% in duration and 58.4% in measured energy.
These are Nucleo branch measurements, with the existing USB/debug bypass and
instrument-calibration limitations. Scene, format and card-state differences
prevent attributing the whole improvement to one change. RAW cycle duration
ranged 0.789634–0.807867 s and energy 0.431091–0.441541 J. The card and board
remain physically supplied; Standby plateau current was 8.08–8.19 mA.

The strict timing decoder directly identifies events 1–9 in these runs. Its
last pulse fails the pre-WFI width tolerance and remains unidentified; Standby
is established independently by the warm-recovery SBF checks. Payload transfer
through final padded-sector readiness took 632.2–634.2 ms. Reset release to the
first observed exposure strobe took 22.60–22.82 ms.

An early IDMA trial reported SD protocol success but saved zero payload bytes.
Full readback caught the failure. STM32N6's SDMMC2 configuration-port security
attribute overrides the DMA master's security setting: the port and master must
both be secure before reading the secure camera SRAM. The runtime now verifies
both attributes, without weakening SRAM protection. A successful controller
status is therefore insufficient evidence of a correct image.

## Build and ownership

`build.py` is an offline builder. It verifies the frozen v66c receiver and prefix
sources before applying explicit transformations, then writes all transformed
sources, binaries, listings and hashes into a new output directory. Vendor
sources and the installed STM32 GNU toolchain remain the same pinned dependencies
used by `capture-sd` and `capture-packed`.

```powershell
python firmware/capture-raw/build.py --out tmp/bringup/raw-example `
  --magic-format --line-stream --async-stop --pattern diagonal
```

The default output is a RAM test image. It must be entered through a verified
early recovery and SRAM bridge; the build command never connects to hardware.
Only the bench owner operates instruments. The existing one-bit 3.3 V wiring
is retained, and the driver never negotiates four-bit or 1.8 V operation.

The image's privileged top-level entry owns its CPU/FPU context and never returns
to a C caller. Its completion branch records and clears only its inactive owned
FP context after all work has finished. This is not a reusable context cleanup
routine for a returning function. Success requires a fresh terminal proof,
idle/deinitialized card, disabled caches, exact immutable code and the expected
park address. A failure report alone does not authorize a power cycle.

## Historical v12–v16 capture and storage paths

This section preserves the earlier header-based implementation and experiments.
The magic-slot sequence above supersedes its addresses, header writes and
publication rules for the selected prototype.

The camera retains the previously qualified ForceRx/lane sequencing and the
idle-checked receiver-data disable before sensor STOP. Sensor output datatype
is `0x30`, while its sample depth remains ten bits; CSI treats it as opaque
eight-bit transport data. The frame is 1,909,600 bytes at `0x34000000` with an
independent 32-byte guard immediately after the true image boundary. V16 also
allocates a separate guard after the padded 1,909,760-byte sector extent.

After arming capture, the remaining storage code loads from NOR and SD
initialization runs while camera DMA and its interrupts continue. The selected
LINE producer publishes conservative completed prefixes; the complete-frame
producer remains available as a fallback. The current card finishes acquisition
before cold SD initialization completes, so the overlap improves readiness but
cannot make this card accept the first sector during that cold frame.

The slot layer scans valid headers for the first FREE slot. With
`--whole-image-preerase`, it waits for validated FRAME before writing PARTIAL,
then checks the original guard and replaces that boundary area with exactly
160 zero padding bytes.
The separate post-padding guard remains live. This avoids copying the full frame
or placing the final sector in a separate transaction. The driver sends
`CMD55(RCA) → ACMD23(3730) → CMD25(payload LBA)`, transferring all 3730 sectors
in one IDMA request. CMD12 and fresh card-ready checks still terminate the write;
ACMD23 is a preparation hint, not automatic transfer termination.

FULL is a separate header write after payload completion, sensor STOP and the
post-padding guard check. The driver then deinitializes before Standby. Without
the option, the original published-prefix chunks and separate padded final
sector remain unchanged. That path preserves before-FRAME streaming for future
cards which finish initialization sooner.

The available `--line-stream` producer can publish conservative prefixes before
FRAME; the whole-image option waits for FRAME even when this producer is enabled.
Its separate [LINE qualification procedure](LINE.md) explains the
64-line holdback, immediate ISR snapshots and forced-overlap diagnostic. The
linear frame buffer is retained in full; transmitted memory is never overwritten
or recycled while camera capture is active.

The optional `--async-stop` experiment starts the same STOP command after the
qualified data-disable sequence, but polls its acknowledgement and standby state
once per nominal millisecond while IDMA writes run. It does not change the sensor
command order. A failed or timed-out poll is deferred until the active SD call
returns; it never parks the CPU in the middle of a healthy IDMA transaction.
The slot is not marked FULL until sensor STOP completes. This option requires
IDMA because CPU-serviced FIFO transfers cannot tolerate an I2C polling delay.

The separate `--dma-sleep` experiment permits shallow WFI inside the IDMA data
wait only for transfers begun after full camera validation and sensor STOP.
Earlier transfers retain polling. The driver requires an active 1 ms SysTick,
enabled interrupts, shallow sleep and retained SRAM/SD/security clocks; it
changes none of those conditions. The owner explicitly enables the required
AXISRAM1–6, ACLK/ACLKNC, RIFSC/RISAF and SDMMC2 sleep clocks using set aliases
that preserve unrelated bits. It clears only the debugger's `DBG_SLEEP`
emulation bit after checking debug-register clock/reset access. Before/after
values are exposed through the manifest's `dma_sleep_clocks` record. The driver
independently checks the result before launch and before sleeping.

The first sleep diagnostic failed closed before its second payload transfer:
the measured SRAM, RIF and SD sleep-clock enables were absent, and no WFI had
occurred. Its PARTIAL slot and original failure evidence remain unchanged.
Enabling those clocks is an explicit owner setup step; relaxing the guard would
have hidden the missing bus/memory retention configuration.

The follow-up RAM v14b enabled those clocks, the NoC sleep clocks, and cleared
debug sleep emulation. It then failed to reach its terminal proof, with high
SRAM inaccessible during the recorded observation. Its actual sleep/wake state
and cause remain under investigation; do not promote this experiment to an
autonomous flash build or treat its current plateau as successful completion.
The polling IDMA path remains the fallback. All original failure evidence is
preserved in the linked durable evidence archive, with large raw waveforms and
private scene pixels kept only under `tmp/bringup/raw-slots-20261024/bench/`.

Cumulative wait statistics are exposed through
the manifest's `dma_wait` address, with the exact HAL tick callback identity.
The option is off by default. When enabled, DWT durations that span WFI measure
active cycles, not elapsed wall time; use the independent millisecond counter
and external instruments for elapsed-time comparisons.

SD protocol READY, DAT0 high and an idle host controller establish completion
under the present powered conditions. Sudden-power-loss protection in the card's
internal translation layer remains unqualified. An unknown card is never
automatically formatted.

## RAM requests and results

Each request is sixteen little-endian 32-bit words at `0x343FD000`. Words 0–2
are magic `0x52535131`, a nonzero request nonce and operation:

| Operation | Number | Arguments in words 3 onward |
| --- | ---: | --- |
| Capture and save | 1 | None |
| Explicit destructive format | 2 | Magic format: words 3 onward must be zero; erase the entire card |
| Read sectors only | 3 | First LBA, count from 1 to 512 |

The older header format instead requires generation low/high and an optional
slot limit for FORMAT. Its request rules remain separate; a zero-generation
request is accepted only for an explicitly identified magic-format build.

READ writes only the dedicated RAM buffer at `0x34200000`, at most 256 KiB,
and issues no card writes. It can retrieve a retained image in chunks without
changing its packed frame in SRAM. A fresh request must still be bound to the
exact terminal state before restarting the entry point.

The 96-word proof at `0x343FD100` is defined by `runtime.h`. It records operation,
nonce, geometry, camera state, slot allocation, SD ownership, counts, timing,
final CPU context and terminal word. The build manifest identifies all code,
frame, proof and structured-card addresses. Per-chunk rows at `0x343FE000`
record call start/end, payload-sector offset, count, published producer bytes,
last READY response, return result and driver transfer cycles. Only the published
row count is current; unused rows deliberately retain prior contents.

Exposure telemetry uses the read-back coarse exposure and line length with the
fixed sensor's nominal 160.8 MHz pixel clock, rounded only after multiplication.
This avoids the shipped driver's integer-microsecond line-time truncation.
Magic slots do not store this telemetry or other image metadata. The legacy
header format retains its metadata validity flags; timestamp and orientation
remain explicitly unavailable.

## Cold-start constraint

The camera receiver must be ready within the existing 4.5 ms START-to-receiver
budget. Loading an entire combined receiver/storage binary before arming capture
can exceed that deadline on the one-bit boot NOR interface. A `--flash` build
therefore places storage code in a separate contiguous load range after the
early receiver. The prefix loads and checks only the early range. After capture
is armed, a bounded NOR reader loads and checks the late range while camera
interrupts remain enabled. The manifest identifies both immutable ranges and
the `RLD1` loader proof at `0x343F9E00`; `RLOK` is published only after the CRC
and transfer-idle checks pass.

The current source also clears `RLD1`'s `RLOK` word at receiver dispatch,
before any camera preparation or arm failure can consult it. This fixed-address
diagnostic area lies outside `.bss` and can retain a previous boot's success
marker across reset. Clearing it prevents early failure cleanup from trusting
late code that the current boot has not yet loaded and verified. This review
fix is **not present in the frozen, measured v12 image**. V15 and later builds,
including selected v17d, contain it. The separate v15 cold
save/Standby/recovery/readback smoke test is described above; the early-failure
case itself is covered offline.

The linker audit requires the vectors and camera interrupt handlers to remain
in the early range, checks direct crossings into late code, and caps early
loading at the qualified v66c receiver's 15,804 bytes. These are offline layout
checks, not a new measured timing guarantee. A failed late load may leave
capture or a NOR read active; its failure park is not a maintenance permission.

The early load is padded to exactly 15,804 bytes. GCC otherwise changes prefix
register allocation and literal-pool placement for some receiver lengths or CRC
values, causing the conservative byte-identity guard to fail. To keep this
deterministic, the prefix compiles with v66c's original CRC constant, then the
builder relocates only the two reviewed CRC data words at offsets `0xC9C` and
`0x1354`. It verifies their exact original bytes, disassembled data-literal form,
and unique ELF mapping. The ELF, raw binary and listing are updated together;
all instructions stay unchanged. The manifest records both CRCs, exact offsets
and hashes, and preserves the unrelocated artifacts. The unchanged recovery
identity checks run again after relocation. This is not permission to patch
arbitrary code or admit a changed recovery branch.

Flash builds support the scene configuration only. The diagonal-pattern prefix
changes literal addresses before the existing conservative recovery boundary,
so it is rejected rather than weakening that check. Deterministic pixel tests
use the RAM build. Both flash completion variants retain the exact PE1/PE6 early
recovery guard; adding their reviewed prefix and sector identities to the
maintenance allowlist is a separate explicit bench preparation step.

```powershell
python firmware/capture-raw/build.py --out tmp/bringup/raw-flash-awake `
  --flash --magic-format --async-stop --line-stream
```

Only after awake hardware qualification should `--standby` be added. It retains
the previously qualified peripheral teardown and accepts it only after complete
camera validation, sensor STOP, full slot commit, and idle/deinitialized SD.

## Cold-cycle measurements

`cold_cycle.py` records one root-owned cold cycle through JS110 and the existing
Saleae API. It is dry-run by default and never sends debugger/UART commands,
changes firmware, or retries a cycle. Execution requires a fresh root-authored
safe-start record that binds the exact flash sector and hashed evidence of idle
NOR/storage ownership. A current plateau by itself never grants permission to
remove power.

The helper retains the earlier qualified owner and power state machine. Its
byte-identical owner source is pinned under `support/single_cycle.py`; only the
`Owner` and fresh-statistics functions are imported. The copied owner's old v59
standalone entry point is not used for RAW measurements.

```powershell
python firmware/capture-raw/cold_cycle.py --out tmp/bringup/raw-cold-01 `
  --build tmp/bringup/raw-flash-standby --safe-start-proof tmp/safe-start.json
```

Future RAW builds use phase protocol v2: each event adds 800 nominal CPU cycles
(2 microseconds), with a 0.4 microsecond decoding tolerance. The first awake
cold run showed about 0.24 microseconds of GPIO/call overhead; that exceeded the
legacy protocol's 0.15 microsecond tolerance. Wider spacing separates the IDs
without changing the old recording's result. The legacy 0.5 microsecond protocol
and its original strict tolerance remain selectable only through its exact
bound build manifest. The shared PNG phase implementation is unchanged.

Camera and SD phases may overlap, so the decoder checks their required
precedence rather than numeric event order. Failed widths remain failed; it
does not assign labels from the expected source sequence. Recordings still need independent image integrity,
actual Standby/SBF and UART recovery qualification. Energy belongs to the
measured JS-fed board branch, not an isolated MCU or production battery path.

For the initial awake flash qualification, add `--expected-end awake`. This
requires a matching awake build and records ten powered seconds after startup.
It makes no terminal-state claim and cannot authorize a follow-up cycle: inspect
the exact RAW terminal/idle proof first. Awake captures have nine markers; only
Standby builds emit marker ten before WFI.

`summarize_cycles.py` is an offline report generator. It replays the exact frozen
v66c native-sample energy analyzer and threshold criteria, so the primary
current-onset → stable-plateau boundary is comparable. The extra one second used
to confirm the plateau is reported separately. Run it after recorders stop:

```powershell
python firmware/capture-raw/summarize_cycles.py --spec tmp/raw-summary-spec.json `
  --out tmp/raw-summary --recorders-stopped
```

The specification has `schema: 1`, a `build` directory, and a `cycles` array.
Each cycle contains `name`, `recording`, and an optional `qualification` JSON
path. Paths are relative to the specification. Without qualification the tool
explicitly reports a current signature, not a completed capture/save cycle.
A qualification binds the cycle name, exact sector, recording-result hash and
hashed SBF reader result. It requires root attestations that SBF was cleared
before this trial and no power-off intervened between the cycle and its warm
recovery/SBF read. The fresh exact-prefix park and unchanged CPUCR/reset state
are checked from that evidence. A separately hashed image report and explicit
full-slot readback attestation can qualify image integrity; SBF alone cannot.

The report emits directly width-decoded phase intervals even when another pulse
fails, but never fills a missing endpoint. In v12's first Standby trial, events
1–9 passed; the last pulse measured 20.49 microseconds and failed the original
20 ±0.4 microsecond rule. Its pre-WFI time remains unidentified. Native JS
energy can still be qualified by independent SBF evidence. Saleae and JS clocks
are independent, so this tool does not assign energy to individual phases.

`energy_compacts.py export` packages small native-sample energy artifacts with
the unchanged v66c exporter. Its sums include every sample and split bins at
the exact integration boundaries; partial boundary bins are never approximated.
The resulting folder retains compressed sums/extrema, raw manifests and chunk
identities, without copying the multi-gigabyte sample arrays. Run
`energy_compacts.py replay --folder PATH` to reproduce all four selected energy
intervals and the primary time/energy medians from that folder alone. This
replays numerical integration, not raw onset/plateau classification or analog
calibration. The existing 9.5 A validity criterion is unchanged.
