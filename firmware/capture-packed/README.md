# Packed RAW10 capture

On October 24, 2026 the CAM-6G3-073CLR and STM32N657 successfully captured
**1120 x 1364 samples as 1,909,600 packed bytes**, without CPU pixel conversion.
Two independent host decoders matched all 1,527,680 samples against an ordinary
RAW10-to-padded16 capture of the same deterministic sensor pattern. A real-scene
packed capture also completed with zero recorded camera errors, intact guards,
stable repeated RAM reads and a recognizable image.

This qualifies the packed capture configuration on this bench. It does not yet
qualify RAW writes to SD, capture/write overlap, DMA contention, cold-start
timing, or energy. The experiment runs from RAM; the installed v66c PNG/FAT32
capture firmware is unchanged. See the [frozen evidence](evidence/2026-10-24-packed-raw10/).

## Configuration that preserves the packed bytes

The sensor already sends packed RAW10 over MIPI. The usual receiver configuration
unpacks it: CSI processes the ten-bit samples and DCMIPP Pipe0 pads each to a
16-bit word. `P0PPCR.PAD` chooses alignment, not packed output.

The tested alternative gives the unchanged RAW10 payload a user-defined packet
type, then treats it as a byte stream through the receiver:

| Setting | Ordinary capture | Packed capture |
| --- | --- | --- |
| Sensor `FORMAT_CTRL`, register `0x030A` | 10 | **10** |
| Sensor `OIF_IMG_CTRL`, register `0x030F` | RAW10 type `0x2B` | **User-defined type `0x30`** |
| `HAL_DCMIPP_CSI_SetVCConfig`, VC0 | `DCMIPP_CSI_DT_BPP10` | **`DCMIPP_CSI_DT_BPP8`** |
| DCMIPP Pipe0 data-type filter | `0x2B` | **`0x30`** |
| Captured bytes per row | 2240 | **1400** |
| Captured bytes per frame | 3,055,360 | **1,909,600** |

The eight-bit receiver setting describes opaque transport bytes; the sensor
still produces ten-bit samples. Readbacks and the exact pixel comparison verify
that the low two bits survive. No ISP, RAW-to-RAW packing loop or PNG encoder is
used on the target. Each four-pixel group occupies five bytes: four upper-eight-
bit values followed by one byte containing the four low-two-bit pairs, first
pixel in bits 1:0. There are no per-row headers or padding in the captured payload.

The configuration saves **1,145,760 bytes (37.5%)** of required frame storage.
For this experiment both variants deliberately reserved the original larger
buffer, with guards at the expected packed end and at the allocation end. The
DMA limit remained at the larger boundary, so the packed size was measured
rather than forced by truncation. Reducing the actual allocation is a subsequent
integration change.

The sensor manual describes separate output-depth and packet-data-type controls;
the MCU manual describes generic byte-stream dumping and padded RAW output.
Their combination is supported here by hardware evidence, not inferred solely
from register names. Reference details and the test-pattern documentation
discrepancy are retained in the evidence's research notes.

## What this permits for SD storage

The packed memory can be the source of an SDMMC IDMA transfer. CPU work can then
be limited to card/filesystem setup, buffer ownership, metadata and completion
handling. The final 352 payload bytes need one 512-byte sector; the remaining
160 bytes are padding, with the true image length recorded in the file/header.
A durable RAW container and metadata layout have not been selected.

There are two different overlaps to consider:

1. Camera DMA writes the next part of a linear frame while SDMMC DMA reads an
   earlier completed part. This requires a proven completion boundary and cache
   ownership rules, but no pixel copy.
2. The host prepares another SD buffer while the card programs earlier data.
   It can queue work, but it must still wait when the card asserts DAT0 busy.
   Double buffering does not make an SD card accept data during a busy interval.

At the previously measured one-bit SD throughput of 2,649,960 bytes/s, the packed
payload alone would take **720.6 ms**. The existing capture envelope is about
**21.9 ms**. Even an ideally ready card could drain only about 58 kB during that
interval, leaving approximately **1.85 MB** buffered. These are calculations
from prior measurements, not new RAW-write timings. The card's cold initialization
currently takes roughly 98-110 ms, so capture can finish before it becomes ready.

DCMIPP Pipe0's double buffering switches whole frames. Its documented controls
do not provide the pixel pipes' line-wrapping ping-pong mode. Start with one
contiguous packed frame and larger multiblock writes, such as 32 KiB, rather than
a separate command for each 512-byte sector. Line events could publish completed
prefixes for overlap, but their RAM-write completion semantics must be measured
before a second DMA engine consumes those regions. `P0DCCNTR` is an end-of-frame
shadow, not an assumed live producer pointer.

Packed RAW eliminates encoding work, while transferring more bytes than the
optimized PNG from the earlier test image. The latter's approximately 449 ms
overlap estimate remains a model; neither pipeline has been measured end to end.
No energy winner is established by these byte counts alone.

Recommended implementation sequence: retained packed RAW save and full readback;
then SDMMC IDMA; then capture-prefix overlap with overrun, busy-delay and boundary
tests. Keep the existing first-exposure timing and sensor/receiver sequencing
until a separately measured change justifies altering them.

## Experiment and recovery

The RAM experiment starts only after exact v66c UART recovery and the qualified
expanded-SRAM bridge. It resets the sensor explicitly and preserves the existing
first-frame PHY sequence. It records the requested nonce, actual byte count,
sensor/receiver settings, camera errors, guard state and completed-stop state.
Host reads retrieve the entire frame twice and compare both copies.

The first native control captured correctly but refused final completion because
the HAL clock calculation had set floating-point context flags. V4 records and
clears only that experiment's inactive owned FP state before publishing its final
park. It never returns to a C caller; this cleanup must not be copied into a
normal returning SAVE function. The original refusal is retained in the evidence.

The generated pattern uses the shipped ST driver's `PATGEN_CTRL=0x0121`, Duster
disabled, and DarkCal mode 2. Both host decoders and all four low-bit values were
exercised; the native control contains 960 distinct sample values. Real-scene
pixels and previews remain local, while deterministic test-pattern fixtures can
be replayed from the evidence archive.

At the final checkpoint, **04:46:36 UTC on October 24**, one measured 15-second
off interval followed by normal flash boot returned the board to **8.177 mA at
4.893 V**. JS110 closed cleanly with range 128 restored and target power left on.
COM8 is closed, BREAK released, Logic 2 remains running, and the boot jumpers and
wiring are unchanged. There is no active bench helper. This is a current signature;
the final photo and Standby flag were not read back. No NOR command was issued
during the work, so v66c remains installed by unchanged-operation provenance.

Replay the compact archive with `python evidence/2026-10-24-packed-raw10/replay.py`
from this folder. Its `materialize.py` reconstructs readable build, record or
support-tool files from the exact deduplicated bytes. The archive deliberately
retains the failed v3 control alongside successful v4 runs.
